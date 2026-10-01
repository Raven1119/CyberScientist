"""Fake evaluation Runs exercise the persistent queue without models or Bohrium."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from cyberscientist import cli, compute, config, db, environment_facts, evaluations, experience_context, mailboxes, sandboxes
from cyberscientist import local_scoring
from cyberscientist.controller import RunController


MODELS = {role: {'runtime': 'codex', 'model_id': 'gpt-6-sol',
                 'reasoning_effort': 'xhigh'} for role in ('brain', 'executor')}


def _challenge(cid: str) -> None:
    db.execute('INSERT INTO challenges(id,platform_challenge_id,origin,title,content,'
               'content_hash,imported_at) VALUES(?,?,?,?,?,?,?)',
               (cid, cid, 'fixture', cid, 'fixture task', cid, db.utcnow()))


def _catalog(monkeypatch, tmp_path) -> None:
    path = tmp_path / 'catalog.json'
    path.write_text(json.dumps({'challenges': [
        {'challenge_id': cid, 'platform_challenge_id': cid,
         'tier': 'fast', 'included': True,
         'science_scorer': {'status': 'spec_validated'}}
        for cid in ('eval_a', 'eval_b')]}))
    monkeypatch.setattr(evaluations, 'CATALOG', path)
    for cid in ('eval_a', 'eval_b'):
        _challenge(cid)
    monkeypatch.setattr(experience_context, 'select', lambda *args, **kwargs: [])
    monkeypatch.setattr(evaluations.skills, 'effective_for', lambda *args, **kwargs: [])


class FakeController:
    def __init__(self):
        self.real = RunController()
        self.starts = []
        self.resumes = []
        self.resume_operations = []

    def create_run(self, *args, **kwargs):
        return self.real.create_run(*args, **kwargs)

    def authorize(self, *args, **kwargs):
        return self.real.authorize(*args, **kwargs)

    async def start_async(self, run_id):
        self.starts.append(run_id)
        trial = 'trial_' + run_id
        db.execute('INSERT INTO trials(id,run_id,goal,success_check,created_at)'
                   ' VALUES(?,?,?,?,?)', (trial, run_id, 'fake', 'fake', db.utcnow()))
        db.execute("UPDATE runs SET phase='eval_scoring',gate='open',current_trial_id=?,"
                   'started_at=? WHERE id=?', (trial, db.utcnow(), run_id))

    async def control(self, run_id, action, text, operation_id):
        self.resumes.append(run_id)
        self.resume_operations.append(operation_id)
        db.execute("UPDATE runs SET phase='eval_scoring' WHERE id=?", (run_id,))

    def _finalize_run(self, run_id, reason):
        db.execute("UPDATE runs SET phase='finished',ended_at=?,end_reason=? WHERE id=?",
                   (db.utcnow(), reason, run_id))


def _fake_score(run_id: str, result_id: str):
    run = db.query_one('SELECT challenge_id,current_trial_id FROM runs WHERE id=?', (run_id,))
    score = 100.0 if run['challenge_id'] == 'eval_a' else 40.0
    db.execute('INSERT INTO local_scores(id,challenge_id,run_id,trial_id,package_sha256,'
               'science_artifact_hashes_json,manifest_science_sha256,science_score,'
               'trace_prediction_json,scorer_version,scorer_file_hashes_json,feature_version,'
               'model_version,sandbox_operation_id,created_at)'
               ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               ('ls_' + result_id, run['challenge_id'], run_id, run['current_trial_id'],
                'package', '{}', 'manifest', score, '{}', 'fake-v1', '{}', 'v1', 'v1',
                'eval-score-' + result_id, db.utcnow()))
    db.append_event(run_id, 'controller', 'evaluation.trace_diagnosed',
                    {'status': 'ready', 'checklist_score': 75,
                     'qualified_codes': ['N09_NO_EXECUTION_EVIDENCE'], 'advisory_cap': 49})
    return 'scored', None


def test_paused_infrastructure_failure_expires_original_grant_and_releases_queue(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    evaluation = evaluations.create_evaluation('fast', 2, 'bounded-fixture')
    first = db.query_one('SELECT * FROM eval_results WHERE eval_id=? ORDER BY rowid', (evaluation['id'],))
    controller = FakeController()
    snapshot = json.loads(db.query_one('SELECT config_json FROM eval_runs WHERE id=?',
                                     (evaluation['id'],))['config_json'])
    marker = evaluations._marker(snapshot, snapshot['entries'][0], first['id'])
    marker['eval_id'] = evaluation['id']
    run = controller.create_run(first['challenge_id'], 'connected', False, eval_mode=marker)
    rid = run['id']
    controller.authorize(rid, 'connected', True, 0, 60, 0, '', max_jobs=2,
                         max_sandboxes=2, max_sandbox_minutes=60)
    db.execute("UPDATE runs SET phase='paused',started_at=? WHERE id=?",
               ((datetime.now(timezone.utc) - timedelta(minutes=59)).isoformat(), rid))
    db.execute("UPDATE eval_results SET run_id=?,status='paused' WHERE id=?", (rid, first['id']))
    db.append_event(rid, 'brain', 'brain.action_rejected',
                    {'op': 'finish', 'error_code': 'SCORE_EXECUTION_UNKNOWN'})
    terminated = []
    async def control(run_id, action, text, operation_id):
        assert action == 'terminate'
        terminated.append((run_id, operation_id))
        db.execute("UPDATE runs SET phase='cancelled',ended_at=? WHERE id=?", (db.utcnow(), run_id))
        return {'status': 'confirmed'}
    monkeypatch.setattr(controller, 'control', control)
    def score_other(run_id, result_id):
        assert run_id != rid, 'no late scorer for the expired Run'
        return _fake_score(run_id, result_id)
    monkeypatch.setattr(evaluations, '_score_run', score_other)
    # Before expiry a science/infrastructure pause is preserved.
    asyncio.run(evaluations.advance(controller))
    assert terminated == []
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'paused'
    starts_before_expiry = len(controller.starts)
    db.execute('UPDATE runs SET started_at=? WHERE id=?',
               ((datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat(), rid))
    asyncio.run(evaluations.advance(controller))
    assert terminated == [(rid, f'eval-expire-{rid}')]
    row = db.query_one('SELECT status,result_json FROM eval_results WHERE id=?', (first['id'],))
    result = json.loads(row['result_json'])
    assert row['status'] == 'failed'
    assert result['science_score'] is None and result['science_status'] == 'budget_exhausted'
    assert result['job_count'] == 0 and result['sandbox_minutes'] == 0
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='evaluation.budget_exhausted'", (rid,))
    assert len(controller.starts) > starts_before_expiry  # The expired Run releases capacity.
    asyncio.run(evaluations.advance(controller))
    assert len(terminated) == 1


def test_two_by_two_evaluation_and_resume(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(evaluations, '_score_run', _fake_score)
    settings = config.load_settings()
    settings['run_defaults']['max_active_runs'] = 2
    config.save_settings(settings)
    created = evaluations.create_evaluation('fast', 2, 'fake')
    assert len(created['results']) == 4
    assert evaluations.create_evaluation('fast', 2, 'fake')['id'] == created['id']
    first = FakeController()
    asyncio.run(evaluations.advance(first))
    assert len(first.starts) == 2  # capacity; no fourth Run created yet
    first_run = db.query_one('SELECT * FROM runs WHERE id=?', (first.starts[0],))
    packet = first.real._lifecycle_packet(first_run, 'trial_done', sparse=True)
    assert packet['authorization']['max_sandboxes'] == 2
    assert packet['authorization']['max_sandbox_minutes'] == 60
    assert packet['authorization']['allow_sandbox_gpu'] is False
    assert packet['evaluation_handoff'] == {
        'platform_submission_allowed': False, 'experience_write_allowed': False,
        'local_scoring_after_finish': True,
        'agent_scoring_sandbox_required_for_finish': False}
    second = FakeController()       # process restart: persisted queue, new controller
    for _ in range(4):
        asyncio.run(evaluations.advance(second))
    result = evaluations.report(created['id'])
    assert result['evaluation']['status'] == 'complete'
    assert result['suite_summary']['completed_count'] == 4
    assert result['suite_summary']['science_mean'] == 70
    assert all(row['result']['scorer_version'] == 'fake-v1' for row in result['evaluation']['results'])
    assert all(row['result']['display_interval']['upper'] == row['result']['science_score'] * .49
               for row in result['evaluation']['results'])
    assert len(first.starts + second.starts) == 4
    assert len({row['run_id'] for row in result['evaluation']['results']}) == 4
    assert db.query_one('SELECT 1 FROM submissions') is None
    assert db.query_one('SELECT 1 FROM experience_revisions') is None
    markdown, structured = evaluations.write_report(created['id'])
    assert 'eval_a' in markdown.read_text() and structured.is_file()
    row = db.query_one('SELECT id,result_json FROM eval_results WHERE eval_id=? ORDER BY rowid LIMIT 1',
                       (created['id'],))
    missing = json.loads(row['result_json'])
    missing.update(science_score=None, science_status='unavailable',
                   science_reason='missing answer artifact',
                   display_interval=evaluations.display_interval(None, None))
    db.execute('UPDATE eval_results SET result_json=? WHERE id=?', (json.dumps(missing), row['id']))
    markdown, _ = evaluations.write_report(created['id'])
    text = markdown.read_text()
    assert 'missing answer artifact' in text
    assert 'Observed suite science mean:' in text and '(scored 3/4)' in text
    assert '| unknown |' in text


def test_report_refreshes_sandbox_minutes_after_cleanup(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(evaluations, '_score_run', _fake_score)
    created = evaluations.create_evaluation('fast', 1, 'cleanup-cost')
    controller = FakeController()
    for _ in range(4):
        asyncio.run(evaluations.advance(controller))
    rid = evaluations.get_evaluation(created['id'])['results'][0]['run_id']
    trial_id = db.query_one('SELECT current_trial_id FROM runs WHERE id=?', (rid,))['current_trial_id']
    started = datetime.now(timezone.utc) - timedelta(minutes=3)
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,'
               'request_json,status,created_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
               ('eval-cost-check', rid, trial_id, 'sb-cost', '{"cpu":"4c8g"}', 'deleting',
                started.isoformat(), (started + timedelta(minutes=10)).isoformat(), db.utcnow()))
    before = evaluations.report(created['id'])['evaluation']['results'][0]['result']
    assert before['sandbox_minutes_status'] == 'lower_bound_pending_cleanup'
    assert before['sandbox_minutes'] >= 3
    stopped = started + timedelta(minutes=3, seconds=30)
    db.execute("UPDATE compute_sandboxes SET status='deleted',deleted_at=?,updated_at=?"
               ' WHERE operation_id=?', (stopped.isoformat(), db.utcnow(), 'eval-cost-check'))
    after = evaluations.report(created['id'])['evaluation']['results'][0]['result']
    assert after['sandbox_minutes_status'] == 'confirmed'
    assert after['sandbox_minutes'] == 3.5
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,request_json,'
               'status,created_at,expires_at,updated_at,deleted_at)'
               ' VALUES(?,?,?,?,?,?,?,?,?)',
               ('local-dns-denied', rid, trial_id, '{}', 'failed', started.isoformat(),
                db.utcnow(), db.utcnow(), started.isoformat()))
    assert evaluations.report(created['id'])['evaluation']['results'][0]['result'][
        'sandbox_minutes'] == 3.5
    from cyberscientist import sandbox_costs
    sandbox_costs.record_prices(rid, {'ok': True, 'stdout': json.dumps({'ok': True,
        'data': {'items': [{'class': 'cpu', 'cpu': '4', 'memory': '8Gi',
                           'sku_id': 4690, 'sku_name': 'c4_m8_cpu', 'price': '0.80 RMB/h'}]}})})
    markdown, structured = evaluations.write_report(created['id'])
    assert 'sandbox_estimate=0.0467 CNY' in markdown.read_text()
    assert 'not a bill' in markdown.read_text()
    report = json.loads(structured.read_text())
    assert report['evaluation']['results'][0]['result']['bohrium_cost_details'][
        'sandbox_estimate']['amount'] == '0.0467'


def test_evaluation_price_query_is_off_loop_and_local_finalization_is_offline(monkeypatch, tmp_path):
    import threading
    from cyberscientist import sandbox_costs
    _catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(evaluations, '_score_run', _fake_score)
    main_thread = threading.get_ident()
    queried = []
    def refresh(rid):
        assert threading.get_ident() != main_thread
        queried.append(rid)
        return {'status': 'unknown'}
    monkeypatch.setattr(sandbox_costs, 'refresh', refresh)
    created = evaluations.create_evaluation('fast', 1, 'price-io')
    controller = FakeController()
    for _ in range(4):
        asyncio.run(evaluations.advance(controller))
    assert len(queried) == 2
    row = evaluations.get_evaluation(created['id'])['results'][0]
    monkeypatch.setattr(sandbox_costs, 'refresh', lambda *args: pytest.fail('local finalize is offline'))
    evaluations._finish_result(row['id'], row['run_id'])


def test_report_distinguishes_job_reservations_from_platform_jobs(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(evaluations, '_score_run', _fake_score)
    created = evaluations.create_evaluation('fast', 1, 'job-accounting')
    controller = FakeController()
    for _ in range(4):
        asyncio.run(evaluations.advance(controller))
    result = evaluations.get_evaluation(created['id'])['results'][0]
    rid = result['run_id']
    trial = db.query_one('SELECT current_trial_id FROM runs WHERE id=?', (rid,))['current_trial_id']
    for operation, platform_id, status in (
        ('local-failed', None, 'not_started'),
        ('ambiguous-upload', None, 'unknown'),
        ('pending-dispatch', None, 'submitting'),
        ('accepted', 12345, 'Finished'),
    ):
        db.execute('INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,'
                   'spec_json,input_directory,platform_job_id,status,created_at,updated_at)'
                   ' VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (operation, rid, trial, 'hash', '{}', 'input', platform_id, status,
                    db.utcnow(), db.utcnow()))
    refreshed = evaluations.report(created['id'])['evaluation']['results'][0]['result']
    assert refreshed['job_count'] == 1
    assert refreshed['job_unknown_count'] == 2
    markdown, _ = evaluations.write_report(created['id'])
    assert '1 (+2 unknown)' in markdown.read_text()


def test_recovering_run_resumes_once(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(evaluations, '_score_run', _fake_score)
    created = evaluations.create_evaluation('fast', 1)
    first = FakeController()
    asyncio.run(evaluations.advance(first))
    rid = created['results'][0]['run_id'] or first.starts[0]
    db.execute("UPDATE runs SET phase='recovering' WHERE id=?", (rid,))
    second = FakeController()
    asyncio.run(evaluations.advance(second))
    assert rid in second.resumes
    assert rid not in second.starts


def test_recovery_uses_new_operation_id_after_each_backend_restart(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    created = evaluations.create_evaluation('fast', 1)
    first = FakeController()
    asyncio.run(evaluations.advance(first))
    rid = created['results'][0]['run_id'] or first.starts[0]
    second = FakeController()
    db.execute("UPDATE runs SET phase='recovering' WHERE id=?", (rid,))
    db.append_event(rid, 'controller', 'run.needs_recovery', {'from_phase': 'running'})
    asyncio.run(evaluations.advance(second))
    first_operation = second.resume_operations[0]
    db.execute("UPDATE runs SET phase='recovering' WHERE id=?", (rid,))
    db.append_event(rid, 'controller', 'run.needs_recovery', {'from_phase': 'running'})
    asyncio.run(evaluations.advance(second))
    assert second.resume_operations[1] != first_operation


def test_one_post_finish_score_retry_reuses_sealed_run(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    created = evaluations.create_evaluation('fast', 1)
    controller = FakeController()
    asyncio.run(evaluations.advance(controller))
    result = evaluations.get_evaluation(created['id'])['results'][0]
    rid, result_id = result['run_id'], result['id']
    db.execute("UPDATE runs SET phase='finished',ended_at=? WHERE id=?", (db.utcnow(), rid))
    evaluations._finish_result(result_id, rid, scoring_status='unavailable',
                               scoring_reason='TLS handshake timeout')
    sealed = config.WORKSPACE_DIR / 'runs' / rid / 'eval' / 'sealed_package.zip'
    sealed.parent.mkdir(parents=True)
    sealed.write_bytes(b'frozen-science-package')
    assert not evaluations.retry_authorized(rid, result_id)
    observed = []
    def repaired_score(run_id, score_result_id, *, retry=False):
        observed.append((run_id, score_result_id, retry))
        assert evaluations.retry_authorized(rid, result_id)
        trial = db.query_one('SELECT current_trial_id FROM runs WHERE id=?', (rid,))['current_trial_id']
        db.execute('INSERT INTO local_scores(id,challenge_id,run_id,trial_id,package_sha256,'
                   'science_artifact_hashes_json,manifest_science_sha256,science_score,'
                   'trace_prediction_json,scorer_version,scorer_file_hashes_json,feature_version,'
                   'model_version,sandbox_operation_id,created_at)'
                   ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('ls_retry', 'eval_a', rid, trial, 'frozen', '{}', 'frozen', 80,
                    '{}', 'fixture', '{}', 'v1', 'v1', 'eval-score-' + result_id + '-retry',
                    db.utcnow()))
        return 'scored', None
    monkeypatch.setattr(evaluations, '_score_run', repaired_score)
    monkeypatch.setattr(evaluations.sandboxes, 'cleanup_run', lambda _: [])
    updated = evaluations.retry_unavailable_score(result_id)
    item = next(x for x in updated['results'] if x['id'] == result_id)
    assert item['result']['science_score'] == 80
    assert observed == [(rid, result_id, True)]
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'finished'
    assert not evaluations.retry_authorized(rid, result_id)
    with pytest.raises(evaluations.EvaluationError, match='已确认'):
        evaluations.retry_unavailable_score(result_id)


def test_completed_matchgate_score_can_be_recovered_from_pinned_receipt(monkeypatch):
    _catalog(monkeypatch, config.WORKSPACE_DIR)
    created = evaluations.create_evaluation('fast', 1, 'receipt-recovery')
    asyncio.run(evaluations.advance(FakeController()))
    result = evaluations.get_evaluation(created['id'])['results'][0]
    rid, result_id, cid = result['run_id'], result['id'], result['challenge_id']
    monkeypatch.setattr(evaluations, 'MATCHGATE_ID', cid)
    trial = db.query_one('SELECT current_trial_id FROM runs WHERE id=?', (rid,))['current_trial_id']
    scorer_dir = config.WORKSPACE_DIR / 'challenges' / cid / 'scorer'
    scorer_dir.mkdir(parents=True)
    (scorer_dir / 'scorer.json').write_text(json.dumps({
        'entrypoint': 'score.py', 'image': 'fixture/score:v1',
        'version': 'test', 'contract_version': 1}))
    (scorer_dir / 'score.py').write_text('print("fixture")\n')
    (scorer_dir / 'requirements.txt').write_text('numpy==2.2.6\n')
    manifest = local_scoring.scorer_manifest(cid)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('arm_manifest.json', json.dumps({
            'arm_version': '1.1', 'entrypoint': 'run.py', 'trace': 'traces/trace.jsonl',
            'execution': {'log_path': 'run.log', 'artifacts': [
                {'path': 'outputs/submission.json'}]}}))
        archive.writestr('run.py', 'print(1)\n')
        archive.writestr('run.log', 'ok\n')
        archive.writestr('outputs/submission.json', '{}')
        archive.writestr('traces/trace.jsonl', json.dumps({
            'step_type': 'observation', 'title': 'seen',
            'timestamp': '2026-09-30T00:00:00Z'}) + '\n')
    sealed = buffer.getvalue()
    sealed_dir = config.WORKSPACE_DIR / 'runs' / rid / 'eval'
    sealed_dir.mkdir(parents=True)
    (sealed_dir / 'sealed_package.zip').write_bytes(sealed)
    db.append_event(rid, 'controller', 'evaluation.sealed',
                    {'sealed_package_sha256': hashlib.sha256(sealed).hexdigest()})
    db.execute("UPDATE runs SET phase='finished',ended_at=? WHERE id=?", (db.utcnow(), rid))
    evaluations._finish_result(result_id, rid, scoring_status='unavailable',
                               scoring_reason='dependency log mixed with score JSON')
    stage = (config.WORKSPACE_DIR / 'runs' / rid / 'trials' / trial
             / 'local_scorer' / ('eval-score-' + result_id))
    stage.mkdir(parents=True)
    (stage / 'science_package.zip').write_bytes(local_scoring._science_package(sealed))
    (stage / 'scorer.zip').write_bytes(local_scoring._archive(manifest['files']))
    resource = b'public-fixture'
    (stage / 'public_resource.zip').write_bytes(resource)
    monkeypatch.setattr(evaluations, 'MATCHGATE_RESOURCE_SHA256',
                        hashlib.sha256(resource).hexdigest())
    sb_op = 'eval-scorer-' + result_id
    created_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,'
               'request_json,status,created_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
               (sb_op, rid, trial, 'sb-confirmed', json.dumps({'image': manifest['image']}),
                'active', created_at, db.utcnow(), db.utcnow()))
    score = {'score': 42, 'components': {}, 'confidence': 'medium',
             'notes': 'synthetic', 'scorer_version': manifest['scorer_version']}
    event = db.append_event(rid, 'controller', 'sandbox.exec_completed', {
        'operation_id': 'eval-score-' + result_id + '-run',
        'sandbox_id': 'sb-confirmed', 'status': 'completed', 'exit_code': 0,
        'command': ('cd /tmp/test && python3 -m pip install -r scorer/requirements.txt && '
                    'CS_SCORER_VERSION=' + manifest['scorer_version']
                    + ' python3 scorer/score.py package.zip'),
        'output': 'Successfully installed numpy\n' + json.dumps(score) + '\n'})
    db.execute("UPDATE compute_sandboxes SET status='deleted',deleted_at=?,updated_at=?"
               ' WHERE operation_id=?', (db.utcnow(), db.utcnow(), sb_op))
    (stage / 'scorer.zip').write_bytes(b'changed')
    with pytest.raises(evaluations.EvaluationError, match='冻结包不符'):
        evaluations.recover_matchgate_score_receipt(result_id)
    (stage / 'scorer.zip').write_bytes(local_scoring._archive(manifest['files']))
    updated = evaluations.recover_matchgate_score_receipt(result_id)
    recovered = next(x for x in updated['results'] if x['id'] == result_id)
    assert recovered['result']['science_score'] == 42
    assert recovered['result']['science_status'] == 'scored'
    assert db.query_one('SELECT science_score FROM local_scores WHERE sandbox_operation_id=?',
                        ('eval-score-' + result_id,))['science_score'] == 42
    proof = db.query_one("SELECT payload FROM events WHERE run_id=?"
                         " AND type='evaluation.local_score_recovered'", (rid,))
    assert json.loads(proof['payload'])['source_event_seq'] == event['seq']


def test_finished_run_sandbox_only_opens_for_recorded_score_retry(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    settings = config.load_settings()
    settings['bohrium']['project_id'] = 88474
    config.save_settings(settings)
    created = evaluations.create_evaluation('fast', 1)
    asyncio.run(evaluations.advance(FakeController()))
    result = evaluations.get_evaluation(created['id'])['results'][0]
    rid, result_id = result['run_id'], result['id']
    db.execute("UPDATE runs SET phase='finished',ended_at=? WHERE id=?", (db.utcnow(), rid))
    evaluations._finish_result(result_id, rid, scoring_status='unavailable',
                               scoring_reason='network failure')
    operation = 'eval-scorer-' + result_id + '-retry'
    calls = []
    def native(args, **kwargs):
        calls.append(args)
        return {'ok': True, 'exit_code': 0,
                'stdout': json.dumps({'data': {'sandboxID': 'sb-retry',
                                               'status_name': 'running'}}), 'stderr': ''}
    monkeypatch.setattr(compute, '_native', native)
    with pytest.raises(compute.ComputeError, match='Run 未运行'):
        sandboxes.create(rid, operation, {'timeout': 60})
    assert not calls
    db.append_event(rid, 'controller', 'evaluation.score_retry_started',
                    {'result_id': result_id})
    response = sandboxes.create(rid, operation, {'timeout': 60})
    assert response['status'] == 'active'
    assert len(calls) == 1 and calls[0][:2] == ['sandbox', 'create']


@pytest.mark.parametrize(('cap', 'expected'), [
    (20, (0, 0)), (29, (0, 0)), (30, (0, 24)), (69, (0, 55.2)),
    (None, (24, 80)),
])
def test_display_interval_branches(cap, expected):
    result = evaluations.display_interval(80, cap)
    assert (result['lower'], result['upper']) == expected
    if cap is None:
        assert result['basis'] == '裁判部分未复刻'
    assert evaluations.display_interval(None, cap)['lower'] is None


def test_eval_submission_and_experience_writes_are_rejected():
    _challenge('eval_guard')
    controller = RunController()
    run = controller.create_run('eval_guard', 'connected', eval_mode={
        'enabled': True, 'models': MODELS,
        'experience_manifests': {'brain': [], 'executor': [], 'both': []}})
    rid = run['id']
    with pytest.raises(mailboxes.MailboxError) as error:
        mailboxes.submit_experiment(rid, None, None, 'fake-op')
    assert error.value.code == 'EVAL_SUBMISSION_FORBIDDEN'
    controller._apply_experience_proposal(rid, 'fake-decision',
                                           {'body_md': 'must not write'})
    with db.transaction() as conn:
        experience_context.adopt_tx(conn, rid, None,
                                    [{'context_id': 'none'}], 'brain', 'fake')
    event = {'run_id': rid, 'source': 'controller', 'type': 'image_facts.observed'}
    assert environment_facts.record('fake-key', 'fake', {}, event)['status'] == 'rejected'
    assert db.query_one('SELECT 1 FROM experience_revisions') is None
    assert db.query_one('SELECT 1 FROM submissions WHERE run_id=?', (rid,)) is None
    kinds = {row['type'] for row in db.query('SELECT type FROM events WHERE run_id=?', (rid,))}
    assert 'evaluation.submission_rejected' in kinds
    assert 'evaluation.experience_write_rejected' in kinds


async def test_eval_finish_enters_scoring_with_open_gate(monkeypatch):
    _challenge('eval_finish')
    controller = RunController()
    rid = controller.create_run('eval_finish', 'connected', eval_mode={
        'enabled': True, 'models': MODELS,
        'experience_manifests': {'brain': [], 'executor': [], 'both': []}})['id']
    controller.authorize(rid, 'connected', True, 0, 60, 0, 'fake')
    trial = 'trial_eval_finish'
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,status,created_at)'
               ' VALUES(?,?,?,?,?,?)',
               (trial, rid, 'fake', 'fake', 'reported_complete', db.utcnow()))
    db.execute("UPDATE runs SET phase='running',gate='waiting_brain',current_trial_id=?,"
               'started_at=? WHERE id=?', (trial, db.utcnow(), rid))
    monkeypatch.setattr(controller, '_make_prime', lambda _: object())
    decision = {'schema_version': 2, 'decision_id': 'finish-eval', 'run_id': rid,
                'observed_state_version': 0, 'summary': 'done', 'evidence_refs': [],
                'experience_proposals': [], 'actions': [{
                    'op': 'finish', 'reason': 'done',
                    'objective_assessment': {'status': 'partial', 'evidence_refs': [],
                                             'remaining_md': ''}}]}
    await controller._apply_decision(rid, decision, {}, None, None)
    run = db.query_one('SELECT phase,gate FROM runs WHERE id=?', (rid,))
    assert (run['phase'], run['gate']) == ('eval_scoring', 'open')
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='evaluation.scoring_started'",
                        (rid,))


def test_science_score_still_runs_when_trace_admission_blocks(monkeypatch):
    _challenge('eval_soft_admission')
    controller = RunController()
    rid = controller.create_run('eval_soft_admission', 'connected', eval_mode={
        'enabled': True, 'models': MODELS,
        'experience_manifests': {'brain': [], 'executor': [], 'both': []}})['id']
    trial = 'trial_soft_admission'
    now = db.utcnow()
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,created_at)'
               ' VALUES(?,?,?,?,?)', (trial, rid, 'fake', 'fake', now))
    db.execute("UPDATE runs SET phase='eval_scoring',gate='open',current_trial_id=? WHERE id=?",
               (trial, rid))
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,'
               'request_json,status,created_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
               ('sx_soft', rid, trial, 'sandbox_soft', '{"image":"fake-image"}',
                'active', now, now, now))
    monkeypatch.setattr(mailboxes, 'preflight_submission', lambda *args, **kwargs: {
        'sealed_bytes': b'fake-sealed', 'sealed_package_sha256': 'fake-sha',
        'data_inputs': {'evidence_class': 'proxy'},
        'trace_diagnostics': {'status': 'ready', 'checklist_score': 0,
                              'advisories': [], 'advisory_cap': None},
        'error_code': 'TRACE_ADMISSION_BLOCKED'})
    monkeypatch.setattr(evaluations.local_scoring, 'scorer_manifest', lambda _: {'image': 'fake-image'})
    monkeypatch.setattr(local_scoring, 'reuse_score', lambda *args: None)
    seen = []
    def fake_evaluate(*args, **kwargs):
        seen.append(kwargs['preflight']['error_code'])
        return {'id': 'ls_fake', 'science_score': 80}
    monkeypatch.setattr(evaluations.local_scoring, 'evaluate', fake_evaluate)
    assert evaluations._score_run(rid, 'er_soft') == ('scored', None)
    assert seen == [None]
    event = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='evaluation.sealed'",
                         (rid,))
    assert json.loads(event['payload'])['admission_error_code'] == 'TRACE_ADMISSION_BLOCKED'


def test_eval_tables_are_idempotent():
    db.init_db()
    db.init_db()
    assert db.query_one("SELECT name FROM sqlite_master WHERE name='eval_results'")


def test_public_challenge_404_uses_hash_pinned_snapshot(monkeypatch):
    from cyberscientist import mailbox_platform
    slug = 'lab-bench-figqa-figqa-0177-b4156bee'
    monkeypatch.setattr(mailbox_platform, 'fetch_platform_challenge',
                        lambda *args: (_ for _ in ()).throw(mailbox_platform.PlatformError('HTTP 404')))
    evaluations._ensure_challenge({'challenge_id': slug, 'platform_challenge_id': slug,
                                    'title': 'FigQA-0177'})
    row = db.query_one('SELECT content_hash,platform_snapshot_json,origin FROM challenges WHERE id=?',
                       (slug,))
    assert row['content_hash'] == '8a86ca4ee7dc49a2dab1d420911ecbee8a16650cd18c9a915a57beda31dd820b'
    assert json.loads(row['platform_snapshot_json'])['source_kind'] == 'pinned_historical_public_snapshot'
    assert row['origin'].startswith('pinned-public-snapshot://')


def test_public_challenge_fallback_rejects_changed_snapshot(monkeypatch, tmp_path):
    from cyberscientist import mailbox_platform
    slug = 'lab-bench-figqa-figqa-0177-b4156bee'
    source = evaluations.PUBLIC_SNAPSHOTS
    (tmp_path / 'manifest.json').write_bytes((source / 'manifest.json').read_bytes())
    (tmp_path / (slug + '.json')).write_bytes((source / (slug + '.json')).read_bytes() + b' ')
    monkeypatch.setattr(evaluations, 'PUBLIC_SNAPSHOTS', tmp_path)
    monkeypatch.setattr(mailbox_platform, 'fetch_platform_challenge',
                        lambda *args: (_ for _ in ()).throw(mailbox_platform.PlatformError('HTTP 404')))
    with pytest.raises(evaluations.EvaluationError, match='哈希不符'):
        evaluations._ensure_challenge({'challenge_id': slug, 'platform_challenge_id': slug,
                                        'title': 'FigQA-0177'})
    assert db.query_one('SELECT 1 FROM challenges WHERE id=?', (slug,)) is None


def test_figqa_unsupported_answer_path_is_caught_before_scoring(monkeypatch):
    challenge = 'lab-bench-figqa-figqa-0177-b4156bee'
    _challenge(challenge)

    def bundle(paths):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for path in paths:
                archive.writestr(path, '[ANSWER]B[/ANSWER]')
        return stream.getvalue()

    with pytest.raises(evaluations.EvaluationError, match='根目录 answer.txt'):
        evaluations._check_scorer_input_path(challenge, bundle(['answer.txt']))
    evaluations._check_scorer_input_path(challenge, bundle(['outputs/answer.txt']))
    with pytest.raises(evaluations.EvaluationError, match='缺少或重复'):
        evaluations._check_scorer_input_path(
            challenge, bundle(['outputs/answer.txt', 'nested/outputs/answer.txt']))
    rid, trial_id = 'run_figqa_path', 'trial_figqa_path'
    db.execute('INSERT INTO runs(id,challenge_id,mode,phase,config_snapshot,created_at,'
               'current_trial_id) VALUES(?,?,?,?,?,?,?)',
               (rid, challenge, 'connected', 'eval_scoring', '{}', db.utcnow(), trial_id))
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,created_at)'
               ' VALUES(?,?,?,?,?)', (trial_id, rid, 'answer', 'file', db.utcnow()))
    sealed = bundle(['answer.txt'])
    monkeypatch.setattr(evaluations.mailboxes, 'preflight_submission', lambda *a, **k: {
        'sealed_bytes': sealed, 'sealed_package_sha256': hashlib.sha256(sealed).hexdigest(),
        'trace_diagnostics': {'status': 'unavailable', 'advisories': []},
        'error_code': None, 'data_inputs': {'evidence_class': 'not_applicable'}})
    monkeypatch.setattr(evaluations.sandboxes, 'create',
                        lambda *a, **k: pytest.fail('unsupported input must not rent a sandbox'))
    status, reason = evaluations._score_run(rid, 'er_figqa_path')
    assert status == 'unavailable' and '根目录 answer.txt' in reason
    assert db.query_one('SELECT 1 FROM compute_sandboxes WHERE run_id=?', (rid,)) is None


def test_one_command_eval_launches_existing_backend(monkeypatch, capsys):
    seen = []

    class Response:
        def __init__(self, body):
            self.body = body
        def close(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    def urlopen(request, timeout):
        seen.append(request)
        return Response(None) if isinstance(request, str) else Response({'id': 'eval_fake',
                                                                          'status': 'running'})

    monkeypatch.setattr(cli.urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(cli.json, 'load', lambda response: response.body)
    monkeypatch.setattr(sys, 'argv', ['cyberscientist', 'eval', 'run', '--suite', 'fast',
                                     '--repeats', '2'])
    cli.main()
    assert len(seen) == 2
    assert json.loads(seen[1].data)['suite'] == 'fast'
    assert 'eval_fake' in capsys.readouterr().out
