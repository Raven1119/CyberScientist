"""Controller admission failures return to the existing native executor outbox."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from cyberscientist import collab, db, local_scoring, mailboxes
from cyberscientist.controller import RunController
from test_collaboration import FakeExecutor, _decision
from test_final_candidate_integrity import _run_with_scorer, _score


def test_repeated_finish_failure_reopens_same_trial_for_executor(monkeypatch):
    rid, tid, *_ = _run_with_scorer()
    before = dict(db.query_one('SELECT * FROM runs WHERE id=?', (rid,)))
    for number in range(3):
        db.execute("INSERT INTO review_requests(id,run_id,source,blocking,status,trigger,created_at,updated_at)"
                   " VALUES(?,?,'lifecycle',0,'done','finish_rejected',?,?)",
                   (f'old-{number}', rid, db.utcnow(), db.utcnow()))
    def failed(*args, **kwargs):
        raise local_scoring.LocalScoreError('INVALID_COMMAND', 'command timeout exceeds remaining sandbox time')
    monkeypatch.setattr(local_scoring, 'score_candidate', failed)
    executor = FakeExecutor()
    controller = RunController()
    controller._prime_instances[rid] = executor
    controller._prime_sessions[rid] = 'native-session'
    asyncio.run(controller._apply_decision(rid, _decision([
        {'op': 'finish', 'reason': 'freeze result'}], rid=rid), {}, None, None))
    run = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    assert run['phase'] == 'running'
    assert run['current_trial_id'] == tid
    assert all(run[key] == before[key] for key in ('started_at', 'authorization_id', 'config_snapshot'))
    assert db.query_one('SELECT status FROM trials WHERE id=?', (tid,))['status'] == 'active'
    guidance = db.query_one("SELECT * FROM guidance WHERE run_id=? AND source='controller'", (rid,))
    assert guidance['status'] == 'sent'
    assert 'INVALID_COMMAND' in guidance['text_md']
    assert '系统修复反馈' in executor.prompts[0][1]
    assert controller.supervision_status(rid)['guidance'][0]['source'] == 'controller'
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='executor.repair_requested'", (rid,))
    assert db.query_one('SELECT 1 FROM compute_jobs WHERE run_id=?', (rid,)) is None
    assert db.query_one('SELECT 1 FROM submissions WHERE run_id=?', (rid,)) is None


def _controller(rid, busy=False):
    controller = RunController()
    executor = FakeExecutor()
    controller._prime_instances[rid] = executor
    controller._prime_sessions[rid] = 'native-session'
    controller._executor_busy[rid] = busy
    return controller, executor


def _failure(rid):
    return db.append_event(rid, 'controller', 'submission.auto_failed',
                           {'code': 'INVALID_PACKAGE'})['seq']


def test_busy_executor_receives_one_repair_at_checkpoint():
    rid, tid, *_ = _run_with_scorer()
    controller, executor = _controller(rid, busy=True)
    first = _failure(rid)
    for _ in range(2):
        asyncio.run(controller._request_executor_repair(rid, tid, stage='submission',
                    code='INVALID_PACKAGE', detail='missing artifact', event_seq=first))
    assert not executor.prompts
    with db.transaction() as conn:
        delivered = collab.deliver_via_checkpoint_return(conn, rid, tid)
        assert len(delivered) == 1 and delivered[0]['source'] == 'controller'
        assert not collab.deliver_via_checkpoint_return(conn, rid, tid)
    assert len(db.query('SELECT id FROM guidance WHERE run_id=?', (rid,))) == 1


@pytest.mark.parametrize('restriction', ['expired', 'paused', 'gate_closed', 'unauthorized', 'wrong_trial'])
def test_repair_never_overrides_original_grant_or_user_pause(restriction):
    rid, tid, *_ = _run_with_scorer()
    controller, executor = _controller(rid)
    if restriction == 'expired':
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        db.execute('UPDATE runs SET started_at=? WHERE id=?', (old, rid))
    elif restriction == 'paused':
        db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
    elif restriction == 'gate_closed':
        db.execute("UPDATE runs SET gate='yielding' WHERE id=?", (rid,))
    elif restriction == 'unauthorized':
        db.execute("UPDATE runs SET mode='connected' WHERE id=?", (rid,))
        db.execute('UPDATE authorizations SET allow_model_calls=0 WHERE run_id=?', (rid,))
    else:
        tid = 'other-trial'
    before = dict(db.query_one('SELECT * FROM runs WHERE id=?', (rid,)))
    assert asyncio.run(controller._request_executor_repair(rid, tid, stage='submission',
                      code='INVALID_PACKAGE', detail='missing artifact', event_seq=_failure(rid))) is None
    assert not executor.prompts
    assert not db.query('SELECT id FROM guidance WHERE run_id=?', (rid,))
    assert dict(db.query_one('SELECT * FROM runs WHERE id=?', (rid,))) == before


def test_unknown_delivery_is_not_prompted_again():
    from cyberscientist.prime import ActionReceipt
    rid, tid, *_ = _run_with_scorer()
    controller, executor = _controller(rid)
    async def unknown(session_id, text):
        executor.prompts.append((session_id, text))
        return ActionReceipt(status='unknown', detail='lost native reply')
    executor.prompt = unknown
    for _ in range(2):
        asyncio.run(controller._request_executor_repair(rid, tid, stage='submission',
                    code='INVALID_PACKAGE', detail='missing artifact', event_seq=_failure(rid)))
    assert len(executor.prompts) == 1
    assert db.query_one('SELECT status FROM guidance WHERE run_id=?', (rid,))['status'] == 'unknown'
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'running'


def test_queued_repair_cannot_start_prompt_after_deadline():
    rid, tid, *_ = _run_with_scorer()
    controller, executor = _controller(rid, busy=True)
    asyncio.run(controller._request_executor_repair(rid, tid, stage='submission',
        code='INVALID_PACKAGE', detail='missing artifact', event_seq=_failure(rid)))
    db.execute('UPDATE runs SET started_at=? WHERE id=?',
               ((datetime.now(timezone.utc) - timedelta(days=3)).isoformat(), rid))
    controller._executor_busy[rid] = False
    asyncio.run(controller._deliver_queued_guidance(rid))
    assert not executor.prompts
    assert db.query_one('SELECT status FROM guidance WHERE run_id=?', (rid,))['status'] == 'queued'


def test_acknowledged_repair_can_return_a_later_failure_to_executor():
    rid, tid, *_ = _run_with_scorer()
    controller, executor = _controller(rid)
    first = asyncio.run(controller._request_executor_repair(rid, tid, stage='submission',
        code='INVALID_PACKAGE', detail='missing artifact', event_seq=_failure(rid)))
    db.execute("UPDATE guidance SET status='acknowledged' WHERE id=?", (first,))
    controller._executor_busy[rid] = False
    second = asyncio.run(controller._request_executor_repair(rid, tid, stage='submission',
        code='INVALID_TRACE', detail='new admission failure', event_seq=_failure(rid)))
    assert first != second and len(executor.prompts) == 2


def test_executor_repair_then_finish_succeeds_without_new_trial(monkeypatch):
    rid, tid, _, files, manifest = _run_with_scorer()
    controller, executor = _controller(rid)
    action = _decision([{'op': 'finish', 'reason': 'seal repaired result'}], rid=rid)
    def failed(*a, **k):
        raise local_scoring.LocalScoreError('INVALID_PACKAGE', 'missing artifact')
    monkeypatch.setattr(local_scoring, 'score_candidate', failed)
    asyncio.run(controller._apply_decision(rid, action, {}, None, None))
    gid = db.query_one('SELECT id FROM guidance WHERE run_id=?', (rid,))['id']
    db.execute("UPDATE guidance SET status='applied' WHERE id=?", (gid,))
    db.execute("UPDATE trials SET status='done' WHERE id=?", (tid,))
    candidate = _score(rid, tid, files, manifest, 'repaired-candidate', 11, 13)
    monkeypatch.setattr(local_scoring, 'score_candidate', lambda *a, **k: candidate)
    asyncio.run(controller._apply_decision(rid, action, {}, None, None))
    run = db.query_one('SELECT phase,current_trial_id FROM runs WHERE id=?', (rid,))
    assert run['phase'] == 'eval_scoring' and run['current_trial_id'] == tid
    assert len(db.query('SELECT id FROM trials WHERE run_id=?', (rid,))) == 1
    assert len(executor.prompts) == 1


@pytest.mark.parametrize('unknown', [False, True])
def test_submission_failure_returns_facts_without_resubmitting(monkeypatch, unknown):
    rid, tid, *_ = _run_with_scorer()
    controller, executor = _controller(rid)
    with db.transaction() as conn:
        gid = collab.create_guidance(conn, rid, source='requested', target_trial_id=tid,
            review_request_id=None, frame_id=None, state_version=0, evidence_revision=0, shadow_epoch=0,
            g={'kind': 'submit', 'intent': 'continue', 'text_md': 'submit', 'reason_md': 'test',
               'expected_change_md': '', 'revisit_when_md': ''})
    calls = []
    def failed(*a, **k):
        calls.append(1)
        if unknown:
            return {'id': 'existing-reservation', 'status': 'unknown', 'error': 'platform reply lost'}
        raise mailboxes.MailboxError('INVALID_PACKAGE', 'missing artifact')
    monkeypatch.setattr(mailboxes, 'submit_experiment', failed)
    asyncio.run(controller._execute_submit(rid, gid, tid))
    assert calls == [1]
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'running'
    repair = db.query_one("SELECT * FROM guidance WHERE source='controller' AND run_id=?", (rid,))
    assert repair['status'] == 'sent' and '不重复创建或提交' in repair['text_md']
    assert ('unknown' if unknown else 'INVALID_PACKAGE') in repair['text_md']
    assert len(executor.prompts) == 1


def test_repair_feedback_and_failure_event_redact_credentials(monkeypatch):
    rid, tid, *_ = _run_with_scorer()
    controller, executor = _controller(rid)
    def failed(*a, **k):
        raise local_scoring.LocalScoreError('INVALID_PACKAGE', 'Authorization: Bearer private-test-secret')
    monkeypatch.setattr(local_scoring, 'score_candidate', failed)
    asyncio.run(controller._apply_decision(rid, _decision([
        {'op': 'finish', 'reason': 'seal'}], rid=rid), {}, None, None))
    assert 'private-test-secret' not in executor.prompts[0][1]
    assert 'private-test-secret' not in json.dumps([dict(r) for r in db.query(
        'SELECT payload FROM events WHERE run_id=?', (rid,))])


def test_final_candidate_is_frozen_before_remote_scoring_failure(monkeypatch):
    import hashlib
    from cyberscientist import config, evaluations
    rid, tid, *_ = _run_with_scorer()
    captured = []
    def failed(run, preflight, *a, **k):
        captured.append(preflight['sealed_bytes'])
        raise local_scoring.LocalScoreError('SCORE_EXECUTION_UNKNOWN', 'remote create response lost')
    monkeypatch.setattr(evaluations, 'score_preflight', failed)
    with pytest.raises(local_scoring.LocalScoreError, match='response lost'):
        local_scoring.score_candidate(rid)
    attempts = config.WORKSPACE_DIR / 'runs' / rid / 'final_candidate' / 'attempts'
    stages = list(attempts.iterdir())
    assert len(stages) == 1
    stage = stages[0]
    assert (stage / 'sealed_package.zip').read_bytes() == captured[0]
    descriptor = json.loads((stage / 'grading_inputs.json').read_text())
    for name, expected in descriptor['files'].items():
        data = (stage / name).read_bytes()
        assert expected == {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    assert not db.query('SELECT id FROM local_scores WHERE run_id=?', (rid,))
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='local_score.inputs_staged'", (rid,))


def test_frozen_failed_score_input_cannot_be_overwritten(tmp_path):
    from cyberscientist import package_seal
    from test_trace_narrative import _zip
    rid, tid, _, files, manifest = _run_with_scorer()
    sealed, _ = package_seal.seal(_zip(files), rid, tid, 0)
    assert local_scoring._stage_score_inputs(tmp_path, sealed, manifest)
    assert not local_scoring._stage_score_inputs(tmp_path, sealed, manifest)
    frozen = (tmp_path / 'sealed_package.zip').read_bytes()
    with pytest.raises(local_scoring.LocalScoreError, match='输入已变化'):
        local_scoring._stage_score_inputs(tmp_path, sealed + b'changed', manifest)
    assert (tmp_path / 'sealed_package.zip').read_bytes() == frozen
