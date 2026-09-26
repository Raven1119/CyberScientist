"""Synthetic CLI receipts only; never call a model or Bohrium."""
import json
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from cyberscientist import compute, config, db, observation, trace_projection
from cyberscientist.controller import RunController
from test_collaboration import _seed_challenge


@pytest.fixture
def run(monkeypatch):
    _seed_challenge()
    settings = config.load_settings()
    settings['bohrium']['project_id'] = 88474
    config.save_settings(settings)
    c = RunController()
    rid = c.create_run('COLLAB_CH', mode='connected')['id']
    c.authorize(rid, 'compute', True, 20, 120, 0, '', max_jobs=3)
    db.execute("UPDATE runs SET phase='running',current_trial_id='trial_fixture',started_at=? WHERE id=?", (db.utcnow(), rid))
    source = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / 'trial_fixture' / 'input'
    source.mkdir(parents=True)
    (source / 'work.py').write_text('print("bounded fixture")')
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('unexpected external call'))
    return rid, source


def spec(**changes):
    return dict(command='python work.py', image_address='fixture/image:1', machine_type='c8_m8_cpu', max_run_time=10, **changes)


def receipt(stdout='', ok=True):
    return dict(ok=ok, exit_code=0, stdout=stdout, stderr='')


def remote(rid, status='Running'):
    row = compute.list_jobs(rid)['items'][0]
    return receipt(json.dumps([{'id': 123, 'jobName': row['spec']['job_name'], 'status': status}]))


@pytest.mark.parametrize('mode', ['cli_error', 'empty_output', 'file'])
def test_download_records_real_files_or_failure(run, monkeypatch, mode):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('JobId: 123'))
    compute.submit(rid, 'retrieval-fixture', spec(), str(source))
    destination = source.parent / 'retrieved'
    def native(args, **kwargs):
        if mode == 'file':
            root = Path(args[args.index('-o') + 1])
            (root / 'output.txt').write_bytes(b'verified fixture')
            return receipt('download completed')
        if mode == 'empty_output':
            return receipt('download completed')
        return receipt('Error: json: cannot unmarshal object into Go struct field RespErr.error of type string', False)
    monkeypatch.setattr(compute, '_native', native)
    compute.cli(rid, ['job', 'download', '-j', '123', '-o', str(destination)], str(source.parent))
    job = compute.list_jobs(rid)['items'][0]
    expected = 'retrieved' if mode == 'file' else 'failed'
    assert job['retrieval_status'] == expected
    if mode == 'file':
        assert job['receipt']['retrieval']['download']['files'] == [{
            'path': 'output.txt', 'bytes': len(b'verified fixture'),
            'sha256': __import__('hashlib').sha256(b'verified fixture').hexdigest()}]
    else:
        assert job['receipt']['retrieval']['download']['files'] == []
    events = db.query('SELECT type,payload FROM events WHERE run_id=? AND type IN (?,?)',
                      (rid, 'job.retrieved', 'job.retrieval_failed'))
    assert len(events) == 1 and events[0]['type'] == ('job.retrieved' if mode == 'file' else 'job.retrieval_failed')
    assert 'accessKey' not in events[0]['payload']


