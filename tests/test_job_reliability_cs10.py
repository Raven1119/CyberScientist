"""Synthetic before/after failures: native v4 IDs, paging and durable replay."""
import json
from datetime import datetime, timedelta, timezone
import pytest
from cyberscientist import compute, config, db, environment_saves
from test_compute_gateway import run, spec, receipt

def modern():
    settings = config.load_settings()
    settings['bohrium'].update(wenyon_executable='synthetic-modern', access_key_secret_ref='local:synthetic', project_id=88474)
    config.save_settings(settings)
    config.update_secret('synthetic', 'synthetic-never-logged-key')

def accepted(jid=123):
    return receipt(json.dumps({'ok': True, 'data': {'jobId': jid, 'bohrJobId': jid + 1000}}))

def age_job(operation):
    old = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
    db.execute('UPDATE compute_jobs SET created_at=?,unknown_since=? WHERE operation_id=?', (old, old, operation))

def test_modern_upload_and_small_create_use_json_ids_and_both_id_domains(run, monkeypatch):
    rid, source = run
    modern()
    calls = []
    monkeypatch.setattr(compute, '_native', lambda args, **kwargs: calls.append((args, kwargs)) or accepted())
    result = compute.submit(rid, 'native-json', spec(), str(source))
    assert result['platform_job_id'] == 123 and result['status'] == 'accepted'
    assert db.query_one('SELECT bohr_job_id FROM compute_jobs')['bohr_job_id'] == 1123
    args, kwargs = calls[0]
    assert '--input_directory' in args and '-p' not in args and kwargs['modern'] is True
    assert result['receipt']['transport'] == 'bohr_v4'

def test_create_timeout_attaches_exact_owned_name_without_replaying(run, monkeypatch):
    rid, source = run
    modern()
    calls = []
    monkeypatch.setattr(compute, '_native', lambda *args, **kwargs: calls.append(args) or receipt('', False))
    compute.submit(rid, 'timed-out', spec(), str(source))
    row = compute.list_jobs(rid)['items'][0]
    assert not compute.occupies_slot(row)
    monkeypatch.setattr(compute, '_job_page', lambda page: {'page': 1, 'total_pages': 1, 'items': [
        {'id': 123, 'bohrId': 1123, 'jobName': row['spec']['job_name'], 'status': 2}]})
    result = compute.reconcile(rid, allow_retry=True)['items'][0]
    assert result['platform_job_id'] == 123 and result['status'] == 'Finished' and len(calls) == 1

def test_absence_on_complete_pages_reposts_new_identity_and_original_frozen_bytes(run, monkeypatch):
    rid, source = run
    modern()
    calls = []
    def native(args, **kwargs):
        calls.append(args)
        if len(calls) == 1: return receipt('', False)
        frozen = __import__('pathlib').Path(args[args.index('--input_directory') + 1])
        assert (frozen / 'work.py').read_text() == 'print("bounded fixture")'
        return accepted(456)
    monkeypatch.setattr(compute, '_native', native)
    compute.submit(rid, 'absent-parent', spec(), str(source))
    age_job('absent-parent')
    (source / 'work.py').write_text('changed after first dispatch')
    monkeypatch.setattr(compute, '_job_page', lambda page: {'page': 1, 'total_pages': 1, 'total': 0, 'items': []})
    compute.reconcile(rid, allow_retry=True)
    rows = compute.list_jobs(rid)['items']
    assert len(rows) == 2 and rows[0]['retry_operation_id'] == rows[1]['operation_id']
    assert rows[1]['retry_of'] == 'absent-parent' and rows[1]['platform_job_id'] == 456
    assert rows[0]['spec']['job_name'] != rows[1]['spec']['job_name']
    compute.reconcile(rid, allow_retry=True)
    assert len(calls) == 2

