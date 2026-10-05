"""Public platform schemas: hash-checked offline validation before side effects."""
from __future__ import annotations
import hashlib
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
import jsonschema
from referencing import Registry, Resource
from . import config, db, observation, trace_selection

KINDS = ('protocol', 'arm_manifest', 'characterization', 'trace_step')
SNAPSHOT = config.WORKSPACE_ROOT / 'vendor' / 'playground_contracts'


def _origin(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('平台公开契约URL无效')
    return parts.scheme + '://' + parts.netloc


def _checked(root, base_url):
    metadata = json.loads((root / 'sources.json').read_text())
    origin = _origin(base_url)
    documents = {}
    for kind in KINDS:
        if _origin(metadata[kind]['source']) != origin:
            raise ValueError('平台契约缓存属于其他平台，请先刷新公开契约')
        raw = (root / (kind + '.json')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != metadata[kind]['sha256']:
            raise ValueError(f'{kind}契约缓存哈希不一致')
        documents[kind] = json.loads(raw)
        if kind != 'protocol':
            jsonschema.validators.validator_for(documents[kind]).check_schema(documents[kind])
    return documents, metadata


def load(base_url=None):
    base_url = base_url or config.load_settings()['playground']['base_url']
    pointer = config.DATA_DIR / 'platform_contracts' / 'current.json'
    if pointer.exists():
        digest = json.loads(pointer.read_text())['sha256']
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('契约缓存指针无效')
        return _checked(pointer.parent / digest, base_url)
    return _checked(SNAPSHOT, base_url)


def describe():
    _, metadata = load()
    return {'status': 'cached', 'documents': metadata, 'fresh_fetch': False}


def refresh():
    base = config.load_settings()['playground']['base_url'].rstrip('/')
    origin = _origin(base)
    documents, metadata, raws = {}, {}, {}
    def fetch(kind, path):
        if not isinstance(path, str): raise ValueError('协议schema引用缺失')
        url = (origin + path if path.startswith('/api/') else urllib.parse.urljoin(base + '/', path))
        if _origin(url) != origin: raise ValueError('拒绝跨平台schema引用')
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={'Accept': 'application/json'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    # Public contract requests carry no business credentials.
                    if _origin(response.geturl()) != origin: raise ValueError('契约响应跳转到其他平台')
                    raw = response.read(2_000_001); status = response.status
                if len(raw) > 2_000_000: raise ValueError('平台契约超过2MB')
                decoded = raw.decode('utf-8')
                if observation.strip_secrets(decoded) != decoded: raise ValueError('公开契约含密钥，拒绝缓存')
                doc = json.loads(raw)
                if kind != 'protocol': jsonschema.validators.validator_for(doc).check_schema(doc)
                documents[kind] = doc; raws[kind] = raw
                metadata[kind] = {'source': url, 'http_status': status, 'sha256': hashlib.sha256(raw).hexdigest(), 'fetched_at': db.utcnow(), 'bytes': len(raw)}
                return
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                if attempt == 2 or isinstance(exc, urllib.error.HTTPError) and exc.code < 500 and exc.code != 429:
                    raise ValueError(f'公开契约读取失败：{kind}/{getattr(exc, "code", type(exc).__name__)}') from exc
                time.sleep(2 ** attempt)
    fetch('protocol', '/api/protocol')
    for kind in KINDS[1:]: fetch(kind, documents['protocol']['schemas'].get(kind))
    digest = hashlib.sha256(json.dumps({k: v['sha256'] for k, v in metadata.items()}, sort_keys=True).encode()).hexdigest()
    root = config.DATA_DIR / 'platform_contracts' / digest; root.mkdir(parents=True, exist_ok=True)
    for kind, raw in raws.items(): (root / (kind + '.json')).write_bytes(raw)
    (root / 'sources.json').write_text(json.dumps(metadata, ensure_ascii=False))
    pointer = root.parent / 'current.json'; temporary = pointer.with_suffix('.tmp')
    temporary.write_text(json.dumps({'sha256': digest})); temporary.replace(pointer)
    return {'status': 'received', 'documents': metadata, 'fresh_fetch': True}


def validate_bundle(raw, base_url=None):
    """Validate exact ZIP JSON against the cached official schemas, never fetch."""
    documents, metadata = load(base_url)
    registry = Registry()
    for kind in KINDS[1:]:
        schema = documents[kind]
        registry = registry.with_resource(schema['$id'], Resource.from_contents(schema))
    errors = []
    def check(kind, value, label):
        schema = documents[kind]
        validator = jsonschema.validators.validator_for(schema)(schema, registry=registry, format_checker=jsonschema.FormatChecker())
        for error in validator.iter_errors(value):
            path = '.'.join(map(str, error.absolute_path))
            errors.append(observation.strip_secrets(f'{label}{"." + path if path else ""}: {error.message}')[:600])
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            manifests = [name for name in names if name == 'arm_manifest.json' or name.endswith('/arm_manifest.json')]
            if len(names) != len(set(names)) or len(manifests) != 1:
                raise ValueError('必须有唯一arm_manifest.json且ZIP成员不可重名')
            if any(name.startswith('/') or '..' in Path(name).parts or '\\' in name for name in names):
                raise ValueError('ZIP成员路径越界')
            manifest_name = manifests[0]; prefix = manifest_name[:-len('arm_manifest.json')]
            def read_json(name):
                info = archive.getinfo(name)
                if info.file_size > 2_000_000: raise ValueError(f'{name}: JSON超过2MB')
                return json.loads(archive.read(name))
            manifest = read_json(manifest_name)
            check('arm_manifest', manifest, 'arm_manifest')
            if not isinstance(manifest, dict): return {'valid': False, 'errors': errors, 'schemas': metadata}
            character = manifest.get('characterization')
            path = character.get('path') if isinstance(character, dict) else character if isinstance(character, str) else None
            if path is not None:
                if not isinstance(path, str) or path.startswith('/') or '..' in Path(path).parts or '\\' in path:
                    raise ValueError('characterization.path: 路径越界')
                if prefix + path not in names: errors.append('characterization.path: 指向的文件不存在')
                else: check('characterization', read_json(prefix + path), 'characterization')
            elif isinstance(character, dict): check('characterization', character, 'characterization')
            elif prefix + 'characterization.json' in names:
                check('characterization', read_json(prefix + 'characterization.json'), 'characterization')
            # Mirror the platform's selection rule, without reading scientific
            # artifacts. Then validate only the selected public trace rows.
            files = {name: b'' for name in names}
            files[manifest_name] = archive.read(manifest_name)
            selection = trace_selection.select(files)
            total = sum(archive.getinfo(name).file_size for name in selection.selected_members)
            if total > 128 * 1024 * 1024:
                raise ValueError('选定轨迹超过128MB')
            for name in selection.selected_members:
                value = archive.read(name).decode('utf-8')
                if selection.rule == 'legacy_json_array':
                    rows = json.loads(value)
                    if not isinstance(rows, list): raise ValueError(f'{name}: 轨迹必须是数组')
                    for index, row in enumerate(rows): check('trace_step', row, f'{name}[{index}]')
                else:
                    for number, line in enumerate(value.splitlines(), 1):
                        if not line.strip(): continue
                        try: row = json.loads(line)
                        except ValueError as exc: raise ValueError(f'{name}:{number}: JSON无效') from exc
                        check('trace_step', row, f'{name}:{number}')
    except (ValueError, KeyError, UnicodeDecodeError, OSError, zipfile.BadZipFile) as exc:
        errors.append(observation.strip_secrets(str(exc))[:600])
    return {'valid': not errors, 'errors': errors, 'schemas': metadata}