@pytest.mark.parametrize('steps,expected', [
    ([('download', True), ('log', False)], 'retrieved'),
    ([('log', False)], 'failed'),
    ([('log', False), ('download', True)], 'retrieved'),
    ([('download', True), ('download', False)], 'retrieved'),
    ([('log', True), ('log', False)], 'failed'),
    ([('download', False), ('log', True)], 'retrieved'),
])
def test_retrieval_summary_keeps_successful_download(run, monkeypatch, steps, expected):
    rid, source = run
    settings = config.load_settings()
    settings['bohrium']['access_key_secret_ref'] = 'local:fixture-key'
    config.save_settings(settings)
    config.update_secret('fixture-key', 'secret-value-for-test')
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('JobId: 123'))
    compute.submit(rid, 'retrieval-sequence', spec(), str(source))
    db.append_event(rid, 'controller', 'job.observed',
                    {'operation_id': 'retrieval-sequence', 'platform_job_id': 123,
                     'status': 'Finished'})
    for index, (operation, succeeds) in enumerate(steps):
        destination = source.parent / f'out-{index}'
        def native(args, **kwargs):
            if succeeds:
                Path(args[args.index('-o') + 1], 'secret-value-for-test.txt').write_bytes(b'fixture result')
                return receipt('download completed')
            return {'ok': False, 'exit_code': 0, 'stdout': 'Error: fixture',
                    'stderr': 'accessKey=secret-value-for-test'}
        monkeypatch.setattr(compute, '_native', native)
        compute.cli(rid, ['job', operation, '-j', '123', '-o', str(destination)],
                    str(source.parent))
    job = compute.list_jobs(rid)['items'][0]
    assert job['retrieval_status'] == expected
    retrieval = job['receipt']['retrieval']
    for operation, succeeds in dict(steps).items():
        assert retrieval[operation]['status'] == ('retrieved' if succeeds else 'failed')
    assert retrieval['download_ever_retrieved'] is any(
        operation == 'download' and succeeds for operation, succeeds in steps)
    events = db.query("SELECT type,payload FROM events WHERE run_id=? AND type IN ('job.retrieved','job.retrieval_failed') ORDER BY seq", (rid,))
    assert [row['type'] for row in events] == [
        'job.retrieved' if succeeds else 'job.retrieval_failed' for _, succeeds in steps]
    assert [json.loads(row['payload'])['operation'] for row in events] == [op for op, _ in steps]
    assert 'secret-value-for-test' not in json.dumps(job['receipt'])
    assert all('secret-value-for-test' not in row['payload'] for row in events)
    cutoff = db.query_one('SELECT MAX(seq) AS n FROM events WHERE run_id=?', (rid,))['n']
    assert observation.job_states(rid, cutoff)[0]['retrieval_status'] == expected
    projected = trace_projection.project(rid, None, cutoff, {})
    terminal = next(step for step in projected if step.get('title') == 'Bohrium Job terminal state')
    assert f'结果取回：{expected}' in terminal['tool_output']


def test_native_zero_exit_unmarshal_error_is_failed_and_redacted(monkeypatch):
    settings = config.load_settings()
    settings['bohrium']['access_key_secret_ref'] = 'local:fixture-key'
    config.save_settings(settings)
    config.update_secret('fixture-key', 'secret-value-for-test')
    error = ('Error: json: cannot unmarshal object into Go struct field '
             'RespErr.error of type string; accessKey=secret-value-for-test')
    monkeypatch.setattr(compute.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a, 0, error, ''))
    result = compute._native(['job', 'download', '-j', '123', '-o', '/tmp/fixture'])
    assert result['exit_code'] == 0 and result['ok'] is False
    assert 'secret-value-for-test' not in json.dumps(result)


def test_job_client_uses_legacy_api_host_without_changing_wenyon(monkeypatch):
    settings = config.load_settings()
    settings['bohrium']['host_overrides'] = {}
    config.save_settings(settings)
    hosts = []
    def native(cmd, **kwargs):
        hosts.append((cmd[1:], kwargs['env']['OPENAPI_HOST']))
        return subprocess.CompletedProcess(cmd, 0, '', '')
    monkeypatch.setattr(compute.subprocess, 'run', native)
    compute._native(['job', 'list'])
    compute._native(['wenyon', 'dataset', 'download', '--help'])
    assert hosts == [(['job', 'list'], 'https://openapi.dp.tech'),
                     (['wenyon', 'dataset', 'download', '--help'], 'https://open.bohrium.com')]


def test_legacy_single_retrieval_receipt_preserves_download_evidence(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('JobId: 123'))
    compute.submit(rid, 'legacy-retrieval', spec(), str(source))
    old = {'retrieval': {'operation': 'download', 'status': 'retrieved',
                         'files': [{'path': 'old.txt', 'sha256': 'a' * 64, 'bytes': 1}],
                         'exit_code': 0}}
    db.execute("UPDATE compute_jobs SET retrieval_status='retrieved',receipt_json=?"
               " WHERE operation_id='legacy-retrieval'", (json.dumps(old),))
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('Error: fixture', False))
    compute.cli(rid, ['job', 'log', '-j', '123', '-o', str(source.parent / 'log-failure')],
                str(source.parent))
    item = compute.list_jobs(rid)['items'][0]
    assert item['retrieval_status'] == 'retrieved'
    assert item['receipt']['retrieval']['download']['status'] == 'retrieved'
    assert item['receipt']['retrieval']['log']['status'] == 'failed'


