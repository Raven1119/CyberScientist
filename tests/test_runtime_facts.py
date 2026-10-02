"""Facts are observations and budget arithmetic, never scientific instructions."""
import asyncio
from datetime import datetime, timedelta, timezone
import json

from cyberscientist import db, local_scoring, runtime_environments, runtime_facts
from cyberscientist.controller import RunController
from test_collaboration import FakeExecutor, _decision
from test_final_candidate_integrity import _run_with_scorer


def _facts_fixture(monkeypatch):
    rid, tid, *_ = _run_with_scorer()
    monkeypatch.setattr(local_scoring, 'scorer_manifest', lambda cid: {
        'image': 'registry.example/public:base', 'entrypoint': 'score.py',
        'scorer_version': 'a'*64, 'runtime': {'environment_id': 'public-toolchain',
                                           'score_timeout': 600}})
    monkeypatch.setattr(runtime_environments, 'facts', lambda: [{
        'id': 'public-toolchain', 'status': 'unverified', 'image': None,
        'identity': {'toolchain_version': '2.0'}}])
    db.append_event(rid, 'controller', 'environment.public_image_catalog', {
        'items': [{'image': 'registry.example/public:older', 'identity': {'toolchain_version': '1.0'}}]})
    db.append_event(rid, 'controller', 'job.price_quote', {
        'rates': {'c4_m8_cpu': {'hourly_rate': '.32', 'currency': 'CNY', 'sku_id': 1}},
        'source': 'native public job pricing', 'observed_at': db.utcnow(),
        'source_receipt_sha256': 'b'*64})
    return rid, tid


def test_unverified_environment_and_available_observations_are_first_frame_facts(monkeypatch):
    rid, tid = _facts_fixture(monkeypatch)
    controller = RunController()
    run = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    frame = controller._lifecycle_packet(run, 'run_start', sparse=True)
    facts = frame['operating_facts']
    assert facts['environment']['status'] == 'unverified'
    assert facts['environment']['known_public_images'][0]['declared_version_match'] is False
    assert facts['environment']['network'] == {
        'job': {'status': 'unknown', 'observations': []},
        'sandbox': {'status': 'unknown', 'observations': []}}
    assert facts['cpu_prices']['job']['rates']['c4_m8_cpu']['hourly_rate'] == '.32'
    assert facts['cpu_prices']['job']['observed_at'] and facts['cpu_prices']['job']['source']
    assert facts['historical_materials']['own_local_materials_allowed'] is True
    executor = FakeExecutor()
    controller._prime_instances[rid] = executor
    controller._prime_sessions[rid] = 'existing-session'
    asyncio.run(controller._apply_decision(rid, _decision([
        {'op': 'start_trial', 'goal': 'attempt task', 'success_check': 'report observations'}], rid=rid),
        frame, None, None))
    assert len(executor.prompts) == 1
    text = executor.prompts[0][1]
    assert 'unverified' in text and 'declared_version_match' in text
    assert 'sandbox_minutes' in text and 'native public job pricing' in text


def test_remaining_time_jobs_sandbox_minutes_and_estimates_update(monkeypatch):
    rid, tid = _facts_fixture(monkeypatch)
    db.execute('UPDATE authorizations SET max_jobs=5,max_sandboxes=2,max_sandbox_minutes=60 WHERE run_id=?', (rid,))
    initial = runtime_facts.facts(rid)
    now = datetime.now(timezone.utc)
    db.execute('UPDATE runs SET started_at=? WHERE id=?', ((now-timedelta(minutes=5)).isoformat(), rid))
    db.execute("INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,spec_json,input_directory,status,created_at,updated_at)"
               " VALUES('job-unknown',?,?, 'hash', '{}','local','unknown',?,?)", (rid,tid,db.utcnow(),db.utcnow()))
    db.execute("INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,request_json,status,created_at,expires_at,updated_at)"
               " VALUES('sandbox-unknown',?,?, '{}','unknown',?,?,?)",
               (rid,tid,now.isoformat(),(now+timedelta(minutes=20)).isoformat(),now.isoformat()))
    updated = runtime_facts.facts(rid)
    assert 295 < initial['remaining']['run_seconds']-updated['remaining']['run_seconds'] < 305
    assert initial['remaining']['jobs'] == 5 and updated['remaining']['jobs'] == 4
    assert updated['remaining']['sandbox_minutes'] == 40
    assert updated['remaining']['sandbox_concurrent_slots'] == 1
    assert updated['scoring']['declared_timeout_seconds'] == 600
    assert updated['scoring']['estimated_seconds'] is None
    assert '授权时间内' in updated['scoring']['notice']
    assert updated['spent_estimates']['job']['amount'] is None
    assert updated['spent_estimates']['job']['unpriced_count'] == 1


def test_scoring_duration_is_from_matching_controlled_execution(monkeypatch):
    rid, _ = _facts_fixture(monkeypatch)
    for version, duration in [('wrong-version', 9999), ('a'*64, 41.3)]:
        db.append_event(rid, 'controller', 'sandbox.exec_completed', {
            'command': f'CS_SCORER_VERSION={version} python3 scorer/score.py package.zip',
            'status': 'completed', 'exit_code': 0, 'duration_seconds': duration})
    scoring = runtime_facts.facts(rid)['scoring']
    assert scoring['estimated_seconds'] == 41.3
    assert scoring['estimate_source'] == 'historical_controlled_execution'
    assert scoring['observation_ref'].startswith(rid + '#')
