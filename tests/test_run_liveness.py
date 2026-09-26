"""W2 liveness and throttling, using only local fake native runtimes."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

from cyberscientist import config, db, model_limits
from cyberscientist.brains.base import BrainEvent, SessionRef
from cyberscientist.brains.demo import DemoBrain
from cyberscientist.controller import PHASES, RunController
from cyberscientist.prime import ActionReceipt, DemoPrime
from cyberscientist.prime.codex_exec import CodexExecutor, _Session as CodexSession
from cyberscientist.prime.kimi_acp import KimiExecutor, _Session as KimiSession


def _run() -> tuple[RunController, str]:
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo)"
               " VALUES('w2','demo://local','W2','fixture','hash',?,1)", (db.utcnow(),))
    controller = RunController()
    rid = controller.create_run('w2')['id']
    controller.authorize(rid, 'demo', False, 0, 30, 0, None)
    old = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (old, rid))
    return controller, rid


def _types(rid: str) -> list[str]:
    return [row['type'] for row in db.query('SELECT type FROM events WHERE run_id=? ORDER BY seq',
                                             (rid,))]


async def test_silent_run_wakes_fake_brain_and_recovers_with_trial():
    controller, rid = _run()
    assert controller.check_liveness(rid) == 'review_queued'
    req = db.query_one("SELECT * FROM review_requests WHERE run_id=?"
                       " AND trigger='stall_detected'", (rid,))
    assert req and req['status'] == 'pending'
    assert controller._lifecycle_packet(controller._require_run(rid), 'stall_detected')[
        'stall_diagnosis']['jobs'] == []
    prime = DemoPrime()
    sid = await prime.start({'run_id': rid})
    controller._prime_instances[rid] = prime
    controller._prime_sessions[rid] = sid
    controller._start_pump[rid] = lambda: None
    await controller._run_one_review(rid, req, DemoBrain(),
                                     SessionRef('demo', 'brain-w2'))
    assert db.query_one("SELECT status FROM review_requests WHERE id=?", (req['id'],))[
        'status'] == 'done'
    assert db.query_one("SELECT COUNT(*) AS n FROM trials WHERE run_id=?", (rid,))['n'] == 1
    assert _types(rid).index('run.stall_detected') < _types(rid).index('trial.created')
    assert controller.check_liveness(rid) is None
    await prime.close(sid)


def test_second_stall_pauses_and_long_job_suppresses_watchdog():
    controller, rid = _run()
    now = time.time()
    assert controller.check_liveness(rid, now=now) == 'review_queued'
    db.execute("UPDATE review_requests SET status='done' WHERE run_id=?", (rid,))
    assert controller.check_liveness(rid, now=now + 301) == 'needs_attention'
    assert controller.run_snapshot(rid)['phase'] == 'paused'
    assert _types(rid).count('run.stall_detected') == 2
    assert _types(rid)[-1] == 'run.needs_attention'

    other, job_run = _run_another('w2-job')
    db.execute("INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,"
               "spec_json,input_directory,status,created_at,updated_at)"
               " VALUES('w2-job-op',?, 'trial','hash','{}','.', 'Running',?,?)",
               (job_run, db.utcnow(), db.utcnow()))
    assert other.check_liveness(job_run, now=time.time() + 7200) is None
    assert 'run.stall_detected' not in _types(job_run)


def test_heartbeat_usage_poll_and_repeated_job_list_do_not_mask_stall():
    controller, rid = _run()
    for kind in ('prime.execution.heartbeat', 'brain.usage.updated', 'job.observed'):
        db.append_event(rid, 'fixture', kind, {'status': 'Running'})
    db.append_event(rid, 'prime', 'prime.execution.progress',
                    {'item_id': 'job-list', 'detail': 'bohr job list'})
    assert controller.check_liveness(rid) == 'review_queued'

    other, active = _run_another('w2-progress')
    db.append_event(active, 'prime', 'prime.execution.progress',
                    {'item_id': 'tool-1', 'detail': '工具完成: 已分析输出'})
    assert other.check_liveness(active) is None


def test_session_restart_gets_one_recovery_window_without_resetting_strike():
    controller, rid = _run()
    assert controller.check_liveness(rid) == 'review_queued'
    db.execute("UPDATE review_requests SET status='error' WHERE run_id=?", (rid,))
    old = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()
    earlier = (datetime.now(timezone.utc) - timedelta(seconds=2000)).isoformat()
    db.execute("UPDATE runs SET started_at=? WHERE id=?", (earlier, rid))
    db.execute("UPDATE events SET occurred_at=? WHERE run_id=?"
               " AND type='run.stall_detected'", (old, rid))
    db.append_event(rid, 'controller', 'brain.session_restarted', {})
    assert controller.check_liveness(rid) is None
    assert _types(rid).count('run.stall_detected') == 1


def _run_another(cid: str) -> tuple[RunController, str]:
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo)"
               " VALUES(?, 'demo://local','W2','fixture','hash',?,1)", (cid, db.utcnow()))
    controller = RunController()
    rid = controller.create_run(cid)['id']
    controller.authorize(rid, 'demo', False, 0, 240, 0, None)
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (old, rid))
    return controller, rid


async def test_brain_429_three_times_then_success_does_not_spend_failed_reviews():
    controller, rid = _run()
    controller.check_liveness(rid)
    req_id = db.query_one("SELECT id FROM review_requests WHERE run_id=?", (rid,))['id']
    prime = DemoPrime()
    sid = await prime.start({'run_id': rid})
    controller._prime_instances[rid] = prime
    controller._prime_sessions[rid] = sid
    controller._start_pump[rid] = lambda: None

    class ThrottledBrain(DemoBrain):
        calls = 0

        async def review(self, session, packet):
            self.calls += 1
            if self.calls <= 3:
                yield BrainEvent('error', {'message': 'HTTP 429 rate_limit_exceeded'})
            else:
                async for event in super().review(session, packet):
                    yield event

    brain = ThrottledBrain()
    for attempt in range(3):
        req = db.query_one('SELECT * FROM review_requests WHERE id=?', (req_id,))
        await controller._run_one_review(rid, req, brain, SessionRef('demo', 'brain'))
        assert db.query_one('SELECT brain_reviews_used FROM runs WHERE id=?', (rid,))[
            'brain_reviews_used'] == 0
        assert db.query_one('SELECT status FROM review_requests WHERE id=?', (req_id,))[
            'status'] == 'pending'
        assert db.query_one("SELECT attempts FROM model_rate_limits WHERE run_id=? AND role='brain'",
                            (rid,))['attempts'] == attempt + 1
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (req_id,))
    await controller._run_one_review(rid, req, brain, SessionRef('demo', 'brain'))
    assert db.query_one('SELECT brain_reviews_used FROM runs WHERE id=?', (rid,))[
        'brain_reviews_used'] == 1
    assert _types(rid).count('model.rate_limited') == 3
    assert 'brain.error' not in _types(rid)
    assert db.query_one('SELECT 1 FROM model_rate_limits WHERE run_id=?', (rid,)) is None
    assert db.query_one('SELECT status FROM review_requests WHERE id=?', (req_id,))[
        'status'] == 'done'
    await prime.close(sid)


def test_continuous_limit_pauses_without_spending_review():
    controller, rid = _run()
    controller.check_liveness(rid)
    req_id = db.query_one('SELECT id FROM review_requests WHERE run_id=?', (rid,))['id']
    db.execute("UPDATE review_requests SET status='running' WHERE id=?", (req_id,))
    db.execute('UPDATE runs SET brain_reviews_used=1 WHERE id=?', (rid,))
    controller._record_model_limit(rid, 'brain', model_limits.RateLimit(),
                                   request_id=req_id, mode='lifecycle')
    old = (datetime.now(timezone.utc) - timedelta(seconds=3601)).isoformat()
    db.execute("UPDATE model_rate_limits SET first_at=? WHERE run_id=?", (old, rid))
    assert controller.check_liveness(rid) == 'rate_limit_attention'
    assert controller.run_snapshot(rid)['phase'] == 'paused'
    assert db.query_one('SELECT brain_reviews_used FROM runs WHERE id=?', (rid,))[
        'brain_reviews_used'] == 0
    assert _types(rid)[-1] == 'run.needs_attention'


async def test_executor_429_retries_exact_prompt_and_never_records_abort():
    controller, rid = _run()
    tid = 'w2-trial'
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at)"
               " VALUES(?,?, 'goal','check','active',?)", (tid, rid, db.utcnow()))
    db.execute('UPDATE runs SET current_trial_id=? WHERE id=?', (tid, rid))

    class Prime:
        prompts: list[str] = []

        async def state(self, session):
            return {'status': 'idle'}

        async def prompt(self, session, prompt):
            self.prompts.append(prompt)
            return ActionReceipt('accepted', 'accepted', f'op-{len(self.prompts)}')

    prime = Prime()
    controller._prime_instances[rid] = prime
    controller._prime_sessions[rid] = 'prime-session'
    controller._prime_prompts[rid] = (tid, 'original complete prompt')
    controller._start_pump[rid] = lambda: None
    controller._executor_busy[rid] = True
    for attempt in range(3):
        await controller._handle_signal(
            {'type': 'prime_event', 'event': {'type': 'model.rate_limited'}},
            rid, asyncio.Queue())
        row = db.query_one("SELECT attempts,state FROM model_rate_limits WHERE run_id=?"
                           " AND role='executor'", (rid,))
        assert row['attempts'] == attempt + 1 and row['state'] == 'waiting'
        db.execute("UPDATE model_rate_limits SET retry_at=? WHERE run_id=?"
                   " AND role='executor'", ((datetime.now(timezone.utc) -
                   timedelta(seconds=1)).isoformat(), rid))
        assert await controller.retry_limited_executor(rid) == 'retried'
    assert prime.prompts == ['original complete prompt'] * 3
    await controller._handle_signal(
        {'type': 'prime_event', 'event': {'type': 'executor.turn_completed',
                                       'stop_reason': 'completed'}},
        rid, asyncio.Queue())
    assert db.query_one('SELECT 1 FROM model_rate_limits WHERE run_id=?', (rid,)) is None
    assert _types(rid).count('model.rate_limited') == 3
    assert 'prime.run.aborted' not in _types(rid)
    assert controller.run_snapshot(rid)['phase'] == 'running'


async def test_hung_brain_session_is_restarted_after_bounded_timeout(monkeypatch):
    controller, rid = _run()
    settings = config.load_settings()
    settings['run_defaults']['brain_review_timeout_seconds'] = 1
    config.save_settings(settings)
    controller.check_liveness(rid)
    controller._review_wake[rid] = asyncio.Event()
    calls = {'opened': 0, 'closed': 0}

    class Brain(DemoBrain):
        async def open(self, spec):
            calls['opened'] += 1
            return SessionRef('demo', f"brain-{calls['opened']}")

        async def close(self, session):
            calls['closed'] += 1

        async def review(self, session, packet):
            if calls['opened'] == 0:
                await asyncio.sleep(60)
            async for event in super().review(session, packet):
                yield event

    brain = Brain()
    monkeypatch.setattr(controller, '_make_brain', lambda settings: Brain())
    prime = DemoPrime()
    sid = await prime.start({'run_id': rid})
    controller._prime_instances[rid] = prime
    controller._prime_sessions[rid] = sid
    controller._start_pump[rid] = lambda: None
    worker = asyncio.create_task(controller._review_worker(rid, brain,
                                 SessionRef('demo', 'brain-initial')))
    try:
        for _ in range(40):
            if 'brain.session_restarted' in _types(rid):
                break
            await asyncio.sleep(0.1)
        assert 'brain.session_restarted' in _types(rid)
        assert calls['closed'] >= 1 and calls['opened'] >= 1
        assert 'brain.session_retried' in _types(rid)
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await prime.close(sid)


def test_classifier_and_nonterminal_wake_policy():
    assert model_limits.classify('HTTP 429; Retry-After: 73').retry_after_seconds == 73
    assert model_limits.classify({'code': 429, 'message': 'throttled',
                                  'retry_after': 17}).retry_after_seconds == 17
    assert model_limits.classify({'code': 'rate_limit_exceeded'}) is not None
    assert model_limits.classify("{'code': 429}") is not None
    assert model_limits.classify('insufficient_quota').reason == 'quota_exhausted'
    assert model_limits.classify('额度耗尽') is not None
    assert model_limits.classify('socket disconnected') is None
    assert model_limits.classify('job id 429 not available') is None
    assert [model_limits.retry_delay(i, model_limits.RateLimit()) for i in range(1, 7)] == [
        60, 120, 240, 480, 900, 900]
    # Every nonterminal phase has an explicit human wake or a bounded timer.
    wake = {'created': 'start_async', 'running': 'watchdog',
            'pausing': 'abort_retry_30s', 'paused': 'control.resume',
            'blocked': 'start_async', 'recovering': 'control.resume'}
    assert set(PHASES) - {'finished', 'failed', 'cancelled'} == set(wake)


async def test_native_executor_adapters_preserve_429_without_abort():
    class ThrottledRpc:
        async def request(self, *args, **kwargs):
            raise RuntimeError('HTTP 429 Retry-After: 5')

    kimi = KimiExecutor(executable='/fake/kimi')
    kimi_session = KimiSession(ThrottledRpc(), 'k')
    await kimi._run_turn(kimi_session, 'prompt')
    assert await kimi_session.queue.get() == {
        'type': 'model.rate_limited', 'retry_after_seconds': 5,
        'reason': 'rate_limit'}
    assert kimi_session.queue.empty()

    codex = CodexExecutor(executable='/fake/codex')
    codex_session = CodexSession(ThrottledRpc(), 'c')
    await codex._run_turn(codex_session, 'prompt')
    assert await codex_session.queue.get() == {
        'type': 'model.rate_limited', 'retry_after_seconds': 5,
        'reason': 'rate_limit'}
    assert codex_session.queue.empty()


async def test_lost_executor_session_restarts_without_replaying_trial(monkeypatch):
    controller, rid = _run()
    closed: list[str] = []

    class Prime:
        prompts: list[str] = []

        async def start(self, spec):
            return 'new-session'

        async def close(self, session):
            closed.append(session)

        async def prompt(self, session, text):
            self.prompts.append(text)
            return ActionReceipt('accepted')

    old, new = Prime(), Prime()
    controller._prime_instances[rid] = old
    controller._prime_sessions[rid] = 'old-session'
    controller._start_pump[rid] = lambda: None
    monkeypatch.setattr(controller, '_make_prime', lambda settings: new)
    await controller._handle_signal({'type': 'prime_error', 'message': 'protocol closed'},
                                    rid, asyncio.Queue())
    assert closed == ['old-session']
    assert controller._prime_sessions[rid] == 'new-session'
    assert not old.prompts and not new.prompts
    assert 'executor.session_restarted' in _types(rid)
    assert db.query_one("SELECT trigger FROM review_requests WHERE run_id=?"
                        " ORDER BY rowid DESC LIMIT 1", (rid,))['trigger'] == 'executor_restarted'
