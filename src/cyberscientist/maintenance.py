"""Two independent, durable end-of-Run model calls: curation and fresh post-review."""
from __future__ import annotations
import asyncio
import hashlib
import json

import jsonschema

from . import config, curation, db, resource_coordinator, trial_notes
from .observation import strip_secrets

CALL_LIMIT = 2
ACTIVE_TASKS: set[asyncio.Task] = set()


def schedule(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    ACTIVE_TASKS.add(task)
    task.add_done_callback(ACTIVE_TASKS.discard)
    return task


def claim_call(run_id: str, operation_id: str, kind: str) -> None:
    """Persist immediately before a native turn; even interrupted calls count."""
    with db.transaction() as conn:
        old = conn.execute('SELECT 1 FROM maintenance_calls WHERE operation_id=?', (operation_id,)).fetchone()
        used = conn.execute('SELECT COUNT(*) FROM maintenance_calls WHERE run_id=?', (run_id,)).fetchone()[0]
        if old:
            raise ValueError('维护调用已开始过；不自动重复未知模型调用')
        if used >= CALL_LIMIT:
            raise ValueError('每个 Run 的整理／复盘独立两次调用额度已用尽')
        conn.execute('INSERT INTO maintenance_calls VALUES(?,?,?,?,?,?)',
                     (operation_id, run_id, kind, 'running', db.utcnow(), db.utcnow()))
        db.append_event_tx(conn, run_id, 'controller', 'maintenance.call_started', {
            'operation_id': operation_id, 'kind': kind, 'used': used + 1, 'limit': CALL_LIMIT})


def complete_call(operation_id: str, status: str) -> None:
    db.execute('UPDATE maintenance_calls SET status=?,updated_at=? WHERE operation_id=?',
               (status, db.utcnow(), operation_id))


def queue_end(controller, run_id: str, reason: str) -> None:
    trial_notes.record_closed(run_id)
    now = db.utcnow()
    db.execute("INSERT OR IGNORE INTO run_post_reviews(run_id,status,reason,created_at,updated_at)"
               " VALUES(?,'pending',?,?,?)", (run_id, reason, now, now))
    try:
        asyncio.get_running_loop()
        schedule(advance(controller, run_id))
    except RuntimeError:
        pass  # The persistent pending row is resumed by the next backend pass.


def persist_end_tx(conn, run_id: str, reason: str) -> None:
    now = db.utcnow()
    conn.execute("INSERT OR IGNORE INTO run_post_reviews(run_id,status,reason,created_at,updated_at)"
                 " VALUES(?,'pending',?,?,?)", (run_id, reason, now, now))


def output_contract() -> dict:
    return {'type': 'object', 'additionalProperties': False,
            'required': ['system_defects_md', 'strategy_lessons', 'environment_notes_md'],
            'properties': {'system_defects_md': {'type': 'string'},
                           'strategy_lessons': curation.schema()['properties']['experience_proposals'],
                           'environment_notes_md': {'type': 'string'}}}


def snapshot(controller, run_id: str) -> dict:
    from . import observation
    through = db.query_one('SELECT COALESCE(MAX(seq),0) FROM events WHERE run_id=?', (run_id,))[0]
    # Complete persisted public events, without per-event clipping. Private
    # scratchpads, raw tokens and reasoning streams do not enter this file.
    steps = []
    private = {'private_note_md', 'note_excerpt', 'research_note_md', 'raw_reasoning', 'raw_token'}
    def public(value):
        if isinstance(value, dict):
            return {k: public(v) for k, v in value.items() if k not in private}
        if isinstance(value, list):
            return [public(v) for v in value]
        return value
    for row in observation.events_through(run_id, 1, through):
        if row['type'] in ('brain.token', 'brain.raw_output', 'brain.private_note', 'prime.reasoning.raw') or row['type'].startswith('brain.private'):
            continue
        steps.append(public(row))
    root = config.WORKSPACE_DIR / 'reviews'
    root.mkdir(parents=True, exist_ok=True)
    trace = root / (run_id + '-public-trace.jsonl')
    raw = strip_secrets(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in steps))
    trace.write_text(raw, encoding='utf-8')
    evidence = curation.run_evidence(run_id)
    full_refs = [f"event:{run_id}:{row['seq']}" for row in steps]
    full_refs += ['checkpoint:' + row['id'] for row in db.query('SELECT id FROM checkpoints WHERE run_id=?', (run_id,))]
    full_refs += ['local_score:' + row['id'] for row in db.query('SELECT id FROM local_scores WHERE run_id=?', (run_id,))]
    environment = [dict(row) for row in db.query("SELECT seq,type,payload FROM events WHERE run_id=? AND source='controller'"
        " AND type IN ('environment.smoke_observed','environment.save_observed','image_facts.observed','sandbox.environment_observed')",
        (run_id,))]
    return {'protocol': 'role_task', 'task': 'run_post_review', 'run_id': run_id,
            'challenge': controller._challenge_for_run(controller._require_run(run_id)),
            'public_trace': {'path': str(trace), 'sha256': hashlib.sha256(raw.encode()).hexdigest(),
                             'through_seq': through, 'steps': len(steps), 'truncated': False},
            'run_evidence': evidence, 'environment_receipts': environment,
            'full_evidence_refs': full_refs,
            'instruction': '在全新上下文中通读完整公开轨迹文件；可分块读取，不只依赖摘要。'
                '先写可照做的步骤、不要做的事和关键数值；不确定性一两句话说明，并引用真实证据。'
                '系统缺陷写给开发者，策略教训写经验候选；环境文字是建议，只有真实回执代码可生效为环境事实。',
            'output_contract': output_contract()}