def test_paging_timeout_retries_failed_page_then_attaches_beyond_old_three_page_cap(run, monkeypatch):
    rid, source = run
    modern()
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('', False))
    compute.submit(rid, 'far-page', spec(), str(source))
    row = compute.list_jobs(rid)['items'][0]
    calls = []
    def page(number):
        calls.append(number)
        if calls == [1, 2]: raise compute.ComputeError('JOB_OBSERVATION_UNKNOWN', 'fake timeout')
        return {'page': number, 'total_pages': 4, 'items': ([{'id': 123, 'bohrId': 1123,
            'jobName': row['spec']['job_name'], 'status': 2}] if number == 4 else [])}
    monkeypatch.setattr(compute, '_job_page', page)
    monkeypatch.setattr(compute.time, 'sleep', lambda seconds: None)
    result = compute.reconcile(rid, allow_retry=True)['items'][0]
    assert calls == [1, 2, 2, 3, 4] and result['platform_job_id'] == 123

def test_paging_unknown_or_truncated_never_replays_and_does_not_hold_slot(run, monkeypatch):
    rid, source = run
    modern()
    calls = []
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt('', False))
    compute.submit(rid, 'query-unknown', spec(), str(source)); age_job('query-unknown')
    monkeypatch.setattr(compute, '_job_page', lambda page: {'page': page, 'total_pages': 101, 'items': []})
    compute.reconcile(rid, allow_retry=True)
    row = compute.list_jobs(rid)['items'][0]
    assert row['status'] == 'unknown' and not compute.occupies_slot(row) and len(calls) == 1

@pytest.mark.parametrize('changes,code', [({'result_path': '/data'}, 'INVALID_RESULT_PATH'),
    ({'command': 'python score.py <base64plan>'}, 'INVALID_SPEC')])
def test_observed_09_invalid_path_and_command_are_rejected_before_reservation(run, monkeypatch, changes, code):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('must reject before dispatch'))
    with pytest.raises(compute.ComputeError) as error:
        compute.submit(rid, 'original-09-error', dict(spec(), **changes), str(source))
    assert error.value.code == code and compute.list_jobs(rid)['items'] == []

def test_new_private_build_uses_native_raw_dockerfile_route_and_safe_name(run, monkeypatch):
    rid, _ = run
    modern(); db.execute('UPDATE authorizations SET max_environment_saves=1 WHERE run_id=?', (rid,))
    calls = []
    def native(args, **kwargs):
        calls.append((args, kwargs))
        return receipt(json.dumps({'ok': True, 'data': {'response': {'id': 123, 'status': 1}}}))
    monkeypatch.setattr(compute, '_native', native)
    result = environment_saves.save(rid, 'MIXED_Name', 'FROM fixture/public:1\nRUN echo ok', 'public software', 'python3 --version')
    assert result['status'] == 'building' and result['resource_id'] == '123'
    args, kwargs = calls[0]
    name = args[args.index('--name') + 1]
    assert name == name.lower() and '.' not in name and kwargs['modern'] is True
    dockerfile = __import__('pathlib').Path(args[args.index('--dockerfile') + 1]).read_text()
    assert dockerfile.startswith('FROM fixture/public:1') and 'RUN python3 --version' in dockerfile

@pytest.mark.parametrize('damage', ['file', 'mode', 'manifest', 'spec'])
def test_corrupt_original_frozen_input_is_never_replayed(run, monkeypatch, damage):
    rid, source = run
    modern(); calls = []
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt('', False))
    compute.submit(rid, 'corrupt-parent', spec(), str(source)); age_job('corrupt-parent')
    root = config.DATA_DIR / 'job-inputs' / 'corrupt-parent'
    if damage == 'file': (root / 'input/work.py').write_text('changed scientific input')
    elif damage == 'mode': (root / 'input/work.py').chmod(0o777)
    elif damage == 'manifest': (root / 'manifest.json').write_text('{}')
    else: (root / 'job.json').write_text('{}')
    monkeypatch.setattr(compute, '_job_page', lambda page: {'page': 1, 'total_pages': 1, 'total': 0, 'items': []})
    compute.reconcile(rid, allow_retry=True); compute.reconcile(rid, allow_retry=True)
    assert len(calls) == 1
    assert db.query_one('SELECT retry_error FROM compute_jobs')['retry_error'] == 'FROZEN_INPUT_CHANGED'