def test_probe_facts_are_read_from_legacy_job_archive(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('JobId: 123'))
    compute.submit(rid, 'archive-probe', spec(), str(source), {'purpose': 'probe'})
    facts = {'packages': {'scipy': {'version': '1.10.1'}}}
    def native(args, **kwargs):
        archive = Path(args[args.index('-o') + 1]) / '123' / 'out.zip'
        archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive, 'w') as out:
            out.writestr('results/facts.json', json.dumps(facts))
            out.writestr('results/data-proof.json', '{}')
        return receipt('Downloading outfile')
    monkeypatch.setattr(compute, '_native', native)
    destination = source.parent / 'probe-results'
    compute.cli(rid, ['job', 'download', '-j', '123', '-o', str(destination)],
                str(source.parent))
    assert compute.list_jobs(rid)['items'][0]['retrieval_status'] == 'retrieved'
    observed = db.query_one("SELECT facts_json FROM image_facts WHERE source_operation_id='archive-probe'")
    assert observed and json.loads(observed['facts_json']) == facts
    assert db.query_one("SELECT COUNT(*) AS n FROM events WHERE run_id=? AND type='image_facts.observed'", (rid,))['n'] == 1


def test_retrieval_column_migration_is_idempotent():
    db.init_db()
    db.init_db()
    columns = db.query('PRAGMA table_info(compute_jobs)')
    assert [row['name'] for row in columns].count('retrieval_status') == 1


def test_create_is_idempotent_and_quota_survives_unknown(run, monkeypatch):
    rid, source = run; calls = []
    monkeypatch.setattr(compute, '_native', lambda args, **k: calls.append(args) or receipt('Error: no response', False))
    assert compute.submit(rid, 'create1', spec(), str(source))['status'] == 'unknown'
    assert compute.submit(rid, 'create1', spec(), str(source))['deduplicated']
    with pytest.raises(compute.ComputeError, match='先对账'):
        compute.submit(rid, 'create2', spec(), str(source))
    assert len(calls) == 1
    assert compute.list_jobs(rid)['reserved_jobs'] == 1
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('[]'))
    compute.reconcile(rid)
    assert compute.list_jobs(rid)['active_or_unknown'] == 1


def test_concurrent_create_reserves_before_dispatch(run, monkeypatch):
    rid, source = run; entered = Event(); release = Event(); calls = []
    def native(args, **kw):
        calls.append(args); entered.set(); assert release.wait(3)
        return receipt('JobId: 123')
    monkeypatch.setattr(compute, '_native', native)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(compute.submit, rid, 'one', spec(), str(source))
        assert entered.wait(3)
        try:
            with pytest.raises(compute.ComputeError) as caught:
                compute.submit(rid, 'two', spec(), str(source))
            assert caught.value.code == 'CREATE_UNKNOWN'
        finally:
            release.set()
        assert first.result()['platform_job_id'] == 123
    assert len(calls) == 1


def test_stop_receipt_not_terminal_and_never_resubmitted(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('JobId: 123'))
    compute.submit(rid, 'one', spec(), str(source))
    calls = []
    def native(args, **kw):
        calls.append(args)
        return remote(rid) if args[1] == 'list' else receipt('accepted')
    monkeypatch.setattr(compute, '_native', native)
    compute.stop(rid, 'one'); compute.stop(rid, 'one'); compute.reconcile(rid)
    assert calls.count(['job', 'terminate', '123']) == 1
    assert compute.list_jobs(rid)['items'][0]['status'] == 'stop_unknown'
    monkeypatch.setattr(compute, '_native', lambda *a, **k: remote(rid, 'Stopped'))
    compute.reconcile(rid)
    assert compute.list_jobs(rid)['active_or_unknown'] == 0
    monkeypatch.setattr(compute, '_native', lambda *a, **k: remote(rid, 'Running'))
    compute.reconcile(rid)
    assert compute.list_jobs(rid)['items'][0]['status'] == 'Stopped'


def test_reconciliation_wins_race_with_late_create_receipt(run, monkeypatch):
    rid, source = run
    def native(*a, **kw):
        # Remote observation arrived before submit's timeout receipt.
        db.execute("UPDATE compute_jobs SET platform_job_id=123,status='Finished' WHERE operation_id='one'")
        return dict(ok=False, unknown=True, stdout='', stderr='timeout')
    monkeypatch.setattr(compute, '_native', native)
    result = compute.submit(rid, 'one', spec(), str(source))
    assert (result['platform_job_id'], result['status']) == (123, 'Finished')


