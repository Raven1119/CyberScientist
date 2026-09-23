"""bohr diagnostic credentials never reach the agent's command output."""
import os
from pathlib import Path
import subprocess
import sys

from cyberscientist import bohr_proxy


def test_redacts_known_values_encoded_values_and_unknown_url_keys():
    text = ('known=a/b+c unknown=https://host/path?accessKey=native-key&x=1 '
            'encoded=a%2Fb%2Bc alternate=https://host/?ACCESS_KEY=another-key')
    result = bohr_proxy.redact(text, ['a/b+c'])
    assert result == ('known=[REDACTED] unknown=https://host/path?accessKey=[REDACTED]&x=1 '
                      'encoded=[REDACTED] alternate=https://host/?ACCESS_KEY=[REDACTED]')


def test_proxy_dispatches_once_with_capability_and_redacts_receipt(monkeypatch, capsys):
    import io, json, urllib.request
    monkeypatch.setenv('CS_TOOL_TOKEN', 'run-capability')
    monkeypatch.setattr(sys, 'argv', ['bohr', 'job', 'submit', '-i', 'job.json', '-p', 'input'])
    calls = []
    def urlopen(request, **kw):
        calls.append(request)
        assert request.headers['Authorization'] == 'Bearer run-capability'
        assert json.loads(request.data)['args'] == sys.argv[1:]
        return io.BytesIO(json.dumps({'status': 'unknown', 'error': '?accessKey=secret'}).encode())
    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    assert bohr_proxy.main() == 1
    assert len(calls) == 1
    assert 'secret' not in capsys.readouterr().out


def test_proxy_timeout_keeps_unknown_without_retry(monkeypatch, capsys):
    import urllib.request
    monkeypatch.setenv('CS_TOOL_TOKEN', 'cap')
    calls = []
    def unavailable(*a, **kw):
        calls.append(1)
        raise TimeoutError('fixture timeout')
    monkeypatch.setattr(urllib.request, 'urlopen', unavailable)
    assert bohr_proxy.main() == 75
    assert len(calls) == 1 and 'unknown' in capsys.readouterr().err


def test_installed_entry_runs_from_research_directory_without_account_key(tmp_path):
    entry = bohr_proxy.install_proxy(tmp_path / 'bin')
    env = {k: v for k, v in os.environ.items() if k not in ('CS_TOOL_TOKEN', 'BOHR_ACCESS_KEY', 'ACCESS_KEY')}
    result = subprocess.run([str(entry), 'version'], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 77
    assert '能力令牌' in result.stderr
    assert Path(entry).stat().st_mode & 0o777 == 0o700
