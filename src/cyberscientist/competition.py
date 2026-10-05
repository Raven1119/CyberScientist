"""Competition rounds use the existing persistent evaluation queue tables.

Import and triage are read-only. Only an explicitly confirmed template grants
the ordinary Run permissions; a round marker never disables capabilities.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import uuid
import urllib.parse
from pathlib import Path
from typing import Any

from . import (challenge_models, config, db, evaluations, platform_scores,
               resource_coordinator, experience_context, backend_identity)


class CompetitionError(ValueError):
    pass


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _public_round(season: str, seq: int) -> dict:
    from .mailbox_platform import BohriumPlaygroundPlatform
    base = config.load_settings()['playground']['base_url']
    result = BohriumPlaygroundPlatform(base_url=base, operator_token=None, timeout=15)._http(
        'GET', '/hackathon/seasons/by-slug/' + urllib.parse.quote(season, safe='') + '/rounds', token=None)
    if not isinstance(result, dict) or not isinstance(result.get('rounds'), list):
        raise CompetitionError('平台轮次协议不符：缺少 rounds')
    row = next((r for r in result['rounds'] if r.get('seq') == seq), None)
    if not row or not isinstance(row.get('challengeIds'), list):
        raise CompetitionError('轮次不存在或缺少 challengeIds')
    return row


def _import(slug: str) -> str:
    found = db.query_one('SELECT id FROM challenges WHERE platform_challenge_id=? ORDER BY imported_at', (slug,))
    if found:
        return found['id']
    local = db.query_one('SELECT id FROM challenges WHERE id=?', (slug,))
    if local:
        return local['id']
    cid = 'local_' + hashlib.sha256(slug.encode()).hexdigest()[:12]
    evaluations._ensure_challenge({'challenge_id': cid, 'platform_challenge_id': slug, 'title': slug})
    return cid


def _challenge_snapshot(cid: str) -> dict:
    """Bind freshly observed public details to this round while retaining CID."""
    from . import mailbox_platform
    challenge = db.query_one('SELECT * FROM challenges WHERE id=?', (cid,))
    value = {'id': cid, 'title': challenge['title'], 'content': challenge['content'],
             'content_sha256': challenge['content_hash'],
             'resources': json.loads(challenge['resources_json'] or '[]'),
             'platform': json.loads(challenge['platform_snapshot_json'] or '{}'),
             'observed_at': db.utcnow(), 'source': 'existing_local'}
    if challenge['platform_challenge_id'] and not challenge['is_demo']:
        settings = config.load_settings()['playground']
        try:
            data = mailbox_platform.fetch_platform_challenge(settings['base_url'], challenge['platform_challenge_id'],
                       config.resolve_secret(settings.get('token_secret_ref') or ''))
            content = (data.get('content') or '').strip()
            if not content:
                raise CompetitionError('当前公开题面为空')
            value.update(title=data.get('title_zh') or data.get('title') or challenge['title'], content=content,
                         content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                         resources=data.get('resources') or [], source='current_public_get',
                         platform={key:data.get(key) for key in ('status','roundStartAt','roundEndAt','scoring')})
        except Exception as exc:
            value.update(source='existing_snapshot_current_refresh_unknown', refresh_error=type(exc).__name__)
    from . import datasets
    datasets.register_resources(cid, value['resources'])
    return value


def import_round(challenge_ids: list[str] | None = None, *, season: str = '',
                 round_seq: int | None = None, label: str = '', mode: str = 'connected') -> dict:
    if mode not in ('connected', 'demo'):
        raise CompetitionError('mode 必须为 connected 或 demo')
    from . import protocol_drift
    drift = protocol_drift.check() if mode == 'connected' else {'status': 'not_checked_demo'}
    public = _public_round(season, round_seq) if season and round_seq is not None else None
    slugs = public['challengeIds'] if public else challenge_ids
    if not isinstance(slugs, list) or not slugs or len(slugs) > 100 or any(
            not isinstance(s, str) or not s.strip() or len(s) > 250 for s in slugs):
        raise CompetitionError('提供赛季和轮次，或 1–100 个题目 ID')
    entries = []
    for slug in dict.fromkeys(slugs):
        cid = _import(slug)
        entries.append({'challenge_id': cid, 'challenge_snapshot': _challenge_snapshot(cid)})
    rid = 'round_' + uuid.uuid4().hex[:12]
    now = db.utcnow()
    snapshot = {'schema': 'cyberscientist-competition/v1', 'mode': mode, 'entries': entries,
                'season': season, 'round_seq': round_seq, 'public_round': public,
                'backend': backend_identity.capture(), 'protocol_drift': drift}
    with db.transaction() as conn:
        conn.execute('INSERT INTO eval_runs(id,suite,repeats,label,status,config_json,created_at,updated_at)'
                     " VALUES(?,'competition',1,?,'draft',?,?,?)", (rid, label, _dump(snapshot), now, now))
        for item in entries:
            conn.execute('INSERT INTO eval_results(id,eval_id,challenge_id,repeat_index,status,created_at,updated_at)'
                         " VALUES(?,?,?,1,'pending',?,?)", ('ri_' + uuid.uuid4().hex[:12], rid,
                         item['challenge_id'], now, now))
    return get_round(rid)


def _round(round_id: str):
    row = db.query_one("SELECT * FROM eval_runs WHERE id=? AND suite='competition'", (round_id,))
    if not row:
        raise CompetitionError('轮次不存在')
    return row


async def triage(round_id: str, controller, allow_model_calls: bool = False) -> dict:
    row = _round(round_id)
    snapshot = json.loads(row['config_json'])
    if snapshot['mode'] == 'connected' and not allow_model_calls:
        raise CompetitionError('分诊调用模型需显式授权')
    settings = config.load_settings()
    settings['app']['mode'] = snapshot['mode']
    owner = 'triage-' + round_id + '-' + uuid.uuid4().hex
    brain = controller._make_brain(settings)
    session = None
    resource_coordinator.reserve_auxiliary(owner, settings)
    try:
        scratch = config.WORKSPACE_DIR / 'rounds' / round_id / owner
        scratch.mkdir(parents=True, exist_ok=True)
        session = await brain.open({'working_directory': str(scratch)})
        for item in db.query('SELECT * FROM eval_results WHERE eval_id=?', (round_id,)):
            challenge = db.query_one('SELECT * FROM challenges WHERE id=?', (item['challenge_id'],))
            try:
                scores = await asyncio.to_thread(platform_scores._collect, challenge['platform_challenge_id']) \
                    if snapshot['mode'] != 'demo' and challenge['platform_challenge_id'] else {'status': 'unknown'}
            except Exception as exc:
                scores = {'status': 'unknown', 'reason': type(exc).__name__}
            packet = {'protocol': 'role_task', 'task': 'competition_triage',
                      'instructions': '只读题面、资源和公开分布，评估难度和预计耗时/花费，给出模型建议及理由。'
                                      '简单题建议 deepseek-flash；难题建议 gpt-6.1-sol。建议不是授权。',
                      'challenge': next(e.get('challenge_snapshot') for e in snapshot['entries'] if e['challenge_id'] == item['challenge_id']),
                      'public_scores': scores, 'solver_roster': challenge_models.roster(settings),
                      'output_contract': {'type': 'object', 'additionalProperties': False,
                          'required': ['difficulty', 'estimated_minutes', 'estimated_cost_cny', 'recommended_model', 'recommended_solver_id', 'reason'],
                          'properties': {'difficulty': {'enum': ['easy', 'medium', 'hard', 'unknown']},
                              'estimated_minutes': {'type': ['number', 'null'], 'minimum': 0},
                              'estimated_cost_cny': {'type': ['number', 'null'], 'minimum': 0},
                              'recommended_model': {'type': 'string'}, 'reason': {'type': 'string'},
                              'recommended_solver_id': {'enum': [None, *[s['id'] for s in challenge_models.roster(settings)]]}}}}
            result = None
            async with asyncio.timeout(180):
                async for event in brain.review(session, packet):
                    if event.type == 'task_result': result = event.payload['result']
                    if event.type == 'error': raise CompetitionError(event.payload.get('message', '分诊失败'))
            if not result or result.get('difficulty') not in ('easy', 'medium', 'hard', 'unknown'):
                raise CompetitionError('分诊缺少有效难度，未编造建议')
            if result.get('recommended_solver_id') and result['recommended_solver_id'] not in {s['id'] for s in challenge_models.roster(settings)}:
                raise CompetitionError('分诊推荐的求解者条目不存在')
            db.execute('UPDATE eval_results SET triage_json=?,updated_at=? WHERE id=?',
                       (_dump(result), db.utcnow(), item['id']))
    except Exception as exc:
        from .model_providers import record_throttle
        record_throttle(settings['brain'], exc)
        raise
    finally:
        try:
            if session:
                try: await brain.close(session)
                except Exception as exc:
                    resource_coordinator.close_failed(owner, exc)
                    raise
        finally: resource_coordinator.release_sessions(owner)
    return get_round(round_id)


def _template(template: dict, mode: str, *, frozen: bool = False) -> dict:
    if not isinstance(template, dict) or set(template) - {'model_config', 'authorization', 'shadow_enabled', 'solver_note', 'solver_id'} - ({'solver_entry'} if frozen else set()):
        raise CompetitionError('模板只接受模型、授权、监督和求解者备注')
    settings = config.load_settings()
    choices = dict(template.get('model_config') or {})
    if frozen and choices.get('brain'):
        from .pi_policy import migrated
        choices['brain'] = migrated(choices['brain'])
    solver_entry = None
    if template.get('solver_id'):
        solver_entry = template.get('solver_entry') if frozen else challenge_models.solver(template['solver_id'], settings)
        if solver_entry.get('id') != template['solver_id']:
            raise CompetitionError('冻结求解者 ID 不匹配')
        solver_entry = challenge_models.roster({**settings, 'solver_roster': [solver_entry]})[0]
        choices['executor'] = solver_entry
    models = {role: challenge_models.choose(role, choices.get(role), settings) for role in ('brain', 'executor')}
    auth = template.get('authorization') or {}
    allowed = {'max_run_minutes', 'max_jobs', 'max_submissions', 'max_model_turns', 'max_sandboxes',
               'max_sandbox_minutes', 'allow_sandbox_gpu', 'allow_data_download', 'job_limits', 'max_environment_saves',
               'max_compute_cost_cny', 'allow_model_calls', 'unlimited_resources'}
    if not isinstance(auth, dict) or set(auth) - allowed:
        raise CompetitionError('授权模板字段不符')
    for key in ('max_run_minutes', 'max_jobs', 'max_submissions', 'max_model_turns', 'max_sandboxes', 'max_sandbox_minutes', 'max_environment_saves'):
        value = auth.get(key, 0)
        if type(value) is not int or value < 0:
            raise CompetitionError('额度必须是非负整数')
    if mode == 'connected' and (auth.get('allow_model_calls') is not True or auth.get('max_run_minutes', 0) <= 0):
        raise CompetitionError('真实轮次须授权模型调用和有界时长')
    if (auth.get('max_sandboxes', 0) == 0) != (auth.get('max_sandbox_minutes', 0) == 0):
        raise CompetitionError('沙箱数量与累计分钟数须同时授权')
    from . import compute, compute_budget
    compute.validate_limits(auth.get('job_limits'))
    compute_budget.validate_cap(auth.get('max_compute_cost_cny'))
    for key in ('allow_model_calls', 'allow_sandbox_gpu', 'allow_data_download', 'unlimited_resources'):
        if key in auth and type(auth[key]) is not bool:
            raise CompetitionError('授权开关必须是布尔值')
    # New confirmations use the competition policy. Frozen old templates retain
    # their original bounded authorization unless they already carried this flag.
    auth = dict(auth, unlimited_resources=auth.get('unlimited_resources', not frozen))
    if not frozen:
        auth['job_limits'] = dict(auth.get('job_limits') or {})
        auth['job_limits'].setdefault('allow_gpu', True)
        auth.setdefault('allow_sandbox_gpu', True)
    if auth['unlimited_resources']:
        auth['max_compute_cost_cny'] = None
    return {'model_config': models, 'authorization': auth, 'solver_id': template.get('solver_id'),
            'solver_entry': solver_entry,
            'shadow_enabled': bool(template.get('shadow_enabled', False)),
            'solver_note': challenge_models.choose('executor', models['executor'] | {
                'note': template.get('solver_note', '') or (solver_entry or {}).get('note', '')}, settings)['note']}


def confirm(round_id: str, template: dict, overrides: dict | None = None) -> dict:
    row = _round(round_id)
    snapshot = json.loads(row['config_json'])
    if row['status'] != 'draft':
        raise CompetitionError('只有待确认轮次可确认')
    base = _template(template, snapshot['mode'])
    choices = {item['id']: (_template(overrides[item['challenge_id']], snapshot['mode']) if item['challenge_id'] in (overrides or {}) else base)
               for item in db.query('SELECT * FROM eval_results WHERE eval_id=?', (round_id,))}
    snapshot['template'] = base
    manifests = {e['challenge_id']: experience_context.select(e['challenge_id'], role='both') for e in snapshot['entries']}
    snapshot['experience_snapshot_sha256'] = hashlib.sha256(_dump(manifests).encode()).hexdigest()
    with db.transaction() as conn:
        changed = conn.execute("UPDATE eval_runs SET status='running',config_json=?,updated_at=?"
                               " WHERE id=? AND status='draft'", (_dump(snapshot), db.utcnow(), round_id))
        if changed.rowcount != 1: raise CompetitionError('轮次状态已变化')
        for ident, choice in choices.items():
            conn.execute('UPDATE eval_results SET template_json=? WHERE id=?', (_dump(choice), ident))
    return get_round(round_id)


def append_run(round_id: str, challenge_id: str, template: dict | None = None) -> dict:
    row = _round(round_id)
    snapshot = json.loads(row['config_json'])
    if challenge_id not in {e['challenge_id'] for e in snapshot['entries']}:
        raise CompetitionError('追加 Run 须复用本轮题目 ID')
    chosen = _template(template or snapshot.get('template', {}), snapshot['mode'], frozen=not bool(template))
    with db.transaction() as conn:
        index = conn.execute('SELECT COALESCE(MAX(repeat_index),0)+1 FROM eval_results'
                             ' WHERE eval_id=? AND challenge_id=?', (round_id, challenge_id)).fetchone()[0]
        conn.execute('INSERT INTO eval_results(id,eval_id,challenge_id,repeat_index,status,template_json,created_at,updated_at)'
                     " VALUES(?,?,?,?,'pending',?,?,?)", ('ri_' + uuid.uuid4().hex[:12], round_id,
                     challenge_id, index, _dump(chosen), db.utcnow(), db.utcnow()))
        conn.execute("UPDATE eval_runs SET status='running',ended_at=NULL WHERE id=?", (round_id,))
    return get_round(round_id)


def update_item(round_id: str, item_id: str, *, priority: int | None = None, paused: bool | None = None) -> dict:
    _round(round_id)
    if not db.query_one('SELECT id FROM eval_results WHERE id=? AND eval_id=?', (item_id, round_id)):
        raise CompetitionError('轮次条目不存在')
    if priority is not None:
        if type(priority) is not int or not -1000 <= priority <= 1000: raise CompetitionError('优先级范围 -1000–1000')
        db.execute('UPDATE eval_results SET priority=? WHERE id=?', (priority, item_id))
    if paused is not None: db.execute('UPDATE eval_results SET paused=? WHERE id=?', (int(paused), item_id))
    return get_round(round_id)


def get_round(round_id: str) -> dict:
    row = _round(round_id)
    items = []
    for r in db.query('SELECT e.*,c.title FROM eval_results e JOIN challenges c ON c.id=e.challenge_id'
                      ' WHERE eval_id=? ORDER BY priority DESC,e.rowid', (round_id,)):
        item = dict(r)
        for key in ('template_json', 'triage_json', 'result_json'):
            item[key.removesuffix('_json')] = json.loads(item.pop(key) or 'null')
        run = db.query_one('SELECT phase,block_reason FROM runs WHERE id=?', (r['run_id'],)) if r['run_id'] else None
        item['phase'] = run['phase'] if run else 'queued'
        item['blocked_reason'] = run['block_reason'] if run else r['error']
        item['local_best'] = db.query_one('SELECT MAX(science_score) FROM local_scores WHERE challenge_id=?',
                                         (r['challenge_id'],))[0]
        scored = db.query_one('SELECT score,score_confidence FROM submissions WHERE run_id=? AND score IS NOT NULL'
                              ' ORDER BY score DESC LIMIT 1', (r['run_id'],))
        item['platform_best'] = dict(scored) if scored else None
        item['trace_diagnostic'] = db.query_one("SELECT payload FROM events WHERE run_id=? AND type IN"
                                               " ('evaluation.trace_diagnosed','trace.diagnosed') ORDER BY seq DESC LIMIT 1",
                                               (r['run_id'],))
        item['trace_diagnostic'] = json.loads(item['trace_diagnostic']['payload']) if item['trace_diagnostic'] else None
        usage = db.query("SELECT payload FROM events WHERE run_id=? AND type IN"
                         " ('brain.usage','prime.usage','brain.usage.updated','prime.usage.updated')", (r['run_id'],))
        item['usage'] = [json.loads(u['payload']) for u in usage][-4:]
        item['cost'] = None
        if r['run_id']:
            from . import compute
            item['cost'] = compute.costs(r['run_id'])
            from . import model_usage
            item['model_cost'] = model_usage.summarize(r['run_id'])
        item['next_action'] = ('继续授权内研究' if item['phase'] == 'running' else
                               '等待资源名额' if item['phase'] == 'queued' else item['blocked_reason'])
        items.append(item)
    snapshot = json.loads(row['config_json'])
    return {'id': round_id, 'label': row['label'], 'status': row['status'], 'items': items,
            'protocol_drift': snapshot.get('protocol_drift', {'status': 'unknown'}),
            'template': snapshot.get('template'), 'experience_snapshot_sha256': snapshot.get('experience_snapshot_sha256'),
            'resources': resource_coordinator.status()}


async def advance_round(controller, evaluation) -> None:
    rid = evaluation['id']
    snapshot = json.loads(evaluation['config_json'])
    for item in db.query('SELECT * FROM eval_results WHERE eval_id=? ORDER BY priority DESC,rowid', (rid,)):
        if item['status'] in ('complete', 'failed'): continue
        if item['retry_at'] and item['retry_at'] > db.utcnow(): continue
        run = db.query_one('SELECT * FROM runs WHERE id=?', (item['run_id'],)) if item['run_id'] else None
        if item['paused']:
            if run and run['phase'] == 'running':
                await controller.control(run['id'], 'pause', None, f"round-pause-{item['id']}-{run['state_version']}")
                db.execute('UPDATE eval_results SET queue_paused=1 WHERE id=?', (item['id'],))
            continue
        template = _template(json.loads(item['template_json']), snapshot['mode'], frozen=True)
        try:
            if run is None:
                # Do not create a capacity-consuming Run while its provider is
                # full. Native startup repeats this check under the writer lock.
                with db.transaction() as conn:
                    resource_coordinator.reserve_sessions_tx(conn, item['id'], template['model_config'])
                    conn.execute('DELETE FROM model_session_leases WHERE owner=?', (item['id'],))
                run = controller.create_run(item['challenge_id'], snapshot['mode'], template['shadow_enabled'],
                                            model_config=template['model_config'])
                db.execute("UPDATE eval_results SET run_id=?,status='created' WHERE id=?", (run['id'], item['id']))
                # Freeze note and round link without creating capability restrictions.
                state = json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (run['id'],))['config_snapshot'])
                state['competition'] = {'round_id': rid, 'item_id': item['id'], 'solver_note': template['solver_note'],
                                        'solver_entry': template.get('solver_entry'),
                                        'challenge_snapshot': next(e.get('challenge_snapshot') for e in snapshot['entries'] if e['challenge_id'] == item['challenge_id'])}
                db.execute('UPDATE runs SET config_snapshot=? WHERE id=?', (_dump(state), run['id']))
            phase = run['phase']
            if phase == 'created':
                if not run['authorization_id']:
                    auth = {'max_model_turns': 0, 'max_jobs': 0, 'max_submissions': 0,
                            'max_sandboxes': 0, 'max_sandbox_minutes': 0, 'max_run_minutes': 0,
                            'allow_model_calls': snapshot['mode'] == 'demo'} | template['authorization']
                    details = next(e.get('challenge_snapshot') for e in snapshot['entries'] if e['challenge_id'] == item['challenge_id'])
                    content = details['content'] if details else db.query_one('SELECT content FROM challenges WHERE id=?', (item['challenge_id'],))['content']
                    controller.authorize(run['id'], snapshot['mode'], note='用户确认的比赛轮次模板', objective=content, **auth)
                await controller.start_async(run['id'])
                db.execute('UPDATE eval_results SET error=NULL,retry_at=NULL WHERE id=?', (item['id'],))
            elif phase == 'recovering':
                recovery = db.query_one("SELECT seq FROM events WHERE run_id=? AND type IN"
                                        " ('run.needs_recovery','run.reopened') ORDER BY seq DESC LIMIT 1", (run['id'],))
                episode = recovery['seq'] if recovery else run['state_version']
                await controller.control(run['id'], 'resume', None, f"round-resume-{run['id']}-{episode}")
            elif phase == 'paused' and item['queue_paused']:
                await controller.control(run['id'], 'resume', None, f"round-unpause-{run['id']}-{run['state_version']}")
                db.execute('UPDATE eval_results SET queue_paused=0 WHERE id=?', (item['id'],))
            elif phase in evaluations.TERMINAL:
                db.execute("UPDATE eval_results SET status=?,updated_at=? WHERE id=?",
                           ('failed' if phase == 'failed' else 'complete', db.utcnow(), item['id']))
            else:
                db.execute('UPDATE eval_results SET status=?,updated_at=? WHERE id=?', (phase, db.utcnow(), item['id']))
        except Exception as exc:
            code = getattr(exc, 'code', '')
            from .model_limits import classify
            if code in ('RUN_ACTIVE', 'RESOURCE_WAIT'):
                db.execute('UPDATE eval_results SET error=? WHERE id=?', (str(exc)[:300], item['id']))
                if code == 'RUN_ACTIVE': break
                continue
            if classify(str(exc)):
                from . import model_limits
                from datetime import datetime, timezone
                delay = model_limits.retry_delay(item['retry_count'] + 1, classify(str(exc)))
                retry_at = model_limits.retry_at(datetime.now(timezone.utc), delay)
                name = getattr(exc, 'provider', None) or resource_coordinator.provider(template['model_config']['executor'])
                resource_coordinator.throttle(name, retry_at)
                db.execute('UPDATE eval_results SET error=?,retry_at=?,retry_count=retry_count+1 WHERE id=?',
                           ('模型限速，等待退避：' + str(exc)[:200], retry_at, item['id']))
                continue
            db.execute("UPDATE eval_results SET status='failed',error=?,updated_at=? WHERE id=?",
                       (type(exc).__name__ + ': ' + str(exc)[:250], db.utcnow(), item['id']))
            if run and run['phase'] == 'created':
                db.execute("UPDATE runs SET phase='failed',ended_at=?,block_reason=? WHERE id=?"
                           " AND phase IN ('created','blocked')", (db.utcnow(), type(exc).__name__, run['id']))
    if not db.query_one("SELECT 1 FROM eval_results WHERE eval_id=? AND status NOT IN ('complete','failed')", (rid,)):
        db.execute("UPDATE eval_runs SET status='complete',ended_at=?,updated_at=? WHERE id=?", (db.utcnow(), db.utcnow(), rid))