@pytest.mark.parametrize('change', [{'max_run_time': 9999}, {'machine_type': 'c32_m32_cpu'}, {'disk_size': 11}, {'nnode': 2}, {'max_reschedule_times': 1}])
def test_resource_admission_rejects_before_native_call(run, change):
    rid, source = run
    with pytest.raises(compute.ComputeError):
        compute.submit(rid, 'one', spec() | change, str(source))
    assert compute.list_jobs(rid)['reserved_jobs'] == 0


@pytest.mark.parametrize('requested_id', [88474, '88474', None])
def test_string_setting_emits_native_integer_project_id(run, monkeypatch, requested_id):
    rid, source = run
    settings = config.load_settings()
    settings['bohrium']['project_id'] = '88474'
    config.save_settings(settings)

    def native(args, **kwargs):
        job_json = json.loads(Path(args[3]).read_text())
        assert job_json['project_id'] == 88474
        assert type(job_json['project_id']) is int
        return receipt('JobId: 123')

    monkeypatch.setattr(compute, '_native', native)
    job_spec = spec() if requested_id is None else spec(project_id=requested_id)
    assert compute.submit(rid, 'project_type', job_spec, str(source))['status'] == 'accepted'


@pytest.mark.parametrize('requested_id', [True, '088474', 88475])
def test_invalid_or_foreign_project_rejected_before_reservation(run, requested_id):
    rid, source = run
    settings = config.load_settings()
    settings['bohrium']['project_id'] = '88474'
    config.save_settings(settings)
    with pytest.raises(compute.ComputeError) as exc:
        compute.submit(rid, 'project_type', spec(project_id=requested_id), str(source))
    assert exc.value.code == 'INVALID_PROJECT'
    assert compute.list_jobs(rid)['reserved_jobs'] == 0


def test_known_native_project_decode_failure_is_not_started(run, monkeypatch):
    rid, source = run
    error = ('failed to parse config file: json: cannot unmarshal string '
             'into Go struct field JobJson.project_id of type int')
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt(error, False))
    result = compute.submit(rid, 'new_parse_failure', spec(), str(source))
    assert result['status'] == 'not_started'
    assert compute.list_jobs(rid)['reserved_jobs'] == 0


def test_historical_local_decode_failure_can_be_settled_with_event(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('Error: no response', False))
    assert compute.submit(rid, 'old_parse_failure', spec(), str(source))['status'] == 'unknown'
    row = db.query_one('SELECT spec_json FROM compute_jobs WHERE operation_id=?',
                       ('old_parse_failure',))
    old_spec = json.loads(row['spec_json'])
    old_spec['project_id'] = '88474'
    error = ('failed to parse config file: json: cannot unmarshal string '
             'into Go struct field JobJson.project_id of type int')
    db.execute('UPDATE compute_jobs SET spec_json=?,receipt_json=? WHERE operation_id=?',
               (json.dumps(old_spec), json.dumps(receipt(error, False)),
                'old_parse_failure'))
    assert compute.resolve_local_parse_failure(rid, 'old_parse_failure')['status'] == 'not_started'
    assert compute.resolve_local_parse_failure(rid, 'old_parse_failure')['deduplicated']
    assert compute.list_jobs(rid)['reserved_jobs'] == 0
    assert any(e['type'] == 'job.not_started_confirmed'
               for e in db.events_after(rid, 0))


def test_ambiguous_create_cannot_be_settled_as_local_parse_failure(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('Error: no response', False))
    compute.submit(rid, 'ambiguous', spec(), str(source))
    with pytest.raises(compute.ComputeError) as exc:
        compute.resolve_local_parse_failure(rid, 'ambiguous')
    assert exc.value.code == 'INSUFFICIENT_EVIDENCE'
    assert compute.list_jobs(rid)['reserved_jobs'] == 1


def test_paused_and_foreign_job_mutations_are_rejected(run):
    rid, source = run
    db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
    with pytest.raises(compute.ComputeError, match='未运行'):
        compute.submit(rid, 'one', spec(), str(source))
    with pytest.raises(compute.ComputeError, match='未登记'):
        compute.cli(rid, ['job', 'terminate', '999'], str(source))


