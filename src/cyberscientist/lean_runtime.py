"""Prepare the pinned, candidate-independent Lean scorer environment in Bohrium."""
from __future__ import annotations

import hashlib
import json
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
            *, project: dict, environment_id: str) -> str:
    """Stage only the immutable small public project into the verified image."""
    from . import db, runtime_environments
    environment = runtime_environments.resolve(environment_id)
    sandbox = db.query_one('SELECT request_json FROM compute_sandboxes'
                           ' WHERE run_id=? AND sandbox_id=?', (run_id, sandbox_id))
    if not sandbox or json.loads(sandbox['request_json']).get('image') != environment['image']:
        raise LeanRuntimeUnavailable('Lean 沙箱没有使用已验证的预置镜像')
    source = (config.WORKSPACE_ROOT / project['path']).resolve()
    if not source.is_relative_to(config.WORKSPACE_ROOT.resolve()):
        raise LeanRuntimeUnavailable('固定公开项目路径越界')
    for name, expected in project['files'].items():
        path = source / name
        if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
            raise LeanRuntimeUnavailable('Lean 固定项目缺失或哈希不符: ' + name)
    project_archive = stage / 'public_project.tar.gz'
    stage.mkdir(parents=True, exist_ok=True)
    with tarfile.open(project_archive, 'w:gz') as archive:
        for name in sorted(project['files']):
            archive.add(source / name, arcname=name, recursive=False)
    if project_archive.stat().st_size > 2_000_000:
        raise LeanRuntimeUnavailable('固定项目异常过大；不传输工具链或缓存')
    remote = '/workspace/cs-public-lean-project-' + operation_id
    command = 'mkdir -p ' + shlex.quote(remote)
    _completed(sandboxes.execute(run_id, sandbox_id, command, 30,
                                operation_id + '-project-mkdir'), 'mkdir')
    _completed(sandboxes.transfer(run_id, 'write', sandbox_id, remote + '/project.tar.gz',
        local_path=str(project_archive), operation_id=operation_id + '-public-project'), 'public-project')
    # The descriptor and all dependency commits are checked in the container;
    # all links point to prebuilt public caches. No curl, git fetch or cache get.
    setup = ("import json, pathlib, subprocess; p=pathlib.Path(" + repr(remote) + "); "
             "e=json.loads(pathlib.Path(" + repr(environment['descriptor_path']) + ").read_text()); "
             "assert all(e[k]==v for k,v in " + repr(environment['identity']) + ".items()); "
             "m=json.loads((p/'lake-manifest.json').read_text()); "
             "roots={n:pathlib.Path(" + repr(environment['mathlib_root']) + ")/'.lake/packages'/n "
             "for n in e['packages']}; roots['mathlib']=pathlib.Path(" + repr(environment['mathlib_root']) + "); "
             "assert all(e['packages'][x['name']]==x['rev'] for x in m['packages']); "
             "q=p/'.lake/packages'; q.mkdir(parents=True,exist_ok=True); "
             "assert all(roots[x['name']].is_dir() for x in m['packages']); "
             "[(q/x['name']).symlink_to(roots[x['name']],target_is_directory=True) "
             "for x in m['packages'] if not (q/x['name']).exists()]")
    command = ('tar -xzf ' + shlex.quote(remote + '/project.tar.gz') + ' -C ' + shlex.quote(remote)
               + ' && python3 -c ' + shlex.quote(setup))
    _completed(sandboxes.execute(run_id, sandbox_id, command, 60,
                                operation_id + '-project-link'), 'project-link')
    build_env = ('PATH=' + shlex.quote(environment['lean_bin']) + ':$PATH '
                 'GIT_ALLOW_PROTOCOL=file MATHLIB_NO_CACHE_ON_UPDATE=1 ')
    # Build the trusted public project before any candidate is loaded. Lake's
    # versioned --no-cache flag prevents automatic remote cache acquisition.
    # Dependencies must already exist above; Git can only use local protocols.
    command = ('cd ' + shlex.quote(remote) + ' && ' + build_env
               + 'lake --no-cache build 1>&2')
    _completed(sandboxes.execute(run_id, sandbox_id, command, 600,
                                operation_id + '-project-build'), 'project-build')
    return ('PATH=' + shlex.quote(environment['lean_bin']) + ':$PATH '
            'CS_LEAN_PROJECT=' + shlex.quote(remote) + ' ')