def write_report(run_id: str, packet: dict | None, result: dict | None, error: str | None) -> str:
    result = result or {}
    trace = (packet or {}).get('public_trace', {})
    body = (f'# Run 复盘：{run_id}\n\n' +
            ('复盘模型结果：unknown；' + error + '\n\n' if error else '独立新上下文复盘结果已保存；完整文件读取程度未单独核实。\n\n') +
            f"公开轨迹：{trace.get('path', 'unknown')}；SHA256 {trace.get('sha256', 'unknown')}；"
            f"步骤 {trace.get('steps', 'unknown')}；截断 {trace.get('truncated', 'unknown')}。\n\n"
            '## 系统缺陷\n\n' + result.get('system_defects_md', 'unknown；未得到模型分析') +
            '\n\n## 策略教训候选\n\n' + json.dumps(result.get('strategy_lessons', []), ensure_ascii=False, indent=2) +
            '\n\n## 环境事实\n\n' + json.dumps((packet or {}).get('environment_receipts', []), ensure_ascii=False, indent=2) +
            '\n\n复盘的环境建议（不升级为事实）：\n' + result.get('environment_notes_md', 'unknown') + '\n')
    target = config.WORKSPACE_DIR / 'reviews' / (run_id + '.md')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(strip_secrets(body), encoding='utf-8')
    return str(target.relative_to(config.WORKSPACE_DIR))


async def advance(controller, only_run_id: str | None = None) -> None:
    from . import power
    if power.shutdown_requested():
        return
    for pending in db.query("SELECT id FROM curation_requests WHERE status='pending'" +
                            (' AND run_id=?' if only_run_id else ''), (only_run_id,) if only_run_id else ()):
        with db.transaction() as conn:
            changed = conn.execute("UPDATE curation_requests SET status='running',updated_at=? WHERE id=? AND status='pending'",
                                   (db.utcnow(), pending['id'])).rowcount
        if changed:
            schedule(controller._run_curation(pending['id']))
    for row in db.query("SELECT * FROM run_post_reviews WHERE status='pending'" +
                        (' AND run_id=?' if only_run_id else ''), (only_run_id,) if only_run_id else ()):
        rid = row['run_id']
        try:
            curated = await controller.curate_run_experience(rid, 'end-curation-' + rid)
        except Exception as exc:
            # A manual curation may be running; leave this end pass queued.
            if getattr(exc, 'code', '') == 'CURATION_RUNNING':
                continue
            curated = {'state': 'failed'}
        if curated['state'] in ('running', 'pending'):
            continue
        with db.transaction() as conn:
            changed = conn.execute("UPDATE run_post_reviews SET status='running',updated_at=?"
                                   " WHERE run_id=? AND status='pending'", (db.utcnow(), rid)).rowcount
        if changed:
            schedule(run_post_review(controller, rid))


