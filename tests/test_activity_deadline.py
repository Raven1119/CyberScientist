"""Live heartbeats and native calls must obey the current activity grant."""
import asyncio
import json
import time
from threading import Event

import pytest
from fastapi.testclient import TestClient

from cyberscientist import api, collab, config, db, run_clock, resource_coordinator
from cyberscientist.brains.base import BrainEvent, SessionRef
from test_power import run


def near_deadline():
    ctl, rid = run()
    db.execute('UPDATE runs SET clock_version=1,active_elapsed_seconds=3599.92 WHERE id=?', (rid,))
    run_clock.start(rid)
    return ctl, rid


def test_remaining_time_reads_live_heartbeat_instead_of_old_snapshot(monkeypatch):
    ctl, rid = run()
    run_clock.start(rid, 1000)
    snapshot = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    for now in (1020, 1040, 1060): run_clock.heartbeat(now)
    monkeypatch.setattr(run_clock.time, 'time', lambda: 1060)
    assert ctl._run_seconds_remaining(snapshot) == 3540
    assert not db.query_one("SELECT 1 FROM events WHERE type='run.offline_gap'")


async def test_signal_rpc_wait_is_cancelled_at_activity_deadline(monkeypatch):
    ctl, rid = near_deadline(); cancelled = asyncio.Event(); sent = []
    async def rpc(*args, **kwargs):
        try:
            await asyncio.sleep(5)
            sent.append('late side effect')
        finally: cancelled.set()
    monkeypatch.setattr(ctl, '_handle_signal', rpc)
    await asyncio.wait_for(ctl._handle_signal_with_deadline({'type': 'fixture'}, rid, asyncio.Queue()), 1)
    assert cancelled.is_set() and not sent
    row = db.query_one('SELECT phase,pending_end_reason FROM runs WHERE id=?', (rid,))
    assert tuple(row) == ('pausing', 'authorization_expired')
    assert db.query_one("SELECT COUNT(*) FROM events WHERE type='run.time_limit'")[0] == 1


async def test_explicit_extended_grant_keeps_inflight_signal_authorized(monkeypatch):
    ctl, rid = near_deadline(); done = []
    async def rpc(*args, **kwargs):
        await asyncio.sleep(.12); done.append(True)
    async def extend():
        await asyncio.sleep(.02)
        db.execute('UPDATE authorizations SET max_run_minutes=61 WHERE run_id=?', (rid,))
    monkeypatch.setattr(ctl, '_handle_signal', rpc)
    await asyncio.gather(extend(), ctl._handle_signal_with_deadline({}, rid, asyncio.Queue()))
    assert done and db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))[0] == 'running'


class HangingBrain:
    def __init__(self, receipt='accepted', close_fails=False):
        self.turn = None; self.cancelled_turn = None; self.closed = False
        self.receipt = receipt; self.close_fails = close_fails; self.late = asyncio.Event()

    async def open(self, spec):
        return SessionRef('fixture', 'original')

    async def review(self, session, packet):
        self.turn = 'exact-native-turn'
        try:
            await self.late.wait()
            yield BrainEvent('review_result', {'result': {'schema_version': 1,
                'message_type': 'review_result', 'frame_id': packet['frame_id'],
                'disposition': 'intervene', 'private_note_md': '', 'watchlist': [],
                'guidance': {'kind': 'submit', 'intent': 'continue', 'text_md': 'late',
                             'reason_md': 'late', 'evidence_refs': []}}})
        finally: self.turn = None

    async def cancel(self, session):
        assert self.turn == 'exact-native-turn'
        self.cancelled_turn = self.turn
        self.late.set()  # Race a late model response against interruption.
        await asyncio.sleep(0)
        return {'status': self.receipt}

    async def close(self, session):
        if self.close_fails: raise RuntimeError('close unconfirmed')
        self.closed = True


