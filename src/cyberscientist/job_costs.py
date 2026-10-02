"""CPU Job estimates from Job quotes; duration units remain an explicit assumption."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json

from . import db

SOURCE = 'bohr machine list --choose-type cpu --scene job'
UNIT_SOURCE = 'https://bohrium-doc.dp.tech/docs/bohrctl/pricing/'


def record_prices(run_id: str, receipt: dict, *, scene: str) -> dict:
    if scene != 'job' or not receipt.get('ok') or receipt.get('truncated'):
        return {'status': 'unknown'}
    try:
        body = json.loads(receipt['stdout'])
        items = body['data']['items'] if body.get('ok') is True else None
        if not isinstance(items, list) or len(items) > 200:
            return {'status': 'unknown'}
    except (KeyError, ValueError, TypeError, AttributeError):
        return {'status': 'unknown'}
    rates = {}
    for item in items:
        if not isinstance(item, dict) or item.get('chooseType') != 'cpu':
            continue
        cpu, memory, gpu = (item.get(k) for k in ('cpuCoreNum', 'memory', 'gpuCoreNum'))
        sku, sku_id, value = (item.get(k) for k in ('skuEnName', 'skuId', 'price'))
        if (type(cpu) is not int or type(memory) is not int or cpu <= 0 or memory <= 0
                or type(gpu) is not int or gpu != 0 or type(sku_id) is not int
                or sku != f'c{cpu}_m{memory}_cpu' or type(value) not in (int, float, str)):
            continue
        try:
            price = Decimal(str(value))
            if not price.is_finite() or price < 0 or price > 1000000:
                continue
        except InvalidOperation:
            continue
        rate = {'hourly_rate': str(price), 'currency': 'CNY', 'sku_id': sku_id}
        if sku in rates and rates[sku] != rate:
            return {'status': 'unknown'}
        rates[sku] = rate
    observed_at = db.utcnow()
    meta = body.get('meta')
    timestamp = meta.get('timestamp') if isinstance(meta, dict) else None
    if type(timestamp) is int:
        try:
            observed_at = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        except (OverflowError, ValueError, OSError):
            pass
    db.append_event(run_id, 'controller', 'job.price_quote', {
        'rates': rates, 'observed_at': observed_at, 'recorded_at': db.utcnow(),
        'source': SOURCE, 'unit_source': UNIT_SOURCE,
        'source_receipt_sha256': hashlib.sha256(receipt['stdout'].encode()).hexdigest()})
    return {'status': 'received', 'rate_count': len(rates)}


def refresh(run_id: str) -> dict:
    if not db.query_one("SELECT 1 FROM compute_jobs WHERE run_id=? AND status!='not_started'", (run_id,)):
        return {'status': 'not_needed'}
    if db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='job.price_quote'", (run_id,)):
        return {'status': 'recorded'}
    # A captured quote can be reused without another platform query. Its
    # original observation time and source hash remain visible.
    quote = db.query_one("SELECT payload FROM events WHERE type='job.price_quote' ORDER BY recorded_at DESC,rowid DESC LIMIT 1")
    if quote:
        db.append_event(run_id, 'controller', 'job.price_quote', json.loads(quote['payload']))
        return {'status': 'recorded'}
    from . import compute
    try:
        result = record_prices(run_id, compute._native(
            ['machine', 'list', '--choose-type', 'cpu', '--scene', 'job',
             '--no-interactive', '--output', 'json'], modern=True, timeout=25), scene='job')
    except Exception as exc:
        result = {'status': 'unknown', 'error_code': type(exc).__name__}
    if result['status'] == 'unknown':
        db.append_event(run_id, 'controller', 'job.price_unavailable', result)
    return result


def estimate(run_id: str) -> dict:
    rows = db.query("SELECT * FROM compute_jobs WHERE run_id=? AND status!='not_started'", (run_id,))
    quote = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='job.price_quote' ORDER BY seq DESC LIMIT 1", (run_id,))
    data = json.loads(quote['payload']) if quote else {}
    total, seconds, priced = Decimal(0), 0, 0
    for row in rows:
        spec = json.loads(row['spec_json'])
        billing = json.loads(row['receipt_json'] or '{}').get('billing', {})
        duration = billing.get('spend_seconds')
        nodes = spec.get('nnode')
        machine = spec.get('machine_type')
        rate = data.get('rates', {}).get(machine) if isinstance(machine, str) else None
        if (row['status'] not in ('Finished', 'Failed', 'Stopped') or not row['platform_job_id']
                or billing.get('source') != '/openapi/v1/job/list:cost'
                or type(duration) is not int or not 0 <= duration <= 31536000
                or type(nodes) is not int or not 1 <= nodes <= 10000 or not rate):
            continue
        priced += 1
        seconds += duration * nodes
        total += Decimal(rate['hourly_rate']) * duration * nodes / 3600
    missing = len(rows) - priced
    return {'status': 'estimated_partial' if priced and missing else 'estimated' if priced else 'unknown',
            'amount': str(total.quantize(Decimal('0.0001'))) if priced else None,
            'currency': 'CNY' if priced else None, 'priced_count': priced, 'unpriced_count': missing,
            'assumed_node_seconds': seconds if priced else None,
            'basis': 'current_job_rate_times_spendTime_assumed_seconds_times_nodes',
            'duration_unit_verified': False,
            'source_receipt_sha256': data.get('source_receipt_sha256'),
            'rate_observed_at': data.get('observed_at'),
            'notice': '当前Job单价×spendTime（暂按秒）×节点数；时长单位未独立验证，非历史单价或账单；缺项不计零'}
