"""Sandbox cost estimates from observed native SKU quotes, never Node rates."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re

from . import config, db


def record_prices(run_id: str, receipt: dict) -> dict:
    if not receipt.get('ok') or receipt.get('truncated'):
        return {'status': 'unknown'}
    try:
        wrapper = json.loads(receipt['stdout'])
        items = wrapper['data']['items'] if wrapper.get('ok') is True else None
        if not isinstance(items, list) or len(items) > 200:
            return {'status': 'unknown'}
    except (ValueError, KeyError, TypeError, AttributeError):
        return {'status': 'unknown'}
    rates = {}
    for item in items:
        if not isinstance(item, dict) or item.get('class') != 'cpu':
            continue
        cpu, memory = str(item.get('cpu', '')), str(item.get('memory', ''))
        match = re.fullmatch(r'([1-9][0-9]{0,3})Gi', memory)
        price = re.fullmatch(r'([0-9]{1,8}(?:\.[0-9]{1,8})?) RMB/h', str(item.get('price', '')))
        if (not re.fullmatch(r'[1-9][0-9]{0,3}', cpu) or not match or not price
                or item.get('sku_name') != f'c{cpu}_m{match[1]}_cpu'
                or type(item.get('sku_id')) is not int):
            continue
        key = cpu + 'c' + match[1] + 'g'
        value = {'hourly_rate': str(Decimal(price[1])), 'currency': 'CNY',
                 'sku_id': item['sku_id'], 'sku_name': item['sku_name']}
        if key in rates and rates[key] != value:
            return {'status': 'unknown'}  # Ambiguous SKUs cannot provide a rate.
        rates[key] = value
    payload = {'rates': rates, 'observed_at': db.utcnow(),
               'source': 'bohr sandbox machine list',
               'source_receipt_sha256': hashlib.sha256(receipt['stdout'].encode()).hexdigest()}
    db.append_event(run_id, 'controller', 'sandbox.price_quote', payload)
    return {'status': 'received', 'rate_count': len(rates)}


def refresh(run_id: str) -> dict:
    if not db.query_one('SELECT 1 FROM compute_sandboxes WHERE run_id=?', (run_id,)):
        return {'status': 'not_needed'}
    if db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='sandbox.price_quote'", (run_id,)):
        return {'status': 'recorded'}
    cfg = config.load_settings()['bohrium']
    if not config.resolve_secret(cfg.get('access_key_secret_ref', '')):
        return {'status': 'missing_credentials'}
    from . import compute
    try:
        result = record_prices(run_id, compute._native(
            ['sandbox', 'machine', 'list', '--output', 'json'], timeout=25))
    except Exception as exc:
        result = {'status': 'unknown', 'error_code': type(exc).__name__}
    if result['status'] == 'unknown':
        db.append_event(run_id, 'controller', 'sandbox.price_unavailable', result)
    return result


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def estimate(run_id: str) -> dict:
    rows = db.query('SELECT * FROM compute_sandboxes WHERE run_id=?', (run_id,))
    quote = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='sandbox.price_quote'"
                         ' ORDER BY seq DESC LIMIT 1', (run_id,))
    data = json.loads(quote['payload']) if quote else {}
    rates = data.get('rates', {})
    observed = {}
    for event in db.query("SELECT payload FROM events WHERE run_id=?"
                          " AND type='sandbox.resources_observed' ORDER BY seq", (run_id,)):
        fact = json.loads(event['payload'])
        observed[(fact.get('operation_id'), fact.get('sandbox_id'))] = fact.get('resources', {})
    total, seconds, priced = Decimal(0), Decimal(0), 0
    for row in rows:
        requested = json.loads(row['request_json'])
        resources = observed.get((row['operation_id'], row['sandbox_id']), {})
        cpu = resources.get('cpu', requested.get('cpu'))
        rate = rates.get(cpu) if not (requested.get('gpu') or resources.get('gpu_count')) else None
        end = (row['deleted_at'] if row['status'] in ('deleted', 'failed') and row['deleted_at']
               else row['updated_at'] if row['status'] == 'failed' else None)
        if not rate or not end:
            continue
        try:
            duration = Decimal(str((_timestamp(end) - _timestamp(row['created_at'])).total_seconds()))
            if duration < 0:
                continue
        except (TypeError, ValueError):
            continue
        priced += 1
        seconds += duration
        total += Decimal(rate['hourly_rate']) * duration / 3600
    missing = len(rows) - priced
    return {'status': 'estimated_partial' if priced and missing else 'estimated' if priced else 'unknown',
            'amount': str(total.quantize(Decimal('0.0001'))) if priced else None,
            'currency': 'CNY' if priced else None, 'priced_count': priced, 'unpriced_count': missing,
            'observed_seconds': float(seconds) if priced else None,
            'basis': 'current_sandbox_rate_times_observed_lifetime',
            'source_receipt_sha256': data.get('source_receipt_sha256'),
            'rate_observed_at': data.get('observed_at'),
            'notice': '当前沙箱公开机型报价×控制器观察生命周期；不是历史单价或实际账单，未定价项不计零'}
