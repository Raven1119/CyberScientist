import pytest
from cyberscientist import config, redeploy


def setup_target(monkeypatch):
    monkeypatch.setattr(redeploy, 'git', lambda *a: 'a' * 40 if a[0] == 'rev-parse' else '')


def test_shutdown_failure_never_signals_or_starts(monkeypatch):
    setup_target(monkeypatch)
    calls = []
    monkeypatch.setattr(redeploy, 'request', lambda *a, **k: calls.append(a[1]) or
                        {'can_shutdown': False, 'errors': [{'error': 'close_unknown'}], 'message': 'still active'})
    monkeypatch.setattr(redeploy.os, 'kill', lambda *a: pytest.fail('must not signal'))
    result = redeploy.redeploy(9999)
    assert result['status'] == 'failed' and result['phase'] == 'shutdown'
    assert calls == ['/api/v1/system/safe-shutdown']


def test_dirty_checkout_stops_before_shutdown(monkeypatch):
    monkeypatch.setattr(redeploy, 'git', lambda *a: 'a' * 40 if a[0] == 'rev-parse' else 'M src/file.py')
    monkeypatch.setattr(redeploy, 'request', lambda *a, **k: pytest.fail('must not touch backend'))
    assert redeploy.redeploy(9999)['phase'] == 'target'


def test_experience_changing_target_refused(monkeypatch):
    def git(*args):
        return 'a' * 40 if args[0] == 'rev-parse' else 'experience/global/x.md' if args[0] == 'diff' else ''
    monkeypatch.setattr(redeploy, 'git', git)
    result = redeploy.redeploy(9999, 'old-tag')
    assert result['status'] == 'failed' and '经验' in result['reason']


@pytest.mark.parametrize('identity', [{}, {'process_id': 1}, {'process_id': '123'}])
def test_missing_or_unsafe_pid_rejected(identity):
    with pytest.raises(RuntimeError):
        redeploy.process_identity(identity)


def test_preflight_failure_stops_before_digest(monkeypatch):
    setup_target(monkeypatch)
    calls = []
    class Process:
        pid = 12345
        def poll(self): return None
    monkeypatch.setattr(redeploy, 'process_identity', lambda value: (12344, 'start'))
    monkeypatch.setattr(redeploy.os, 'kill', lambda *a: None)
    monkeypatch.setattr(redeploy, 'alive', lambda *a: False)
    monkeypatch.setattr(redeploy.subprocess, 'Popen', lambda *a, **k: Process())
    def request(port, path, *a, **k):
        calls.append(path)
        return {'can_shutdown': True} if path.endswith('safe-shutdown') else {
            'ok': True, 'process_id': 12345, 'backend': {'commit': 'a'*40}} if path.endswith('health') else {
            'status': 'ready'} if path.endswith('resume') else {'status': 'fail'}
    monkeypatch.setattr(redeploy, 'request', request)
    result = redeploy.redeploy(9999)
    assert result['status'] == 'failed' and result['phase'] == 'preflight'
    assert '/api/v1/ops/digest' not in calls
