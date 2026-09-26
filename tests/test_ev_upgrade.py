"""CS-EV-01 boundaries: only temp DBs, fake adapters, no cloud calls."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from cyberscientist import arm_admission, compute, config, datasets, db, job_preflight, mailboxes, package_seal
from cyberscientist.controller import RunController
from cyberscientist.decision_extraction import extract_decision
from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform, PlatformError


def test_v2_brain_decision_extracted_from_fenced_final_message():
    decision = {"schema_version": 2, "decision_id": "start-1", "run_id": "run_1",
                "observed_state_version": 0, "summary": "Start a trial",
                "evidence_refs": ["frame_1"],
                "actions": [{"op": "start_trial", "goal": "Inspect the dataset",
                             "success_check": "Report the receipt"}],
                "experience_proposals": []}
    message = "```json\n" + json.dumps(decision) + "\n```"
    assert extract_decision(message, {"run_id": "run_1"}) == decision


def _bundle(steps: list[dict] | None = None, *, artifacts: list[dict] | None = None,
            log_text: str = "validated long execution line\n") -> bytes:
    manifest = {"arm_version": "1.1", "entrypoint": "src/reproduce.py",
                "execution": {"log_path": "results/run.log", "ran_at": "2026-09-25T00:00:00Z",
                              "wall_time_s": 20, "artifacts": artifacts or []},
                "trace": {"files": ["traces/trace.jsonl"]}}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("arm_manifest.json", json.dumps(manifest))
        archive.writestr("characterization.json", "{}")
        archive.writestr("src/reproduce.py", "print('fixture')\n")
        archive.writestr("results/run.log", log_text)
        archive.writestr("results/output.txt", "data")
        archive.writestr("traces/trace.jsonl", "\n".join(json.dumps(s) for s in (steps or [])))
    return out.getvalue()


def _protocol() -> dict:
    return json.loads((__import__('pathlib').Path(__file__).resolve().parents[1] / 'contracts' /
                       'arm_protocol.json').read_text())


def _run(*, resources: list[dict] | None = None, allow_data: bool = False, max_trials: int = 1):
    db.execute("INSERT INTO challenges(id,platform_challenge_id,origin,title,content,content_hash,"
               "contract_status,imported_at,is_demo,resources_json)"
               " VALUES('ev_ch','ev','manual://local','EV','task','hash','unknown',?,0,?)",
               (db.utcnow(), json.dumps(resources or [])))
    datasets.register_resources('ev_ch', resources or [])
    settings = config.load_settings()
    settings['run_defaults']['max_trials'] = max_trials
    settings['bohrium']['project_id'] = 88474
    config.save_settings(settings)
    controller = RunController()
    rid = controller.create_run('ev_ch', mode='connected')['id']
    controller.authorize(rid, 'model_roundtrip', True, 10, 60, 2, 'original goal',
                         max_jobs=2, allow_data_download=allow_data)
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    return controller, rid


def test_trace_projection_real_pair_and_deterministic_seal():
    _, rid = _run()
    db.append_event(rid, 'prime', 'prime.execution.progress',
                    {'item_id': 'item1', 'status': 'inProgress', 'detail': 'Run fixture'}, trial_id=None)
    db.append_event(rid, 'prime', 'prime.execution.progress',
                    {'item_id': 'item1', 'status': 'completed', 'detail': 'Run fixture',
                     'output': 'validated long execution line'}, trial_id=None)
    cutoff = db.query_one('SELECT MAX(seq) AS n FROM events WHERE run_id=?', (rid,))['n']
    source = _bundle([{'checkpoint': 'cp1', 'event': 'not typed'}])
    assert arm_admission.check(source, _protocol())['verdict'] == 'blocked'
    sealed1, steps = package_seal.seal(source, rid, None, cutoff)
    sealed2, _ = package_seal.seal(source, rid, None, cutoff)
    assert sealed1 == sealed2
    report = arm_admission.check(sealed1, _protocol())
    assert report['verdict'] == 'admitted'
    assert report['signals']['paired_tool_calls']['ok'] is True
    assert [s['step_type'] for s in steps] == ['tool_call', 'tool_result']
    assert all('cost_usd' not in s and s['cs_ref'].startswith(rid + '#') for s in steps)
    later = db.append_event(rid, 'prime', 'prime.execution.progress',
                            {'item_id': 'later', 'status': 'started'})
    sealed3, later_steps = package_seal.seal(source, rid, None, cutoff)
    assert sealed3 == sealed1 and not any(s.get('tool_call_id') == 'later' for s in later_steps)


def test_trace_unpaired_and_missing_artifact_do_not_light_signals():
    _, rid = _run()
    db.append_event(rid, 'prime', 'prime.execution.progress',
                    {'item_id': 'only-start', 'status': 'started'})
    source = _bundle(artifacts=[{'path': 'missing.png'}])
    sealed, steps = package_seal.seal(source, rid, None, 100)
    report = arm_admission.check(sealed, _protocol())
    assert [s['step_type'] for s in steps] == ['tool_call']
    assert report['signals']['paired_tool_calls']['ok'] is False
    assert report['signals']['artifact_path']['ok'] is False


def test_projected_trace_redacts_secret_and_omits_hidden_reasoning(monkeypatch):
    _, rid = _run()
    monkeypatch.setattr(config, 'load_secrets', lambda: {'account': 'fixture-secret-value'})
    db.append_event(rid, 'prime', 'prime.execution.progress',
                    {'item_id': 'fixture-secret-value', 'status': 'completed',
                     'detail': 'fixture-secret-value', 'output': 'fixture-secret-value',
                     'hidden_reasoning': 'private thought'})
    sealed, _ = package_seal.seal(_bundle(), rid, None, 100)
    assert b'fixture-secret-value' not in sealed
    with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
        projected = archive.read(package_seal.TRACE)
    assert b'fixture-secret-value' not in projected
    assert b'private thought' not in projected
    assert b'cost_usd' not in projected


def test_missing_protocol_is_indeterminate_and_proxy_blocks_without_reservation(monkeypatch):
    resources = [{'dataset_id': 'public-id', 'version_id': '1', 'role': 'task-public-data'}]
    _, rid = _run(resources=resources)
    trial = 'trial_ev'
    base = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / trial
    base.mkdir(parents=True)
    (base / 'result_package.zip').write_bytes(_bundle([
        {'step_type': 'tool_call', 'title': 'Real fixture call', 'tool_call_id': 'x'},
        {'step_type': 'tool_result', 'title': 'Real fixture result', 'tool_call_id': 'x'}]))
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,created_at)"
               " VALUES(?,?,?,?,?)", (trial, rid, 'g', 's', db.utcnow()))
    check = mailboxes.preflight_submission(rid, trial, None)
    assert check['error_code'] == 'PROXY_EVIDENCE'
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.submit_experiment(rid, trial, None, 'ev-submit')
    assert exc.value.code == 'PROXY_EVIDENCE'
    assert db.query_one('SELECT COUNT(*) AS n FROM submissions')['n'] == 0
    assert mailboxes.preflight_submission(rid, trial, None,
        allow_proxy_evidence=True)['error_code'] is None
    monkeypatch.setattr(mailboxes, '_protocol_snapshot', lambda: None)
    assert mailboxes.preflight_submission(rid, trial, None,
        allow_proxy_evidence=True)['error_code'] == 'TRACE_ADMISSION_INDETERMINATE'


def test_blocked_trace_never_reserves_submission():
    _, rid = _run()
    trial = 'blocked-trial'
    base = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / trial
    base.mkdir(parents=True)
    (base / 'result_package.zip').write_bytes(_bundle([{'checkpoint': 'old', 'event': 'untyped'}]))
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,created_at)"
               " VALUES(?,?,?,?,?)", (trial, rid, 'g', 's', db.utcnow()))
    report = mailboxes.preflight_submission(rid, trial, None)
    assert report['admission']['verdict'] == 'blocked'
    assert report['error_code'] == 'TRACE_ADMISSION_BLOCKED'
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.submit_experiment(rid, trial, None, 'blocked-submit')
    assert exc.value.code == 'TRACE_ADMISSION_BLOCKED'
    assert db.query_one('SELECT COUNT(*) AS n FROM submissions')['n'] == 0


def test_platform_bundle_blocked_keeps_draft_and_skips_submit(tmp_path):
    pkg = tmp_path / 'bundle.zip'; pkg.write_bytes(_bundle())
    platform = BohriumPlaygroundPlatform('https://fixture.invalid')
    calls = []; stages = []
    def fake_http(method, path, **kwargs):
        calls.append(path)
        return {'id': 12} if path.endswith('/attempts') else {
            'bundleStatus': 'needs_review',
            'validation': {'trace_admission': {'admitted': False}},
            'violations': [{'rule': 'trace_admission_blocked'}]}
    platform._http = fake_http
    with pytest.raises(PlatformError) as error:
        platform.submit_package('fixture', 'secret', str(pkg), 'challenge',
                                meta={'on_stage': lambda stage, *args: stages.append(stage)})
    assert not error.value.no_side_effect
    assert stages[-1] == 'bundle_blocked'
    assert not any(path.endswith('/submit') for path in calls)


def test_data_authorization_and_unknown_wenyon_hash(monkeypatch):
    resources = [{'dataset_id': 'public-id', 'version_id': '1', 'role': 'task-public-data'}]
    _, rid = _run(resources=resources, allow_data=False)
    key = 'wenyon:public-id@1'
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('unauthorized CLI'))
    with pytest.raises(datasets.DataError) as exc:
        datasets.materialize('ev_ch', key, 'data1')
    assert exc.value.code == 'NOT_AUTHORIZED'
    db.execute('UPDATE authorizations SET allow_data_download=1 WHERE run_id=?', (rid,))
    calls = []
    def fake_cli(args, **kwargs):
        calls.append(args)
        output = __import__('pathlib').Path(args[args.index('--output-dir') + 1])
        (output / 'sample.txt').write_text('public data')
        return {'ok': True, 'exit_code': 0, 'stdout': '{}', 'stderr': ''}
    monkeypatch.setattr(compute, '_native', fake_cli)
    item = datasets.materialize('ev_ch', key, 'data1')
    assert item['status'] == 'unverified' and item['hash_semantics'] == 'unknown'
    assert (__import__('pathlib').Path(item['workspace_path']) / 'DATA_MANIFEST.json').is_file()
    assert datasets.materialize('ev_ch', key, 'data1')['deduplicated']
    assert len(calls) == 1
    root = __import__('pathlib').Path(item['workspace_path'])
    assert datasets.input_refs(root) == [item['materialization_id']]
    (root / 'sample.txt').chmod(0o644)
    (root / 'sample.txt').write_text('changed')
    with pytest.raises(datasets.DataError) as changed:
        datasets.input_refs(root)
    assert changed.value.code == 'DATA_CHANGED'


def test_data_authorization_is_bound_to_requesting_run(monkeypatch):
    resources = [{'dataset_id': 'public-id', 'version_id': '1', 'role': 'task-public-data'}]
    controller, authorized_run = _run(resources=resources, allow_data=True)
    # Simulate a recovered duplicate-active state; the endpoint must still enforce its Run identity.
    db.execute("UPDATE runs SET phase='finished' WHERE id=?", (authorized_run,))
    other_run = controller.create_run('ev_ch', mode='connected')['id']
    controller.authorize(other_run, 'model_roundtrip', True, 10, 60, 2,
                         'other goal', max_jobs=2, allow_data_download=False)
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?",
               (db.utcnow(), other_run))
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (authorized_run,))
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('unauthorized CLI'))
    with pytest.raises(datasets.DataError) as exc:
        datasets.materialize('ev_ch', 'wenyon:public-id@1', 'other-run', other_run)
    assert exc.value.code == 'NOT_AUTHORIZED'
    db.execute("UPDATE data_materializations SET operation_id='known'"
               " WHERE challenge_id='ev_ch' AND resource_key='wenyon:public-id@1'")
    with pytest.raises(datasets.DataError) as replay:
        datasets.materialize('ev_ch', 'wenyon:public-id@1', 'known', other_run)
    assert replay.value.code == 'NOT_AUTHORIZED'
    assert db.query_one("SELECT COUNT(*) AS n FROM data_materializations"
                        " WHERE operation_id='other-run'")['n'] == 0
    assert authorized_run != other_run


def test_wenyon_uses_dedicated_cli_and_isolated_home(monkeypatch, tmp_path):
    home = tmp_path / 'wenyon-home'
    settings = config.load_settings()
    settings['bohrium'].update(executable='/fixture/old-bohr',
                               wenyon_executable='/fixture/modern-bohr',
                               wenyon_home=str(home))
    config.save_settings(settings)
    calls = []
    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs['env']))
        return subprocess.CompletedProcess(cmd, 0, 'fixture', '')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert compute._native(['wenyon', 'dataset', 'download', '--help'])['ok']
    assert compute._native(['job', 'list'])['ok']
    assert calls[0][0][0] == '/fixture/modern-bohr'
    assert calls[0][1]['HOME'] == str(home)
    assert calls[0][1]['XDG_RUNTIME_DIR'] == str(home / '.run')
    assert calls[0][1]['XDG_STATE_HOME'] == str(home / '.local/state')
    assert calls[1][0][0] == '/fixture/old-bohr'
    assert calls[1][1]['HOME'] == os.environ.get('HOME')


def test_missing_wenyon_extension_is_classified_without_download(monkeypatch):
    resources = [{'dataset_id': 'public-id', 'version_id': '1', 'role': 'task-public-data'}]
    _, rid = _run(resources=resources, allow_data=True)
    monkeypatch.setattr(compute, '_native', lambda *a, **k:
                        {'ok': False, 'exit_code': 1, 'stdout': 'wenyon is not installed', 'stderr': ''})
    result = datasets.materialize('ev_ch', 'wenyon:public-id@1', 'missing-cli', rid)
    assert result['status'] == 'failed' and result['error_code'] == 'WENYON_CLI_UNAVAILABLE'


def test_wenyon_401_receipt_is_auth_required_without_materialization(monkeypatch):
    receipt = {'ok': False, 'exit_code': 3, 'stdout': '',
               'stderr': 'Error: API error: 401: Not authenticated'}
    resources = [{'dataset_id': 'public-id', 'version_id': '1', 'role': 'task-public-data'}]
    _, rid = _run(resources=resources, allow_data=True)
    calls = []
    def fake_cli(*args, **kwargs):
        calls.append(args)
        return receipt
    monkeypatch.setattr(compute, '_native', fake_cli)
    item = datasets.materialize('ev_ch', 'wenyon:public-id@1', 'auth-required', rid)
    assert item['status'] == 'failed' and item['error_code'] == 'AUTH_REQUIRED'
    assert item['total_bytes'] is None and 'workspace_path' not in item
    assert len(calls) == 1
    event = db.query_one("SELECT type FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 1", (rid,))
    assert event['type'] == 'data.access_denied'


def _synthetic_wenyon_fixture(root: Path) -> tuple[dict, dict]:
    """Create a v1 public manifest without committing a real download."""
    data = b'synthetic task data\n'
    output = root / 'resources' / 'README.md'
    output.parent.mkdir(parents=True)
    output.write_bytes(data)
    manifest = {'schema_version': 'playground-wenyon-public-manifest/v1',
                'source_question_id': 'synthetic-question',
                'resources': [{'staged_path': 'resources/README.md',
                               'sha256': hashlib.sha256(data).hexdigest(),
                               'size': len(data)}]}
    manifest_bytes = json.dumps(manifest, separators=(',', ':')).encode()
    (root / 'public-manifest.json').write_bytes(manifest_bytes)
    total = len(data) + len(manifest_bytes)
    resource = {'dataset_id': 'synthetic-v1', 'version_id': '1',
                'role': 'task-public-data', 'bytes': total,
                'public_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest()}
    receipt = {'ok': True, 'exit_code': 0, 'stderr': '',
               'stdout': {'downloaded': 2, 'failed': 0, 'bytes': total}}
    return resource, receipt


def test_wenyon_public_manifest_verifies_downloaded_files(monkeypatch, tmp_path):
    source = tmp_path / 'download'
    resource, receipt = _synthetic_wenyon_fixture(source)
    _, rid = _run(resources=[resource], allow_data=True)
    def fake_cli(args, **kwargs):
        staging = Path(args[args.index('--output-dir') + 1])
        shutil.copytree(source, staging, dirs_exist_ok=True)
        return receipt | {'stdout': json.dumps(receipt['stdout'])}
    monkeypatch.setattr(compute, '_native', fake_cli)
    item = datasets.materialize('ev_ch', datasets.resource_key(resource), 'synthetic-manifest', rid)
    assert item['status'] == 'verified' and item['hash_semantics'] == 'manifest_sha256'
    assert item['total_bytes'] == resource['bytes']
    receipt = json.loads(db.query_one('SELECT receipt_json FROM data_materializations WHERE id=?',
                                      (item['materialization_id'],))['receipt_json'])
    assert receipt['cli_result']['downloaded'] == 2
    assert receipt['cli_result']['failed'] == 0
    assert receipt['cli_stdout_sha256']
    root = Path(item['workspace_path'])
    assert datasets.input_refs(root) == [item['materialization_id']]
    assert hashlib.sha256((root / 'public-manifest.json').read_bytes()).hexdigest() == resource['public_manifest_sha256']


@pytest.mark.parametrize('tamper', ['expected_hash', 'resource_file'])
def test_wenyon_public_manifest_mismatch_is_not_materialized(monkeypatch, tamper, tmp_path):
    source = tmp_path / 'download'
    resource, _ = _synthetic_wenyon_fixture(source)
    resource = (resource | {'public_manifest_sha256': '0' * 64}
                if tamper == 'expected_hash' else resource)
    _, rid = _run(resources=[resource], allow_data=True)
    def fake_cli(args, **kwargs):
        staging = Path(args[args.index('--output-dir') + 1])
        shutil.copytree(source, staging, dirs_exist_ok=True)
        if tamper == 'resource_file':
            (staging / 'resources' / 'README.md').write_text('tampered')
        return {'ok': True, 'exit_code': 0, 'stdout': '{}', 'stderr': ''}
    monkeypatch.setattr(compute, '_native', fake_cli)
    item = datasets.materialize('ev_ch', datasets.resource_key(resource), 'wrong-manifest', rid)
    assert item['status'] == 'failed' and item['error_code'] == 'HASH_MISMATCH'
    assert 'workspace_path' not in item


def test_job_preflight_missing_module_network_and_image_api():
    with pytest.raises(job_preflight.PreflightError) as missing:
        job_preflight.check_sources({'run.py': b'import probe\n'}, 'python run.py')
    assert missing.value.code == 'MISSING_LOCAL_MODULE'
    with pytest.raises(job_preflight.PreflightError) as network:
        job_preflight.check_sources({'run.py': b'print(1)'}, 'pip install mpmath && python run.py')
    assert network.value.code == 'NETWORK_INSTALL_UNDECLARED'
    dynamic = job_preflight.check_sources({'run.py': b'__import__("unknown")\n'}, 'python run.py')
    assert dynamic['dynamic_import_unchecked']
    with pytest.raises(job_preflight.PreflightError) as facts:
        job_preflight.check_image_facts({'third_party': ['scipy']}, 'image:1',
            [{'module': 'scipy.sparse.linalg', 'attr': 'gmres', 'params': ['rtol']}], None)
    assert facts.value.code == 'IMAGE_FACTS_MISSING'
    assert facts.value.details['probe']['job']['max_run_time'] == 5
    with pytest.raises(job_preflight.PreflightError) as mismatch:
        job_preflight.check_image_facts({'third_party': ['scipy']}, 'image:1',
            [{'module': 'scipy.sparse.linalg', 'attr': 'gmres', 'params': ['rtol']}],
            {'packages': {'scipy': {'api': {'scipy.sparse.linalg.gmres': {'params': ['tol']}}}}})
    assert mismatch.value.code == 'API_MISMATCH'
    assert job_preflight.check_sources({'pkg/run.py': b'from .foo import bar\n',
        'pkg/foo.py': b'bar = 1\n'}, entry='pkg/run.py')['entry'] == 'pkg/run.py'
    assert job_preflight.check_sources({'pkg.v1/run.py': b'from .foo import bar\n',
        'pkg.v1/foo.py': b'bar = 1\n'}, entry='pkg.v1/run.py')['entry'] == 'pkg.v1/run.py'


async def test_termination_preserves_delivery_and_historical_projection():
    controller, rid = _run()
    for tid, status in [('done', 'reported_complete'), ('active', 'active')]:
        db.execute('INSERT INTO trials(id,run_id,goal,success_check,status,created_at)'
                   ' VALUES(?,?,?,?,?,?)', (tid, rid, tid, 's', status, db.utcnow()))
    db.append_event(rid, 'controller', 'trial.reported_complete', {'trial_id': 'done'}, trial_id='done')
    await controller.control(rid, 'terminate', None, 'terminate-ev')
    snap = controller.run_snapshot(rid)
    assert snap['end_reason'] == 'user_terminate'
    assert {t['id']: t['status'] for t in snap['trials']} == {'done': 'reported_complete', 'active': 'interrupted'}
    db.execute("UPDATE trials SET status='interrupted' WHERE id='done'")
    assert next(t for t in controller.run_snapshot(rid)['trials'] if t['id'] == 'done')['delivered']


async def test_v2_budget_is_run_local_and_intent_recoverable(monkeypatch):
    controller, rid = _run(max_trials=1)
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,status,created_at)'
               " VALUES('old',?,?,?,'reported_complete',?)", (rid, 'old goal', 's', db.utcnow()))
    db.execute("UPDATE runs SET current_trial_id='old' WHERE id=?", (rid,))
    monkeypatch.setattr(controller, '_make_prime', lambda settings: object())
    decision = {'schema_version': 2, 'decision_id': 'd1', 'run_id': rid,
                'observed_state_version': 0, 'summary': 'next', 'evidence_refs': [],
                'actions': [{'op': 'start_trial', 'goal': 'new goal', 'success_check': 's'}],
                'experience_proposals': []}
    await controller._apply_decision(rid, decision, {}, None, None)
    snap = controller.run_snapshot(rid)
    assert snap['gate'] == 'awaiting_budget' and snap['objective_md'] == 'original goal'
    assert json.loads(snap['pending_action_json'])['action']['goal'] == 'new goal'
    controller.update_budget(rid, max_trials=2)
    assert controller.run_snapshot(rid)['gate'] == 'open'
    assert config.load_settings()['run_defaults']['max_trials'] == 1


@pytest.mark.parametrize('resolution,expected_count', [('replay', 2), ('drop', 1)])
async def test_v2_pending_intent_resolution(monkeypatch, resolution, expected_count):
    controller, rid = _run(max_trials=1)
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,status,created_at)'
               " VALUES('old',?,?,?,'reported_complete',?)", (rid, 'old goal', 's', db.utcnow()))
    db.execute("UPDATE runs SET current_trial_id='old' WHERE id=?", (rid,))
    class FakePrime:
        async def prompt(self, *args):
            return SimpleNamespace(status='accepted', detail='fixture')
    monkeypatch.setattr(controller, '_make_prime', lambda settings: FakePrime())
    base = {'schema_version': 2, 'run_id': rid, 'observed_state_version': 0,
            'summary': 'next', 'evidence_refs': [], 'experience_proposals': []}
    await controller._apply_decision(rid, base | {'decision_id': 'first', 'actions': [
        {'op': 'start_trial', 'goal': 'saved goal', 'success_check': 's'}]}, {}, None, None)
    assert controller.run_snapshot(rid)['gate'] == 'awaiting_budget'
    controller.update_budget(rid, max_trials=2)
    pending = controller.run_snapshot(rid)['pending_action_json']
    assert pending and controller._lifecycle_packet(
        controller._require_run(rid), 'budget_granted')['pending_intent']
    await controller._apply_decision(rid, base | {'decision_id': 'resolve',
        'pending_intent_resolution': resolution,
        'actions': [{'op': 'wait', 'reason': 'fixture'}]}, {}, None, None)
    assert db.query_one('SELECT COUNT(*) AS n FROM trials WHERE run_id=?', (rid,))['n'] == expected_count
    assert controller.run_snapshot(rid)['pending_action_json'] is None
    assert controller.run_snapshot(rid)['objective_md'] == 'original goal'
    assert {row['goal'] for row in db.query('SELECT goal FROM trials WHERE run_id=?', (rid,))} == (
        {'old goal', 'saved goal'} if resolution == 'replay' else {'old goal'})


@pytest.mark.parametrize('signal,steps', [
    ('log_anchor', [{'step_type': 'observation', 'body': 'validated long execution line'}]),
    ('artifact_path', [{'step_type': 'artifact', 'artifact_path': 'results/output.txt'}]),
    ('paired_tool_calls', [{'step_type': 'tool_call', 'tool_call_id': 'x'},
                           {'step_type': 'tool_result', 'tool_call_id': 'x'}]),
    ('declared_cost', [{'step_type': 'observation', 'cost_usd': 0.01}]),
    ('timeline', [{'step_type': 'observation', 'timestamp': '2026-09-25T00:00:01Z'},
                  {'step_type': 'decision', 'timestamp': '2026-09-25T00:00:02Z'}]),
    ('substance', [{'step_type': 'observation', 'title': 'long enough observation'},
                   {'step_type': 'decision', 'title': 'long enough decision'}]),
])
def test_protocol_six_signal_examples(signal, steps):
    report = arm_admission.check(_bundle(steps), _protocol())
    assert report['signals'][signal]['ok'] is True
    assert report['verdict'] == 'admitted'


@pytest.mark.parametrize('signal,steps', [
    ('log_anchor', [{'step_type': 'observation', 'body': 'no matching log text'}]),
    ('artifact_path', [{'step_type': 'artifact', 'artifact_path': 'missing.txt'}]),
    ('paired_tool_calls', [{'step_type': 'tool_call', 'tool_call_id': 'x'}]),
    ('declared_cost', [{'step_type': 'observation', 'title': 'no declared cost'}]),
    ('timeline', [{'step_type': 'observation', 'timestamp': '2026-09-25T00:00:01Z'}]),
    ('substance', [{'step_type': 'observation', 'title': 'short'}]),
])
def test_protocol_six_signal_near_misses(signal, steps):
    report = arm_admission.check(_bundle(steps), _protocol())
    assert report['signals'][signal]['ok'] is False


def test_wenyon_401_idempotent_and_timeout_unknown(monkeypatch):
    resources = [{'dataset_id': 'public-id', 'version_id': '1', 'role': 'task-public-data'}]
    controller, rid = _run(resources=resources, allow_data=True)
    calls = []
    def denied(*args, **kwargs):
        calls.append(1)
        return {'ok': False, 'exit_code': 1, 'stdout': 'HTTP 401', 'stderr': ''}
    monkeypatch.setattr(compute, '_native', denied)
    failed = datasets.materialize('ev_ch', 'wenyon:public-id@1', 'denied')
    assert failed['status'] == 'failed' and failed['error_code'] == 'AUTH_REQUIRED'
    assert datasets.materialize('ev_ch', 'wenyon:public-id@1', 'denied')['deduplicated']
    assert len(calls) == 1
    assert any(e['type'] == 'data.access_denied' for e in db.events_after(rid, 0))
    monkeypatch.setattr(compute, '_native', lambda *a, **k:
                        {'ok': False, 'unknown': True, 'exit_code': None, 'stdout': '', 'stderr': ''})
    unknown = datasets.materialize('ev_ch', 'wenyon:public-id@1', 'timeout')
    assert unknown['status'] == 'unknown' and unknown['error_code'] == 'TIMEOUT'
    packet = controller._lifecycle_packet(controller._require_run(rid), 'fixture')
    assert any(item['status'] == 'unknown' and item['error_code'] == 'TIMEOUT'
               for item in packet['data_status'])


def test_url_hash_mismatch_does_not_enter_store(monkeypatch):
    resources = [{'url': 'https://fixture.invalid/data', 'sha256': '0' * 64,
                  'bytes': 4, 'role': 'task-public-data'}]
    _run(resources=resources, allow_data=True)
    class Response(io.BytesIO):
        headers = {'Content-Length': '4'}
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: Response(b'data'))
    item = datasets.materialize('ev_ch', datasets.resource_key(resources[0]), 'url-hash')
    assert item['status'] == 'failed' and item['error_code'] == 'HASH_MISMATCH'
    assert not (config.DATA_DIR / 'data-store').exists()


def test_run_local_bohr_wenyon_route_uses_actual_workspace_path(monkeypatch):
    resources = [{'dataset_id': 'public-id', 'version_id': '1', 'role': 'task-public-data'}]
    _, rid = _run(resources=resources, allow_data=True)
    trial = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / 't'
    trial.mkdir(parents=True)
    db.execute("UPDATE runs SET current_trial_id='t' WHERE id=?", (rid,))
    def fake_cli(args, **kwargs):
        output = Path(args[args.index('--output-dir') + 1])
        (output / 'data.txt').write_text('123')
        return {'ok': True, 'exit_code': 0, 'stdout': '{}', 'stderr': ''}
    monkeypatch.setattr(compute, '_native', fake_cli)
    result = compute.cli(rid, ['wenyon', 'dataset', 'download', 'public-id',
                               '--version', '1', '--output-dir', 'ignored', '--output', 'json'], str(trial))
    assert result['status'] == 'unverified'
    assert Path(result['workspace_path']).is_dir()
    assert 'ignored' not in result['workspace_path']


def test_materialized_job_input_records_refs_and_rejects_tampering(monkeypatch):
    resources = [{'dataset_id': 'public-id', 'version_id': '1', 'role': 'task-public-data'}]
    _, rid = _run(resources=resources, allow_data=True)
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,created_at)"
               " VALUES('data-trial',?,?,?,?)", (rid, 'g', 's', db.utcnow()))
    db.execute("UPDATE runs SET current_trial_id='data-trial' WHERE id=?", (rid,))
    def fake_native(args, **kwargs):
        if args[:3] == ['wenyon', 'dataset', 'download']:
            (Path(args[args.index('--output-dir') + 1]) / 'data.txt').write_text('fixture data')
            return {'ok': True, 'exit_code': 0, 'stdout': '{}', 'stderr': ''}
        return {'ok': True, 'exit_code': 0, 'stdout': 'JobId: 123', 'stderr': ''}
    monkeypatch.setattr(compute, '_native', fake_native)
    item = datasets.materialize('ev_ch', 'wenyon:public-id@1', 'data-job', rid)
    source = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / 'data-trial' / 'input'
    source.mkdir(parents=True)
    shutil.copytree(item['workspace_path'], source / 'data')
    (source / 'run.py').write_text('print("fixture")')
    spec = {'command': 'python run.py', 'image_address': 'fixture/image:1',
            'machine_type': 'c2_m2_cpu', 'max_run_time': 5}
    compute.submit(rid, 'job-with-data', spec, str(source))
    row = db.query_one("SELECT data_refs_json FROM compute_jobs WHERE operation_id='job-with-data'")
    assert json.loads(row['data_refs_json']) == [item['materialization_id']]
    (source / 'data' / 'data.txt').chmod(0o644)
    (source / 'data' / 'data.txt').write_text('changed')
    with pytest.raises(compute.ComputeError) as exc:
        compute.submit(rid, 'tampered-job', spec, str(source))
    assert exc.value.code == 'DATA_CHANGED'
    assert db.query_one("SELECT COUNT(*) AS n FROM compute_jobs WHERE operation_id='tampered-job'")['n'] == 0


def test_probe_purpose_is_counted_and_old_submit_reports_unchecked_api(monkeypatch):
    _, rid = _run(max_trials=1)
    db.execute("UPDATE runs SET current_trial_id='probe-trial' WHERE id=?", (rid,))
    source = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / 'probe-trial' / 'input'
    source.mkdir(parents=True)
    (source / 'cs_probe.py').write_text('print("fixture")')
    calls = []
    def fake_native(*args, **kwargs):
        calls.append(1)
        return {'ok': True, 'exit_code': 0, 'stdout': f'JobId: {len(calls)}', 'stderr': ''}
    monkeypatch.setattr(compute, '_native', fake_native)
    spec = {'command': 'python cs_probe.py', 'image_address': 'fixture/image:1',
            'machine_type': 'c2_m2_cpu', 'max_run_time': 5}
    compute.submit(rid, 'probe-job', spec, str(source), {'purpose': 'probe'})
    row = db.query_one("SELECT purpose FROM compute_jobs WHERE operation_id='probe-job'")
    assert row['purpose'] == 'probe'
    compute.submit(rid, 'old-job', spec, str(source))
    assert compute.list_jobs(rid)['reserved_jobs'] == 2
    reports = [e['payload'] for e in db.events_after(rid, 0) if e['type'] == 'job.preflight']
    assert len(reports) == 2
    assert all(item['report']['api_checked'] is False for item in reports)


def test_compute_preflight_rejects_before_job_reservation(monkeypatch):
    _, rid = _run()
    db.execute("UPDATE runs SET current_trial_id='t' WHERE id=?", (rid,))
    source = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / 't' / 'input'
    source.mkdir(parents=True)
    (source / 'run.py').write_text('import probe\n')
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('must not dispatch'))
    spec = {'command': 'python run.py', 'image_address': 'fixture/image:1',
            'machine_type': 'c2_m2_cpu', 'max_run_time': 5}
    with pytest.raises(compute.ComputeError) as exc:
        compute.submit(rid, 'missing-module', spec, str(source))
    assert exc.value.code == 'MISSING_LOCAL_MODULE'
    assert db.query_one('SELECT COUNT(*) AS n FROM compute_jobs')['n'] == 0
    (source / 'run.py').write_text('print(1)\n')
    with pytest.raises(compute.ComputeError) as facts:
        compute.submit(rid, 'missing-facts', spec, str(source),
            {'api_checks': [{'module': 'scipy.sparse.linalg', 'attr': 'gmres', 'params': ['rtol']}]})
    assert facts.value.code == 'IMAGE_FACTS_MISSING'
    assert db.query_one('SELECT COUNT(*) AS n FROM compute_jobs')['n'] == 0


async def test_v2_finish_requires_objective_assessment(monkeypatch):
    controller, rid = _run()
    monkeypatch.setattr(controller, '_make_prime', lambda settings: object())
    monkeypatch.setattr(controller, '_defer_finish_for_curation', lambda *a: False)
    base = {'schema_version': 2, 'decision_id': 'finish-ev', 'run_id': rid,
            'observed_state_version': 0, 'summary': 'finished', 'evidence_refs': [],
            'experience_proposals': []}
    await controller._apply_decision(rid, base | {'actions': [{'op': 'finish', 'reason': 'r'}]}, {}, None, None)
    assert controller.run_snapshot(rid)['phase'] == 'running'
    await controller._apply_decision(rid, base | {'actions': [{'op': 'finish', 'reason': 'r',
        'objective_assessment': {'status': 'achieved', 'evidence_refs': [], 'remaining_md': ''}}]}, {}, None, None)
    assert controller.run_snapshot(rid)['phase'] == 'running'
    await controller._apply_decision(rid, base | {'actions': [{'op': 'finish', 'reason': 'partial evidence',
        'objective_assessment': {'status': 'partial', 'evidence_refs': [], 'remaining_md': 'unresolved'}}]}, {}, None, None)
    snap = controller.run_snapshot(rid)
    assert snap['phase'] == 'finished' and snap['objective_status'] == 'partial'


async def test_review_metrics_and_read_only_csv(monkeypatch, tmp_path):
    controller, rid = _run()
    review_id = 'rev_ev'
    db.execute("INSERT INTO review_requests(id,run_id,source,status,trigger,created_at,updated_at)"
               " VALUES(?,?,'shadow','pending','passive',?,?)",
               (review_id, rid, db.utcnow(), db.utcnow()))
    async def fake_impl(*args):
        db.execute("UPDATE review_requests SET status='done',frame_json='{}' WHERE id=?", (review_id,))
        db.append_event(rid, 'brain', 'brain.usage.updated',
                        {'review_id': review_id, 'usage': {'last': {'totalTokens': 12,
                        'inputTokens': 10, 'cachedInputTokens': 2, 'outputTokens': 2}}})
    monkeypatch.setattr(controller, '_run_one_review_impl', fake_impl)
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (review_id,))
    await controller._run_one_review(rid, req, None, None)
    metric = next(e['payload'] for e in db.events_after(rid, 0) if e['type'] == 'brain.review_metrics')
    assert metric['review_id'] == review_id and metric['tokens_last_total'] == 12
    assert metric['outcome'] == 'silent' and metric['trace_reads'] == 0
    csv = tmp_path / 'metrics.csv'
    script = Path(__file__).resolve().parents[1] / 'checks' / 'measure_brain_context.py'
    result = subprocess.run([sys.executable, str(script), str(config.DB_PATH), '--csv', str(csv)],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['measured'] == 1 and review_id in csv.read_text()


async def test_review_metrics_missing_usage_stays_null(monkeypatch):
    controller, rid = _run()
    review_id = 'rev_without_usage'
    db.execute("INSERT INTO review_requests(id,run_id,source,status,trigger,created_at,updated_at)"
               " VALUES(?,?,'shadow','pending','passive',?,?)",
               (review_id, rid, db.utcnow(), db.utcnow()))
    async def fake_impl(*args):
        db.execute("UPDATE review_requests SET status='done',frame_json='{}' WHERE id=?", (review_id,))
    monkeypatch.setattr(controller, '_run_one_review_impl', fake_impl)
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (review_id,))
    await controller._run_one_review(rid, req, None, None)
    metric = next(e['payload'] for e in db.events_after(rid, 0) if e['type'] == 'brain.review_metrics')
    assert metric['tokens_last_total'] is None
    assert metric['tokens_input'] is None
    assert metric['tokens_cached'] is None
    assert metric['tokens_output'] is None
    assert metric['packet_bytes'] == 2


def test_legacy_run_budget_keeps_v1_global_semantics():
    controller, rid = _run()
    snapshot = json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (rid,))['config_snapshot'])
    snapshot.pop('lifecycle_version')
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?', (json.dumps(snapshot), rid))
    controller.update_budget(rid, max_trials=4)
    assert config.load_settings()['run_defaults']['max_trials'] == 4
    assert controller.run_snapshot(rid)['budget']['max_trials'] == 4


@pytest.mark.parametrize('filename', ['result_package.json', 'submission.csv'])
def test_nonzip_proxy_gate_precedes_submission_reservation(monkeypatch, filename):
    resources = [{'dataset_id': 'public-id', 'version_id': '1', 'role': 'task-public-data'}]
    _, rid = _run(resources=resources)
    trial = 'nonzip_proxy'
    base = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / trial
    base.mkdir(parents=True)
    (base / filename).write_text('fixture')
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,created_at) VALUES(?,?,?,?,?)',
               (trial, rid, 'g', 's', db.utcnow()))
    platform_calls = []
    platform = SimpleNamespace(name='fixture', is_demo=False)
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    monkeypatch.setattr(mailboxes, '_perform_submission', lambda *a: platform_calls.append(a))
    db.execute("INSERT INTO mailboxes(id,role,email,platform,secret_ref,status,submission_limit,is_demo,created_at)"
               " VALUES('proxy_mb','experiment','fixture@example.test','fixture','local:fixture','active',2,0,?)",
               (db.utcnow(),))
    assert mailboxes.preflight_submission(rid, trial, None)['admission']['verdict'] == 'not_applicable'
    assert mailboxes.preflight_submission(rid, trial, None)['error_code'] == 'PROXY_EVIDENCE'
    with pytest.raises(mailboxes.MailboxError) as error:
        mailboxes.submit_experiment(rid, trial, None, 'blocked-'+filename)
    assert error.value.code == 'PROXY_EVIDENCE'
    assert db.query_one('SELECT COUNT(*) AS n FROM submissions')['n'] == 0
    assert db.query_one("SELECT submissions_used FROM mailboxes WHERE id='proxy_mb'")[0] == 0
    assert platform_calls == []
    mailboxes.submit_experiment(rid, trial, None, 'allowed-'+filename,
                                allow_proxy_evidence=True)
    event = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='submission.created' ORDER BY seq DESC LIMIT 1", (rid,))
    assert json.loads(event['payload'])['allow_proxy_evidence'] is True
    assert db.query_one('SELECT COUNT(*) AS n FROM submissions')['n'] == 1
    assert len(platform_calls) == 1


def test_nonzip_official_data_and_unknown_follow_bundle_proxy_semantics(monkeypatch):
    _, rid = _run()
    base = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / 't'
    base.mkdir(parents=True)
    (base / 'result_package.json').write_text('{}')
    monkeypatch.setattr(mailboxes, '_data_inputs', lambda *a: {'evidence_class': 'official_data', 'materializations': []})
    assert mailboxes.preflight_submission(rid, 't', None)['error_code'] is None
    monkeypatch.setattr(mailboxes, '_data_inputs', lambda *a: {'evidence_class': 'unknown', 'materializations': []})
    assert mailboxes.preflight_submission(rid, 't', None)['error_code'] is None


@pytest.mark.parametrize('length,expected', [(11, False), (12, True), (80, True), (81, False)])
def test_log_anchor_exact_trimmed_line_bounds(length, expected):
    line = 'x' * length
    report = arm_admission.check(_bundle([{'step_type': 'observation', 'body': '  '+line+'  '}],
                                         log_text=line+'\n'), _protocol())
    assert report['signals']['log_anchor']['ok'] is expected


def test_log_anchor_missing_thresholds_notes_defaults():
    protocol = _protocol()
    thresholds = protocol['trace_anti_fraud']['admission']['thresholds']
    for name in ('log_anchor_min_chars', 'log_anchor_max_chars', 'log_anchor_fields'):
        thresholds.pop(name)
    report = arm_admission.check(_bundle([{'step_type': 'observation', 'body': 'x'*12}],
                                         log_text='x'*12), protocol)
    assert report['signals']['log_anchor']['ok'] is True
    assert sum('使用默认值' in note for note in report['notes']) == 3


def _pending_run(controller, rid):
    pending = {'decision_id': 'first', 'action': {'op': 'start_trial', 'goal': 'next', 'success_check': 's'},
               'state_version': 0}
    db.execute("UPDATE runs SET gate='awaiting_budget',pending_action_json=? WHERE id=?",
               (json.dumps(pending), rid))
    return pending


def test_drop_pending_intent_wakes_running_brain_and_paused_only_clears():
    controller, rid = _run()
    pending = _pending_run(controller, rid)
    controller.drop_pending_intent(rid, 'user changed direction')
    snap = controller.run_snapshot(rid)
    assert snap['gate'] == 'open' and snap['pending_action_json'] is None
    req = db.query_one("SELECT * FROM review_requests WHERE run_id=? AND trigger='pending_intent_dropped'", (rid,))
    assert req['status'] == 'pending' and 'user changed direction' in req['frame_json']
    packet = controller._lifecycle_packet(controller._require_run(rid), 'pending_intent_dropped',
                                          user_guidance=json.loads(req['frame_json'])['user_guidance'])
    assert pending['action']['goal'] in packet['user_guidance']
    db.execute("UPDATE runs SET phase='finished' WHERE id=?", (rid,))
    controller2 = RunController()
    rid2 = controller2.create_run('ev_ch', mode='connected')['id']
    _pending_run(controller2, rid2)
    db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid2,))
    controller2.drop_pending_intent(rid2, 'paused cleanup')
    assert db.query_one("SELECT COUNT(*) AS n FROM review_requests WHERE run_id=? AND trigger='pending_intent_dropped'", (rid2,))['n'] == 0


async def test_pending_drop_review_limit_pauses_instead_of_hanging(monkeypatch):
    controller, rid = _run()
    _pending_run(controller, rid)
    db.execute('UPDATE runs SET brain_reviews_used=? WHERE id=?',
               (config.load_settings()['run_defaults']['max_brain_reviews'], rid))
    controller.drop_pending_intent(rid, 'quota')
    req = db.query_one("SELECT * FROM review_requests WHERE run_id=? AND trigger='pending_intent_dropped'", (rid,))
    await controller._run_one_review_impl(rid, req, object(), None)
    assert controller.run_snapshot(rid)['phase'] == 'paused'
    assert db.query_one("SELECT COUNT(*) AS n FROM events WHERE run_id=? AND type='run.review_limit'", (rid,))['n'] == 1
    assert db.query_one('SELECT status FROM review_requests WHERE id=?', (req['id'],))['status'] == 'obsolete'


async def test_awaiting_budget_user_steer_is_reviewed_and_auto_is_obsolete(monkeypatch):
    controller, rid = _run()
    _pending_run(controller, rid)
    seen = []
    class Brain:
        async def review(self, session, packet):
            seen.append(packet)
            yield SimpleNamespace(type='decision', payload={'decision': {
                'schema_version': 2, 'decision_id': 'steer-decision', 'run_id': rid,
                'observed_state_version': packet['state_version'], 'summary': 'keep gate',
                'evidence_refs': [], 'actions': [{'op': 'start_trial', 'goal': 'new', 'success_check': 's'}],
                'pending_intent_resolution': 'revise', 'experience_proposals': []}})
    auto_id = controller._enqueue_lifecycle(rid, 'trial.stalled')
    await controller._run_one_review_impl(rid, db.query_one('SELECT * FROM review_requests WHERE id=?', (auto_id,)), Brain(), None)
    auto = db.query_one('SELECT status,error FROM review_requests WHERE id=?', (auto_id,))
    assert auto['status'] == 'obsolete' and '预算' in auto['error']
    user_id = controller._enqueue_lifecycle(rid, 'user_steer', user_guidance='reconsider')
    await controller._run_one_review_impl(rid, db.query_one('SELECT * FROM review_requests WHERE id=?', (user_id,)), Brain(), None)
    assert db.query_one('SELECT status FROM review_requests WHERE id=?', (user_id,))['status'] == 'done'
    assert seen[0]['gate'] == 'awaiting_budget' and seen[0]['pending_intent']['action']['goal'] == 'next'
    rejected = [json.loads(row['payload']) for row in db.query("SELECT payload FROM events WHERE run_id=? AND type='brain.action_rejected'", (rid,))]
    assert any('awaiting_budget' in item.get('reason', '') for item in rejected)


async def test_awaiting_budget_brain_can_drop_pending_intent(monkeypatch):
    controller, rid = _run()
    _pending_run(controller, rid)
    decision = {'schema_version': 2, 'decision_id': 'drop-while-waiting', 'run_id': rid,
                'observed_state_version': 0, 'summary': 'drop', 'evidence_refs': [],
                'pending_intent_resolution': 'drop', 'actions': [{'op': 'wait', 'reason': 'drop'}],
                'experience_proposals': []}
    await controller._apply_decision(rid, decision, {}, None, None)
    snap = controller.run_snapshot(rid)
    assert snap['pending_action_json'] is None and snap['gate'] == 'open'
    assert db.query_one("SELECT COUNT(*) AS n FROM events WHERE run_id=? AND type='run.pending_intent_resolved'", (rid,))['n'] == 1
    assert db.query_one("SELECT COUNT(*) AS n FROM review_requests WHERE run_id=? AND trigger='pending_intent_dropped'", (rid,))['n'] == 1


async def test_awaiting_budget_brain_can_finish_with_objective_assessment(monkeypatch):
    controller, rid = _run()
    _pending_run(controller, rid)
    monkeypatch.setattr(controller, '_defer_finish_for_curation', lambda *a: False)
    decision = {'schema_version': 2, 'decision_id': 'finish-while-waiting', 'run_id': rid,
                'observed_state_version': 0, 'summary': 'partial result', 'evidence_refs': [],
                'pending_intent_resolution': 'revise', 'actions': [{'op': 'finish', 'reason': 'done',
                'objective_assessment': {'status': 'partial', 'evidence_refs': [],
                                         'remaining_md': 'Further work remains'}}],
                'experience_proposals': []}
    await controller._apply_decision(rid, decision, {}, None, None)
    assert controller.run_snapshot(rid)['phase'] == 'finished'
    assert controller.run_snapshot(rid)['objective_status'] == 'partial'
