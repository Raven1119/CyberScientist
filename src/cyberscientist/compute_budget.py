"""One atomic CNY estimate reservation for Jobs and sandboxes; never a bill."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json

from . import db


def validate_cap(value):
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
        if type(value) not in (int, float, str) or not amount.is_finite() or amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        from .compute import ComputeError
        raise ComputeError('INVALID_LIMITS', '算力估算金额上限必须是有限正数')
    return str(amount)


def _cap(run_id):
    row = db.query_one('SELECT a.max_compute_cost_cny FROM authorizations a JOIN runs r'
                       ' ON r.authorization_id=a.id WHERE r.id=?', (run_id,))
    return row['max_compute_cost_cny'] if row else None


def rate(run_id, kind, sku):
    """Resolve a captured CPU quote; fetch at most once here, before reserving."""
    if _cap(run_id) is None:
        return None
    from . import runtime_facts, compute, job_costs, sandbox_costs
    quote = runtime_facts._quote(run_id, kind)
    candidate = quote['rates'].get(sku)
    if not candidate:
        argv = (['machine', 'list', '--choose-type', 'cpu', '--scene', 'job']
                if kind == 'job' else ['sandbox', 'machine', 'list'])
        receipt = compute._native(argv + ['--no-interactive', '--output', 'json'], modern=True, timeout=25)
        if kind == 'job':
            job_costs.record_prices(run_id, receipt, scene='job')
        else:
            sandbox_costs.record_prices(run_id, receipt)
        quote = runtime_facts._quote(run_id, kind)
        candidate = quote['rates'].get(sku)
    if not candidate or candidate.get('currency') != 'CNY':
        raise compute.ComputeError('COMPUTE_PRICE_UNKNOWN', '无法按公开CPU单价核对金额上限',
                                   {'kind': kind, 'resource': sku, 'price_status': 'unknown'})
    try:
        value = Decimal(str(candidate.get('hourly_rate')))
        if not value.is_finite() or value < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        raise compute.ComputeError('COMPUTE_PRICE_UNKNOWN', 'CPU公开单价无效')
    return {'hourly_rate_cny': str(value), 'quote_ref': quote['event_ref']}


def _amount(conn, row):
    """Known closed lifetimes settle; ambiguous creation reserves its full bound."""
    table = 'compute_jobs' if row['kind'] == 'job' else 'compute_sandboxes'
    resource = conn.execute(f'SELECT * FROM {table} WHERE run_id=? AND operation_id=?',
                            (row['run_id'], row['operation_id'])).fetchone()
    seconds = row['duration_seconds']
    if resource:
        if row['kind'] == 'job' and resource['status'] == 'not_started':
            return Decimal(0)
        end = None
        if row['kind'] == 'job' and resource['status'] in ('Finished', 'Failed', 'Stopped'):
            end = resource['updated_at']
        elif row['kind'] == 'sandbox' and resource['deleted_at']:
            end = resource['deleted_at']
        if end:
            seconds = min(seconds, max(0, (datetime.fromisoformat(end)
                - datetime.fromisoformat(resource['created_at'])).total_seconds()))
    return Decimal(row['hourly_rate_cny']) * Decimal(str(seconds)) / 3600


def summary_tx(conn, run_id):
    rows = conn.execute('SELECT * FROM compute_cost_reservations WHERE run_id=?', (run_id,)).fetchall()
    amount = sum((_amount(conn, row) for row in rows), Decimal(0))
    return {'committed_estimate_cny': str(amount), 'reservations': len(rows),
            'basis': 'public_rate_times_reserved_or_closed_lifetime', 'is_bill': False}


def summary(run_id):
    with db.transaction() as conn:
        result = summary_tx(conn, run_id)
    cap = _cap(run_id)
    result['cap_cny'] = cap
    result['remaining_cny'] = str(max(Decimal(0), Decimal(cap)-Decimal(result['committed_estimate_cny']))) if cap else None
    return result


def reserve_tx(conn, run_id, kind, operation_id, seconds, quote):
    from .compute import ComputeError
    auth = conn.execute('SELECT a.max_compute_cost_cny FROM authorizations a JOIN runs r'
                        ' ON r.authorization_id=a.id WHERE r.id=?', (run_id,)).fetchone()
    if not auth or auth['max_compute_cost_cny'] is None:
        return
    if not quote:
        raise ComputeError('COMPUTE_PRICE_UNKNOWN', '创建前没有可核验的CPU单价')
    existing = conn.execute('SELECT 1 FROM compute_cost_reservations WHERE run_id=? AND kind=?'
                            ' AND operation_id=?', (run_id, kind, operation_id)).fetchone()
    if existing:
        return
    amount = Decimal(quote['hourly_rate_cny']) * seconds / 3600
    used = Decimal(summary_tx(conn, run_id)['committed_estimate_cny'])
    if used + amount > Decimal(auth['max_compute_cost_cny']):
        raise ComputeError('COMPUTE_COST_LIMIT', '新资源将超出本Run的公开单价估算上限',
            {'committed_estimate_cny': str(used), 'requested_estimate_cny': str(amount),
             'cap_cny': auth['max_compute_cost_cny'], 'is_bill': False})
    conn.execute('INSERT INTO compute_cost_reservations VALUES(?,?,?,?,?,?,?,?)',
                 (run_id, operation_id, kind, quote['hourly_rate_cny'], seconds, str(amount),
                  quote['quote_ref'], db.utcnow()))
