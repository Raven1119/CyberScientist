"""Missing scorers can be frozen once; research cannot replace a grader."""
import json

import pytest

from cyberscientist import config, db, local_scoring
from test_trace_narrative import _fixture


def _draft():
    rid, tid, *_, trial = _fixture()
    db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?", (rid,))
    source = trial / 'scorer-draft'
    source.mkdir()
    (source / 'scorer.json').write_text(json.dumps({
        'entrypoint': 'score.py', 'image': 'registry.example/test:v1',
        'version': 'test', 'contract_version': 1}))
    # An import side effect would fail the test if initialization executed it.
    (source / 'score.py').write_text('raise RuntimeError("never execute on host")\n')
    return rid, tid, source


def _initialize(rid, tid, source, operation='initialize-one'):
    return local_scoring.initialize_scorer(rid, tid, operation, str(source))


def test_initialize_freezes_exact_bytes_and_provenance_without_execution():
    rid, tid, source = _draft()
    result = _initialize(rid, tid, source)
    frozen = config.WORKSPACE_DIR / 'challenges' / 'MB_CH' / 'scorer'
    assert (frozen / 'score.py').read_bytes() == (source / 'score.py').read_bytes()
    assert result['scorer_version'] == local_scoring.scorer_manifest('MB_CH')['scorer_version']
    assert result['status'] == 'initialized'
    assert result['authority'] == 'local_candidate_not_official'
    assert _initialize(rid, tid, source)['deduplicated'] is True
    events = db.query("SELECT payload FROM events WHERE type='science.scorer_initialized'")
    assert len(events) == 1
    assert json.loads(events[0]['payload'])['file_hashes'] == result['file_hashes']
    with pytest.raises(local_scoring.LocalScoreError, match='已有'):
        _initialize(rid, tid, source, 'another-operation')
    (source / 'score.py').write_text('changed')
    with pytest.raises(local_scoring.LocalScoreError) as error:
        _initialize(rid, tid, source)
    assert error.value.code == 'OPERATION_CONFLICT'


@pytest.mark.parametrize('fault', ['old_trial', 'closed_gate', 'outside', 'symlink',
                                  'invalid', 'secret', 'existing_empty', 'existing_link'])
def test_initialization_rejects_unauthorized_or_unsafe_drafts(fault, tmp_path, monkeypatch):
    rid, tid, source = _draft()
    if fault == 'old_trial':
        tid = 'other-trial'
    elif fault == 'closed_gate':
        db.execute("UPDATE runs SET gate='closed' WHERE id=?", (rid,))
    elif fault == 'outside':
        source = source.parent.parent
    elif fault == 'symlink':
        (source / 'link').symlink_to(source / 'score.py')
    elif fault == 'invalid':
        (source / 'scorer.json').write_text('{}')
    elif fault == 'secret':
        monkeypatch.setattr(config, 'sensitive_values', lambda: ['test-sensitive-value'])
        (source / 'secret.txt').write_text('test-sensitive-value')
    else:
        target = config.WORKSPACE_DIR / 'challenges' / 'MB_CH' / 'scorer'
        target.parent.mkdir(parents=True)
        if fault == 'existing_empty':
            target.mkdir()
        else:
            target.symlink_to(tmp_path / 'absent')
    with pytest.raises(local_scoring.LocalScoreError):
        _initialize(rid, tid, source)
    assert not db.query("SELECT 1 FROM operations WHERE kind='scorer.initialize:MB_CH'")
    assert not db.query("SELECT 1 FROM events WHERE type='science.scorer_initialized'")


def test_operation_ids_cannot_be_rebound():
    rid, tid, source = _draft()
    db.record_operation('initialize-one', rid, 'other', 'confirmed')
    with pytest.raises(local_scoring.LocalScoreError) as error:
        _initialize(rid, tid, source)
    assert error.value.code == 'OPERATION_CONFLICT'


def test_deleted_frozen_scorer_cannot_be_reinitialized():
    import shutil
    rid, tid, source = _draft()
    _initialize(rid, tid, source)
    frozen = config.WORKSPACE_DIR / 'challenges' / 'MB_CH' / 'scorer'
    frozen.chmod(0o755)
    shutil.rmtree(frozen)
    with pytest.raises(local_scoring.LocalScoreError) as error:
        _initialize(rid, tid, source, 'after-deletion')
    assert error.value.code == 'SCORER_EXISTS'


def test_initialization_failure_does_not_publish_partial_source(monkeypatch):
    rid, tid, source = _draft()
    target = config.WORKSPACE_DIR / 'challenges' / 'MB_CH' / 'scorer'
    from pathlib import Path
    original = Path.rename
    def fail_publish(path, destination):
        if destination == target:
            raise OSError('injected rename failure')
        return original(path, destination)
    monkeypatch.setattr(Path, 'rename', fail_publish)
    with pytest.raises(OSError, match='injected'):
        _initialize(rid, tid, source)
    assert not target.exists()
    assert not list(target.parent.glob('.scorer-init-*'))
    assert not db.query('SELECT 1 FROM operations')


def test_mcp_schema_exposes_initialization():
    from cyberscientist import mcp_bridge
    tool = next(t for t in mcp_bridge._TOOLS if t['name'] == 'research_local_score')
    assert 'initialize' in tool['inputSchema']['properties']['action']['enum']
    assert 'source_directory' in tool['inputSchema']['properties']


def test_api_initialization_requires_executor_and_routes_authenticated_run(monkeypatch):
    from fastapi.testclient import TestClient
    from cyberscientist import api, collab
    rid, tid, source = _draft()
    identity = {'run_id': rid, 'role': 'brain'}
    monkeypatch.setattr(collab, 'validate_token', lambda token: identity if token == 'fixture' else None)
    client = TestClient(api.create_app())
    body = {'action': 'initialize', 'trial_id': tid, 'operation_id': 'api-init',
            'source_directory': str(source), 'run_id': 'ignored-untrusted-run'}
    assert client.post('/api/v1/tools/local_score', json=body).status_code == 401
    headers = {'Authorization': 'Bearer fixture'}
    assert client.post('/api/v1/tools/local_score', json=body, headers=headers).status_code == 403
    identity['role'] = 'executor'
    result = client.post('/api/v1/tools/local_score', json=body, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'initialized'
    assert db.query_one('SELECT run_id FROM operations WHERE operation_id=?', ('api-init',))['run_id'] == rid
