"""Read-only comparison of public platform contracts against reviewed snapshots."""
from __future__ import annotations
import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid
from . import config, db, observation, platform_contracts

DOCS = {'arm_docs': '/api/docs/arm-bundles', 'agent_api_docs': '/api/docs/dev/AGENT_API.md'}
BASELINE = platform_contracts.SNAPSHOT


def _read_public(name: str, path: str, base: str, *, json_document: bool) -> tuple[object, dict]:
    origin = platform_contracts._origin(base)
    if not isinstance(path, str) or not path.startswith('/api/'):
        raise ValueError('公开文档引用缺失或无效')
    url = origin + path
    if platform_contracts._origin(url) != origin: raise ValueError('拒绝跨平台公开文档')
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'Accept': 'application/json,text/plain'})
            with urllib.request.urlopen(request, timeout=30) as response:
                if platform_contracts._origin(response.geturl()) != origin: raise ValueError('文档跨平台跳转')
                raw = response.read(2_000_001); status = response.status
            if len(raw) > 2_000_000: raise ValueError('公开文档超过2MB')
            decoded = raw.decode('utf-8')
            if observation.strip_secrets(decoded) != decoded: raise ValueError('文档含疑似密钥，未保存')
            digest = hashlib.sha256(raw).hexdigest()
            root = config.DATA_DIR / 'platform_drift' / digest; root.mkdir(parents=True, exist_ok=True)
            target = root / (name + '.txt')
            if target.exists() and target.read_bytes() != raw: raise ValueError('冻结公开文档已改变')
            if not target.exists(): target.write_bytes(raw)
            meta = {'source': url, 'sha256': digest, 'bytes': len(raw), 'http_status': status, 'status': 'received'}
            value = decoded
            if json_document:
                try: value = json.loads(decoded)
                except ValueError: meta['format_status'] = 'invalid_json'
            return value, meta
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2 or isinstance(exc, urllib.error.HTTPError) and exc.code < 500 and exc.code != 429: raise
            time.sleep(2 ** attempt)
    raise RuntimeError('公开文档读取未完成')


def _fetch_docs(base: str) -> tuple[dict, dict]:
    documents, metadata = {}, {}
    for name, path in DOCS.items():
        documents[name], metadata[name] = _read_public(name, path, base, json_document=False)
    return documents, metadata


def fetch_documents() -> tuple[dict, dict]:
    # Detection must not depend on our old validator accepting a changed API.
    # Each received document remains evidence if another reference fails.
    base = config.load_settings()['playground']['base_url']
    documents, metadata = {}, {}
    def receive(name, path, json_document=True):
        try:
            documents[name], metadata[name] = _read_public(name, path, base, json_document=json_document)
        except Exception as exc:
            metadata[name] = {'status': 'unknown', 'reason': observation.strip_secrets(str(exc))[:400]}
    receive('protocol', '/api/protocol')
    protocol = documents.get('protocol')
    schemas = protocol.get('schemas', {}) if isinstance(protocol, dict) else {}
    if not isinstance(schemas, dict): schemas = {}
    for name in platform_contracts.KINDS[1:]: receive(name, schemas.get(name))
    for name, path in DOCS.items(): receive(name, path, False)
    return documents, metadata


def _baseline(base: str) -> tuple[dict, dict]:
    documents, metadata = platform_contracts._checked(BASELINE, base)
    doc_meta = json.loads((BASELINE / 'docs_sources.json').read_text())
    for name in DOCS:
        raw = (BASELINE / (name + '.txt')).read_bytes()
        if platform_contracts._origin(doc_meta[name]['source']) != platform_contracts._origin(base): raise ValueError('文档快照属于其他平台')
        if hashlib.sha256(raw).hexdigest() != doc_meta[name]['sha256']: raise ValueError('文档快照哈希不一致')
        documents[name] = raw.decode('utf-8')
    return documents, metadata | doc_meta


