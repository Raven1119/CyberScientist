"""Sandbox cost estimates from observed native SKU quotes, never Node rates."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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


def record_costs(run_id: str, receipt: dict) -> dict:
    """Project a read-only native billing observation onto exact owned IDs.

    The current CLI contract uses paymentType=0 (or absent) for CNY and 1
    for photons. Query-time values are not final settlement confirmations.
    """
    if not receipt.get('ok') or receipt.get('truncated'):
        return {'status': 'unknown'}
    try:
        body = json.loads(receipt['stdout'])
        items = body['data']['items'] if body.get('ok') is True else None
        if not isinstance(items, list) or len(items) > 100:
            return {'status': 'unknown'}
    except (ValueError, KeyError, TypeError, AttributeError):
        return {'status': 'unknown'}
    owned = {row['sandbox_id']: row['operation_id'] for row in db.query(
        'SELECT sandbox_id,operation_id FROM compute_sandboxes WHERE run_id=?', (run_id,))
        if row['sandbox_id']}
    costs, conflicts = {}, set()
    for item in items:
        if not isinstance(item, dict):
            continue
        sid = item.get('sandbox_id')
        payment = item.get('paymentType', 0)
        if not isinstance(sid, str) or sid not in owned or type(payment) is not int or payment not in (0, 1):
            continue
        value = item.get('photonCost', item.get('cost')) if payment == 1 else item.get('cost')
        if type(value) not in (int, float, str):
            continue
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or amount < 0 or amount > Decimal('1000000000'):
                continue
        except InvalidOperation:
            continue
        cost = {'sandbox_id': sid, 'operation_id': owned[sid], 'amount': str(amount),
                'currency': 'photons' if payment == 1 else 'CNY'}
        if sid in costs and costs[sid] != cost:
            conflicts.add(sid)
        costs[sid] = cost
    meta = body.get('meta')
    timestamp = meta.get('timestamp') if isinstance(meta, dict) else None
    observed_at = None
    if type(timestamp) is int:
        try:
            observed_at = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            pass
    payload = {'costs': [costs[sid] for sid in sorted(costs) if sid not in conflicts],
               'observed_at': observed_at, 'recorded_at': db.utcnow(),
               'final_settlement_confirmed': False,
               'source': 'bohr sandbox list --query all',
               'source_receipt_sha256': hashlib.sha256(receipt['stdout'].encode()).hexdigest()}
    db.append_event(run_id, 'controller', 'sandbox.cost_observed', payload)
    return {'status': 'received', 'matched_count': len(payload['costs'])}


def observed_costs(run_id: str) -> dict:
    row = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='sandbox.cost_observed'"
                       ' ORDER BY seq DESC LIMIT 1', (run_id,))
    data = json.loads(row['payload']) if row else {}
    owned = {(r['sandbox_id'], r['operation_id']) for r in db.query(
        'SELECT sandbox_id,operation_id FROM compute_sandboxes WHERE run_id=?', (run_id,))}
    costs = [item for item in data.get('costs', [])
             if (item['sandbox_id'], item['operation_id']) in owned]
    totals = {}
    for item in costs:
        currency = item['currency']
        totals[currency] = totals.get(currency, Decimal(0)) + Decimal(item['amount'])
    return {'status': 'observed' if costs else 'unknown',
            'amounts': {key: str(value) for key, value in totals.items()},
            'matched_count': len(costs), 'unmatched_count': len(owned) - len(costs),
            'final_settlement_confirmed': False,
            'observed_at': data.get('observed_at'),
            'recorded_at': data.get('recorded_at'),
            'source_receipt_sha256': data.get('source_receipt_sha256')}


def refresh(run_id: str) -> dict:
    if not db.query_one('SELECT 1 FROM compute_sandboxes WHERE run_id=?', (run_id,)):
        return {'status': 'not_needed'}
    cfg = config.load_settings()['bohrium']
    if not config.resolve_secret(cfg.get('access_key_secret_ref', '')):
        return {'status': 'missing_credentials'}
    from . import compute
    if not db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='sandbox.cost_observed'", (run_id,)):
        try:
            receipt = compute._native(['sandbox', 'list', '--query', 'all', '--page-size', '100',
                                       '--output', 'json'], timeout=25)
            # Keep the complete redacted source locally for billing audits;
            # only the owned projection above enters Run events and the UI.
            from .bohr_proxy import redact_value
            safe = redact_value(receipt, list(config.sensitive_values()))
            raw = json.dumps(safe, ensure_ascii=False, sort_keys=True).encode()
            folder = config.DATA_DIR / 'audit' / 'billing'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (hashlib.sha256(raw).hexdigest() + '.json')).write_bytes(raw)
            observed = record_costs(run_id, receipt)
        except Exception as exc:
            observed = {'status': 'unknown', 'error_code': type(exc).__name__}
        if observed['status'] == 'unknown':
            db.append_event(run_id, 'controller', 'sandbox.cost_unavailable', observed)
    if db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='sandbox.price_quote'", (run_id,)):
        return {'status': 'recorded'}
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
