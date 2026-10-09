"""Stage only declared science outputs; never extract an untrusted ZIP wholesale."""
import hashlib
import io
import json
from pathlib import PurePosixPath
import stat
import zipfile

from . import native_logs, trace_selection


def source_path(value):
    if not isinstance(value, str):
        raise ValueError('输出路径须为字符串')
    app_path = value.startswith(('/app/', 'app/'))
    value = value.removeprefix('/app/').removeprefix('app/')
    if (not value.startswith('outputs/') and not app_path) or '\\' in value:
        raise ValueError('输出契约须为明确的 /app 文件或 outputs 文件')
    path = PurePosixPath(value)
    if any(part in ('..', '.', '') for part in value.split('/')) or path.is_absolute():
        raise ValueError('输出路径越界')
    return path.as_posix()


def output_path(value):
    path = source_path(value)
    return path if path.startswith('outputs/') else 'outputs/' + path


def stage(content, directory, manifest, *, contract=None):
    """Contract paths take precedence; fallback requires executor declarations."""
    declared = []
    for item in manifest.get('expected_outputs', []):
        if isinstance(item, dict):
            path = item.get('path') or item.get('name')
            if isinstance(path, str) and ('outputs/' in path):
                declared.append(output_path(path))
    specifications = {output_path(p): source_path(p) for p in contract['paths']} if contract else {p:p for p in declared}
    paths = sorted(specifications)
    if not paths:
        raise ValueError('缺少题面输出契约及执行者明确产物清单；未发送')
    hashes = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        root = trace_selection.bundle_root({name: b'' for name in names})
        for path in paths:
            source = specifications[path]
            matches = [n for n in names if n in (root + source, root + 'app/' + source)]
            if len(matches) != 1:
                raise ValueError('契约产物缺失或重复：' + path)
            entry = archive.getinfo(matches[0])
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.file_size > 128 * 1024**2:
                raise ValueError('产物为链接或过大：' + path)
            raw = archive.read(matches[0])
            # Use the native classifier on an ordinary plaintext JSON message.
            if native_logs.contains_secrets(json.dumps({'content': raw.decode('utf-8', errors='replace')})):
                raise ValueError('产物命中密钥分类器：' + path)
            target = directory / path.removeprefix('outputs/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            hashes[path] = hashlib.sha256(raw).hexdigest()
    if contract:
        from jsonschema import validate
        for path, schema in contract.get('json_schemas', {}).items():
            target = directory / output_path(path).removeprefix('outputs/')
            validate(json.loads(target.read_text()), schema)
    return {'source': 'task_contract' if contract else 'executor_manifest',
            'included': paths, 'excluded_declared': sorted(set(declared) - set(paths)),
            'sha256': hashes, 'notice': '只暂存列出的输出；其他源码、日志、证据不作为科学输出上传'}


def verify_built(content, expected):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        actual = {n: hashlib.sha256(archive.read(n)).hexdigest()
                  for n in archive.namelist() if n.startswith('outputs/') and not n.endswith('/')}
        if actual != expected:
            raise ValueError('官方CLI构建的科学输出与暂存白名单不一致')


def contract_for_run(run_id):
    from . import artifact_contracts
    facts = artifact_contracts.for_run(run_id)
    snapshot = json.loads(facts.get('platform_snapshot_json') or '{}')
    contract = snapshot.get('output_contract')
    if isinstance(contract, dict) and isinstance(contract.get('paths'), list):
        return contract
    # Explicit task output paths are useful even when no JSON schema is supplied.
    inspected = artifact_contracts.inspect('', task_content=facts['content'])
    paths = [p for p in inspected['task_paths'] if p.startswith(('/app/', 'app/', 'outputs/'))]
    return {'paths': paths} if paths else None
