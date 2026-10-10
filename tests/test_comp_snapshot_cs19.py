import json
from pathlib import Path

import pytest

from cyberscientist import runtime_snapshot as snapshot


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
    (tmp_path / 'bad.txt').write_text('another-private-value')
    assert snapshot.scan(tmp_path, known_values=['another-private-value'])['hit_count'] == 1


def test_push_replaces_read_only_export_bytes(tmp_path, monkeypatch):
    import subprocess
    root=runtime(tmp_path);repo=tmp_path/'CyberScientist-comp-export'
    snapshot.export(root,repo)
    real_run=subprocess.run
    def git(*args):
        return real_run(['git',*args],cwd=repo,capture_output=True,text=True,check=True).stdout.strip()
    git('init','-b','main');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
    git('remote','add','origin','https://github.com/Raven1119/CyberScientist-comp.git')
    git('add','.');git('commit','-m','fixture initial export')
    readonly=repo/'src/cyberscientist/cli.py';readonly.chmod(0o444)
    binary=tmp_path/'gh';binary.write_text('fixture')
    monkeypatch.setattr(snapshot.shutil,'which',lambda name:str(binary))
    def process(argv,**kwargs):
        if argv[0]==str(binary):
            return subprocess.CompletedProcess(argv,0,json.dumps({'isPrivate':True,'url':'https://github.com/Raven1119/CyberScientist-comp'}),'')
        if 'push' in argv:return subprocess.CompletedProcess(argv,0,'','')
        if 'ls-remote' in argv:return subprocess.CompletedProcess(argv,0,git('rev-parse','HEAD')+'\trefs/heads/main','')
        return real_run(argv,**kwargs)
    monkeypatch.setattr(snapshot.subprocess if hasattr(snapshot,'subprocess') else subprocess,'run',process)
    result=snapshot.push(root)
    assert result['private'] and result['scan']['hit_count']==0
    assert readonly.read_bytes()==(root/'src/cyberscientist/cli.py').read_bytes()
    assert git('status','--porcelain')==''
    assert git('log','-1','--format=%s').endswith(' CS-UP-21')
