import hashlib
import io
import json
from pathlib import Path
import zipfile
import pytest
from cyberscientist import config, db, mailboxes, platform_contracts as contracts
from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform, PlatformError
from test_trace_narrative import _fixture
from test_mailbox_platform import valid_arm_zip


def bundle(manifest, character=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('arm_manifest.json', json.dumps(manifest))
        archive.writestr('run.py', 'print(42)')
        archive.writestr('traces/trace.jsonl', '')
        if character is not None: archive.writestr('characterization.json', json.dumps(character))
    return stream.getvalue()


def test_official_schema_catches_both_abc_draft_defects_offline_and_valid_passes(monkeypatch):
    monkeypatch.setattr(contracts.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('offline validation never fetches'))
    manifest = {'arm_version': '1.1', 'paper': {'title': 'fixture'}, 'entrypoint': 'run.py',
        'execution': {'log_path': 'run.log', 'artifacts': ['result.json']}, 'expected_outputs': [{'name': 'result'}]}
    failed = contracts.validate_bundle(bundle(manifest))
    assert not failed['valid']
    assert any('execution.artifacts.0' in error and 'object' in error for error in failed['errors'])
    assert any('expected_outputs.0' in error and 'type' in error for error in failed['errors'])
    manifest['execution']['artifacts'] = [{'id': 'result', 'path': 'result.json', 'type': 'data'}]
    manifest['expected_outputs'][0]['type'] = 'data'
    assert contracts.validate_bundle(bundle(manifest))['valid']
    manifest['characterization'] = {'path': 'characterization.json'}
    invalid = contracts.validate_bundle(bundle(manifest, {'envelope': 'bad type'}))
    assert any('characterization.envelope' in error for error in invalid['errors'])


def test_connected_preflight_and_adapter_reject_before_reservation_or_http(monkeypatch):
    rid, tid, _, _, _, _, _, _, trial_dir = _fixture()
    db.execute("UPDATE runs SET mode='connected' WHERE id=?", (rid,))
    manifest = {'arm_version': '1.1', 'paper': {'title': 'fixture'}, 'entrypoint': 'run.py',
        'execution': {'log_path': 'run.log', 'artifacts': ['result.json']}, 'expected_outputs': [{'name': 'result'}]}
    raw = bundle(manifest); path = trial_dir / 'result_package.zip'; path.write_bytes(raw)
    monkeypatch.setattr(mailboxes.arm_admission, 'check', lambda *_: {'verdict': 'admitted', 'signals': {}})
    checked = mailboxes.preflight_submission(rid, tid, None)
    assert checked['error_code'] == 'PLATFORM_SCHEMA_INVALID'
    assert any('expected_outputs.0' in e for e in checked['advisory_warnings'])
    assert not db.query('SELECT * FROM submissions')
    platform = BohriumPlaygroundPlatform('https://play.bohrium.com/api')
    monkeypatch.setattr(platform, '_http', lambda *a, **k: pytest.fail('bad schema must never create/upload'))
    with pytest.raises(PlatformError, match='execution.artifacts.0') as error:
        platform.submit_package('fixture', 'fixture-token', str(path), 'old')
    assert error.value.no_side_effect


def test_schema_cache_checksum_failure_is_visible():
    root = config.DATA_DIR / 'platform_contracts' / ('a' * 64); root.mkdir(parents=True)
    for path in contracts.SNAPSHOT.iterdir(): (root / path.name).write_bytes(path.read_bytes())
    (root.parent / 'current.json').write_text(json.dumps({'sha256': 'a' * 64}))
    (root / 'arm_manifest.json').write_text('{}')
    with pytest.raises(ValueError, match='缓存哈希'): contracts.validate_bundle(valid_arm_zip())


def test_refresh_uses_protocol_schema_links_public_no_credentials_and_keeps_offline_cache(monkeypatch):
    from types import SimpleNamespace
    docs = json.loads((contracts.SNAPSHOT / 'protocol.json').read_text())
    urls = []; origin = 'https://play.bohrium.com'
    def open_public(request, timeout):
        assert not request.has_header('Authorization'); urls.append(request.full_url)
        name = 'protocol' if request.full_url.endswith('/protocol') else next(k for k, path in docs['schemas'].items() if request.full_url == origin + path)
        raw = (contracts.SNAPSHOT / (name + '.json')).read_bytes()
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def geturl(self): return request.full_url
            def read(self, n): return raw
        return Response()
    monkeypatch.setattr(contracts.urllib.request, 'urlopen', open_public)
    result = contracts.refresh()
    assert result['fresh_fetch'] and len(urls) == 4
    monkeypatch.setattr(contracts.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('cached'))
    assert contracts.validate_bundle(valid_arm_zip())['valid']


def test_selected_trace_schema_reports_file_line_and_field():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('arm_manifest.json', json.dumps({'arm_version': '1.1', 'paper': {'title': 'fixture'}, 'entrypoint': 'run.py', 'trace': 'selected.jsonl'}))
        archive.writestr('selected.jsonl', '\n{"step_type":"observation","tokens":"wrong"}\n')
        archive.writestr('traces/ignored.jsonl', 'not JSON')
    result = contracts.validate_bundle(stream.getvalue())
    assert result['errors'] == ["selected.jsonl:2.tokens: 'wrong' is not of type 'integer'"]


def test_platform_switch_cannot_use_other_origin_cache_or_send(monkeypatch, tmp_path):
    path = tmp_path / 'package.zip'; path.write_bytes(valid_arm_zip())
    platform = BohriumPlaygroundPlatform('https://other.example/api')
    monkeypatch.setattr(platform, '_http', lambda *a, **k: pytest.fail('origin mismatch cannot send'))
    with pytest.raises(PlatformError, match='其他平台') as error:
        platform.submit_package('fixture', 'fixture-token', str(path), 'old')
    assert error.value.no_side_effect


@pytest.mark.parametrize('damage', ['checksum', 'external_ref', 'missing_dialect'])
def test_exact_replay_releases_reservation_when_contract_is_unusable(monkeypatch, damage):
    from test_mailboxes import _seed_challenge, _make_run, _make_package, _set_scored
    _seed_challenge(); rid = _make_run(); path = _make_package(rid)
    package = config.WORKSPACE_DIR / path; package = package.with_suffix('.zip'); package.write_bytes(valid_arm_zip())
    mailboxes.register_experiment(1)
    source = mailboxes.submit_experiment(rid, 'trial_mb1', package.relative_to(config.WORKSPACE_DIR).as_posix(), 'baseline')
    _set_scored(source['id'], 20)
    root = config.DATA_DIR / 'platform_contracts' / ('a' * 64); root.mkdir(parents=True)
    for item in contracts.SNAPSHOT.iterdir(): (root / item.name).write_bytes(item.read_bytes())
    (root.parent / 'current.json').write_text(json.dumps({'sha256': 'a' * 64}))
    if damage == 'checksum': (root / 'arm_manifest.json').write_text('{}')
    else:
        raw = json.dumps({'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'urn:fixture', '$ref': 'https://unavailable.invalid/schema'}).encode()
        if damage == 'missing_dialect': raw = b'{"$id":"urn:fixture","type":"object"}'
        (root / 'arm_manifest.json').write_bytes(raw)
        metadata = json.loads((root / 'sources.json').read_text()); metadata['arm_manifest']['sha256'] = hashlib.sha256(raw).hexdigest()
        (root / 'sources.json').write_text(json.dumps(metadata))
    platform = BohriumPlaygroundPlatform('https://play.bohrium.com/api'); platform.name = 'demo'; platform.is_demo = True
    monkeypatch.setattr(platform, '_http', lambda *a, **k: pytest.fail('broken cache cannot send'))
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    replay = mailboxes.submit_exact_replay(source['id'], 'replay', 'same bytes')
    assert replay['status'] == 'failed' and replay['reservation_released'] == 1
    assert db.query_one('SELECT * FROM submissions WHERE id=?', (source['id'],))['score'] == 20
