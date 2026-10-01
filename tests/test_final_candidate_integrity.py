"""Cross-trial candidate loss and duplicate scoring, using synthetic artifacts."""
import asyncio
import hashlib
import json

import pytest

from cyberscientist import db, evaluations, local_scoring, mailboxes, package_seal, sandboxes
from cyberscientist.controller import RunController
from test_collaboration import _decision
from test_local_scoring import _scorer
from test_trace_narrative import _fixture, _zip


def _run_with_scorer():
    rid, tid, package, files, *_ = _fixture()
    _scorer()
    snapshot = json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',
                                      (rid,))['config_snapshot'])
    snapshot['eval_mode'] = {'enabled': True}
    db.execute("UPDATE runs SET config_snapshot=?,phase='running',started_at=? WHERE id=?",
               (json.dumps(snapshot), db.utcnow(), rid))
    db.execute("UPDATE trials SET status='done' WHERE id=?", (tid,))
    return rid, tid, package, files, local_scoring.scorer_manifest('MB_CH')


def _score(rid, tid, files, manifest, op, a, b):
    sealed, _ = package_seal.seal(_zip(files), rid, tid, 0)
    science = {'score': a+b, 'components': {'part_a': {'score': a}, 'part_b': {'score': b}},
               'confidence': 'high', 'notes': 'synthetic score',
               'scorer_version': manifest['scorer_version']}
    return local_scoring._record_score('MB_CH', rid, tid, op, sealed, manifest, science)


def test_finish_rejects_loss_of_registered_components_and_brain_can_confirm(monkeypatch):
    rid, tid, _, files, manifest = _run_with_scorer()
    for candidate_tid, values in [('candidate_a', (11, 0)), ('candidate_b', (0, 13))]:
        db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at)"
                   " VALUES(?,?,'synthetic','synthetic','done',?)",
                   (candidate_tid, rid, db.utcnow()))
        candidate_files = files | {'candidate.txt': candidate_tid.encode()}
        _score(rid, candidate_tid, candidate_files, manifest, candidate_tid, *values)
    candidate = _score(rid, tid, files, manifest, 'final-placeholder', 0, 0)
    calls = []
    monkeypatch.setattr(local_scoring, 'score_candidate',
                        lambda *args, **kwargs: calls.append(1) or candidate, raising=False)
    controller = RunController()
    action = {'op': 'finish', 'reason': 'freeze synthetic result',
              'objective_assessment': {'status': 'partial', 'evidence_refs': [],
                                       'remaining_md': 'synthetic unresolved result'}}
    asyncio.run(controller._apply_decision(rid, _decision([action], rid=rid), {}, None, None))
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'running'
    rejected = db.query_one("SELECT payload FROM events WHERE run_id=?"
                            " AND type='brain.action_rejected' ORDER BY seq DESC LIMIT 1", (rid,))
    facts = json.loads(rejected['payload'])['final_package_check']
    losses = {item['component']: item for item in facts['regressions']}
    assert losses['/components/part_a/score']['best_score'] == 11
    assert losses['/components/part_b/score']['best_score'] == 13
    assert all(item['current_score'] == 0 and item['candidate_artifact_hashes']
               for item in losses.values())
    assert calls == [1]
    packet = controller._lifecycle_packet(db.query_one('SELECT * FROM runs WHERE id=?', (rid,)),
                                         'finish_rejected', sparse=True)
    assert packet['final_package_check']['confirmation_token'] == facts['confirmation_token']
    action['finish_confirmation'] = {'token': facts['confirmation_token'],
                                      'reason_md': 'explicitly retain this incomplete synthetic result'}
    asyncio.run(controller._apply_decision(rid, _decision([action], rid=rid), {}, None, None))
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'eval_scoring'
    assert db.query_one("SELECT 1 FROM events WHERE run_id=?"
                        " AND type='run.final_package_confirmed'", (rid,))
    assert db.query_one('SELECT 1 FROM submissions WHERE run_id=?', (rid,)) is None


def test_final_evaluation_reuses_identical_science_and_scorer_without_sandbox(monkeypatch):
    rid, tid, _, files, manifest = _run_with_scorer()
    first = mailboxes.preflight_submission(rid, tid, None, allow_proxy_evidence=True)
    source = local_scoring._record_score('MB_CH', rid, tid, 'prior-registered',
        first['sealed_bytes'], manifest, {'score': 24,
        'components': {'part_a': {'score': 11}, 'part_b': {'score': 13}},
        'confidence': 'high', 'notes': 'synthetic', 'scorer_version': manifest['scorer_version']})
    db.execute("UPDATE runs SET phase='eval_scoring' WHERE id=?", (rid,))
    db.append_event(rid, 'controller', 'synthetic.trace_only_change', {})
    # The evolving trace changes the outer bundle, while scorer input stays fixed.
    check = mailboxes.preflight_submission(rid, tid, None, allow_proxy_evidence=True)
    check['error_code'] = None
    monkeypatch.setattr(mailboxes, 'preflight_submission', lambda *args, **kwargs: check)
    monkeypatch.setattr(sandboxes, 'create',
                        lambda *args, **kwargs: pytest.fail('cache reuse must not create a sandbox'))
    monkeypatch.setattr(local_scoring, 'evaluate',
                        lambda *args, **kwargs: pytest.fail('cache reuse must not execute science'))
    assert evaluations._score_run(rid, 'er_cache') == ('scored', None)
    derived = db.query_one('SELECT * FROM local_scores WHERE sandbox_operation_id=?',
                           ('eval-score-er_cache',))
    assert derived['source_local_score_id'] == source['id']
    assert derived['science_score'] == 24
    assert db.query_one('SELECT 1 FROM compute_sandboxes WHERE run_id=?', (rid,)) is None


