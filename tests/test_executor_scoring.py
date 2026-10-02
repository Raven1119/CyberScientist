"""Synthetic original-sandbox recovery and forged receipt rejection."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from cyberscientist import compute, config, db, executor_scoring, local_scoring, mailboxes, sandboxes
from test_final_candidate_integrity import _run_with_scorer


def _setup(monkeypatch, identity=False, public=False):
    rid, tid, _, _, manifest = _run_with_scorer()
    if identity or public:
        path = config.WORKSPACE_DIR / 'challenges/MB_CH/scorer/scorer.json'
        desc = json.loads(path.read_text())
        runtime = {}
        if identity:
            runtime['environment_id'] = 'synthetic-env'
            monkeypatch.setattr(executor_scoring.runtime_environments, 'recipe', lambda _: {
                'identity': {'tool_version': '1.2.3'}, 'identity_checks': {
                    'tool_version': {'argv': ['synthetic-tool', '--version']}},
                'recipe_sha256': 'a'*64, 'dockerfile_sha256': 'b'*64})
        if public:
            public_file = config.WORKSPACE_DIR / 'public.zip'
            public_file.write_bytes(local_scoring._archive({'public.txt': b'public fixture'}))
            monkeypatch.setattr(config, 'WORKSPACE_ROOT', config.WORKSPACE_DIR)
            runtime['public_resource'] = {
                'path': 'public.zip', 'sha256': hashlib.sha256(public_file.read_bytes()).hexdigest(),
                'environment_variable': 'CS_PUBLIC_FIXTURE', 'directory': '.'}
        desc['runtime'] = runtime
        path.write_text(json.dumps(desc))
    sid = 'original-owned-sandbox'
    now = db.utcnow()
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,request_json,'
               'status,created_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
               ('original-create', rid, tid, sid, json.dumps({'image': manifest['image']}),
                'active', now, (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(), now))
    prepared = executor_scoring.prepare(rid, tid, 'executor-candidate', sid)
    stored = json.loads(db.query_one('SELECT plan_json FROM executor_score_plans')['plan_json'])
    plan = stored['plan']
    output = {'schema_version': 1, 'inputs': dict(plan['inputs']),
              'environment_identity': dict(plan['identity']), 'science': {
                  'score': 64.79, 'components': {'part': {'score': 64.79}},
                  'confidence': 'high', 'notes': 'Synthetic controlled result',
                  'scorer_version': plan['scorer_version']}}
    return rid, tid, sid, prepared, output


def _execute(monkeypatch, rid, sid, command, output):
    def native(args, **kwargs):
        assert args[:2] == ['sandbox', 'exec']
        return {'ok': True, 'exit_code': 0, 'stdout': json.dumps({'ok': True,
                'data': {'exit_code': 0, 'stdout': json.dumps(output), 'stderr': ''}}), 'stderr': ''}
    monkeypatch.setattr(compute, '_native', native)
    return sandboxes.execute(rid, sid, command, 120, 'executor-grading-execution')


def test_executor_recovers_system_failure_in_original_sandbox_and_cache_is_formal(monkeypatch):
    rid, tid, sid, prepared, output = _setup(monkeypatch)
    monkeypatch.setattr(sandboxes, 'transfer', lambda *a, **k: {'status': 'failed', 'receipt': {'stderr': 'transfer timeout'}})
    monkeypatch.setattr(compute, '_native', lambda *a, **k: {'ok': True, 'exit_code': 0, 'stdout': '{}'})
    with pytest.raises(local_scoring.LocalScoreError) as error:
        local_scoring.evaluate(rid, tid, sid, 'system-failed')
    assert error.value.details['stage'] == 'scorer'
    assert not db.query('SELECT * FROM local_scores')
    _execute(monkeypatch, rid, sid, prepared['command'], output)
    score = executor_scoring.register(rid, tid, 'executor-candidate', 'executor-grading-execution')
    assert score['science_score'] == 64.79 and score['score_source'] == 'executor_verified'
    assert db.query_one('SELECT COUNT(*) AS n FROM compute_sandboxes')['n'] == 1
    assert executor_scoring.register(rid, tid, 'executor-candidate', 'executor-grading-execution')['deduplicated']
    check = mailboxes.preflight_submission(rid, tid, None, allow_proxy_evidence=True)
    manifest = local_scoring.scorer_manifest('MB_CH')
    monkeypatch.setattr(sandboxes, 'create', lambda *a, **k: pytest.fail('must reuse, never rent'))
    reused = local_scoring.reuse_score(rid, tid, 'finish-reuse', check['sealed_bytes'], manifest)
    assert reused['science_score'] == 64.79 and reused['score_source'] == 'executor_verified'
    assert not local_scoring.final_package_check(rid, reused)['regressions']


@pytest.mark.parametrize('tamper,code', [
    ('science_hash', 'SCORE_INPUT_MISMATCH'), ('scorer_hash', 'SCORE_INPUT_MISMATCH'),
    ('public_hash', 'SCORE_INPUT_MISMATCH'), ('command', 'SCORE_COMMAND_MISMATCH'),
    ('environment', 'SCORE_ENVIRONMENT_MISMATCH'), ('receipt', 'SCORE_RECEIPT_MISMATCH'),
    ('multi_json', 'INVALID_SCORE_OUTPUT'), ('exit', 'SCORE_EXIT_NONZERO')])
def test_untrusted_result_rejected_with_actionable_reason(monkeypatch, tamper, code):
    rid, tid, sid, prepared, output = _setup(monkeypatch, identity=True, public=True)
    key = {'science_hash': 'science_package.zip', 'scorer_hash': 'scorer.zip',
           'public_hash': 'public_resource.zip'}.get(tamper)
    if key:
        output['inputs'][key] = '0'*64
    if tamper == 'environment':
        output['environment_identity']['tool_version'] = 'old'
    _execute(monkeypatch, rid, sid, 'echo forged' if tamper == 'command' else prepared['command'], output)
    if tamper in ('receipt', 'multi_json', 'exit'):
        row = db.query_one('SELECT receipt_json FROM compute_sandbox_operations WHERE operation_id=?',
                           ('executor-grading-execution',))
        receipt = json.loads(row['receipt_json'])
        data = json.loads(receipt['stdout'])
        if tamper == 'exit':
            data['data']['exit_code'] = 1
        elif tamper == 'multi_json':
            data['data']['stdout'] += '\n{}'
        else:
            data['data']['stdout'] = '{}'
        receipt['stdout'] = json.dumps(data)
        raw = sandboxes._json(receipt)
        db.execute('UPDATE compute_sandbox_operations SET receipt_json=? WHERE operation_id=?',
                   (raw, 'executor-grading-execution'))
        if tamper != 'receipt':  # Faithfully captured invalid native output, rather than post-capture tampering.
            db.execute('UPDATE compute_sandbox_operations SET receipt_sha256=? WHERE operation_id=?',
                       (hashlib.sha256(raw.encode()).hexdigest(), 'executor-grading-execution'))
    with pytest.raises(local_scoring.LocalScoreError) as error:
        executor_scoring.register(rid, tid, 'executor-candidate', 'executor-grading-execution')
    assert error.value.code == code
    assert not db.query('SELECT * FROM local_scores')


def test_prepare_plan_cannot_be_rebound_or_accept_caller_score(monkeypatch):
    rid, tid, sid, prepared, _ = _setup(monkeypatch)
    assert executor_scoring.prepare(rid, tid, 'executor-candidate', sid)['command'] == prepared['command']
    with pytest.raises(local_scoring.LocalScoreError) as error:
        executor_scoring.prepare(rid, tid, 'executor-candidate', sid, environment_paths={'PYTHONPATH': '/tmp/forge'})
    assert error.value.code == 'OPERATION_CONFLICT'
    with pytest.raises(local_scoring.LocalScoreError) as error:
        executor_scoring.prepare(rid, tid, 'another-plan', sid, environment_paths={'PYTHONPATH': '/tmp/forge'})
    assert error.value.code == 'INVALID_ENVIRONMENT_PATH'
    import inspect
    assert 'score' not in inspect.signature(executor_scoring.register).parameters


@pytest.mark.parametrize('tamper', [None, 'hash', 'identity', 'multiple_json'])
def test_fixed_runner_checks_inputs_and_identity_in_same_execution(tmp_path, tamper):
    import base64
    import os
    import subprocess
    import sys
    from pathlib import Path
    from cyberscientist import scoring_runner
    code = ('import json,os\nprint(json.dumps({"score":17,"components":{},"confidence":"high",'
            '"notes":"fixture","scorer_version":os.environ["CS_SCORER_VERSION"]}))\n')
    if tamper == 'multiple_json':
        code += 'print("{}")\n'
    scorer = {'score.py': code.encode()}
    (tmp_path / 'scorer.zip').write_bytes(local_scoring._archive(scorer))
    (tmp_path / 'science_package.zip').write_bytes(local_scoring._archive({'fixture.txt': b'fixture'}))
    (tmp_path / 'public_resource.zip').write_bytes(local_scoring._archive({'public.txt': b'fixture'}))
    plan = {'remote': str(tmp_path), 'inputs': {name: hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()
            for name in ('scorer.zip', 'science_package.zip', 'public_resource.zip')},
            'identity': {'fixture_version': '1.2.3'},
            'identity_checks': {'fixture_version': {'argv': [sys.executable, '-I', '-c', 'print("1.2.3")']}},
            'environment_paths': {}, 'project_files': {}, 'scorer_files': {
                'score.py': hashlib.sha256(code.encode()).hexdigest()},
            'scorer_version': 'a'*64, 'entrypoint': 'score.py', 'score_timeout': 10,
            'public_resource': {'environment_variable': 'CS_PUBLIC_FIXTURE', 'directory': 'public'}}
    if tamper == 'hash':
        plan['inputs']['science_package.zip'] = '0'*64
    if tamper == 'identity':
        plan['identity']['fixture_version'] = 'wrong'
    process = subprocess.run([sys.executable, '-I', str(Path(scoring_runner.__file__)),
        base64.b64encode(json.dumps(plan).encode()).decode()], capture_output=True, text=True,
        env={**os.environ, 'CS_SCORER_VERSION': 'forged', 'PYTHONPATH': '/tmp/untrusted'}, timeout=20)
    if tamper:
        assert process.returncode != 0 and not process.stdout.strip()
    else:
        result = json.loads(process.stdout)
        assert process.returncode == 0 and result['science']['score'] == 17
        assert result['inputs'] == plan['inputs'] and result['environment_identity'] == plan['identity']
        assert result['science']['scorer_version'] == 'a'*64
