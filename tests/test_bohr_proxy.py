"""bohr diagnostic credentials never reach the agent's command output."""
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

import pytest

from cyberscientist import bohr_proxy


def test_redacts_known_values_encoded_values_and_unknown_url_keys():
    text = ('known=a/b+c unknown=https://host/path?accessKey=native-key&x=1 '
            'encoded=a%2Fb%2Bc alternate=https://host/?ACCESS_KEY=another-key')
    result = bohr_proxy.redact(text, ['a/b+c'])
    assert result == ('known=[REDACTED] unknown=https://host/path?accessKey=[REDACTED]&x=1 '
                      'encoded=[REDACTED] alternate=https://host/?ACCESS_KEY=[REDACTED]')


@pytest.mark.parametrize('key', ['Signature', 'sig', 'OSSAccessKeyId', 'AWSAccessKeyId',
    'X-Amz-Signature', 'X-Amz-Credential', 'X-Amz-Security-Token',
    'X-Goog-Signature', 'access_token'])
@pytest.mark.parametrize('encoding', ['plain', 'json_amp', 'html_amp', 'encoded_url'])
def test_unknown_presigned_url_credentials_are_redacted(key, encoding):
    url = f'https://example.invalid/out.zip?Expires=123&{key}=temporary%2Bsecret&download=1'
    expected = f'https://example.invalid/out.zip?Expires=123&{key}=[REDACTED]&download=1'
    if encoding == 'json_amp':
        url, expected = (s.replace('&', r'\u0026') for s in (url, expected))
    elif encoding == 'html_amp':
        url, expected = (s.replace('&', '&amp;') for s in (url, expected))
    elif encoding == 'encoded_url':
        url = quote(url, safe='')
        expected = quote(expected, safe='').replace('%5BREDACTED%5D', '[REDACTED]')
    assert bohr_proxy.redact(url, []) == expected


def test_presigned_redaction_keeps_json_valid_and_unrelated_scientific_fields():
    import json
    payload = {'signature': 'scientific signature', 'score': 100,
        'link': 'https://example.invalid/out.zip?OSSAccessKeyId=temporary-id&Signature=temporary-signature'}
    stdout = json.dumps(payload).replace('&', r'\u0026')
    result = json.loads(bohr_proxy.redact(stdout, []))
    assert result['signature'] == 'scientific signature' and result['score'] == 100
    assert 'temporary-id' not in result['link'] and 'temporary-signature' not in result['link']


def test_encoded_ampersand_inside_credential_is_not_a_parameter_separator():
    url = 'https://example.invalid/out.zip?Signature=fake%26nested%3Dsecret&download=1'
    assert bohr_proxy.redact(url, []) == 'https://example.invalid/out.zip?Signature=[REDACTED]&download=1'
    encoded = quote(url, safe='')
    assert 'fake' not in bohr_proxy.redact(encoded, [])
    assert 'secret' not in bohr_proxy.redact(encoded, [])


def test_native_receipt_redacts_unknown_signed_links_in_both_streams(monkeypatch):
    from cyberscientist import compute
    link = 'https://example.invalid/out.zip?Expires=123&OSSAccessKeyId=temporary-id&Signature=temporary-signature'
    calls = []
    def native(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, link, 'download URL: ' + link)
    monkeypatch.setattr(subprocess, 'run', native)
    receipt = compute._native(['job', 'describe', '-j', '123', '-l'])
    assert receipt['ok'] and len(calls) == 1
    for stream in ('stdout', 'stderr'):
        assert 'temporary-id' not in receipt[stream]
        assert 'temporary-signature' not in receipt[stream]
        assert 'Expires=123' in receipt[stream]


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