@pytest.mark.parametrize('change', ['artifact', 'manifest', 'scorer'])
def test_score_cache_never_reuses_changed_inputs(change):
    rid, tid, _, files, manifest = _run_with_scorer()
    _score(rid, tid, files, manifest, 'known-input', 11, 13)
    if change == 'artifact':
        files['result.txt'] = b'a different scientific artifact'
    elif change == 'manifest':
        value = json.loads(files['arm_manifest.json'])
        value['title'] = 'changed manifest'
        files['arm_manifest.json'] = json.dumps(value).encode()
    else:
        manifest = dict(manifest, scorer_version='different-scorer-hash')
    sealed, _ = package_seal.seal(_zip(files), rid, tid, 0)
    assert local_scoring.reuse_score(rid, tid, 'must-rescore', sealed, manifest) is None


def test_score_cache_migration_only_adds_column_and_preserves_rows():
    import sqlite3
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.execute('CREATE TABLE local_scores(id TEXT PRIMARY KEY)')
    connection.execute("INSERT INTO local_scores(id) VALUES('old')")
    for _ in range(2):
        db._ensure_columns(connection, 'local_scores', db.LOCAL_SCORE_V2_COLUMNS)
    row = connection.execute('SELECT * FROM local_scores').fetchone()
    assert row['id'] == 'old' and row['science_input_sha256'] is None
    assert [item['name'] for item in connection.execute('PRAGMA table_info(local_scores)')].count('science_input_sha256') == 1


def test_pause_during_final_scoring_cannot_be_overwritten_by_finish(monkeypatch):
    rid, tid, _, files, manifest = _run_with_scorer()
    candidate = _score(rid, tid, files, manifest, 'pause-race', 11, 13)
    def paused(*args, **kwargs):
        db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
        return candidate
    monkeypatch.setattr(local_scoring, 'score_candidate', paused)
    asyncio.run(RunController()._apply_decision(rid, _decision([
        {'op': 'finish', 'reason': 'synthetic finish'}], rid=rid), {}, None, None))
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'paused'
    rejected = db.query_one("SELECT payload FROM events WHERE run_id=?"
                            " AND type='brain.action_rejected' ORDER BY seq DESC LIMIT 1", (rid,))
    assert json.loads(rejected['payload'])['error_code'] == 'FINAL_PACKAGE_STATE_CHANGED'


def test_component_registry_distinguishes_scores_from_runtime_diagnostics():
    scores = local_scoring.component_scores({'score': 10, 'components': {
        'runtime_seconds': 120, 'quality': 0.9,
        'part': {'score': 7, 'fidelity': 0.8, 'time': 12},
        'bonus': {'points': {'first': 3, 'second': 0}}}})
    assert scores == {'/score': 10, '/components/part/score': 7,
                      '/components/bonus/points/first': 3, '/components/bonus/points/second': 0}


def test_plateau_scores_reject_lost_declared_candidates_and_allow_confirmation(monkeypatch):
    from cyberscientist import config
    rid, tid, _, files, _ = _run_with_scorer()
    path = config.WORKSPACE_DIR / 'challenges/MB_CH/scorer/scorer.json'
    description = json.loads(path.read_text())
    description['comparison_contract'] = {'higher_is_better': ['/components/*/quality'],
        'verification': 'Synthetic monotone grading input; formal points have a plateau.'}
    path.write_text(json.dumps(description))
    manifest = local_scoring.scorer_manifest('MB_CH')
    def candidate(operation, a, b):
        sealed, _ = package_seal.seal(_zip(files | {'candidate.txt': operation.encode()}), rid, tid, 0)
        return local_scoring._record_score('MB_CH', rid, tid, operation, sealed, manifest,
            {'score': 0, 'components': {'Q1': {'score': 0, 'quality': a, 'runtime': 9},
                                      'Q2': {'score': 0, 'quality': b, 'runtime': 3}},
             'confidence': 'high', 'notes': 'synthetic plateau', 'scorer_version': manifest['scorer_version']})
    first = candidate('better-q1', .8, 0)
    second = candidate('better-q2', 0, .81)
    final = candidate('placeholder', .0001, .00001)
    # Later edits cannot reinterpret the registered identities/contract.
    description.pop('comparison_contract'); path.write_text(json.dumps(description))
    monkeypatch.setattr(local_scoring, 'score_candidate', lambda *a, **k: final)
    controller = RunController()
    action = {'op': 'finish', 'reason': 'synthetic plateau finish'}
    asyncio.run(controller._apply_decision(rid, _decision([action], rid=rid), {}, None, None))
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'running'
    facts = local_scoring.latest_final_check(rid)['final_package_check']
    losses = {item['component']: item for item in facts['regressions']}
    assert set(losses) == {'/components/Q1/quality', '/components/Q2/quality'}
    assert losses['/components/Q1/quality']['best_score'] == .8
    assert losses['/components/Q1/quality']['current_score'] == .0001
    assert losses['/components/Q1/quality']['candidate_package_sha256'] == first['package_sha256']
    assert losses['/components/Q2/quality']['candidate_package_sha256'] == second['package_sha256']
    assert all(item['candidate_artifact_hashes'] for item in losses.values())
    assert final['science_score'] == 0  # Comparison does not rewrite formal points.
    action['finish_confirmation'] = {'token': facts['confirmation_token'], 'reason_md': 'retain synthetic result'}
    asyncio.run(controller._apply_decision(rid, _decision([action], rid=rid), {}, None, None))
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'eval_scoring'
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='run.final_package_confirmed'", (rid,))


