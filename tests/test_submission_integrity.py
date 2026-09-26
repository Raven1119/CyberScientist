import threading
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from cyberscientist import config, db, mailboxes
from test_mailboxes import _seed_challenge, _make_run, _make_package


def setup_run(limit=1):
    _seed_challenge()
    rid = _make_run(limit)
    path = _make_package(rid)
    mailboxes.register_experiment(1)
    return rid, path


def test_unknown_consumes_budget_and_same_operation_checks_payload(monkeypatch):
    rid, path = setup_run()
    platform = mailboxes._platform()
    def lost(*a, **kw): raise TimeoutError('response lost')
    monkeypatch.setattr(platform, 'submit_package', lost)
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    sub = mailboxes.submit_experiment(rid, 'trial_mb1', path, 'lost')
    assert sub['status'] == 'unknown'
    assert db.query_one('SELECT submissions_used FROM mailboxes')['submissions_used'] == 1
    with pytest.raises(mailboxes.MailboxError, match='授权'):
        mailboxes.submit_experiment(rid, 'trial_mb1', path, 'another')
    _make_package(rid, content='changed')
    with pytest.raises(mailboxes.MailboxError, match='幂等'):
        mailboxes.submit_experiment(rid, 'trial_mb1', path, 'lost')


def test_parallel_requests_cannot_exceed_run_budget(monkeypatch):
    rid, path = setup_run()
    platform = mailboxes._platform()
    entered, release = threading.Event(), threading.Event()
    def slow(*a, **kw):
        entered.set(); assert release.wait(3)
        return {'accepted': True, 'receipt': 'fake-only'}
    monkeypatch.setattr(platform, 'submit_package', slow)
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(mailboxes.submit_experiment, rid, 'trial_mb1', path, 'first')
        assert entered.wait(3)
        try:
            with pytest.raises(mailboxes.MailboxError, match='授权'):
                mailboxes.submit_experiment(rid, 'trial_mb1', path, 'second')
        finally: release.set()
        assert first.result()['status'] == 'submitted'


def test_adapter_gets_frozen_bytes_and_attempt_survives_timeout(monkeypatch):
    from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform
    rid, path = setup_run()
    original = (config.WORKSPACE_DIR / path).read_bytes()
    platform = BohriumPlaygroundPlatform('https://unused.invalid')
    platform.name = 'demo'; platform.is_demo = True
    def http(method, url, **kwargs):
        if url.endswith('/attempts'):
            (config.WORKSPACE_DIR / path).write_bytes(b'changed')
            return {'id': 'known-attempt'}
        raise TimeoutError('submit receipt lost')
    monkeypatch.setattr(platform, '_http', http)
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    sub = mailboxes.submit_experiment(rid, 'trial_mb1', path, 'stages')
    assert sub['status'] == 'unknown' and sub['platform_ref'] == 'known-attempt'
    assert sub['stage'] == 'submit_sent'
    assert (config.WORKSPACE_DIR / sub['package_path']).read_bytes() == original


def test_partial_registration_persists_each_success(monkeypatch):
    platform = mailboxes._platform()
    native = platform.register_account
    calls = []
    def partial():
        calls.append(1)
        if len(calls) == 2: raise TimeoutError('response lost')
        return native()
    monkeypatch.setattr(platform, 'register_account', partial)
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    result = mailboxes.register_experiment(3)
    assert len(result['items']) == 1 and result['errors']
    assert len(mailboxes.list_mailboxes()['items']) == 1


@pytest.mark.parametrize('failed_stage', ['create_sent','upload_sent','submit_sent'])
def test_each_lost_receipt_keeps_attempt_and_reservation(monkeypatch, failed_stage):
    from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform
    rid, path = setup_run()
    package = config.WORKSPACE_DIR / path
    package = package.with_suffix('.zip')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('arm_manifest.json', json.dumps({
            'arm_version': '1.1', 'entrypoint': 'src/reproduce.py',
            'execution': {'log_path': 'results/run.log'},
            'trace': {'files': ['traces/trace.jsonl']}}))
        archive.writestr('src/reproduce.py', 'print("fixture")\n')
        archive.writestr('results/run.log', 'fixture log\n')
        archive.writestr('characterization.json', '{}')
        archive.writestr('traces/trace.jsonl', '\n'.join(json.dumps(row) for row in [
            {'step_type': 'tool_call', 'title': 'fixture call', 'tool_call_id': 'x'},
            {'step_type': 'tool_result', 'title': 'fixture result', 'tool_call_id': 'x'}]))
    package.write_bytes(buf.getvalue())
    platform = BohriumPlaygroundPlatform('https://unused.invalid')
    platform.name='demo'; platform.is_demo=True
    calls=[]
    def http(method, url, **kwargs):
        calls.append(url)
        phase='create_sent' if url.endswith('/attempts') else 'upload_sent' if url.endswith('/bundle') else 'submit_sent'
        if phase == failed_stage: raise TimeoutError('lost')
        return {'id':'original-attempt'}
    monkeypatch.setattr(platform,'_http',http)
    monkeypatch.setattr(mailboxes,'_platform',lambda:platform)
    relative=package.relative_to(config.WORKSPACE_DIR).as_posix()
    sub=mailboxes.submit_experiment(rid,'trial_mb1',relative,'stage-loss')
    assert sub['status']=='unknown' and sub['stage']==failed_stage
    assert sub['platform_ref']==(None if failed_stage=='create_sent' else 'original-attempt')
    count=len(calls)
    retry=mailboxes.submit_experiment(rid,'trial_mb1',relative,'stage-loss')
    assert retry['deduplicated'] and len(calls)==count


async def test_slow_registration_does_not_block_health(monkeypatch):
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app
    platform=mailboxes._platform()
    native=platform.register_account
    entered, release=threading.Event(),threading.Event()
    def slow():
        entered.set(); assert release.wait(5)
        return native()
    monkeypatch.setattr(platform,'register_account',slow)
    monkeypatch.setattr(mailboxes,'_platform',lambda:platform)
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://local') as client:
        request=asyncio.create_task(client.post('/api/v1/mailboxes/experiment/register',json={'count':1}))
        try:
            assert await asyncio.to_thread(entered.wait,3)
            response=await asyncio.wait_for(client.get('/api/v1/health'),0.5)
            assert response.status_code==200
        finally: release.set()
        assert (await request).status_code==200