def test_input_is_frozen_and_credentials_are_never_uploaded(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(config, 'resolve_secret', lambda _: 'fixture-account-secret')
    (source / 'work.py').write_text('fixture-account-secret')
    result = compute.submit(rid, 'one', spec(), str(source))
    assert result['status'] == 'not_started'
    assert 'fixture-account-secret' not in json.dumps(result)
    assert compute.list_jobs(rid)['reserved_jobs'] == 0


def test_native_exit_zero_error_is_failure_and_key_redacted(monkeypatch):
    settings = config.load_settings(); settings['bohrium']['executable'] = '/fixture/bohr'
    config.save_settings(settings)
    monkeypatch.setattr(config, 'resolve_secret', lambda _: 'fixture-key')
    calls = []
    def native(cmd, **kw):
        calls.append(cmd)
        assert kw['env']['BOHR_ACCESS_KEY'] == 'fixture-key'
        return subprocess.CompletedProcess(cmd, 0, 'Error: ?accessKey=fixture-key', '')
    monkeypatch.setattr(subprocess, 'run', native)
    r = compute._native(['version'])
    assert not r['ok'] and 'fixture-key' not in json.dumps(r) and len(calls) == 1


def test_job_state_is_reconstructed_at_frame_cutoff(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('JobId: 123'))
    compute.submit(rid, 'one', spec(), str(source))
    cutoff = db.query_one('SELECT MAX(seq) AS s FROM events WHERE run_id=?', (rid,))['s']
    monkeypatch.setattr(compute, '_native', lambda *a, **k: remote(rid, 'Failed'))
    compute.reconcile(rid)
    assert observation.job_states(rid, cutoff)[0]['status'] == 'accepted'
    assert observation.job_states(rid, cutoff + 1)[0]['status'] == 'Failed'


async def test_capability_api_binds_run_and_rejects_revoked_token(run, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app
    from cyberscientist import collab
    rid, source = run
    app = create_app()
    with db.transaction() as conn:
        token = collab.issue_token(conn, rid, 'executor', 'fixture', 1)
    calls = []
    monkeypatch.setattr(compute, '_native', lambda args, **k: calls.append(args) or receipt('JobId: 123'))
    payload = dict(action='submit', operation_id='http1', spec=spec(), input_directory=str(source), run_id='foreign')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://local') as client:
        r = await client.post('/api/v1/tools/job', json=payload, headers={'Authorization': 'Bearer ' + token})
        assert r.status_code == 200, r.text
        assert r.json()['platform_job_id'] == 123
        again = await client.post('/api/v1/tools/job', json=payload, headers={'Authorization': 'Bearer ' + token})
        assert again.json()['deduplicated']
        with db.transaction() as conn:
            collab.revoke_run_tokens(conn, rid)
        denied = await client.post('/api/v1/tools/job', json=payload, headers={'Authorization': 'Bearer ' + token})
        assert denied.status_code == 401
    assert len(calls) == 1 and compute.list_jobs(rid)['reserved_jobs'] == 1


def test_legacy_run_cannot_treat_untracked_jobs_as_free_quota(run):
    rid, source = run
    row = db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (rid,))
    snapshot = json.loads(row['config_snapshot']); snapshot.pop('compute_policy_version')
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?', (json.dumps(snapshot), rid))
    with pytest.raises(compute.ComputeError) as exc:
        compute.submit(rid, 'legacy', spec(), str(source))
    assert exc.value.code == 'LEGACY_RUN'


def test_restart_marks_inflight_unknown_without_retry(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('JobId: 123'))
    compute.submit(rid, 'one', spec(), str(source))
    db.execute("UPDATE compute_jobs SET status='submitting' WHERE operation_id='one'")
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('restart must not mutate cloud'))
    compute.recover_pending()
    assert compute.list_jobs(rid)['items'][0]['status'] == 'unknown'
    assert compute.list_jobs(rid)['active_or_unknown'] == 1


def test_concurrency_and_lifetime_quota_are_separate(run, monkeypatch):
    rid, source = run; ids = iter([1, 2, 3])
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt(f'JobId: {next(ids)}'))
    compute.submit(rid, 'one', spec(), str(source)); compute.submit(rid, 'two', spec(), str(source))
    with pytest.raises(compute.ComputeError) as exc:
        compute.submit(rid, 'three', spec(), str(source))
    assert exc.value.code == 'CONCURRENCY_LIMIT'
    db.execute("UPDATE compute_jobs SET status='Failed' WHERE operation_id='one'")
    compute.submit(rid, 'three', spec(), str(source))
    db.execute("UPDATE compute_jobs SET status='Stopped'")
    with pytest.raises(compute.ComputeError) as exc:
        compute.submit(rid, 'four', spec(), str(source))
    assert exc.value.code == 'JOB_LIMIT'
