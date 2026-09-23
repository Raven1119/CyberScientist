"""Synthetic CLI receipts only; never call a model or Bohrium."""
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from cyberscientist import compute, config, db, observation
from cyberscientist.controller import RunController
from test_collaboration import _seed_challenge


@pytest.fixture
def run(monkeypatch):
    _seed_challenge()
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
