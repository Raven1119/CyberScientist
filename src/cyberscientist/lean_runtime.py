"""Prepare the pinned, candidate-independent Lean scorer environment in Bohrium."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import tarfile
from pathlib import Path

from . import config, sandboxes

ARCHIVES = {
    'lean.tar.zst': '5f2069e6f5db73780f374ccb49ce8ea649aa20a0cebf0116816744c999ce72aa',
    'packages.tar.gz': 'e9e97fe311c54e38b2c8f56dc9e208e3b5850abe3643e6afc6a9c397ebcbe71e',
    'curl-7.88.1': '5be118c1ce46d29cfa8dc658d16d4bb227f27eb3e1ec767c2bdb7aff69e1150c',
    '085121bd6ca2077c.ltar': '4bd73ef3b9e520f01a8d4bf03aa270e6af07e1382348cb136d2ae4f1263bfff4',
    '2cee2bbd50fe34ab.ltar': '52593ba130e9e10d803558592937e0095c1bea6695299046cb0294bb8742cdf1',
    'a709e667602cde09.ltar': 'be2257ffb09a33f6e440015522b63df5320d3199eb9cd8c7cc5f8de859fd611a',
    '4496a677034e8299.ltar': '42721c1a930e65352490ad1ecb331e7978c907889ee1d93bd5eea5743a087ab0',
    '4551110295d650d8.ltar': 'c4f9fbc6041dfedab11e189357e1da8de3d08e9e012aa9449d1da219bf05e501',
}
PROJECT_HASHES = {
    'PairCore.lean': '26e3be2cee9df5d5b021f3c4662386db3974b51fbb0b07a03616b9fb36a73415',
    'Problem.lean': 'e2ef57d93676b310b8dc43d836c40dfcdebdfe7f3476bf66b5c40c7bd82d5cdb',
    'lean-toolchain': '2bdc48adfa58d0017e538a0ad117c5d73d35deec879978f909406a80c8037273',
    'lakefile.toml': 'd9698381e02837db51d2b5e5bd746d7514db9b57a805015b7d8f4a80eb79d2e3',
    'lake-manifest.json': '7d78a9a7f1ff478f6a609653c74817d10e199b9425daf26d9c1027fa53375fef',
}
CHUNK_BYTES = 64 * 1024 * 1024
SOURCE = (config.WORKSPACE_ROOT / '.package-checks' /
          'paired-block-final-20260928' / 'staged')


class LeanRuntimeUnavailable(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source(source: Path = SOURCE) -> None:
    """Require the exact previously verified public toolchain and project."""
    for name, expected in ARCHIVES.items():
        path = source / name
        if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
            raise LeanRuntimeUnavailable('Lean 可信运行资源缺失或哈希不符: ' + name)
    for name, expected in PROJECT_HASHES.items():
        path = source / 'project' / name
        if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
            raise LeanRuntimeUnavailable('Lean 可信项目缺失或哈希不符: ' + name)


def _completed(result: dict, step: str) -> None:
    if result.get('status') != 'completed':
        raise LeanRuntimeUnavailable('Lean 评分环境准备未确认: ' + step)


def prepare(run_id: str, sandbox_id: str, stage: Path, operation_id: str,
            *, source: Path = SOURCE) -> None:
    """Copy only pinned public dependencies; never transfer prior answers/cases."""
    validate_source(source)
    upload = stage / 'lean_runtime'
    upload.mkdir(parents=True, exist_ok=True)
    remote = '/workspace/cs-lean-stage'
    _completed(sandboxes.execute(run_id, sandbox_id,
        'mkdir -p ' + remote + ' /workspace/paired-block-project/.lake/packages'
        ' /workspace/lean /workspace/mathlib-cache', 30, operation_id + '-runtime-mkdir'),
        'mkdir')

    project_archive = upload / 'project.tar.gz'
    temporary = upload / 'project.tar.gz.tmp'
    with tarfile.open(temporary, 'w:gz') as archive:
        for name in sorted(PROJECT_HASHES):
            archive.add(source / 'project' / name, arcname=name, recursive=False)
    temporary.replace(project_archive)

    transfer_files = [project_archive, source / 'packages.tar.gz',
                      source / 'curl-7.88.1',
                      *(source / name for name in ARCHIVES if name.endswith('.ltar'))]
    for path in transfer_files:
        local = upload / path.name
        if path != local and not local.exists():
            os.link(path, local)
        _completed(sandboxes.transfer(run_id, 'write', sandbox_id,
            remote + '/' + path.name, local_path=str(local),
            operation_id=operation_id + '-runtime-' + path.name.replace('.', '-')),
            path.name)

    parts = []
    with (source / 'lean.tar.zst').open('rb') as stream:
        index = 0
        while chunk := stream.read(CHUNK_BYTES):
            name = f'lean-{index:02d}.part'
            local = upload / name
            if local.exists() and local.read_bytes() != chunk:
                raise LeanRuntimeUnavailable('Lean 分块与冻结源不一致: ' + name)
            if not local.exists():
                local.write_bytes(chunk)
            _completed(sandboxes.transfer(run_id, 'write', sandbox_id,
                remote + '/' + name, local_path=str(local),
                operation_id=operation_id + '-runtime-' + name.replace('.', '-')),
                name)
            parts.append(name)
            index += 1
    if not parts:
        raise LeanRuntimeUnavailable('Lean 归档为空')

    parts_arg = ' '.join(shlex.quote(remote + '/' + name) for name in parts)
    checksum = ARCHIVES['lean.tar.zst']
    remote_checks = ' && '.join(
        'echo ' + shlex.quote(expected + '  ' + remote + '/' + name)
        + ' | sha256sum -c -'
        for name, expected in ARCHIVES.items() if name != 'lean.tar.zst')
    project_check = ('echo ' + shlex.quote(_sha256(project_archive) + '  '
                                      + remote + '/project.tar.gz') + ' | sha256sum -c -')
    command = (
        f'cat {parts_arg} > {remote}/lean.tar.zst && '
        f'echo {shlex.quote(checksum + "  " + remote + "/lean.tar.zst")} | sha256sum -c - && '
        + remote_checks + ' && ' + project_check + ' && '
        f'cd /workspace/paired-block-project && '
        f'tar -xzf {remote}/project.tar.gz && '
        f'tar -xzf {remote}/packages.tar.gz -C .lake/packages && '
        f'tar --zstd -xf {remote}/lean.tar.zst --no-same-owner '
        f'--strip-components=1 -C /workspace/lean && '
        f'cp {remote}/*.ltar /workspace/mathlib-cache/ && '
        f'cp {remote}/curl-7.88.1 /workspace/mathlib-cache/ && '
        f'chmod 755 /workspace/mathlib-cache/curl-7.88.1 && '
        'PATH=/workspace/lean/bin:$PATH lean --version')
    _completed(sandboxes.execute(run_id, sandbox_id, command, 300,
                                 operation_id + '-runtime-unpack'), 'unpack')

    manifest = json.loads((source / 'project' / 'lake-manifest.json').read_text())
    checks = ' && '.join(
        f'test "$(git -C .lake/packages/{shlex.quote(item["name"])} rev-parse HEAD)" = '
        + shlex.quote(item['rev']) for item in manifest['packages'])
    modules = [line.split()[1] for line in
               (source / 'project' / 'PairCore.lean').read_text().splitlines()
               if line.startswith('import ')]
    env = 'PATH=/workspace/lean/bin:$PATH NO_PROXY=* no_proxy=* MATHLIB_CACHE_DIR=/workspace/mathlib-cache'
    build = ('cd /workspace/paired-block-project && ' + checks + ' && '
             + env + ' lake exe cache get ' + ' '.join(map(shlex.quote, modules))
             + ' && ' + env + ' lake build PairCore')
    _completed(sandboxes.execute(run_id, sandbox_id, build, 600,
                                 operation_id + '-runtime-build'), 'build')
