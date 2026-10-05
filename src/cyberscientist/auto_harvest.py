"""Ordinary competition harvest, durable intent and no replay after uncertainty."""
from __future__ import annotations
import asyncio
import json
import math
from datetime import datetime, timezone, timedelta
from . import config, db, mailboxes, platform_scores, power

ACTIVE_TASKS: set[asyncio.Task] = set()


def validate(params: dict) -> dict:
    defaults = config.DEFAULT_SETTINGS['harvest']
    if not isinstance(params, dict) or set(params) - set(defaults):
        raise ValueError('自动收割参数无效')
    result = defaults | params
    for key in ('score_threshold', 'deadline_check_hours'):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{key} 须为非负有限数值')
    if type(result['experiments_done_at_leader']) is not bool:
        raise ValueError('experiments_done_at_leader 须为布尔值')
    return result


def reconcile_interrupted(*, include_running: bool = True) -> None:
    # Submission receipts are reconciled separately; a started harvest is never resent.
    with db.transaction() as conn:
        for row in conn.execute("SELECT * FROM automatic_harvests WHERE status IN ('running','unknown')" if include_running else "SELECT * FROM automatic_harvests WHERE status='unknown'").fetchall():
            result = conn.execute('SELECT id,status FROM submissions WHERE operation_id=?', (row['operation_id'],)).fetchone()
            status = 'done' if result and result['status'] == 'submitted' else 'unknown'
            if row['status'] == status:
                continue
            conn.execute('UPDATE automatic_harvests SET status=?,error=?,updated_at=? WHERE source_submission_id=?',
                         (status, None if status == 'done' else '重启时收割尚未确认；不重发', db.utcnow(), row['source_submission_id']))
            db.append_event_tx(conn, row['run_id'], 'controller', 'harvest.' + status,
                               {'source_submission_id': row['source_submission_id'], 'reason': 'startup_reconciliation'})


def experiments_done(conn, run) -> bool:
    if run['phase'] != 'finished':
        return False
    if conn.execute("SELECT 1 FROM runs WHERE challenge_id=? AND phase NOT IN ('finished','cancelled','failed') LIMIT 1", (run['challenge_id'],)).fetchone():
        return False
    if conn.execute("SELECT 1 FROM eval_results WHERE challenge_id=? AND run_id IS NULL AND status NOT IN ('complete','failed') LIMIT 1", (run['challenge_id'],)).fetchone():
        return False
    # An exhausted/interrupted Run cannot assert scientific work is complete.
    for participant in conn.execute('SELECT id,end_reason FROM runs WHERE challenge_id=?', (run['challenge_id'],)).fetchall():
        if participant['end_reason'] in ('authorization_expired', 'brain_review_limit', 'runtime_error'):
            return False
    return True


def _trigger(run, source, params: dict) -> dict | None:
    if source['score'] >= params['score_threshold']:
        return {'reason': 'score_threshold', 'score': source['score'], 'params': params}
    if params['experiments_done_at_leader'] and experiments_done(db.get_db(), run):
        distribution = platform_scores.get(run['id'], fresh=True)
        leaders = distribution.get('top_10_scores') or []
        if distribution.get('status') == 'ok' and leaders and source['score'] >= max(leaders):
            return {'reason': 'experiments_done_at_leader', 'score': source['score'], 'leader': max(leaders), 'params': params}
    return None


