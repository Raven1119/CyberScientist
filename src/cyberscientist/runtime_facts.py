"""Read-only operating facts, shared by brain frames and executor tools."""
from __future__ import annotations

from datetime import datetime, timezone
import json

from . import db, local_scoring, runtime_environments


def _quote(run_id: str, kind: str) -> dict:
    row = db.query_one("SELECT run_id,seq,payload,recorded_at FROM events WHERE source='controller'"
                       " AND type=? ORDER BY (run_id=?) DESC,recorded_at DESC,rowid DESC LIMIT 1",
                       (kind + '.price_quote', run_id))
    if not row:
        return {'status': 'unknown', 'rates': {}, 'source': None, 'observed_at': None}
    data = json.loads(row['payload'])
    return {'status': 'observed', 'rates': data.get('rates', {}),
            'source': data.get('source'), 'observed_at': data.get('observed_at'),
            'source_receipt_sha256': data.get('source_receipt_sha256'),
            'event_ref': f"{row['run_id']}#{row['seq']}"}


def record_public_images(receipt: dict, *, query: str) -> dict:
    """Cache public discovery separately from any historical research trace."""
    import hashlib
    if not receipt.get('ok') or receipt.get('truncated'):
        return {'status': 'unknown'}
    try:
        body = json.loads(receipt['stdout'])
        items = body['data']['items']
        if body.get('ok') is not True or not isinstance(items, list):
            return {'status': 'unknown'}
    except (ValueError, TypeError, KeyError):
        return {'status': 'unknown'}
    safe_items = [{key: item[key] for key in ('name', 'image', 'image_address', 'address', 'description', 'identity')
                   if key in item} for item in items if isinstance(item, dict)][:30]
    data = {'items': safe_items, 'source': 'bohr image search', 'query': query,
            'source_receipt_sha256': hashlib.sha256(receipt['stdout'].encode()).hexdigest()}
    db.execute('INSERT INTO runtime_observations VALUES(?,?,?) ON CONFLICT(kind) DO UPDATE SET'
               ' payload_json=excluded.payload_json,observed_at=excluded.observed_at',
               ('public_image_catalog', json.dumps(data, ensure_ascii=False), db.utcnow()))
    return {'status': 'observed', 'items': len(safe_items)}


