"""Independent reconciliation for newly uncertain v4 creates, plus durable advice."""
from __future__ import annotations
import asyncio
import json
import logging
from . import compute, db, power

ACTIVE: dict[str, asyncio.Task] = {}
ADVICE_ACTIVE: dict[str, asyncio.Task] = {}
log = logging.getLogger(__name__)

async def _recover(run_id):
    worker = asyncio.create_task(asyncio.to_thread(compute.reconcile, run_id, allow_retry=True))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        # Cancelling an asyncio waiter cannot stop its native worker thread.
        # Keep registration until that thread has actually returned.
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if worker.done() and not worker.cancelled():
            worker.exception()
        raise

def _start(controller, run_id):
    task = ACTIVE.get(run_id)
    if task is None:
        task = asyncio.create_task(_recover(run_id))
        ACTIVE[run_id] = task
        def finished(done):
            if ACTIVE.get(run_id) is done:
                ACTIVE.pop(run_id, None)
            if not done.cancelled() and done.exception() is not None:
                log.error('Job reconciliation failed for %s: %s', run_id, type(done.exception()).__name__)
            elif controller is not None:
                controller.notify_run_change(run_id)
        task.add_done_callback(finished)
    return task

async def reconcile(run_id, controller=None):
    """All asynchronous retry-capable entrypoints share a tracked worker."""
    return await asyncio.shield(_start(controller, run_id))

async def advance(controller) -> None:
    if power.shutdown_requested():
        return
    for row in db.query("SELECT DISTINCT j.run_id FROM compute_jobs j JOIN runs r ON r.id=j.run_id "
                        "WHERE r.phase='running' AND j.status='unknown' AND j.concurrency_released=1 "
                        "AND json_extract(j.receipt_json,'$.transport')='bohr_v4'"):
        rid = row['run_id']
        _start(controller, rid)
    for event in db.query("SELECT e.* FROM events e JOIN runs r ON r.id=e.run_id WHERE "
                         "e.type='job.sandbox_fallback_advice' AND r.phase='running' "
                         "AND NOT EXISTS (SELECT 1 FROM system_state s WHERE s.key='job_advice:'||e.run_id||':'||e.seq)"):
        key = f"job_advice:{event['run_id']}:{event['seq']}"
        if key not in ADVICE_ACTIVE:
            ADVICE_ACTIVE[key] = asyncio.create_task(_deliver_advice(controller, dict(event), key))

async def _deliver_advice(controller, event, key):
    try:
        data = json.loads(event['payload'])
        gid = await controller._request_executor_repair(event['run_id'], event['trial_id'],
            stage='job_create', code='CONSECUTIVE_CREATE_FAILURES',
            detail=data['advice'] + '\n真实创建失败事实：' + json.dumps(data, ensure_ascii=False),
            event_seq=event['seq'], failure_details=data)
        if gid:
            db.execute('INSERT OR IGNORE INTO system_state(key,value) VALUES(?,?)',
                       (key, gid))
    except Exception:
        log.exception('Job fallback advice delivery failed for %s', event['run_id'])
    finally:
        ADVICE_ACTIVE.pop(key, None)

async def drain() -> None:
    """Do not cancel to_thread work: observe actual create completion before exit."""
    if ACTIVE or ADVICE_ACTIVE:
        await asyncio.gather(*(asyncio.shield(task) for task in list(ACTIVE.values()) + list(ADVICE_ACTIVE.values())), return_exceptions=True)