@pytest.mark.parametrize('receipt,close_fails', [('accepted', False), ('unknown', False), ('unknown', True)])
async def test_review_expiry_interrupts_exact_turn_before_cancellation_without_late_submit(receipt, close_fails):
    ctl, rid = near_deadline()
    with db.transaction() as conn:
        req_id = collab._enqueue_request_tx(conn, rid, source='requested', blocking=False, trigger='manual')
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (req_id,))
    brain = HangingBrain(receipt, close_fails)
    expired = await asyncio.wait_for(ctl._review_with_deadline(rid, req, brain, SessionRef('fixture', 'original')), 1)
    assert expired and brain.cancelled_turn == 'exact-native-turn' and brain.turn is None
    assert brain.closed == (not close_fails)
    assert not db.query('SELECT * FROM submissions') and not db.query('SELECT * FROM guidance')
    assert db.query_one('SELECT status FROM review_requests WHERE id=?', (req_id,))[0] == 'obsolete'
    event = db.query_one("SELECT payload FROM events WHERE type='brain.interrupt_requested'")
    assert json.loads(event[0])['receipt']['status'] == receipt
    assert bool(resource_coordinator.close_unknowns()) == close_fails


def test_heartbeat_keeps_running_while_sandbox_expiry_worker_is_blocked(monkeypatch):
    ctl, rid = run()
    db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
    entered = Event(); release = Event(); now = [1000.0]
    def blocked():
        entered.set(); assert release.wait(5)
    monkeypatch.setattr(api.sandboxes, 'expire_due', blocked)
    monkeypatch.setattr(api, 'CLOCK_HEARTBEAT_SECONDS', .005)
    monkeypatch.setattr(run_clock.time, 'time', lambda: now[0])
    with TestClient(api.create_app()) as client:
        try:
            assert entered.wait(1)
            db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
            run_clock.start(rid, now[0])
            for tick in (1020.0, 1040.0, 1060.0):
                now[0] = tick
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    if db.query_one('SELECT clock_heartbeat_at FROM runs WHERE id=?', (rid,))[0] == tick: break
                    time.sleep(.005)
                else: pytest.fail('clock blocked behind remote sandbox work')
            row = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
            assert run_clock.elapsed(row, 1060) == 60
            assert not db.query_one("SELECT 1 FROM events WHERE type='run.offline_gap'")
        finally:
            release.set()
            db.execute("UPDATE runs SET phase='finished' WHERE id=?", (rid,))


@pytest.mark.parametrize('lifecycle', [False, True])
async def test_configured_timeout_rejects_late_review_and_decision(monkeypatch, lifecycle):
    ctl, rid = run(); run_clock.start(rid)
    with db.transaction() as conn:
        req_id = collab._enqueue_request_tx(conn, rid,
            source='lifecycle' if lifecycle else 'requested', blocking=False, trigger='manual')
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (req_id,))
    settings = config.load_settings()
    settings['run_defaults']['brain_review_timeout_seconds'] = .02
    monkeypatch.setattr(config, 'load_settings', lambda: settings)
    applied = []
    async def apply(*args): applied.append(True)
    monkeypatch.setattr(ctl, '_apply_decision', apply)
    class LateDecisionBrain(HangingBrain):
        async def review(self, session, packet):
            if not lifecycle:
                async for event in super().review(session, packet): yield event
                return
            self.turn = 'exact-native-turn'
            try:
                await self.late.wait()
                yield BrainEvent('decision', {'decision': {'actions': [{'op': 'start_trial'}]}})
            finally: self.turn = None
    brain = LateDecisionBrain()
    assert not await ctl._review_with_deadline(rid, req, brain, SessionRef('fixture', 'original'))
    assert db.query_one('SELECT status FROM review_requests WHERE id=?', (req_id,))[0] == 'error'
    assert brain.closed and not applied
    assert not db.query('SELECT * FROM submissions') and not db.query('SELECT * FROM guidance')
    assert not db.query('SELECT * FROM trials')


