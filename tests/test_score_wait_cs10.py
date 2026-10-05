import asyncio
import json
import pytest
from cyberscientist import api, collab, config, db, mailboxes, maintenance, run_clock, score_wait
from cyberscientist.controller import ControllerError
from test_collaboration import _rig, _wait, _decision
from test_trace_narrative import _fixture
from test_mailboxes import _set_scored


async def test_submission_wait_stops_native_turns_and_clock_then_score_wakes_pi_for_variant(monkeypatch):
    rid, tid, *_ = _fixture()
    controller, brain, executor = _rig(False)
    monkeypatch.setattr(maintenance, 'queue_end', lambda *a: pytest.fail('waiting must not run maintenance'))
    await controller.start_async(rid)
    assert await _wait(lambda: bool(brain.calls))
    await brain.results.put({'decision': _decision([], rid=rid)})
    assert await _wait(lambda: db.query_one("SELECT 1 FROM review_requests WHERE run_id=? AND status='done'", (rid,)))
    mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, 'check', lambda *_: {'verdict': 'admitted', 'signals': {}})
    source = mailboxes.submit_experiment(rid, tid, None, 'wait-baseline', prediction_md='20')
    assert source['score_confidence'] is None
    controller.notify_run_change(rid)
    assert await _wait(lambda: rid not in controller._tasks)
    row = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    assert row['phase'] == 'waiting_score' and row['clock_active_since'] is None
    before, calls, prompts = run_clock.elapsed(row), len(brain.calls), len(executor.prompts)
    await asyncio.sleep(.15)
    assert run_clock.elapsed(db.query_one('SELECT * FROM runs WHERE id=?', (rid,))) == before
    assert len(brain.calls) == calls and len(executor.prompts) == prompts
    db.execute("UPDATE submissions SET score=20,score_status='scored',score_confidence='provisional' WHERE id=?", (source['id'],))
    controller.notify_run_change(rid); await asyncio.sleep(.05)
    assert not controller._tasks
    _set_scored(source['id'], 20)
    controller.notify_run_change(rid)
    assert await _wait(lambda: len(brain.calls) == calls + 1)
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'running'
    # A PI tool choice after score wake, using the actual capability endpoint.
    from httpx import ASGITransport, AsyncClient
    monkeypatch.setattr(api, 'controller', controller)
    monkeypatch.setattr(collab, 'validate_token', lambda _: {'role': 'brain', 'run_id': rid})
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        response = await client.post('/api/v1/tools/trace_variant', headers={'authorization': 'Bearer fixture'},
            json={'source_submission_id': source['id'], 'operation_id': 'after-score-variant',
                  'prediction_md': 'projection variant', 'projection_only': True})
    assert response.status_code == 200, response.text
    assert response.json()['variant_of'] == source['id'] and response.json()['science_artifact_match'] == 1
    assert await _wait(lambda: rid not in controller._tasks)
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'waiting_score'
    assert len([e for e in db.events_after(rid, 0) if e['type'] == 'run.score_wake']) == 1


async def test_finished_run_reopens_original_workspace_events_and_authorization_then_new_trial(monkeypatch):
    rid, original_tid, *_ = _fixture()
    controller, brain, executor = _rig(False)
    monkeypatch.setattr(maintenance, 'queue_end', lambda *a: None)
    await controller.start_async(rid)
    assert await _wait(lambda: bool(brain.calls))
    await brain.results.put({'decision': _decision([], rid=rid)})
    assert await _wait(lambda: db.query_one("SELECT 1 FROM review_requests WHERE run_id=? AND status='done'", (rid,)))
    before = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    controller._finalize_run(rid, 'original completion')
    assert await _wait(lambda: rid not in controller._tasks)
    archive = db.events_after(rid, 0)
    await controller.control(rid, 'reopen', 'continue prior workspace', 'finished-reopen')
    await controller.control(rid, 'resume', None, 'finished-resume')
    assert await _wait(lambda: len(brain.calls) >= 2)
    await brain.results.put({'decision': _decision([{'op': 'start_trial', 'goal': 'new test', 'success_check': 'fixture'}], rid=rid,
        sv=db.query_one('SELECT state_version FROM runs WHERE id=?', (rid,))['state_version'])})
    assert await _wait(lambda: len(db.query('SELECT * FROM trials WHERE run_id=?', (rid,))) == 2)
    after = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    assert before['authorization_id'] == after['authorization_id']
    assert before['config_snapshot'] == after['config_snapshot']
    assert after['current_trial_id'] != original_tid
    assert db.events_after(rid, 0)[:len(archive)] == archive
    assert (config.WORKSPACE_DIR / 'runs' / rid / 'trials' / original_tid / 'result_package.zip').exists()
    await controller.control(rid, 'terminate', None, 'close-fixture')