def test_short_duplicate_or_changing_pages_cannot_prove_absence(monkeypatch):
    for pages in [
        [{'page': 1, 'total_pages': 1, 'total': 1, 'items': []}],
        [{'page': 1, 'total_pages': 2, 'total': 2, 'items': [{'id': 7}]},
         {'page': 2, 'total_pages': 2, 'total': 2, 'items': [{'id': 7}]}],
        [{'page': 1, 'total_pages': 2, 'total': 2, 'items': [{'id': 7}]},
         {'page': 2, 'total_pages': 2, 'total': 3, 'items': [{'id': 8}]}]]:
        monkeypatch.setattr(compute, '_job_page', lambda number: pages[number - 1])
        remote, metadata = compute._read_job_pages([{'spec': {'job_name': 'absent'}}])
        assert metadata['complete'] is False and metadata['absence_does_not_prove_not_created']

@pytest.mark.parametrize('use_modern', [False, True])
def test_actual_query_client_and_billing_source_are_attributed_separately(run, monkeypatch, use_modern):
    rid, source = run
    modern()
    if not use_modern:
        settings = config.load_settings(); settings['bohrium']['wenyon_executable'] = ''; config.save_settings(settings)
    monkeypatch.setattr(compute, '_native', lambda *a, **k: accepted() if use_modern else receipt('JobId: 123'))
    compute.submit(rid, 'route-fact', spec(), str(source))
    row = compute.list_jobs(rid)['items'][0]
    item = {'id': 123, 'jobName': row['spec']['job_name'], 'status': 2, 'cost': '0.01'}
    if not use_modern: item['bohrId'] = 1123  # IDs cannot establish the actual API route.
    monkeypatch.setattr(compute, '_job_page', lambda page: {'page': 1, 'total_pages': 1, 'items': [item]})
    compute.reconcile(rid, allow_retry=True)
    facts = json.loads(db.query_one("SELECT payload FROM events WHERE type='environment.host_observed'")['payload'])
    assert facts['client'] == ('bohr_v4' if use_modern else 'legacy_job')
    assert facts['host'] == ('https://open.bohrium.com' if use_modern else 'https://openapi.dp.tech')
    billing = compute.list_jobs(rid)['items'][0]['receipt']['billing']
    assert billing['source'] == ('/openapi/v4/job/list:cost' if use_modern else '/openapi/v1/job/list:cost')

@pytest.mark.asyncio
async def test_new_unknown_reconciliation_is_independent_of_a_blocked_old_poll(run, monkeypatch):
    import asyncio
    from threading import Event
    from cyberscientist import job_recovery
    from cyberscientist.controller import RunController
    rid, source = run
    modern()
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('', False))
    compute.submit(rid, 'urgent-create', spec(), str(source))
    blocked, release, urgent = Event(), Event(), Event()
    def reconcile(identifier, **kwargs):
        if identifier == 'old-slow-run':
            blocked.set(); assert release.wait(3)
        else: urgent.set()
    monkeypatch.setattr(compute, 'reconcile', reconcile)
    old_poll = asyncio.create_task(job_recovery.reconcile('old-slow-run'))
    while not blocked.is_set(): await asyncio.sleep(.001)
    await job_recovery.advance(RunController())
    try:
        assert await asyncio.to_thread(urgent.wait, 1)
    finally:
        release.set(); await old_poll; await job_recovery.drain()