def advance_sync() -> None:
    reconcile_interrupted(include_running=False)
    from . import features
    if power.shutdown_requested() or not features.enabled('auto_harvest'):
        return
    params = validate(config.load_settings().get('harvest', {}))
    for run in db.query("SELECT * FROM runs WHERE phase IN ('running','waiting_score','finished')"):
        snapshot = json.loads(run['config_snapshot'])
        if snapshot.get('automatic_harvest_version') != 1:
            continue  # no retroactive irreversible authorization on historical Runs
        auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],))
        if not auth or auth['max_submissions'] <= 0:
            continue
        end = mailboxes._round_end(run['config_snapshot'])
        if end and end - timedelta(hours=params['deadline_check_hours']) <= datetime.now(timezone.utc):
            key = 'harvest_deadline_checked:' + run['id']
            with db.transaction() as conn:
                if not conn.execute('SELECT 1 FROM system_state WHERE key=?', (key,)).fetchone():
                    conn.execute('INSERT INTO system_state VALUES(?,?)', (key, db.utcnow()))
                    db.append_event_tx(conn, run['id'], 'controller', 'harvest.deadline_check', {'round_end': end.isoformat()})
        # Only this Run's experiment package may consume this Run's bounded authorization.
        sources = db.query("SELECT s.* FROM submissions s JOIN mailboxes m ON m.id=s.mailbox_id"
                           " WHERE s.run_id=? AND s.is_harvest=0 AND m.role='experiment'"
                           " AND s.status='submitted' AND s.score_status='scored' AND s.score_confidence='confirmed'"
                           " AND s.score IS NOT NULL ORDER BY s.score DESC,s.created_at DESC", (run['id'],))
        for src in sources:
            if src['score_anomaly'] or src['scorecard_consistent'] == 0 or not math.isfinite(src['score']):
                continue
            old = db.query_one('SELECT status FROM automatic_harvests WHERE source_submission_id=?', (src['id'],))
            if old and old['status'] != 'waiting':
                continue
            trigger = _trigger(run, src, params)
            if trigger is None:
                continue
            reason = trigger['reason']
            operation = 'auto-harvest-' + src['id']
            with db.transaction() as conn:
                if power.shutdown_requested() or not features.enabled('auto_harvest'):
                    return
                try:
                    mailboxes._check_budget(conn, run['id'], terminal_harvest=True)
                    current = conn.execute('SELECT * FROM submissions WHERE id=?', (src['id'],)).fetchone()
                    mailboxes._automatic_harvest_guard(conn, current, trigger)
                except mailboxes.MailboxError as exc:
                    if exc.code == 'LOWER_SCORE':
                        continue
                    if exc.code != 'HARVEST_PENDING':
                        continue
                    conn.execute("INSERT OR IGNORE INTO automatic_harvests VALUES(?,?,?,'waiting',?,NULL,NULL,?,?)",
                                 (src['id'], operation, run['id'], str(exc), db.utcnow(), db.utcnow()))
                    continue
                now = db.utcnow()
                conn.execute("INSERT OR IGNORE INTO automatic_harvests VALUES(?,?,?,'waiting',?,NULL,NULL,?,?)",
                             (src['id'], operation, run['id'], reason, now, now))
                changed = conn.execute("UPDATE automatic_harvests SET status='running',reason=?,result_json=?,updated_at=?"
                                       " WHERE source_submission_id=? AND status='waiting'", (reason, json.dumps(trigger), now, src['id']))
                if not changed.rowcount:
                    continue
                db.append_event_tx(conn, run['id'], 'controller', 'harvest.started',
                                   {'source_submission_id': src['id'], 'operation_id': operation, 'trigger': reason})
            try:
                result = mailboxes.harvest_submit(src['id'], operation, True, True, automatic=True)
                status = 'done' if result['status'] == 'submitted' else result['status']
                error = result.get('error')
            except Exception as exc:
                from .observation import strip_secrets
                result = None
                status = 'failed' if isinstance(exc, mailboxes.MailboxError) else 'unknown'
                error = strip_secrets(str(exc))[:800]
            with db.transaction() as conn:
                conn.execute('UPDATE automatic_harvests SET status=?,result_json=?,error=?,updated_at=? WHERE source_submission_id=?',
                             (status, json.dumps({'submission_id': result['id'], 'status': result['status']}) if result else None,
                              error, db.utcnow(), src['id']))
                db.append_event_tx(conn, run['id'], 'controller', 'harvest.' + status,
                                   {'source_submission_id': src['id'], 'submission_id': result['id'] if result else None,
                                    'error': error, 'no_automatic_retry': status != 'done'})
            break


async def advance() -> None:
    """Keep the actual HTTP worker alive and visible until completion at shutdown."""
    if power.shutdown_requested() or any(not task.done() for task in ACTIVE_TASKS):
        return
    from . import resource_coordinator
    async def worker():
        owner = 'automatic-harvest-http'
        task = asyncio.current_task()
        resource_coordinator.register_auxiliary(owner, task)
        http = asyncio.create_task(asyncio.to_thread(advance_sync))
        try:
            while not http.done():
                try:
                    await asyncio.shield(http)
                except asyncio.CancelledError:
                    continue  # repeated cancellations cannot erase an in-flight HTTP worker
            http.result()
        finally:
            resource_coordinator.release_sessions(owner)
    task = asyncio.create_task(worker())
    ACTIVE_TASKS.add(task)
    task.add_done_callback(ACTIVE_TASKS.discard)


async def drain() -> None:
    tasks = [task for task in ACTIVE_TASKS if not task.done()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