def facts(run_id: str) -> dict:
    run = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    if not run:
        return {'status': 'unknown'}
    auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],))
    now = datetime.now(timezone.utc)
    from . import run_clock
    elapsed = run_clock.elapsed(run)
    jobs = db.query("SELECT status FROM compute_jobs WHERE run_id=? AND status!='not_started'", (run_id,))
    sandbox_rows = db.query('SELECT created_at,expires_at,deleted_at,status FROM compute_sandboxes'
                           ' WHERE run_id=?', (run_id,))
    committed_seconds = sum(max(0, (datetime.fromisoformat(r['deleted_at'] or r['expires_at'])
                                  - datetime.fromisoformat(r['created_at'])).total_seconds())
                            for r in sandbox_rows)
    remaining = {'run_seconds': max(0, auth['max_run_minutes'] * 60 - elapsed) if auth else None,
                 'jobs': max(0, auth['max_jobs'] - len(jobs)) if auth else None,
                 'sandbox_minutes': max(0, auth['max_sandbox_minutes'] - committed_seconds / 60) if auth else None,
                 'sandbox_concurrent_slots': max(0, auth['max_sandboxes'] - sum(
                     r['status'] in ('creating', 'active', 'unknown', 'deleting') for r in sandbox_rows)) if auth else None}
    quotes = {kind: _quote(run_id, kind) for kind in ('job', 'sandbox')}
    try:
        manifest = local_scoring.scorer_manifest(run['challenge_id'])
    except local_scoring.LocalScoreError as exc:
        scoring = {'status': 'unknown', 'reason': exc.code}
        environment = {'status': 'unknown', 'declared_image': None}
    else:
        runtime = manifest.get('runtime', {})
        scoring = {'status': 'declared', 'scorer_version': manifest['scorer_version'],
                   'runtime_declaration': runtime,
                   'estimated_seconds': runtime.get('estimated_seconds'),
                   'declared_timeout_seconds': runtime.get('score_timeout', 120),
                   'estimate_source': 'scorer.json' if runtime.get('estimated_seconds') else 'unknown',
                   'notice': '最终评分需要在授权时间内完成；timeout是上限，不是实测耗时。'}
        observations = db.query("SELECT payload,run_id,seq FROM events WHERE source='controller'"
            " AND type='sandbox.exec_completed' AND json_extract(payload,'$.status')='completed'"
            " ORDER BY recorded_at DESC,rowid DESC LIMIT 100")
        for observation in observations:
            payload = json.loads(observation['payload'])
            command = payload.get('command', '')
            duration = payload.get('duration_seconds')
            if (manifest['scorer_version'] in command and 'scorer/' + manifest['entrypoint'] in command
                    and type(duration) in (float, int) and duration > 0):
                scoring.update(estimated_seconds=duration, estimate_source='historical_controlled_execution',
                               observation_ref=f"{observation['run_id']}#{observation['seq']}")
                break
        environment_id = runtime.get('environment_id')
        descriptor = next((item for item in runtime_environments.facts()
                           if item.get('id') == environment_id), None)
        environment = {'status': descriptor.get('status', 'unverified') if descriptor else 'unknown',
                       'declared_image': manifest['image'], 'environment_id': environment_id,
                       'required_identity': descriptor.get('identity') if descriptor else None,
                       'verified_image': descriptor.get('image') if descriptor else None,
                       'descriptor': descriptor,
                       'notice': '未验证的环境是事实；执行器可在已授权Job或沙箱内自行准备。'}
    catalog = db.query_one("SELECT payload,run_id,seq,recorded_at FROM events WHERE source='controller'"
        " AND type='environment.public_image_catalog' ORDER BY recorded_at DESC,rowid DESC LIMIT 1")
    required = environment.get('required_identity')
    observed = db.query_one("SELECT * FROM runtime_observations WHERE kind='public_image_catalog'")
    catalog_items = (json.loads(observed['payload_json']).get('items', []) if observed else
                     json.loads(catalog['payload']).get('items', []) if catalog else [])
    environment['known_public_images'] = [item | {'declared_version_match':
        (all(item.get('identity', {}).get(key) == value for key, value in required.items())
         if required and isinstance(item.get('identity'), dict) else 'unknown')}
        for item in catalog_items[:30]]
    environment['public_image_source'] = ('observation:public_image_catalog' if observed else
                                         f"{catalog['run_id']}#{catalog['seq']}" if catalog else None)
    environment['public_image_observed_at'] = observed['observed_at'] if observed else catalog['recorded_at'] if catalog else None
    environment['network'] = {kind: {'status': 'unknown', 'observations': []} for kind in ('job', 'sandbox')}
    for row in db.query("SELECT payload,run_id,seq FROM events WHERE source='controller'"
                        " AND type='compute.network_observed' ORDER BY recorded_at DESC,rowid DESC LIMIT 20"):
        payload = json.loads(row['payload'])
        kind = payload.get('resource_kind')
        if kind in environment['network']:
            environment['network'][kind]['status'] = 'observed'
            environment['network'][kind]['observations'].append({
                'host': payload.get('host'), 'result': payload.get('result', 'unknown'),
                'event_ref': f"{row['run_id']}#{row['seq']}"})
    from . import compute, compute_budget
    limits = compute.validate_limits(json.loads(auth['job_limits_json'])) if auth else compute.DEFAULT_LIMITS
    import re
    allowed_machines = {}
    for name, price in quotes['job']['rates'].items():
        match = re.fullmatch(r'c(\d+)_m(\d+)_cpu', name)
        if match and int(match[1]) <= limits['max_cpu'] and int(match[2]) <= limits['max_memory_gb']:
            allowed_machines[name] = price
    channels = {}
    for row in db.query('SELECT status,input_bytes FROM compute_jobs'):
        size = row['input_bytes']
        bucket = 'unknown' if size is None else '<=1MiB' if size <= 1024**2 else '<=256MiB' if size <= 256*1024**2 else '>256MiB'
        stats = channels.setdefault(bucket, {'attempts': 0, 'finished': 0, 'unknown': 0})
        stats['attempts'] += 1
        stats['finished'] += row['status'] == 'Finished'
        stats['unknown'] += row['status'] == 'unknown'
    transfer_channels = {}
    for row in db.query("SELECT payload FROM events WHERE source='controller' AND type='sandbox.files_write'"):
        payload = json.loads(row['payload'])
        size = sum(item.get('bytes', 0) for item in payload.get('files', []))
        bucket = '<=1MiB' if size <= 1024**2 else '<=256MiB' if size <= 256*1024**2 else '>256MiB'
        stats = transfer_channels.setdefault(bucket, {'attempts': 0, 'completed': 0, 'unknown': 0})
        stats['attempts'] += 1
        stats['completed'] += payload.get('status') == 'completed'
        stats['unknown'] += payload.get('status') == 'unknown'
    from . import environment_saves
    saved_environments = environment_saves.saves()
    cost = compute.costs(run_id)
    return {'status': 'observed', 'observed_at': now.isoformat(), 'remaining': remaining,
            'scoring': scoring, 'environment': environment, 'cpu_prices': quotes,
            'effective_job_limits': limits, 'allowed_priced_machines': allowed_machines,
            'channels_by_input_size': {'job': channels, 'sandbox_transfer': transfer_channels}, 'registered_environments': runtime_environments.facts() + saved_environments,
            'environment_save_authorization': {'limit': auth['max_environment_saves'] if auth else 0,
                'used': sum(item['run_id'] == run_id for item in saved_environments), 'cost_status': 'unknown' if saved_environments else 'no_saves'},
            'spent_estimates': {'job': cost['job_estimate'], 'sandbox': cost['sandbox_estimate']},
            'compute_budget': compute_budget.summary(run_id),
            'budget_note': '未知费用不计零；价格附观察时间，不是供应商最终账单。',
            'historical_materials': {'own_local_materials_allowed': True,
                                     'other_users_submissions_allowed': False}}