@pytest.mark.asyncio
async def test_two_consecutive_failures_reach_executor_outbox_and_success_resets_streak(monkeypatch):
    from test_final_candidate_integrity import _run_with_scorer
    from test_executor_repair import _controller
    from cyberscientist import job_recovery
    rid, tid, root, *_ = _run_with_scorer()
    db.execute("UPDATE runs SET mode='connected' WHERE id=?", (rid,))
    db.execute('UPDATE authorizations SET max_jobs=3 WHERE run_id=?', (rid,))
    source = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / tid / 'input'
    source.mkdir(); (source / 'work.py').write_text('print("synthetic")')
    modern(); monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('', False))
    compute.submit(rid, 'failure-one', spec(), str(source)); compute.submit(rid, 'failure-two', spec(), str(source))
    controller, executor = _controller(rid)
    monkeypatch.setattr(compute, 'reconcile', lambda rid, **kwargs: {})
    await job_recovery.advance(controller); await job_recovery.drain()
    assert len(executor.prompts) == 1 and '授权沙箱' in executor.prompts[0][1]
    assert 'CONSECUTIVE_CREATE_FAILURES' in executor.prompts[0][1]
    await job_recovery.advance(controller); await job_recovery.drain()
    assert len(executor.prompts) == 1
    monkeypatch.setattr(compute, '_native', lambda *a, **k: accepted())
    compute.submit(rid, 'successful-create', spec(), str(source))
    count = len(db.query("SELECT 1 FROM events WHERE type='job.sandbox_fallback_advice'"))
    compute._maybe_fallback_advice(rid, tid)
    assert len(db.query("SELECT 1 FROM events WHERE type='job.sandbox_fallback_advice'")) == count

@pytest.mark.parametrize('damage', ['file', 'mode'])
def test_retry_copy_cannot_bless_input_changed_after_original_verification(run, monkeypatch, damage):
    rid, source = run
    modern(); calls = []
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt('', False))
    compute.submit(rid, 'changing-parent', spec(), str(source)); age_job('changing-parent')
    original_verify = compute._verify_frozen_retry
    verifications = []
    def verify(row, frozen):
        original = original_verify(row, frozen)
        verifications.append(row['operation_id'])
        if len(verifications) == 1:
            if damage == 'file': (frozen / 'work.py').write_text('changed after verification')
            else: (frozen / 'work.py').chmod(0o777)
        return original
    monkeypatch.setattr(compute, '_verify_frozen_retry', verify)
    monkeypatch.setattr(compute, '_job_page', lambda page: {'page': 1, 'total_pages': 1, 'total': 0, 'items': []})
    compute.reconcile(rid, allow_retry=True)
    assert len(calls) == 1 and len(compute.list_jobs(rid)['items']) == 1
    assert db.query_one('SELECT retry_error FROM compute_jobs')['retry_error'] == 'FROZEN_INPUT_CHANGED'

@pytest.mark.parametrize('when', ['observation', 'reservation', 'dispatch'])
def test_original_job_found_wins_over_pending_retry_at_every_local_boundary(run, monkeypatch, when):
    from cyberscientist import compute_budget
    rid, source = run
    modern(); calls = []
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt('', False))
    compute.submit(rid, 'found-parent', spec(), str(source)); age_job('found-parent')
    db.execute("UPDATE compute_jobs SET status='not_started',retry_operation_id='persisted-retry' WHERE operation_id='found-parent'")
    row = compute.list_jobs(rid)['items'][0]
    def found():
        db.execute("UPDATE compute_jobs SET status='Running',platform_job_id=123,bohr_job_id=1123 WHERE operation_id='found-parent'")
    if when == 'observation':
        monkeypatch.setattr(compute, '_job_page', lambda page: {'page': 1, 'total_pages': 1, 'total': 1,
            'items': [{'id': 123, 'bohrId': 1123, 'jobName': row['spec']['job_name'], 'status': 1}]})
        compute.reconcile(rid, allow_retry=True)
    else:
        if when == 'reservation':
            rate = compute_budget.rate
            monkeypatch.setattr(compute_budget, 'rate', lambda *a, **k: (found(), rate(*a, **k))[1])
        else:
            file_sha = compute._file_sha256
            def sha(path):
                value = file_sha(path)
                if path.parent.name == 'persisted-retry': found()
                return value
            monkeypatch.setattr(compute, '_file_sha256', sha)
        compute._dispatch_retry(rid, row, 'persisted-retry')
    assert len(calls) == 1
    parent = db.query_one("SELECT * FROM compute_jobs WHERE operation_id='found-parent'")
    assert parent['platform_job_id'] == 123 and parent['status'] == 'Running'
    if when == 'dispatch':
        child = db.query_one("SELECT * FROM compute_jobs WHERE operation_id='persisted-retry'")
        assert child['status'] == 'not_started'
    else: assert len(compute.list_jobs(rid)['items']) == 1