@pytest.mark.parametrize('contract', [
    {'higher_is_better': ['/score'], 'verification': 'fixture'},
    {'higher_is_better': ['/components/a~2b'], 'verification': 'fixture'},
    {'higher_is_better': ['/components/*/value'], 'verification': ''},
    {'higher_is_better': ['/components/*/value'], 'verification': 'fixture', 'direction': 'guessed'},
])
def test_comparison_contract_rejects_unreviewable_fields(contract):
    with pytest.raises(local_scoring.LocalScoreError, match='单调比较'):
        local_scoring.validate_comparison(contract)


def test_score_and_comparison_registration_are_atomic(monkeypatch):
    rid, tid, _, files, manifest = _run_with_scorer()
    def interrupted(*a, **k):
        raise RuntimeError('registration interrupted')
    monkeypatch.setattr(db, 'append_event_tx', interrupted)
    with pytest.raises(RuntimeError, match='registration interrupted'):
        _score(rid, tid, files, manifest, 'interrupted-score', 1, 2)
    assert not db.query('SELECT 1 FROM local_scores WHERE run_id=?', (rid,))


def test_cache_preserves_declared_comparison_without_creating_sandbox(monkeypatch):
    from cyberscientist import config
    rid, tid, _, _, _ = _run_with_scorer()
    path = config.WORKSPACE_DIR / 'challenges/MB_CH/scorer/scorer.json'
    description = json.loads(path.read_text())
    description['comparison_contract'] = {'higher_is_better': ['/components/*/quality'],
        'verification': 'Synthetic monotone input.'}
    path.write_text(json.dumps(description)); manifest = local_scoring.scorer_manifest('MB_CH')
    first = mailboxes.preflight_submission(rid, tid, None, allow_proxy_evidence=True)
    source = local_scoring._record_score('MB_CH', rid, tid, 'declared-source', first['sealed_bytes'],
        manifest, {'score': 0, 'components': {'part': {'score': 0, 'quality': .8}},
                   'confidence': 'high', 'notes': 'synthetic', 'scorer_version': manifest['scorer_version']})
    db.execute("UPDATE runs SET phase='eval_scoring' WHERE id=?", (rid,))
    def forbidden(*a, **k):
        pytest.fail('cached declared comparisons must not create or execute a sandbox')
    monkeypatch.setattr(sandboxes, 'create', forbidden)
    monkeypatch.setattr(local_scoring, 'evaluate', forbidden)
    assert evaluations._score_run(rid, 'er_declared_cache') == ('scored', None)
    derived = db.query_one('SELECT * FROM local_scores WHERE sandbox_operation_id=?',
                           ('eval-score-er_declared_cache',))
    assert derived['source_local_score_id'] == source['id']
    assert local_scoring._registered_components(derived)['/components/part/quality'] == .8


def test_mutated_final_snapshot_is_not_silently_accepted(monkeypatch):
    from cyberscientist import config
    rid, tid, _, files, manifest = _run_with_scorer()
    candidate = _score(rid, tid, files, manifest, 'accepted-snapshot', 11, 13)
    facts = local_scoring.final_package_check(rid, candidate)
    db.append_event(rid, 'controller', 'run.final_package_checked', {'final_package_check': facts})
    folder = config.WORKSPACE_DIR / 'runs' / rid / 'final_candidate'
    folder.mkdir()
    (folder/'sealed_package.zip').write_bytes(b'changed frozen package')
    db.execute("UPDATE runs SET phase='eval_scoring' WHERE id=?", (rid,))
    monkeypatch.setattr(sandboxes, 'create', lambda *args, **kwargs: pytest.fail('must not rent'))
    status, reason = evaluations._score_run(rid, 'er_tampered')
    assert status == 'unavailable' and '已对账' in reason
