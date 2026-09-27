"""W2 scorer contract, owned sandbox execution and confirmed-score pairing."""
from __future__ import annotations

import hashlib
import json

import pytest

from cyberscientist import config, db, local_scoring, mailboxes, sandboxes
from test_trace_narrative import _fixture, _zip


def _scorer():
    directory = config.WORKSPACE_DIR / 'challenges' / 'MB_CH' / 'scorer'
    directory.mkdir(parents=True)
    (directory / 'scorer.json').write_text(json.dumps({
        'entrypoint': 'score.py', 'image': 'registry.example/challenge:v1',
        'version': '0.1.0', 'contract_version': 1}))
    (directory / 'score.py').write_text('print("fake scorer")\n')
    return directory


def test_scorer_file_change_creates_new_version():
    from test_mailboxes import _seed_challenge
    _seed_challenge()
    directory = _scorer()
    first = local_scoring.scorer_manifest('MB_CH')
    assert first['file_hashes']['score.py'] == hashlib.sha256(b'print("fake scorer")\n').hexdigest()
    (directory / 'score.py').write_text('print("new scorer")\n')
    second = local_scoring.scorer_manifest('MB_CH')
    assert second['scorer_version'] != first['scorer_version']


def test_scorer_directory_must_stay_inside_challenge_workspace():
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at)"
               " VALUES('../outside','local','x','x','x',?)", (db.utcnow(),))
    with pytest.raises(local_scoring.LocalScoreError) as error:
        local_scoring.scorer_manifest('../outside')
    assert error.value.code == 'SCORER_MISSING'


def test_trace_predictor_is_deterministic():
    rid, tid, package, files, rows, *_ = _fixture()
    sealed, _ = mailboxes.package_seal.seal(package, rid, tid, 0)
    first = local_scoring.predict_trace(sealed)
    assert first == local_scoring.predict_trace(sealed)
    assert first['feature_version'] and first['model_version']
    assert first['features']['steps'] >= 1