def _paths(before, after, prefix='') -> list[str]:
    if before == after: return []
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            path = prefix + ('.' if prefix else '') + key
            result += _paths(before[key], after[key], path) if key in before and key in after else [path]
            if len(result) >= 30: break
        return result[:30]
    return [prefix or '(root)']


def facts() -> dict:
    row = db.query_one("SELECT payload_json,observed_at FROM runtime_observations WHERE kind='protocol_drift'")
    last = json.loads(row['payload_json']) if row else {'status': 'unknown', 'reason': '尚未检查'}
    try: origin = platform_contracts._origin(config.load_settings()['playground']['base_url'])
    except ValueError: origin = None
    if row and last.get('platform_origin') != origin:
        last = {'status': 'unknown', 'reason': '当前平台与上次检查的平台不同，需重新检查',
                'platform_origin': origin, 'historical_observation': last}
    if not config.load_settings()['features'].get('protocol_drift', True):
        return {'status': 'disabled', 'last_observation': last}
    return last


def check() -> dict:
    if not config.load_settings()['features'].get('protocol_drift', True): return facts()
    origin = None
    try:
        base = config.load_settings()['playground']['base_url']
        origin = platform_contracts._origin(base)
        baseline, previous = _baseline(base)
        current, observed = fetch_documents()
        if any(meta.get('source') and platform_contracts._origin(meta['source']) != origin for meta in observed.values()):
            raise ValueError('检查期间平台配置变化，未确认兼容性')
        changes = [{'document': name, 'baseline_sha256': previous[name]['sha256'], 'observed_sha256': meta['sha256'],
                    'changed_paths': _paths(baseline[name], current[name]), 'source': meta['source']}
                   for name, meta in observed.items() if meta.get('sha256') and meta['sha256'] != previous[name]['sha256']]
        errors = [{'document': name, 'reason': meta.get('reason', '公开文档格式不明')}
                  for name, meta in observed.items() if not meta.get('sha256') or meta.get('format_status')]
        result = {'status': 'changed' if changes else 'unknown' if errors else 'unchanged',
                  'changes': changes, 'complete': not errors, 'errors': errors,
                  'documents': observed, 'notice': '公开协议变化是平台事实；未验证我们的适配器是否兼容。'}
    except Exception as exc:
        result = {'status': 'unknown', 'changes': [], 'reason': observation.strip_secrets(str(exc))[:400]}
    now = db.utcnow()
    result.update(observed_at=now, platform_origin=origin)
    result = json.loads(observation.strip_secrets(json.dumps(result, ensure_ascii=False)))
    with db.transaction() as conn:
        if result['status'] == 'unknown' or result.get('complete') is False:
            prior_row = conn.execute("SELECT payload_json FROM runtime_observations WHERE kind='protocol_drift'").fetchone()
            prior = json.loads(prior_row['payload_json']) if prior_row else {}
            if prior.get('platform_origin') == origin:
                if prior.get('status') in ('changed', 'unchanged'):
                    result['last_verified'] = {key: value for key, value in prior.items() if key not in ('last_verified', 'historical_observation')}
                elif prior.get('last_verified'): result['last_verified'] = prior['last_verified']
            elif prior:
                result['historical_observation'] = {key: value for key, value in prior.items() if key not in ('last_verified', 'historical_observation')}
        conn.execute('INSERT OR REPLACE INTO runtime_observations VALUES(?,?,?)', ('protocol_drift', json.dumps(result, ensure_ascii=False), now))
        if result['status'] == 'changed':
            digest = hashlib.sha256(json.dumps(result['changes'], sort_keys=True).encode()).hexdigest()
            conn.execute('INSERT OR IGNORE INTO alerts(id,dedupe_key,kind,title,payload,created_at) VALUES(?,?,?,?,?,?)',
                         ('alert_' + uuid.uuid4().hex[:12], 'protocol-drift:' + digest, 'platform.protocol_changed',
                          '平台协议或接口文档发生变化', json.dumps(result, ensure_ascii=False), now))
    return result
