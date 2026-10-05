"""Operator-facing observations and explicit recovery, with no secret output."""
import asyncio
import json
import subprocess
from datetime import datetime, timezone
from . import alerts, backend_identity, config, db, experiences, observation, power, resource_coordinator

RESUME_TASK = None


def safe(value):
    return json.loads(observation.strip_secrets(json.dumps(value, ensure_ascii=False)))


def events(run_id, tail=20):
    if type(tail) is not int or not 1 <= tail <= 1000: raise ValueError('tail须为1–1000整数')
    if not db.query_one('SELECT id FROM runs WHERE id=?', (run_id,)): raise ValueError('Run不存在')
    rows = db.query('SELECT seq,source,type,payload,recorded_at FROM events WHERE run_id=? ORDER BY seq DESC LIMIT ?', (run_id, tail))
    return safe({'run_id': run_id, 'items': [dict(r) | {'payload': json.loads(r['payload'])} for r in reversed(rows)]})


def pending():
    return safe({'alerts': alerts.pending(), 'experience_approvals': [
        {k: item.get(k) for k in ('id', 'title', 'revision_id', 'evidence_status')}
        for item in experiences.pending_approvals()['items']]})


def status():
    from . import leaderboards
    from .mailboxes import _instant
    now = datetime.now(timezone.utc); settings = config.load_settings(); runs = []
    for row in db.query('SELECT id,challenge_id,phase,current_trial_id,block_reason,created_at,clock_version,resume_on_startup FROM runs ORDER BY created_at DESC'):
        last = db.query_one('SELECT seq,type,recorded_at FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 1', (row['id'],))
        stamp = _instant(last['recorded_at'] if last else row['created_at'])
        quiet = max(0, (now - stamp).total_seconds()) if stamp else None
        local = db.query_one("SELECT MAX(science_score) FROM local_scores WHERE run_id=? AND score_source IN ('system','executor_verified')", (row['id'],))[0]
        confirmed = db.query_one("SELECT MAX(score) FROM submissions WHERE run_id=? AND status='submitted' AND score_status='scored' AND score_confidence='confirmed' AND (score_anomaly IS NULL OR score_anomaly='')", (row['id'],))[0]
        runs.append(dict(row) | {'local_best': local, 'platform_best': confirmed,
                                'topic_best_current_platform': leaderboards.own_best(row['challenge_id']),
                                'last_event': dict(last) if last else None,
                                'stuck': {'suspected': row['phase'] == 'running' and quiet is not None and quiet > settings['run_defaults']['stall_seconds'],
                                          'quiet_seconds': quiet, 'notice': '静默时长只作提醒，不证明科研停滞'}})
    loaded = backend_identity.loaded(); checkout = backend_identity.capture(); tags = []; tags_status = 'unknown'
    if loaded.get('commit'):
        try:
            proc = subprocess.run(['git', 'tag', '--points-at', loaded['commit']], cwd=config.WORKSPACE_ROOT, capture_output=True, text=True, timeout=5)
            if proc.returncode == 0: tags = proc.stdout.splitlines(); tags_status = 'observed'
        except (OSError, subprocess.TimeoutExpired): pass
    recent = db.query("SELECT run_id,seq,type,payload,recorded_at FROM events WHERE type LIKE '%.error' OR type LIKE '%.failed' OR type IN ('run.runtime_error','run.needs_attention','submission.unknown') ORDER BY rowid DESC LIMIT 20")
    return safe({'status': 'ok', 'observed_at': db.utcnow(), 'shutdown_requested': power.shutdown_requested(),
                 'runs': runs, 'pending': pending(), 'recent_errors': [dict(r) | {'payload': json.loads(r['payload'])} for r in recent],
                 'resources': resource_coordinator.status(), 'native_close_unknowns': resource_coordinator.close_unknowns(),
                 'features': settings['features'], 'code': {'loaded': loaded, 'checkout': checkout, 'matches': loaded == checkout, 'tags': tags, 'tags_status': tags_status}})


async def _thread(fn, *args, **kwargs):
    # HTTP cancellation cannot discard the actual thread or clear its owner.
    task = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
    cancelled = False
    while not task.done():
        try: await asyncio.shield(task)
        except asyncio.CancelledError: cancelled = True
        except Exception: break
    result = task.result()
    if cancelled: raise asyncio.CancelledError
    return result


async def _resume(controller):
    owner = 'ops-resume'; resource_coordinator.register_auxiliary(owner, asyncio.current_task())
    try:
        shutdown_active = power.shutdown_requested()
        retry = db.query_one("SELECT 1 FROM runs WHERE phase='recovering' AND clock_version=1 AND resume_on_startup=1 LIMIT 1")
        if not shutdown_active and not retry: return {'status': 'ready', 'resumed': [], 'notice': '没有待恢复的关机意图，无需重复恢复'}
        epoch = db.query_one("SELECT value FROM system_state WHERE key='shutdown_epoch'")
        epoch = epoch['value'] if epoch else None
        from . import compute, mailboxes, sandboxes
        receipts = []; errors = []
        for rid in compute.reconciliation_runs(startup=True):
            try: receipts.append({'kind': 'jobs', 'run_id': rid, 'result': await _thread(compute.reconcile, rid, allow_retry=False)})
            except Exception as exc: errors.append({'kind': 'jobs', 'error': type(exc).__name__})
        if db.query_one("SELECT 1 FROM compute_sandboxes WHERE status NOT IN ('deleted','expired','failed') LIMIT 1"):
            try: receipts.append({'kind': 'sandboxes', 'result': await _thread(sandboxes.reconcile_startup, cleanup_terminal=False)})
            except Exception as exc: errors.append({'kind': 'sandboxes', 'error': type(exc).__name__})
        try: receipts.append({'kind': 'submissions', 'result': await _thread(mailboxes.poll_pending_by_challenge)})
        except Exception as exc: errors.append({'kind': 'submissions', 'error': type(exc).__name__})
        others = [t for t in resource_coordinator.auxiliary_tasks() if t is not asyncio.current_task()]
        if resource_coordinator.close_unknowns() or shutdown_active and (others or db.query_one('SELECT 1 FROM model_session_leases LIMIT 1')):
            errors.append({'error': '原生会话尚未确认关闭'})
        current = db.query_one("SELECT value FROM system_state WHERE key='shutdown_epoch'")
        if (current['value'] if current else None) != epoch: errors.append({'error': '对账期间发生新的安全关机，恢复已取消'})
        if errors: return safe({'status': 'unknown', 'resumed': [], 'reconciliation': receipts, 'errors': errors, 'shutdown_requested': power.shutdown_requested()})
        # Only explicit shutdown intent is eligible. Manual/legacy pauses remain.
        db.execute("UPDATE runs SET phase='recovering' WHERE phase='paused' AND clock_version=1 AND resume_on_startup=1")
        resumed = await power.recover(controller, expected_shutdown_epoch=epoch)
        return safe({'status': 'unknown' if power.shutdown_requested() or any(r.get('status') == 'unknown' for r in resumed) else 'ready', 'resumed': resumed, 'reconciliation': receipts, 'shutdown_requested': power.shutdown_requested()})
    finally:
        resource_coordinator.unregister_auxiliary(owner)


async def resume(controller):
    global RESUME_TASK
    if RESUME_TASK is None or RESUME_TASK.done(): RESUME_TASK = asyncio.create_task(_resume(controller))
    return await asyncio.shield(RESUME_TASK)


async def drain():
    if RESUME_TASK and not RESUME_TASK.done():
        RESUME_TASK.cancel(); await asyncio.gather(RESUME_TASK, return_exceptions=True)
