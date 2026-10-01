import hashlib
import json
import tarfile

import pytest

from cyberscientist import lean_runtime


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
    monkeypatch.setattr(lean_runtime, 'CHUNK_BYTES', 4)
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

    lean_runtime.prepare('run-test', 'sandbox-test', tmp_path / 'stage', 'op-test', source=source)

    names = {path.rsplit('/', 1)[-1] for path, _, _ in transferred}
    assert names == {'project.tar.gz', 'packages.tar.gz', 'curl-7.88.1',
                     'lean-00.part', 'lean-01.part'}
    with tarfile.open(tmp_path / 'stage' / 'lean_runtime' / 'project.tar.gz') as archive:
        assert set(archive.getnames()) == {'PairCore.lean', 'lake-manifest.json'}
    assert all('labels.json' not in command and 'answer.lean' not in command
               for command in commands)
