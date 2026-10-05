"""A reviewer sees the frozen lax grader and proposes tests; it never scores."""
import hashlib
import json
from pathlib import Path
import pytest
from cyberscientist import config, db, local_scoring, package_reviews, sandboxes
from cyberscientist.brains.base import BrainEvent, SessionRef
from cyberscientist.controller import RunController
from test_package_reviews import seed
from test_local_scoring import _scorer


class Auditor:
    def __init__(self): self.packet = None
    async def open(self, spec):
        self.cwd = Path(spec['working_directory'])
        assert not {'mcp_servers', 'env', 'resume_thread_id'} & spec.keys()
        return SessionRef('fixture', 'audit-session')
    async def close(self, session): pass
    async def review(self, session, packet):
        self.packet = packet
        source = packet['scorer_source']
        assert source['status'] == 'observed'
        assert source['sources']['score.py'] == 'def score(candidate):\n    return 100\n'
        assert 'residual below 0.01' in packet['challenge']
        for name in ('scorer.json', 'score.py'):
            path = self.cwd / 'scorer' / name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == source['file_hashes'][name]
            assert path.stat().st_mode & 0o222 == 0
        assert packet['local_score_status'] == 'observed'
        assert packet['local_scores'][0]['science_score'] == 100
        assert '不运行评分器' in packet['instructions'] and '由PI决定' in packet['instructions']
        yield BrainEvent('task_result', {'result': {'verdict': 'issues', 'issues': ['Missing dimensions and residual threshold'], 'summary_md': 'The constant grader is too lenient',
            'scorer_audit': {'coverage_findings': ['dimensions missing', 'residual criterion missing'],
                'threshold_format_md': 'No comparison with 0.01', 'leniency_md': 'Always returns 100',
                'method_completeness_md': 'Missing equations and limitations', 'replay_network_md': 'No demonstrated offline replay',
                'negative_controls': [{'case_md': 'Wrong dimension', 'expected_failure_md': 'score 0', 'covers_md': 'dimensions'},
                    {'case_md': 'Residual 1.0', 'expected_failure_md': 'score 0', 'covers_md': 'residual threshold'}]}}})


async def test_frozen_lax_scorer_audited_and_registered_score_reused_without_compute(monkeypatch):
    rid = seed(); root = _scorer(); (root / 'score.py').write_text('def score(candidate):\n    return 100\n')
    db.execute("UPDATE challenges SET content='Check dimensions and residual below 0.01' WHERE id='MB_CH'")
    package = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / 'trial_mb1' / 'result_package.json'
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    manifest = local_scoring.scorer_manifest('MB_CH')
    db.execute('INSERT INTO local_scores(id,challenge_id,run_id,trial_id,package_sha256,science_artifact_hashes_json,manifest_science_sha256,science_score,science_result_json,trace_prediction_json,scorer_version,scorer_file_hashes_json,feature_version,model_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               ('prior-score', 'MB_CH', rid, 'trial_mb1', digest, '{}', 'fixture-science-manifest', 100, '{}', '{}', manifest['scorer_version'], json.dumps(manifest['file_hashes']), 'fixture', 'fixture', db.utcnow()))
    monkeypatch.setattr(local_scoring, 'evaluate', lambda *a, **k: pytest.fail('reviewer must reuse, never evaluate'))
    monkeypatch.setattr(sandboxes, 'create', lambda *a, **k: pytest.fail('reviewer cannot create compute'))
    auditor = Auditor(); controller = RunController(); monkeypatch.setattr(controller, '_make_brain', lambda _: auditor)
    result = await package_reviews.review(controller, rid, 'trial_mb1', 'audit-lax')
    assert result['status'] == 'done' and len(result['result']['scorer_audit']['negative_controls']) == 2
    (root / 'score.py').write_text('changed after snapshot')
    assert (auditor.cwd / 'scorer/score.py').read_text() == 'def score(candidate):\n    return 100\n'
    assert len(db.query('SELECT * FROM local_scores')) == 1
    assert not db.query('SELECT * FROM compute_jobs') and not db.query('SELECT * FROM compute_sandboxes')
    from httpx import ASGITransport, AsyncClient
    from cyberscientist import api
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        response = await client.get(f'/api/v1/runs/{rid}/package-reviews')
    assert response.status_code == 200
    assert response.json()['items'][0]['result']['scorer_audit']['coverage_findings'] == ['dimensions missing', 'residual criterion missing']


@pytest.mark.parametrize('registered', [True, False])
async def test_scorer_secret_is_rejected_before_model_or_export(monkeypatch, registered):
    rid = seed(); root = _scorer(); secret = 'fixture-source-secret-1492' if registered else 'sk-' + 'Q'*48
    monkeypatch.setattr(config, 'sensitive_values', lambda: [secret] if registered else [])
    (root / 'score.py').write_text('key = ' + repr(secret))
    controller = RunController(); monkeypatch.setattr(controller, '_make_brain', lambda _: pytest.fail('no model'))
    with pytest.raises(ValueError, match='源码含密钥'):
        await package_reviews.review(controller, rid, 'trial_mb1', 'secret-source')
    assert not db.query('SELECT * FROM package_reviews')
    assert not any(secret in p.read_text(errors='replace') for p in (config.WORKSPACE_DIR / 'package_reviews').rglob('*.py'))


async def test_scorer_audit_off_preserves_original_reviewer_behavior(monkeypatch):
    from test_package_reviews import Reviewer
    rid = seed(); _scorer()
    settings = config.load_settings(); settings['features']['scorer_audit'] = False; config.save_settings(settings)
    monkeypatch.setattr(package_reviews, 'snapshot_scorer', lambda *a: pytest.fail('audit disabled'))
    calls = []; controller = RunController(); monkeypatch.setattr(controller, '_make_brain', lambda _: Reviewer(calls))
    result = await package_reviews.review(controller, rid, 'trial_mb1', 'audit-off')
    assert result['status'] == 'done'
    packet = next(value for kind, value in calls if kind == 'packet')
    assert packet['scorer_source']['status'] == 'disabled' and 'scorer_audit' not in packet['output_contract']['required']