@pytest.mark.parametrize('close_fails', [False, True])
async def test_manual_pause_unknown_interrupt_closes_before_resume(monkeypatch, close_fails):
    from cyberscientist.controller import ControllerError
    ctl, rid = run(); run_clock.start(rid)
    ctl._signals[rid] = asyncio.Queue()
    with db.transaction() as conn:
        req_id = collab._enqueue_request_tx(conn, rid, source='requested', blocking=False, trigger='manual')
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (req_id,))
    brain = HangingBrain('unknown', close_fails)
    reviewing = asyncio.create_task(ctl._review_with_deadline(rid, req, brain, SessionRef('fixture', 'original')))
    while brain.turn is None: await asyncio.sleep(.001)
    await ctl.control(rid, 'pause', None, 'manual-pause')
    db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,)); run_clock.freeze(rid)
    assert not await asyncio.wait_for(reviewing, 2)
    assert brain.cancelled_turn and brain.turn is None
    if close_fails:
        with pytest.raises(ControllerError, match='停止仍在核对'):
            await ctl.control(rid, 'resume', None, 'unsafe-resume')
        assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))[0] == 'paused'
    else:
        assert brain.closed and ctl._brain_instances[rid] is None
        await ctl.control(rid, 'resume', None, 'safe-resume')
        assert not brain.turn  # An old closed instance cannot launch a new review.


@pytest.mark.parametrize('retry_close,prime_close_fails', [(False, False), (True, False), (False, True)])
async def test_main_loop_expiry_drains_delayed_interrupt_despite_repeated_worker_cancel(monkeypatch, retry_close, prime_close_fails):
    from types import SimpleNamespace
    from cyberscientist import maintenance
    ctl, rid = run()
    db.execute('UPDATE runs SET clock_version=1,active_elapsed_seconds=3599.8 WHERE id=?', (rid,))
    run_clock.start(rid)
    with db.transaction() as conn:
        req_id = collab._enqueue_request_tx(conn, rid, source='requested', blocking=False, trigger='manual')
    interrupted = asyncio.Event(); release = asyncio.Event()
    class SlowBrain(HangingBrain):
        close_attempts = 0
        async def close(self, session):
            self.close_attempts += 1
            if retry_close and self.close_attempts == 1:
                raise RuntimeError('first close unknown')
            await super().close(session)
        async def cancel(self, session):
            assert self.turn == 'exact-native-turn'
            self.cancelled_turn = self.turn; interrupted.set()
            await release.wait()
            self.late.set()
            return {'status': 'unknown'}
    class IdlePrime:
        async def start(self, spec): return 'executor-original'
        async def events(self, sid):
            await asyncio.Event().wait()
            yield {}
        async def abort(self, sid): return SimpleNamespace(status='confirmed', detail='fixture stopped')
        async def close(self, sid):
            if prime_close_fails: raise RuntimeError('executor close remains unknown')
    brain = SlowBrain()
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: brain)
    monkeypatch.setattr(ctl, '_make_prime', lambda settings: IdlePrime())
    monkeypatch.setattr(ctl, '_enqueue_lifecycle', lambda *args, **kwargs: None)
    monkeypatch.setattr(maintenance, 'queue_end', lambda *args: None)
    queue = asyncio.Queue(); ctl._signals[rid] = queue
    main = asyncio.create_task(ctl._run_loop(rid, queue)); ctl._tasks[rid] = main
    try:
        await asyncio.wait_for(interrupted.wait(), 2)
        worker = ctl._review_tasks[rid]
        for _ in range(100):
            if worker.cancelling(): break
            await asyncio.sleep(.005)
        else: pytest.fail('main loop did not cancel its worker during expiry cleanup')
        worker.cancel(); await asyncio.sleep(0)
        assert brain.turn == 'exact-native-turn' and not brain.closed
        assert resource_coordinator.auxiliary_tasks() and not main.done()
        release.set()
        await asyncio.wait_for(main, 2)
        assert brain.closed and brain.turn is None
        assert bool(resource_coordinator.close_unknowns()) == prime_close_fails
        assert bool(db.query_one("SELECT 1 FROM events WHERE type='brain.close_unknown'")) == retry_close
        assert not resource_coordinator.auxiliary_tasks() and not ctl._tasks
        assert db.query_one("SELECT COUNT(*) FROM events WHERE type='run.time_limit'")[0] == 1
        assert db.query_one('SELECT phase,end_reason FROM runs WHERE id=?', (rid,))[:] == ('finished', 'authorization_expired')
        assert not db.query('SELECT * FROM guidance') and not db.query('SELECT * FROM submissions')
        assert db.query_one('SELECT status FROM review_requests WHERE id=?', (req_id,))[0] == 'obsolete'
        from cyberscientist import power
        assert (await power.safe_shutdown(ctl, timeout=.01))['can_shutdown'] == (not prime_close_fails)
    finally:
        release.set()
        if not main.done(): main.cancel()
        await asyncio.gather(main, return_exceptions=True)


