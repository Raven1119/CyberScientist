import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('comp_snapshot', Path(__file__).parents[1] / 'tools/export_comp_snapshot.py')
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def runtime(tmp_path):
    root = tmp_path / 'comp'
    for directory in ('.runtime/releases/version', '.runtime/codex', '.cyberscientist', 'src/cyberscientist'):
        (root / directory).mkdir(parents=True)
    (root / 'src/cyberscientist/cli.py').write_text('print("runtime")\n')
    data = (root / 'src/cyberscientist/cli.py').read_bytes()
    (root / '.runtime/version.json').write_text(json.dumps({'commit': 'version'}))
    (root / '.runtime/releases/version/manifest.json').write_text(json.dumps({'commit': 'version', 'files': {'src/cyberscientist/cli.py': snapshot.digest(data)}}))
    (root / '.cyberscientist/settings.json').write_text(json.dumps({'skills': {'always_on': []}, 'token': 'private-value', 'token_secret_ref': 'agent-reference'}))
    (root / '.runtime/codex/config.toml').write_text('model = "test"\napi_key = "private-value"\n')
    (root / '.runtime/codex/auth.json').write_text('NEVER EXPORT')
    return root


def test_snapshot_preserves_runtime_bytes_and_excludes_credentials(tmp_path):
    root = runtime(tmp_path); target = tmp_path / 'export'
    snapshot.export(root, target)
    assert (target / 'src/cyberscientist/cli.py').read_bytes() == (root / 'src/cyberscientist/cli.py').read_bytes()
    assert not list(target.rglob('auth.json'))
    settings = json.loads((target / 'snapshot/settings.json').read_text())
    assert settings['token'] == '[REDACTED]'
    assert settings['token_secret_ref'] == 'agent-reference'
    assert 'private-value' not in (target / 'snapshot/codex/config.toml').read_text()


def test_forbidden_manifest_and_tampered_runtime_fail_before_export(tmp_path):
    root = runtime(tmp_path)
    manifest = root / '.runtime/releases/version/manifest.json'
    manifest.write_text(json.dumps({'files': {'.runtime/codex/auth.json': snapshot.digest(b'NEVER EXPORT')}}))
    with pytest.raises(ValueError, match='Invalid manifest path'):
        snapshot.export(root, tmp_path / 'forbidden')
    manifest.write_text(json.dumps({'files': {'src/cyberscientist/cli.py': 'invalid'}}))
    with pytest.raises(ValueError, match='Published bytes mismatch'):
        snapshot.export(root, tmp_path / 'tampered')


def test_scanner_reports_positions_without_printing_values(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot.config, 'sensitive_values', lambda: ['known-private-value'])
    (tmp_path / 'bad.txt').write_text('asp_' + 'a' * 40 + '\nknown-private-value\nBearer ' + 'b' * 30)
    result = snapshot.scan(tmp_path)
    assert result['hit_count'] == 3
    assert 'known-private-value' not in json.dumps(result)
    (tmp_path / 'bad.txt').write_text('access_key = get_bohrium_environment_key().strip()\npattern = "asp_"\n')
    assert snapshot.scan(tmp_path)['hit_count'] == 0
