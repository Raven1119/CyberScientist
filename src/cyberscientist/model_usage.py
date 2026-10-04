"""Read-only token accounting from cumulative native session observations."""
from __future__ import annotations
import json
from . import db


def summarize(run_id: str) -> dict:
    row = db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (run_id,))
    settings = json.loads(row['config_snapshot'])['settings']
    sessions = {}
    unknown = []
    for event in db.query("SELECT seq,type,payload FROM events WHERE run_id=? AND type IN"
                          " ('brain.usage.updated','prime.usage.updated','maintenance.usage') ORDER BY seq", (run_id,)):
        payload = json.loads(event['payload'])
        role = ('executor' if event['type'].startswith('prime.') else
                'post_review' if payload.get('kind') == 'postreview' else 'brain')
        wrapped = payload.get('usage') or {}
        # Maintenance retains the complete BrainEvent payload.
        if isinstance(wrapped, dict) and 'usage' in wrapped:
            payload = {**payload, 'session_id': wrapped.get('session_id')}
            wrapped = wrapped['usage'] or {}
        total = wrapped.get('total') if isinstance(wrapped, dict) else None
        sid = payload.get('session_id')
        if not sid or not isinstance(total, dict):
            unknown.append({'seq': event['seq'], 'role': role, 'reason': 'missing_session_or_cumulative_usage'})
            continue
        counts = {key: total.get(source) for key, source in
                  [('input', 'inputTokens'), ('cached_input', 'cachedInputTokens'), ('output', 'outputTokens')]}
        if any(type(counts[k]) is not int or counts[k] < 0 for k in ('input', 'output')):
            unknown.append({'seq': event['seq'], 'role': role, 'reason': 'missing_input_or_output'})
            continue
        old = sessions.get(sid)
        if old and (counts['input'] < old['tokens']['input'] or counts['output'] < old['tokens']['output']):
            unknown.append({'seq': event['seq'], 'role': role, 'reason': 'cumulative_counter_regressed'})
            continue
        sessions[sid] = {'role': role, 'session_id': sid, 'tokens': counts}
    for item in sessions.values():
        choice = settings[item['role']]
        identity = (choice.get('provider') or choice['runtime']) + '/' + choice['model_id']
        price = settings.get('model_pricing', {}).get(identity)
        item.update(model=identity, estimate=None, invoice_status='unknown')
        if not price:
            continue
        try:
            validate({identity: price})
        except (ValueError, TypeError, KeyError):
            item['pricing_error'] = 'invalid_price_config'
            continue
        counts = item['tokens']
        rates = [price[t] for t in ('off_peak', 'peak') if t in price]
        tier = price.get('billing_tier')
        if tier in ('off_peak', 'peak'):
            rates = [price[tier]]
        costs = []
        cached = counts['cached_input']
        caches = [cached] if type(cached) is int and 0 <= cached <= counts['input'] else [0, counts['input']]
        for rate in rates:
            for hit in caches:
                costs.append(((counts['input'] - hit) * rate['input'] + hit * rate['cached_input'] + counts['output'] * rate['output']) / 1_000_000)
        if costs:
            item['estimate'] = {'currency': price['currency'], 'lower': min(costs), 'upper': max(costs),
                                'source': price['source'], 'observed_on': price['observed_on'], 'billing_tier': tier}
    missing = [role for role in ('brain', 'executor', 'post_review') if not any(s['role'] == role for s in sessions.values())]
    return {'sessions': list(sessions.values()), 'unknown_observations': unknown,
            'roles_without_observed_usage': missing, 'invoice_status': 'unknown',
            'aggregation': 'latest monotone cumulative counters per distinct native session; missing is unknown'}


def validate(prices: dict) -> None:
    import math
    if not isinstance(prices, dict):
        raise ValueError('价格配置必须为对象')
    for name, price in prices.items():
        if not isinstance(name, str) or not isinstance(price, dict) or not price.get('source') or not price.get('observed_on') or price.get('currency') not in ('USD', 'CNY'):
            raise ValueError('价格须含币种、来源和观察日期')
        if price.get('billing_tier') not in ('unknown', 'off_peak', 'peak'):
            raise ValueError('价格时段须为 unknown/off_peak/peak')
        if price.get('billing_tier') in ('off_peak', 'peak') and price['billing_tier'] not in price:
            raise ValueError('所选计费时段缺少价格')
        for tier in ('off_peak', 'peak'):
            if tier not in price:
                continue
            for key in ('input', 'cached_input', 'output'):
                value = price[tier].get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError('每百万 token 价格须为非负有限数')