@pytest.mark.parametrize('status', ['pending', 'error', 'obsolete'])
def test_transactional_review_acceptance_rejects_nonrunning_request(status):
    from test_collaboration import _guidance, _review_result
    ctl, rid = run()
    with db.transaction() as conn:
        req_id = collab._enqueue_request_tx(conn, rid, source='requested', blocking=False, trigger='manual')
        conn.execute('UPDATE review_requests SET status=? WHERE id=?', (status, req_id))
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (req_id,))
    ctl._apply_review_result(rid, req, 'requested', {'frame_id': 'stale'},
        _review_result('stale', 'intervene', _guidance(kind='submit')))
    assert db.query_one('SELECT status FROM review_requests WHERE id=?', (req_id,))[0] == status
    assert not db.query('SELECT * FROM guidance') and not db.query('SELECT * FROM submissions')


async def test_review_first_expiry_during_signal_does_not_retry_unknown_close_on_stale_wake(monkeypatch):
    from types import SimpleNamespace
    from cyberscientist import maintenance
    ctl, rid = near_deadline()
    with db.transaction() as conn:
        collab._enqueue_request_tx(conn, rid, source='requested', blocking=False, trigger='manual')
    review_interrupt = asyncio.Event(); first_close = asyncio.Event(); signal_cancelled = asyncio.Event()
    class Brain(HangingBrain):
        async def cancel(self, session):
            review_interrupt.set()
            return await super().cancel(session)
    class Executor:
        closes = 0
        async def start(self, spec): return 'original-executor'
        async def events(self, sid):
            await asyncio.Event().wait()
            yield {}
        async def abort(self, sid): return SimpleNamespace(status='accepted', detail='not terminal')
        async def close(self, sid):
            self.closes += 1
            if self.closes == 1:
                first_close.set()
                raise RuntimeError('first executor close unknown')
    original_wait = ctl._wait_for_active_work
    async def review_first(run_id, task, timeout=None):
        if timeout is None: await review_interrupt.wait()
        return await original_wait(run_id, task, timeout)
    original_signal = ctl._handle_signal
    async def blocked_signal(signal, *args, **kwargs):
        if signal['type'] != 'fixture_block':
            return await original_signal(signal, *args, **kwargs)
        try: await asyncio.Event().wait()
        finally: signal_cancelled.set()
    brain = Brain(); executor = Executor()
    monkeypatch.setattr(ctl, '_make_brain', lambda _: brain)
    monkeypatch.setattr(ctl, '_make_prime', lambda _: executor)
    monkeypatch.setattr(ctl, '_enqueue_lifecycle', lambda *args, **kwargs: None)
    monkeypatch.setattr(ctl, '_wait_for_active_work', review_first)
    monkeypatch.setattr(ctl, '_handle_signal', blocked_signal)
    monkeypatch.setattr(maintenance, 'queue_end', lambda *args: None)
    queue = asyncio.Queue(); ctl._signals[rid] = queue
    await queue.put({'type': 'fixture_block'})
    main = asyncio.create_task(ctl._run_loop(rid, queue)); ctl._tasks[rid] = main
    try:
        await asyncio.wait_for(first_close.wait(), 2)
        await asyncio.sleep(.05)
        assert signal_cancelled.is_set() and executor.closes == 1
        assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))[0] == 'pausing'
        await queue.put({'type': 'prime_event', 'event': {'type': 'run.aborted', 'detail': 'native terminal'}})
        await asyncio.wait_for(main, 2)
        assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))[0] == 'finished'
        assert not resource_coordinator.close_unknowns()
    finally:
        if not main.done(): main.cancel()
        await asyncio.gather(main, return_exceptions=True)