def test_score_wait_feature_off_keeps_old_behavior_and_historical_data():
    rid, *_ = _fixture(); settings = config.load_settings(); settings['features']['await_score'] = False; config.save_settings(settings)
    assert score_wait.enter(rid) is False
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'created'


@pytest.mark.parametrize('blocked', ['capacity', 'shutdown', 'close_unknown', 'user_pause'])
async def test_persisted_confirmed_score_scan_retries_after_temporary_block_without_repoll(monkeypatch, blocked):
    from cyberscientist import competition, resource_coordinator
    from cyberscientist.controller import RunController
    rid, tid, *_ = _fixture()
    mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, 'check', lambda *_: {'verdict': 'admitted', 'signals': {}})
    source = mailboxes.submit_experiment(rid, tid, None, 'stable-score', prediction_md='20')
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    assert score_wait.enter(rid)
    _set_scored(source['id'], 20)
    # A fresh controller only sees the persisted wait/confirmed receipt.
    restarted = RunController(); calls = []
    async def resume(run_id, action, text, op):
        calls.append((run_id, action, op))
        if blocked == 'capacity' and len(calls) == 1:
            raise resource_coordinator.ResourceWait('provider full')
        db.execute("UPDATE runs SET phase='running' WHERE id=?", (run_id,))
    monkeypatch.setattr(restarted, 'control', resume)
    if blocked == 'shutdown': db.execute("INSERT OR REPLACE INTO system_state VALUES('shutdown_requested','1')")
    if blocked == 'close_unknown': db.execute('INSERT OR REPLACE INTO system_state VALUES(?,?)', ('native_close_unknown:' + rid, '{}'))
    if blocked == 'user_pause':
        rnd = competition.import_round(['MB_CH'], mode='demo')
        db.execute('UPDATE eval_results SET run_id=?,paused=1 WHERE eval_id=?', (rid, rnd['id']))
    restarted.scan_score_waits(); await asyncio.sleep(.05)
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'waiting_score'
    db.execute("INSERT OR REPLACE INTO system_state VALUES('shutdown_requested','0')")
    db.execute('DELETE FROM system_state WHERE key=?', ('native_close_unknown:' + rid,))
    db.execute('UPDATE eval_results SET paused=0 WHERE run_id=?', (rid,))
    restarted.scan_score_waits(); await asyncio.sleep(.05)
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'running'
    assert calls[-1] == (rid, 'resume', 'score-wake-' + source['id'])


def test_old_trial_variant_does_not_mark_another_active_trial_completed(monkeypatch):
    rid, tid, *_ = _fixture(); mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, 'check', lambda *_: {'verdict': 'admitted', 'signals': {}})
    source = mailboxes.submit_experiment(rid, tid, None, 'old-science', prediction_md='20'); _set_scored(source['id'], 20)
    variant = mailboxes.submit_trace_variant(source['id'], 'old-variant', 'new trace', projection_only=True)
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at) VALUES('another',?,'unfinished','none','active',?)", (rid, db.utcnow()))
    db.execute("UPDATE runs SET phase='running',current_trial_id='another' WHERE id=?", (rid,))
    assert score_wait.enter(rid)
    assert db.query_one("SELECT status FROM trials WHERE id='another'")['status'] == 'interrupted'
    assert db.query_one('SELECT status FROM trials WHERE id=?', (tid,))['status'] == 'done'
    assert variant['trial_id'] == tid


