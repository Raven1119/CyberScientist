import json

import pytest

from cyberscientist import db, local_scoring, runtime_environments, sandboxes, evaluations
from test_evaluations import _challenge
from test_final_candidate_integrity import _run_with_scorer
from test_compute_gateway import run, spec


def test_recipe_is_not_a_verified_environment_and_identity_mismatch_rejected():
    facts = runtime_environments.facts()
    lean = next(item for item in facts if item['id']=='lean-4.32.2')
    assert lean['identity']['lean_version'] == '4.32.2'
    assert lean['status'] == 'unverified' and lean['image'] is None
    assert next(item for item in facts if item['id']=='competition-materials')['status']=='unverified'
    with pytest.raises(runtime_environments.EnvironmentUnavailable):
        runtime_environments.resolve('lean-4.32.2')
    with pytest.raises(runtime_environments.EnvironmentUnavailable):
        runtime_environments.register_verified('lean-4.32.2',
            image_address='registry.example/lean:fixed', platform_image_id='synthetic-id',
            observed_descriptor={'lean_version': 'wrong'}, receipt_sha256='a'*64)
    assert not db.query('SELECT * FROM runtime_environments')


def test_verified_identity_registry_exposes_public_environment_facts(monkeypatch):
    expected = runtime_environments.recipe('lean-4.32.2')
    runtime_environments.register_verified('lean-4.32.2',
        image_address='registry.example/lean:fixed', platform_image_id='synthetic-id',
        observed_descriptor=expected['identity'], receipt_sha256='a'*64)
    first = runtime_environments.resolve('lean-4.32.2')
    assert first['image'] == 'registry.example/lean:fixed'
    assert first['mathlib_root'] == '/opt/cs-mathlib'
    db.init_db(); db.init_db()
    assert runtime_environments.resolve('lean-4.32.2') == first


def test_missing_prebuilt_environment_does_not_block_controlled_attempt(monkeypatch):
    rid, tid, _, files, manifest = _run_with_scorer()
    manifest['runtime'] = {'environment_id': 'lean-4.32.2'}
    monkeypatch.setattr(local_scoring, 'scorer_manifest', lambda _: manifest)
    monkeypatch.setattr(local_scoring, 'reuse_score', lambda *args: None)
    monkeypatch.setattr(sandboxes, 'bounded_lifetime', lambda *args: 60)
    attempts = []
    monkeypatch.setattr(sandboxes, 'create', lambda *args, **kwargs:
                        attempts.append(args) or {'status': 'active', 'sandbox_id': 'synthetic-score-sandbox'})
    monkeypatch.setattr(local_scoring, 'evaluate', lambda *args, **kwargs: {'science_score': 10})
    row = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    from test_trace_narrative import _zip
    assert evaluations.score_preflight(row, {'sealed_bytes': _zip(files)},
                                       'synthetic-score', 'synthetic-sandbox')['science_score'] == 10
    assert len(attempts) == 1


def test_large_input_warns_before_reservation_and_lists_only_verified_availability(run, monkeypatch):
    rid, source = run
    payload = source / 'synthetic-payload.bin'
    with payload.open('wb') as stream:
        stream.truncate(256*1024**2 + 1)
    from cyberscientist import compute
    monkeypatch.setattr(compute, '_native', lambda *args, **kwargs:
                        {'ok': False, 'not_started': True, 'stderr': 'synthetic no dispatch'})
    assert compute.submit(rid, 'large-input', spec(), str(source))['status'] == 'not_started'
    warning = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='job.input_warning'", (rid,))
    facts = json.loads(warning['payload'])
    assert facts['input_bytes'] > 256*1024**2
    assert facts['reservation_created'] is False
    assert facts['prebuilt_environments'][0]['status'] == 'unverified'
    assert db.query('SELECT 1 FROM compute_jobs WHERE run_id=?', (rid,))
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='job.input_warning'", (rid,))
