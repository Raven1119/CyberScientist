"""One client call waits on bounded, read-only server observations."""
import asyncio
import time
from functools import partial
from . import compute, db, power, resource_coordinator


async def wait(run_id, operation_id, timeout=1200, *, kind):
    if type(timeout) is not int or not 0 <= timeout <= 1200:
        raise compute.ComputeError('INVALID_TIMEOUT', 'wait上限1200秒')
    compute._run(run_id)
    table = 'compute_jobs' if kind == 'job' else 'compute_sandbox_operations'
    row = db.query_one('SELECT * FROM '+table+' WHERE run_id=? AND operation_id=?', (run_id,operation_id))
    if not row or kind == 'sandbox' and row['action'] != 'background':
        raise compute.ComputeError('NOT_OWNED', '等待操作不属于本Run')
    owner = db.query_one('SELECT trial_id FROM compute_sandboxes WHERE run_id=? AND sandbox_id=?', (run_id,row['sandbox_id'])) if kind == 'sandbox' else row
    trial_id = owner['trial_id'] if owner else None
    started = time.monotonic(); deadline = started + timeout
    terminal_states = ('Finished','Failed','Stopped','not_started') if kind == 'job' else ('completed','failed','cancelled')
    result = {'operation_id': operation_id, 'status': row['status']}
    db.append_event(run_id,'controller','server.wait_started',{'kind':kind,'operation_id':operation_id,'timeout_seconds':timeout},trial_id=trial_id)
    async def observe():
        if kind == 'job':
            await resource_coordinator.tracked_thread(partial(compute.reconcile,allow_retry=False),run_id,owner_prefix='job-wait-read-')
            return dict(db.query_one('SELECT * FROM compute_jobs WHERE run_id=? AND operation_id=?',(run_id,operation_id)))
        from . import sandbox_background
        return await resource_coordinator.tracked_thread(sandbox_background.poll,run_id,operation_id,owner_prefix='sandbox-wait-read-')
    while result['status'] not in terminal_states and deadline > time.monotonic() and not power.shutdown_requested():
        try:
            result = await asyncio.wait_for(observe(), timeout=max(.001,deadline-time.monotonic()))
        except asyncio.TimeoutError:
            break
        except compute.ComputeError:
            raise
        except Exception as exc:
            result = {'operation_id':operation_id,'status':'unknown','observation_error':type(exc).__name__}
        if result['status'] in terminal_states:
            break
        await asyncio.sleep(min(3,max(0,deadline-time.monotonic())))
    terminal = result['status'] in terminal_states
    summary = {'kind':kind,'operation_id':operation_id,'terminal':terminal,
               'timed_out':not terminal and not power.shutdown_requested(),
               'wait_status':'terminal' if terminal else 'interrupted' if power.shutdown_requested() else 'timeout',
               'waited_seconds':round(time.monotonic()-started,3),'status':result['status']}
    db.append_event(run_id,'controller','server.wait_finished',summary,trial_id=trial_id)
    return result | summary
