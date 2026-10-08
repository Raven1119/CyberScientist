"""Immediate bounded format repair on the same native session."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
import jsonschema
from . import curation, decision, role_tasks
from .decision_extraction import _extract_json, extract_question_answer
from .observation import strip_secrets
from .brains.base import BrainEvent

MAX_REWRITES = 2
_COLLAB = json.loads((Path(__file__).resolve().parents[2] / 'contracts/collaboration.schema.json').read_text())


def parse(text: str, packet: dict) -> BrainEvent:
    protocol = packet.get('protocol')
    value = role_tasks.extract(text) or _extract_json(text)
    if protocol == 'role_task':
        schema, kind, key = packet['output_contract'], 'task_result', 'result'
    elif protocol == 'experience_curation':
        schema, kind, key = curation.schema(), 'curation_result', 'result'
    elif protocol == 'review_result':
        schema = {'$ref': '#/$defs/ReviewResult', '$defs': _COLLAB['$defs']}
        kind, key = 'review_result', 'result'
    elif protocol == 'executor_question':
        # Historical choice answers retain the existing compatibility route.
        answer = extract_question_answer(text)
        if answer is not None and value and 'message_type' not in value and 'answers' in value:
            return BrainEvent('question_answer', answer)
        schema = {'$ref': '#/$defs/ResearchAnswer', '$defs': _COLLAB['$defs']}
        kind, key = 'question_answer', None
    else:
        if value is not None: value.setdefault('run_id', packet.get('run_id', ''))
        schema, kind, key = decision.load_schema(), 'decision', 'decision'
    if value is None:
        errors = ['(root): 最终输出必须是符合契约的 JSON 对象']
    else:
        validator = jsonschema.validators.validator_for(schema)(schema)
        errors = [f"{'.'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
                  for e in validator.iter_errors(value)]
    if errors:
        return BrainEvent('error', {'code': 'FORMAT_INVALID',
            'message': strip_secrets('; '.join(errors[:8]))[:2400]})
    return BrainEvent(kind, {key: value} if key else value)


def feedback_prompt(prompt: str, packet: dict) -> str:
    feedback = packet.get('_format_feedback')
    if not feedback: return prompt
    if feedback.startswith('trace_delivery:') and isinstance(packet.get('_read_missing_chunks'), list):
        return (prompt + '\n后端未核验完整轨迹。本次只补读指定的只读分块，已验证分块不用重复；'
            '禁止科学计算、联网、修改和提交。全部补读后在本会话重新输出完整JSON。\n' + feedback)
    return prompt + '\n上次结构化输出未执行。仅修正以下字段格式，在本会话重写完整 JSON；不要重复工具或受控动作。\n' + feedback


def set_budget(runtime, run_id: str, kind: str):
    runtime.format_rewrite_budget = (run_id, kind)


def claim_rewrite(runtime):
    from . import config, db, maintenance, power, run_limits, run_clock
    if power.shutdown_requested(): raise ValueError('安全关机不发起格式重写')
    if getattr(runtime, 'allow_format_rewrites', True) is False:
        raise ValueError('本次仅授权一次原生调用；格式重写需另行授权')
    context = getattr(runtime, 'format_rewrite_budget', None)
    if context is None: return None  # Standalone callers own their bounded authorization.
    rid, kind = context
    if kind == 'post_review_version':
        with db.transaction() as conn:
            grant = conn.execute('SELECT * FROM run_post_review_versions WHERE id=?', (rid,)).fetchone()
            run = conn.execute('SELECT phase FROM runs WHERE id=?', (grant['run_id'],)).fetchone() if grant else None
            if not grant or not grant['allow_model_calls'] or grant['status'] != 'running' or not run or run['phase'] not in maintenance.TERMINAL:
                raise ValueError('当前复盘格式纠正未获授权')
            if grant['calls_used'] >= grant['native_call_limit']:
                raise ValueError('本次复盘格式纠正额度已用尽')
            conn.execute('UPDATE run_post_review_versions SET calls_used=calls_used+1,updated_at=? WHERE id=?', (db.utcnow(), rid))
            db.append_event_tx(conn, grant['run_id'], 'brain', 'post_review.format_rewrite_reserved',
                {'review_id': rid, 'calls_used': grant['calls_used'] + 1, 'native_call_limit': grant['native_call_limit']})
        return None
    operation = 'format-rewrite-' + uuid.uuid4().hex
    if kind in ('maintenance', 'post_review_legacy'):
        auth = db.query_one('SELECT a.allow_model_calls FROM authorizations a JOIN runs r ON r.authorization_id=a.id AND a.run_id=r.id WHERE r.id=?', (rid,))
        if not auth or not auth['allow_model_calls']: raise ValueError('原维护模型授权不可用')
        maintenance.claim_call(rid, operation, 'format_rewrite', terminal_only=kind == 'post_review_legacy')
        return operation
    with db.transaction() as conn:
        run = conn.execute('SELECT * FROM runs WHERE id=?', (rid,)).fetchone()
        auth = conn.execute('SELECT * FROM authorizations WHERE id=? AND run_id=?', (run['authorization_id'], rid)).fetchone()
        if not auth or not auth['allow_model_calls'] or run['phase'] not in ('created', 'running'):
            raise ValueError('当前状态未授权新的格式重写')
        if (auth['max_run_minutes'] or auth['unlimited_resources']) and run_clock.remaining(run, auth) <= 0:
            raise ValueError('原Run时间授权已用尽')
        snapshot = json.loads(run['config_snapshot'])
        settings = snapshot['settings']
        settings['run_defaults'] = config.load_settings()['run_defaults']
        if kind == 'shadow':
            row = conn.execute('SELECT reviews_used FROM supervision WHERE run_id=?', (rid,)).fetchone()
            if not row: raise ValueError('原静默审阅预算不存在')
            limit = snapshot.get('shadow', {}).get('max_reviews', config.DEFAULT_SETTINGS['shadow']['max_reviews'])
            if not run_limits.unlimited(rid, conn=conn) and row['reviews_used'] >= limit:
                raise ValueError('原静默审阅额度已用尽')
            conn.execute('UPDATE supervision SET reviews_used=reviews_used+1 WHERE run_id=?', (rid,))
        elif kind == 'brain':
            if not run_limits.unlimited(rid, conn=conn) and run['brain_reviews_used'] >= settings['run_defaults']['max_brain_reviews']:
                raise ValueError('原PI调用额度已用尽')
            conn.execute('UPDATE runs SET brain_reviews_used=brain_reviews_used+1 WHERE id=?', (rid,))
        db.append_event_tx(conn, rid, 'brain', 'brain.format_rewrite_reserved', {'operation_id': operation, 'kind': kind})
    return None


async def review(runtime, session, packet):
    current = packet
    reservation = None
    for attempt in range(MAX_REWRITES + 1):
        invalid = None
        status = 'unknown'
        try:
            async for event in runtime._review_once(session, current):
                if event.type == 'error' and event.payload.get('code') == 'FORMAT_INVALID':
                    invalid = event
                else:
                    if event.type == 'error':
                        status = 'unknown' if event.payload.get('code') == 'NATIVE_TURN_UNKNOWN' else 'failed'
                        # Persist before exposing the error: consumers may stop
                        # iteration immediately, without resuming this generator.
                        if reservation:
                            from .maintenance import complete_call
                            complete_call(reservation, status)
                            reservation = None
                    yield event
                    if event.type == 'error':
                        return  # Native failures are not format retries.
            status = 'failed' if invalid else 'done'
        finally:
            if reservation:
                from .maintenance import complete_call
                complete_call(reservation, status)
                reservation = None
        if invalid is None: return
        if attempt == MAX_REWRITES:
            yield invalid
            return
        try: reservation = claim_rewrite(runtime)
        except ValueError as exc:
            yield BrainEvent('error', {'code': 'FORMAT_REWRITE_BLOCKED', 'message': strip_secrets(str(exc)) + '; ' + invalid.payload['message']})
            return
        yield BrainEvent('progress', {'status': 'format_rewrite', 'attempt': attempt + 1,
            'detail': invalid.payload['message'], 'session_id': session.session_id})
        current = {**packet, '_format_feedback': invalid.payload['message']}
