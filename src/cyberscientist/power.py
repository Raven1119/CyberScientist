"""Local shutdown barrier, consistent backup and bounded startup recovery."""
from __future__ import annotations
import asyncio
import sqlite3
import uuid
from . import config, db, run_clock, resource_coordinator


def shutdown_requested() -> bool:
    row = db.query_one("SELECT value FROM system_state WHERE key='shutdown_requested'")
    return bool(row and row['value'] == '1')


def begin_shutdown():
    with db.transaction() as conn:
        conn.execute("INSERT OR REPLACE INTO system_state(key,value) VALUES('shutdown_requested','1')")
        conn.execute("INSERT OR REPLACE INTO system_state(key,value) VALUES('shutdown_epoch',?)", (uuid.uuid4().hex,))


async def safe_shutdown(controller, timeout: float = 60) -> dict:
    begin_shutdown()
    errors = []
    for row in db.query("SELECT * FROM runs WHERE phase='running'"):
        try:
            await controller.control(row['id'], 'pause', None, 'shutdown-' + uuid.uuid4().hex)
            db.execute('UPDATE runs SET resume_on_startup=1 WHERE id=? AND clock_version=1', (row['id'],))
        except Exception as exc:
            errors.append({'run_id': row['id'], 'error': type(exc).__name__})
    deadline = asyncio.get_running_loop().time() + timeout
    while db.query_one("SELECT id FROM runs WHERE phase IN ('running','pausing')") and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(.05)
    unsettled = [dict(r) for r in db.query("SELECT id,phase FROM runs WHERE phase IN ('running','pausing')")]
    if not unsettled and not errors:
        # Cancellation closes both native processes, including an active PI
        # review. The executor safe-point receipt was obtained above.
        tasks = list(set(controller._tasks.values()) | set(resource_coordinator.auxiliary_tasks()))
        tasks = [task for task in tasks if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            completed, still_running = await asyncio.wait(tasks, timeout=15)
            for task in completed:
                if not task.cancelled() and task.exception() is not None:
                    errors.append({'error': type(task.exception()).__name__})
            if still_running:
                errors.append({'error': 'native_process_close_timeout'})
    from . import preflight
    await preflight.retry_closes(timeout=max(0, deadline - asyncio.get_running_loop().time()))
    from . import competition_triage
    await competition_triage.retry_closes(timeout=max(0, deadline - asyncio.get_running_loop().time()))
    errors.extend(resource_coordinator.close_unknowns())
    from . import job_recovery
    recovery_tasks = list(job_recovery.ACTIVE.values()) + list(job_recovery.ADVICE_ACTIVE.values())
    if recovery_tasks:
        _, pending = await asyncio.wait(recovery_tasks, timeout=max(0, deadline - asyncio.get_running_loop().time()))
        if pending:
            errors.append({'error': 'job_reconciliation_still_active', 'tasks': len(pending)})
    db.execute("UPDATE curation_requests SET status='failed',error='安全关机中断整理；不会自动重复调用模型',updated_at=? WHERE status='running'", (db.utcnow(),))
    auxiliary = resource_coordinator.auxiliary_tasks()
    if auxiliary or db.query_one('SELECT 1 FROM model_session_leases LIMIT 1'):
        errors.append({'error': 'native_sessions_still_open', 'auxiliary_tasks': len(auxiliary)})
    run_clock.heartbeat()
    backup_dir = config.WORKSPACE_ROOT / '.package-checks' / 'shutdown'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (uuid.uuid4().hex + '.sqlite')
    with sqlite3.connect(backup) as target:
        db.get_db().backup(target)
    jobs = [dict(r) for r in db.query("SELECT operation_id,run_id,status,platform_job_id FROM compute_jobs WHERE status NOT IN ('Finished','Failed','Stopped','not_started')")]
    sandboxes = [dict(r) for r in db.query("SELECT operation_id,run_id,status,sandbox_id FROM compute_sandboxes WHERE status IN ('creating','active','unknown','deleting')")]
    return {'can_shutdown': not unsettled and not errors, 'backup': str(backup),
            'unsettled_runs': unsettled, 'errors': errors, 'remote_jobs': jobs,
            'remote_sandboxes': sandboxes, 'remote_costs_continue': True,
            'message': '可以关机' if not unsettled and not errors else '暂停尚未确认，暂不能关机'}


NO_EPOCH = object()


async def recover(controller, *, expected_shutdown_epoch=NO_EPOCH) -> list[dict]:
    """Called only after remote reconciliation; manual pauses remain manual."""
    # A concurrent new shutdown always wins over an earlier explicit resume.
    def changed():
        row = db.query_one("SELECT value FROM system_state WHERE key='shutdown_epoch'")
        return expected_shutdown_epoch is not NO_EPOCH and (row['value'] if row else None) != expected_shutdown_epoch
    with db.transaction() as conn:
        if changed(): return []
        conn.execute("INSERT OR REPLACE INTO system_state(key,value) VALUES('shutdown_requested','0')")
    results = []
    for row in db.query("SELECT id FROM runs WHERE phase='recovering' AND clock_version=1 AND resume_on_startup=1"):
        if changed(): break
        try:
            result = await controller.control(row['id'], 'resume', None, 'startup-' + uuid.uuid4().hex)
            results.append({'run_id': row['id'], **result})
        except Exception as exc:
            results.append({'run_id': row['id'], 'status': 'unknown', 'error': type(exc).__name__})
            db.append_event(row['id'], 'controller', 'run.recovery_pending', {'error': type(exc).__name__})
    return results