async def test_user_pause_during_wait_cleanup_blocks_wake_until_explicit_resume(monkeypatch):
    rid, tid, *_ = _fixture(); controller, brain, executor = _rig(False)
    monkeypatch.setattr(maintenance, 'queue_end', lambda *a: pytest.fail('wait/pause cannot postreview'))
    await controller.start_async(rid)
    assert await _wait(lambda: bool(brain.calls))
    await brain.results.put({'decision': _decision([], rid=rid)})
    assert await _wait(lambda: db.query_one("SELECT 1 FROM review_requests WHERE run_id=? AND status='done'", (rid,)))
    mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, 'check', lambda *_: {'verdict': 'admitted', 'signals': {}})
    source = mailboxes.submit_experiment(rid, tid, None, 'wait-manual-pause', prediction_md='20')
    controller.notify_run_change(rid)
    await controller.control(rid, 'pause', None, 'pause-before-cleanup')
    assert await _wait(lambda: rid not in controller._tasks)
    count = len(brain.calls); _set_scored(source['id'], 20)
    controller.scan_score_waits(); await asyncio.sleep(.05)
    assert len(brain.calls) == count
    await controller.control(rid, 'resume', None, 'resume-score-wait')
    assert await _wait(lambda: len(brain.calls) == count + 1)
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'running'
    assert not db.query_one('SELECT 1 FROM system_state WHERE key=?', ('await_score:' + rid,))
    # Return to a pending score wait so teardown remains nonterminal/no maintenance.
    variant = mailboxes.submit_trace_variant(source['id'], 'finish-fixture-variant', 'projection', projection_only=True)
    controller.notify_run_change(rid)
    assert await _wait(lambda: rid not in controller._tasks)


async def test_manual_wait_pause_survives_restart_pending_resume_does_not_open_model(monkeypatch):
    from cyberscientist.controller import RunController
    rid, tid, *_ = _fixture(); mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, 'check', lambda *_: {'verdict': 'admitted', 'signals': {}})
    source = mailboxes.submit_experiment(rid, tid, None, 'restart-paused-wait', prediction_md='20')
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    assert score_wait.enter(rid)
    controller = RunController(); await controller.control(rid, 'pause', None, 'pause-wait-restart')
    fresh = RunController(); fresh.reconcile_on_startup()
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'paused'
    monkeypatch.setattr(fresh, '_make_brain', lambda _: pytest.fail('pending score cannot open model'))
    await fresh.control(rid, 'resume', None, 'resume-pending-restart')
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'waiting_score'
    fresh.scan_score_waits(); await asyncio.sleep(.05)
    assert not fresh._tasks and not fresh._score_wakes


async def test_wait_retains_unknown_native_close_handle_and_retries_before_wake(monkeypatch):
    rid, tid, *_ = _fixture(); controller, brain, executor = _rig(False)
    attempts = []
    async def close(session):
        attempts.append(session)
        if len(attempts) == 1: raise RuntimeError('close transport timeout')
    monkeypatch.setattr(executor, 'close', close)
    monkeypatch.setattr(maintenance, 'queue_end', lambda *a: pytest.fail('waiting no maintenance'))
    await controller.start_async(rid); assert await _wait(lambda: bool(brain.calls))
    await brain.results.put({'decision': _decision([], rid=rid)})
    assert await _wait(lambda: db.query_one("SELECT 1 FROM review_requests WHERE run_id=? AND status='done'", (rid,)))
    mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, 'check', lambda *_: {'verdict': 'admitted', 'signals': {}})
    source = mailboxes.submit_experiment(rid, tid, None, 'close-unknown-wait', prediction_md='20')
    controller.notify_run_change(rid); assert await _wait(lambda: rid not in controller._tasks)
    assert controller._waiting_close_handles[rid][0][0] is executor
    assert db.query_one('SELECT 1 FROM system_state WHERE key=?', ('native_close_unknown:' + rid,))
    calls = len(brain.calls); controller.scan_score_waits()
    assert await _wait(lambda: rid not in controller._waiting_close_handles)
    assert len(attempts) == 2 and len(brain.calls) == calls
    assert not db.query_one('SELECT 1 FROM system_state WHERE key=?', ('native_close_unknown:' + rid,))