def test_untracked_read_only_reconciliation_cannot_create_paid_retry(run, monkeypatch):
    rid, source = run
    modern(); calls = []
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt('', False))
    compute.submit(rid, 'read-only-parent', spec(), str(source)); age_job('read-only-parent')
    monkeypatch.setattr(compute, '_job_page', lambda page: {'page': 1, 'total_pages': 1, 'total': 0, 'items': []})
    compute.reconcile(rid)
    assert len(calls) == 1 and db.query_one('SELECT status FROM compute_jobs')['status'] == 'unknown'

@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_worker', [False, True])
async def test_cancelled_reconciliation_stays_tracked_until_actual_thread_finishes(run, monkeypatch, cancel_worker):
    import asyncio
    from threading import Event
    from cyberscientist import job_recovery, power
    from cyberscientist.controller import RunController
    rid, _ = run
    db.execute("UPDATE runs SET phase='paused',gate='closed' WHERE id=?", (rid,))
    entered, release = Event(), Event()
    def reconcile(identifier, **kwargs):
        assert kwargs['allow_retry'] is True
        entered.set(); assert release.wait(5)
        return {'actual_worker_finished': True}
    monkeypatch.setattr(compute, 'reconcile', reconcile)
    caller = asyncio.create_task(job_recovery.reconcile(rid))
    while not entered.is_set(): await asyncio.sleep(.001)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError): await caller
    if cancel_worker: job_recovery.ACTIVE[rid].cancel()
    try:
        report = await power.safe_shutdown(RunController(), timeout=.01)
        assert not report['can_shutdown'] and rid in job_recovery.ACTIVE
        assert any(e['error'] == 'job_reconciliation_still_active' for e in report['errors'])
    finally:
        release.set(); await job_recovery.drain(); await asyncio.sleep(0)
    assert rid not in job_recovery.ACTIVE
    assert (await power.safe_shutdown(RunController(), timeout=.1))['can_shutdown']

def test_frozen_manifest_hash_and_parse_use_the_same_bytes(run, monkeypatch):
    from pathlib import Path
    rid, source = run
    modern(); monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('', False))
    compute.submit(rid, 'manifest-buffer', spec(), str(source))
    row = compute.list_jobs(rid)['items'][0]
    frozen = config.DATA_DIR / 'job-inputs/manifest-buffer/input'
    read = Path.read_bytes
    def replace_after_read(path):
        content = read(path)
        if path == frozen.parent / 'manifest.json':
            changed = json.loads(content)
            changed['file_modes']['work.py'] = 0o777
            path.write_text(json.dumps(changed))
            (frozen / 'work.py').chmod(0o777)
        return content
    monkeypatch.setattr(Path, 'read_bytes', replace_after_read)
    with pytest.raises(compute.ComputeError) as error:
        compute._verify_frozen_retry(row, frozen)
    assert error.value.code == 'FROZEN_INPUT_CHANGED'

def test_modern_transport_exception_retains_recovery_identity_and_releases_slot(run, monkeypatch):
    rid, source = run
    modern()
    def timeout(*args, **kwargs): raise TimeoutError('synthetic transport exception')
    monkeypatch.setattr(compute, '_native', timeout)
    result = compute.submit(rid, 'transport-exception', spec(), str(source))
    assert result['status'] == 'unknown' and result['receipt']['transport'] == 'bohr_v4'
    assert not compute.occupies_slot(compute.list_jobs(rid)['items'][0])
    assert db.query_one("SELECT 1 FROM events WHERE type='job.reconciliation_scheduled'")
