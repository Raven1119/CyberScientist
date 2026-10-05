"""Public native GPU machine observations, distinct from permission or stock promises."""
import hashlib
import json

from . import db


def record(kind: str, receipt: dict) -> dict:
    if kind not in ('job', 'sandbox') or not receipt.get('ok') or receipt.get('truncated'):
        return {'status': 'unknown'}
    try:
        body = json.loads(receipt['stdout'])
        data = body['data']
        items = data['items']
        page = data.get('pagination', {})
        if (body.get('ok') is not True or not isinstance(items, list) or not isinstance(page, dict)
                or page.get('has_more') is not False
                or 'total' in page and (type(page['total']) is not int or page['total'] != len(items))):
            return {'status': 'unknown'}
        keys = ('skuEnName', 'skuId', 'cpuCoreNum', 'memory', 'gpuCoreNum', 'gpu', 'vmemory', 'hasStock', 'price') if kind == 'job' else ('sku_name', 'sku_id', 'cpu', 'memory', 'gpu_core_num', 'gpu', 'price')
        safe = [{k: item[k] for k in keys if k in item} for item in items if isinstance(item, dict)
                and item.get('chooseType', item.get('class')) == 'gpu']
    except (ValueError, KeyError, TypeError):
        return {'status': 'unknown'}
    payload = {'status': 'observed', 'items': safe, 'source': 'bohr machine list GPU' if kind == 'job' else 'bohr sandbox machine list',
               'source_receipt_sha256': hashlib.sha256(receipt['stdout'].encode()).hexdigest()}
    db.execute('INSERT INTO runtime_observations VALUES(?,?,?) ON CONFLICT(kind) DO UPDATE SET payload_json=excluded.payload_json,observed_at=excluded.observed_at',
               ('gpu_catalog:' + kind, json.dumps(payload), db.utcnow()))
    return payload


def facts() -> dict:
    result = {}
    for kind in ('job', 'sandbox'):
        row = db.query_one('SELECT * FROM runtime_observations WHERE kind=?', ('gpu_catalog:' + kind,))
        result[kind] = json.loads(row['payload_json']) | {'observed_at': row['observed_at']} if row else {'status': 'unknown', 'items': []}
    return result


def refresh() -> dict:
    from . import compute
    for kind, argv in (('job', ['machine', 'list', '--choose-type', 'gpu', '--scene', 'job']), ('sandbox', ['sandbox', 'machine', 'list'])):
        try:
            record(kind, compute._native(argv + ['--no-interactive', '-o', 'json'], modern=True, timeout=30))
        except Exception:
            pass  # Preserve the last observation and its timestamp; never invent a machine.
    return facts()


def job(name: str) -> dict | None:
    return next((item for item in facts()['job']['items'] if item.get('skuEnName') == name), None)