async def run_post_review(controller, run_id: str) -> None:
    owner = 'postreview-' + run_id
    brain = session = packet = result = None
    error = None
    deferred = cancelled = False
    try:
        controller._require_model_authorization(run_id)
        settings = controller._runtime_settings(run_id)
        original = settings['brain']
        settings['brain'] = dict(settings.get('post_review') or config.DEFAULT_SETTINGS['post_review'])
        if not settings['brain'].get('executable') and original.get('runtime') == settings['brain']['runtime']:
            settings['brain']['executable'] = original.get('executable', '')
        resource_coordinator.reserve_auxiliary(owner, settings)
        packet = snapshot(controller, run_id)
        db.execute('UPDATE run_post_reviews SET packet_json=? WHERE run_id=?', (json.dumps(packet, ensure_ascii=False), run_id))
        brain = controller._make_brain(settings)
        root = config.WORKSPACE_DIR / 'reviews'
        session = await brain.open({'working_directory': str(root), 'instructions': packet['instruction']})
        claim_call(run_id, owner, 'postreview')
        async for event in brain.review(session, packet):
            if event.type == 'task_result':
                result = json.loads(strip_secrets(json.dumps(event.payload['result'], ensure_ascii=False)))
            elif event.type == 'error':
                raise ValueError(strip_secrets(str(event.payload.get('message', '复盘失败'))))
            elif event.type == 'usage':
                usage = json.loads(strip_secrets(json.dumps(event.payload, ensure_ascii=False)))
                db.append_event(run_id, 'brain', 'maintenance.usage', {'kind': 'postreview', 'usage': usage})
        jsonschema.validate(result, output_contract())
        refs = set(packet['full_evidence_refs'])
        ids = []
        for proposal in result['strategy_lessons']:
            if not proposal['evidence_refs'] or not set(proposal['evidence_refs']) <= refs:
                raise ValueError('复盘提议引用不属于本次公开快照')
            if proposal['scope'] == 'challenge' and proposal['challenge_id'] != packet['run_evidence']['challenge_id']:
                raise ValueError('复盘提议不能指向其他题目')
        for proposal in result['strategy_lessons']:
            candidate = {**proposal, 'evidence_status': 'hypothesis'}
            # A post-review candidate cannot demote or overwrite an active
            # recipe or another Run's strategy. PI adoption is separate.
            candidate.pop('target_id', None)
            candidate.pop('expected_revision', None)
            if candidate.get('kind') == 'strategy':
                candidate['kind'] = 'heuristic'
            eid = controller._apply_experience_proposal(run_id, owner, candidate, candidate=True)
            if eid:
                ids.append(eid)
        result['experience_ids'] = ids
    except resource_coordinator.ResourceWait:
        deferred = True
        db.execute("UPDATE run_post_reviews SET status='pending',updated_at=? WHERE run_id=?", (db.utcnow(), run_id))
        return
    except asyncio.CancelledError:
        cancelled = True
        error = '关机或进程中断；已开始的模型调用不自动重发'
        raise
    except Exception as exc:
        error = strip_secrets(str(exc))[:500]
    finally:
        if brain is not None and session is not None:
            try:
                await brain.close(session)
            except Exception as exc:
                resource_coordinator.close_failed(owner, exc)
        resource_coordinator.release_sessions(owner)
        if not deferred and (packet is not None or error is not None):
            path = write_report(run_id, packet, result, error)
            status = 'unknown' if cancelled else ('failed' if error else 'done')
            with db.transaction() as conn:
                conn.execute('UPDATE maintenance_calls SET status=?,updated_at=? WHERE operation_id=?', (status, db.utcnow(), owner))
                conn.execute('UPDATE run_post_reviews SET status=?,result_json=?,report_path=?,error=?,updated_at=? WHERE run_id=?',
                    (status, json.dumps(result, ensure_ascii=False) if result else None, path, error, db.utcnow(), run_id))
            db.append_event(run_id, 'controller', 'run.post_review_' + status, {'report_path': path, 'error': error})


def reconcile_interrupted() -> None:
    """Reconcile both interrupted turns and an interrupted reconciliation."""
    for row in db.query("SELECT * FROM maintenance_calls WHERE status IN ('running','unknown')"):
        now = db.utcnow()
        if row['kind'] == 'curation':
            request = db.query_one('SELECT status FROM curation_requests WHERE id=?', (row['operation_id'],))
            if request and request['status'] in ('done', 'failed'):
                if row['status'] == 'running':
                    complete_call(row['operation_id'], request['status'])
                continue
            with db.transaction() as conn:
                conn.execute("UPDATE maintenance_calls SET status='unknown',updated_at=? WHERE operation_id=?", (now, row['operation_id']))
                conn.execute("UPDATE curation_requests SET status='failed',error='模型调用被重启中断；不自动重发',updated_at=? WHERE id=?", (now, row['operation_id']))
        else:
            post = db.query_one('SELECT * FROM run_post_reviews WHERE run_id=?', (row['run_id'],))
            if post and post['status'] in ('done', 'failed', 'unknown'):
                if row['status'] == 'running':
                    complete_call(row['operation_id'], post['status'])
                continue
            error = '模型调用被重启中断；不自动重发'
            try:
                packet = json.loads(post['packet_json']) if post and post['packet_json'] else None
            except (TypeError, ValueError):
                packet = None
            try:
                path = write_report(row['run_id'], packet, None, error)
            except OSError:
                path = None
                error += '；报告文件写入失败，保留数据库记录'
            with db.transaction() as conn:
                conn.execute("UPDATE maintenance_calls SET status='unknown',updated_at=? WHERE operation_id=?", (now, row['operation_id']))
                conn.execute("UPDATE run_post_reviews SET status='unknown',error=?,report_path=?,updated_at=? WHERE run_id=?", (error, path, now, row['run_id']))
    db.execute("UPDATE curation_requests SET status='pending' WHERE status='running'"
               " AND id NOT IN (SELECT operation_id FROM maintenance_calls)")
    db.execute("UPDATE run_post_reviews SET status='pending' WHERE status='running'"
               " AND ('postreview-' || run_id) NOT IN (SELECT operation_id FROM maintenance_calls)")
