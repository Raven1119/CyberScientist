import hashlib
import json
import tarfile

import pytest

from cyberscientist import lean_runtime, db


def test_pinned_lean_runtime_rejects_missing_or_changed_input(tmp_path, monkeypatch):
    monkeypatch.setattr(lean_runtime, 'ARCHIVES', {'lean.tar.zst': hashlib.sha256(b'good').hexdigest()})
    monkeypatch.setattr(lean_runtime, 'PROJECT_HASHES', {'PairCore.lean': hashlib.sha256(b'fixed').hexdigest()})
    (tmp_path / 'project').mkdir()
    (tmp_path / 'project' / 'PairCore.lean').write_bytes(b'fixed')
    with pytest.raises(lean_runtime.LeanRuntimeUnavailable, match='缺失'):
        lean_runtime.validate_source(tmp_path)
    (tmp_path / 'lean.tar.zst').write_bytes(b'wrong')
    with pytest.raises(lean_runtime.LeanRuntimeUnavailable, match='哈希不符'):
        lean_runtime.validate_source(tmp_path)
    (tmp_path / 'lean.tar.zst').write_bytes(b'good')
    lean_runtime.validate_source(tmp_path)


def test_paired_block_runtime_stages_only_trusted_project(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    project = source / 'project'
    project.mkdir(parents=True)
    (project / 'PairCore.lean').write_text('import Mathlib.Data.Nat.Basic\n')
    (project / 'lake-manifest.json').write_text(json.dumps({'packages': []}))
    (source / 'lean.tar.zst').write_bytes(b'abcdefgh')
    (source / 'packages.tar.gz').write_bytes(b'packages')
    (source / 'curl-7.88.1').write_bytes(b'curl')
    (source / 'labels.json').write_text('historical labels must not transfer')
    (source / 'cases').mkdir()
    (source / 'cases' / 'answer.lean').write_text('historical answer')
    monkeypatch.setattr(lean_runtime, 'ARCHIVES', {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in ('lean.tar.zst', 'packages.tar.gz', 'curl-7.88.1')})
    monkeypatch.setattr(lean_runtime, 'PROJECT_HASHES', {
        name: hashlib.sha256((project / name).read_bytes()).hexdigest()
        for name in ('PairCore.lean', 'lake-manifest.json')})
    from cyberscientist import runtime_environments
    monkeypatch.setattr(runtime_environments, 'resolve', lambda _: {
        'image': 'registry.example/prebuilt:fixed', 'identity': {},
        'descriptor_path': '/opt/environment.json', 'mathlib_root': '/opt/mathlib',
        'lean_bin': '/opt/lean/bin'})
    monkeypatch.setattr(db, 'query_one', lambda *args: {
        'request_json': '{"image":"registry.example/prebuilt:fixed"}'})
    transferred = []
    commands = []
    def transfer(_run, _action, _sandbox, remote, *, local_path, operation_id):
        transferred.append((remote, local_path, operation_id))
        return {'status': 'completed'}
    def execute(_run, _sandbox, command, _timeout, _operation):
        commands.append(command)
        return {'status': 'completed'}
    monkeypatch.setattr(lean_runtime.sandboxes, 'transfer', transfer)
    monkeypatch.setattr(lean_runtime.sandboxes, 'execute', execute)

    monkeypatch.setattr(lean_runtime.config, 'WORKSPACE_ROOT', tmp_path)
    lean_runtime.prepare('run-test', 'sandbox-test', tmp_path / 'stage', 'op-test',
        project={'path': 'source/project', 'files': lean_runtime.PROJECT_HASHES},
        environment_id='synthetic-environment')

    names = {path.rsplit('/', 1)[-1] for path, _, _ in transferred}
    assert names == {'project.tar.gz'}
    assert all('curl' not in command and 'cache get' not in command and 'git fetch' not in command
               for command in commands)
    with tarfile.open(tmp_path / 'stage' / 'public_project.tar.gz') as archive:
        assert set(archive.getnames()) == {'PairCore.lean', 'lake-manifest.json'}
    assert all('labels.json' not in command and 'answer.lean' not in command
               for command in commands)
    assert any('lake --no-cache build' in command and 'GIT_ALLOW_PROTOCOL=file' in command
               and 'MATHLIB_NO_CACHE_ON_UPDATE=1' in command for command in commands)


@pytest.mark.parametrize('status', ['failed', 'unknown'])
def test_prebuilt_project_build_failure_is_not_reported_ready(tmp_path, monkeypatch, status):
    from cyberscientist import config, runtime_environments
    monkeypatch.setattr(config, 'WORKSPACE_ROOT', tmp_path)
    source = tmp_path / 'public-project'
    source.mkdir()
    raw = b'public synthetic module'
    (source/'Core.lean').write_bytes(raw)
    monkeypatch.setattr(runtime_environments, 'resolve', lambda _: {
        'image': 'registry.example/prebuilt:fixed', 'identity': {},
        'descriptor_path': '/opt/environment.json', 'mathlib_root': '/opt/mathlib',
        'lean_bin': '/opt/lean/bin'})
    monkeypatch.setattr(db, 'query_one', lambda *args: {
        'request_json': '{"image":"registry.example/prebuilt:fixed"}'})
    calls = []
    def execute(*args):
        calls.append(args[2])
        return {'status': status if 'lake --no-cache build' in args[2] else 'completed'}
    monkeypatch.setattr(lean_runtime.sandboxes, 'execute', execute)
    monkeypatch.setattr(lean_runtime.sandboxes, 'transfer', lambda *args, **kwargs: {'status':'completed'})
    with pytest.raises(lean_runtime.LeanRuntimeUnavailable, match='project-build'):
        lean_runtime.prepare('run-synthetic','sandbox-synthetic',tmp_path/'stage','op-synthetic',
            project={'path':'public-project','files':{'Core.lean':hashlib.sha256(raw).hexdigest()}},
            environment_id='synthetic')
    assert any('lake --no-cache build' in command for command in calls)