def test_fake_sandbox_scorer_records_and_calibrates(monkeypatch):
    rid, tid, package, files, rows, *_ = _fixture()
    _scorer()
    db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?", (rid,))
    sid = 'fake-sandbox-001'
    now = db.utcnow()
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,'
               'request_json,status,created_at,expires_at,updated_at)'
               ' VALUES(?,?,?,?,?,?,?,?,?)',
               ('fake-create',rid,tid,sid,json.dumps({'image':'registry.example/challenge:v1'}),
                'active',now,now,now))
    monkeypatch.setattr(mailboxes.arm_admission, 'check',
                        lambda *_: {'verdict': 'admitted', 'signals': {}})
    calls = []
    version = local_scoring.scorer_manifest('MB_CH')['scorer_version']
    def fake_execute(run_id, sandbox_id, command, timeout, operation_id):
        calls.append(('exec', operation_id, command))
        if operation_id.endswith('-run'):
            output = {'score': 20.0, 'components': {'scientific': 20.0},
                      'confidence': 'medium', 'notes': 'fake result',
                      'scorer_version': version}
            return {'status': 'completed', 'receipt': {'stdout': json.dumps({
                'data': {'stdout': json.dumps(output)}})}}
        return {'status': 'completed'}
    def fake_transfer(run_id, action, sandbox_id, remote_path, **kwargs):
        calls.append(('transfer', kwargs['operation_id'], remote_path))
        assert action == 'write' and (kwargs['local_path'].endswith('.zip'))
        return {'status': 'completed'}
    monkeypatch.setattr(sandboxes, 'execute', fake_execute)
    monkeypatch.setattr(sandboxes, 'transfer', fake_transfer)
    row = local_scoring.evaluate(rid, tid, sid, 'score-one')
    assert row['science_score'] == 20.0
    assert row['predicted_display_score'] == 20.0
    assert json.loads(row['scorer_file_hashes_json']) == local_scoring.scorer_manifest('MB_CH')['file_hashes']
    assert len(calls) == 4 and all(call[1].startswith('score-one-') for call in calls)
    assert local_scoring.evaluate(rid, tid, sid, 'score-one')['deduplicated'] is True
    db.append_event(rid, 'controller', 'checkpoint.created',
                    {'checkpoint_id': 'after-science'}, trial_id=tid)
    mailboxes.register_experiment(1)
    submission = mailboxes.submit_experiment(rid, tid, None, 'baseline',
        prediction_md=f'local_score:{row["id"]} 科学分应为 20')
    assert submission['package_sha256'] != row['package_sha256']
    derived = db.query_one('SELECT * FROM local_scores WHERE package_sha256=?',
                           (submission['package_sha256'],))
    assert derived['source_local_score_id'] == row['id']
    frozen = (config.WORKSPACE_DIR / submission['package_path']).read_bytes()
    staged = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / tid / 'local_scorer' / 'score-one' / 'science_package.zip'
    assert staged.read_bytes() == local_scoring._science_package(frozen)
    platform = mailboxes._platform()
    monkeypatch.setattr(platform, 'fetch_attempt', lambda *_: {
        'scorecard': {'harbor_score': 19, 'trace_score': 75}}, raising=False)
    monkeypatch.setattr(platform, 'fetch_score_details', lambda *_: {
        'scoringState': {'scoreIsFinal': True, 'displayScore': 18,
                         'workerStatus': 'completed'}}, raising=False)
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    settings = config.load_settings()
    settings['polling']['score_confirmation_seconds'] = 0
    config.save_settings(settings)
    mailboxes.poll_scores(run_id=rid, manual=True)
    assert db.query_one('SELECT score_confidence FROM submissions WHERE id=?',
                        (submission['id'],))['score_confidence'] == 'provisional'
    mailboxes.poll_scores(run_id=rid, manual=True)
    assert db.query_one('SELECT score_confidence FROM submissions WHERE id=?',
                        (submission['id'],))['score_confidence'] == 'confirmed'
    paired = db.query_one('SELECT * FROM score_calibration WHERE submission_id=?',
                          (submission['id'],))
    assert paired['local_score_id'] == derived['id']
    assert paired['display_delta'] == 2
    assert paired['science_delta'] == 1
    assert paired['trace_delta'] == -5
    db.execute("UPDATE submissions SET score_confidence='provisional' WHERE id=?", (submission['id'],))
    with db.transaction() as conn:
        local_scoring.calibrate_tx(conn, submission['id'])
    assert db.query_one('SELECT valid FROM score_calibration WHERE submission_id=?',
                        (submission['id'],))['valid'] == 0
    altered = dict(files, **{'result.txt': b'changed science\n'})
    trial_dir = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / tid
    (trial_dir / 'result_package.zip').write_bytes(_zip(altered))
    changed = mailboxes.submit_experiment(rid, tid, None, 'changed-science',
        prediction_md=f'local_score:{row["id"]} 科学产物变化，应重新评分')
    assert not db.query_one('SELECT 1 FROM local_scores WHERE package_sha256=?',
                            (changed['package_sha256'],))


def test_scorer_requires_matching_image_before_remote_operation(monkeypatch):
    rid, tid, package, files, rows, *_ = _fixture()
    _scorer()
    db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?", (rid,))
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,'
               'request_json,status,created_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
               ('wrong-image',rid,tid,'wrong-box',json.dumps({'image':'other'}),
                'active',db.utcnow(),db.utcnow(),db.utcnow()))
    monkeypatch.setattr(sandboxes, 'execute', lambda *_: pytest.fail('remote operation reached'))
    with pytest.raises(local_scoring.LocalScoreError) as error:
        local_scoring.evaluate(rid, tid, 'wrong-box', 'score-wrong')
    assert error.value.code == 'SCORER_IMAGE_MISMATCH'
