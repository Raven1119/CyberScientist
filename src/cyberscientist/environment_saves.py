"""Bounded private environment builds, observed receipts and no blind retries."""
from __future__ import annotations
import base64
import hashlib
import json
import re
import urllib.error
import urllib.request
from . import compute, config, db, environment_facts


def _api(method, path, payload=None):
    settings = config.load_settings()['bohrium']
    if settings.get('wenyon_executable') and method == 'POST' and path == 'image/private':
        from pathlib import Path
        stage = config.DATA_DIR / 'environment-builds' / hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        stage.mkdir(parents=True, exist_ok=True)
        dockerfile = stage / 'Dockerfile'
        dockerfile.write_bytes(base64.b64decode(payload['dockerfile'], validate=True))
        receipt = compute._native(['image', 'build', '--name', payload['name'],
            '--project-id', str(payload['projectId']), '--desc', payload['desc'],
            '--dockerfile', str(dockerfile), '-y', '--no-interactive', '-o', 'json'], modern=True)
        try:
            envelope = json.loads(receipt['stdout'])
            response = envelope.get('data', {}).get('response', {})
        except (ValueError, AttributeError):
            envelope, response = {}, {}
        accepted = receipt['ok'] and envelope.get('ok') is True and response.get('id')
        return {'status': 'received' if accepted else 'unknown' if receipt.get('unknown') else 'failed',
                'route': '/openapi/v4/sandbox_work/image/build',
                'body': {'code': 0, 'data': response} if accepted else envelope,
                'native_receipt': receipt, 'sha256': hashlib.sha256(receipt['stdout'].encode()).hexdigest()}
    key = config.resolve_secret(config.load_settings()['bohrium'].get('access_key_secret_ref', ''))
    if not key:
        raise compute.ComputeError('MISSING_CREDENTIAL', '环境保存缺少 Bohrium 凭据')
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    version = 'v4' if settings.get('wenyon_executable') else 'v2'
    request = urllib.request.Request(compute.client_host_overrides(settings, wenyon=True)['OPENAPI_HOST'] + '/openapi/' + version + '/' + path,
        data=json.dumps(payload).encode() if payload is not None else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return {'status': 'unknown', 'reason': 'oversized_response'}
            parsed = json.loads(raw)
            from .bohr_proxy import redact_value
            return {'status': 'received', 'http_status': response.status, 'route': '/openapi/' + version + '/' + path,
                    'body': redact_value(parsed, [key]), 'sha256': hashlib.sha256(raw).hexdigest()}
    except urllib.error.HTTPError as exc:
        return {'status': 'failed' if 400 <= exc.code < 500 else 'unknown', 'http_status': exc.code}
    except (OSError, ValueError):
        return {'status': 'unknown', 'reason': 'transport_or_json'}


def saves() -> list[dict]:
    return [dict(row) for row in db.query('SELECT operation_id,run_id,status,resource_id,recipe_json,smoke_command,recipe_sha256,cost_status,created_at FROM environment_saves')]


def save(run_id, operation_id, dockerfile, recipe, smoke_command):
    if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,70}', operation_id):
        raise compute.ComputeError('INVALID_OPERATION', '环境保存需要稳定 operation_id')
    if (not isinstance(dockerfile, str) or len(dockerfile) > 20_000
            or not isinstance(recipe, str) or not recipe.strip() or len(recipe) > 20_000
            or not isinstance(smoke_command, str) or not smoke_command.strip() or len(smoke_command) > 4000):
        raise compute.ComputeError('INVALID_ENVIRONMENT', '需要有界公开软件配方、Dockerfile 和冒烟命令')
    from .observation import strip_secrets
    if any(strip_secrets(value) != value for value in (dockerfile, recipe, smoke_command)):
        raise compute.ComputeError('SECRET_INPUT', '环境配方含密钥，未保存或投递')
    # Builds contain public software only: no workspace copies or credentials.
    if re.search(r'(?im)^\s*(COPY|ADD|SECRET)\b|(?im:ENV\s+\S*(?:KEY|TOKEN|PASSWORD|SECRET)\b)|result_package\.zip|auth\.json|secrets\.json|\.env\b', dockerfile):
        raise compute.ComputeError('INVALID_ENVIRONMENT', '私有环境仅保存公开软件；不复制科研产物或凭据')
    effective = dockerfile.rstrip() + '\nRUN ' + smoke_command + '\n'
    project = compute._project_id(config.load_settings()['bohrium']['project_id'])
    digest = hashlib.sha256(effective.encode()).hexdigest()
    request = json.dumps({'recipe': recipe, 'dockerfile': effective}, ensure_ascii=False, sort_keys=True)
    with db.transaction() as conn:
        prior = conn.execute('SELECT * FROM environment_saves WHERE operation_id=?', (operation_id,)).fetchone()
        if prior:
            if prior['run_id'] != run_id or prior['recipe_json'] != request:
                raise compute.ComputeError('OPERATION_CONFLICT', '环境保存 ID 已绑定其他配方')
            return dict(prior) | {'deduplicated': True}
        run = conn.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        auth = conn.execute('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],)).fetchone() if run else None
        if not run or run['phase'] != 'running' or run['gate'] != 'open':
            raise compute.ComputeError('RUN_NOT_RUNNING', '环境保存需要运行中的授权 Run')
        if not auth or auth['max_environment_saves'] <= 0:
            raise compute.ComputeError('NOT_AUTHORIZED', '未授权环境保存数量')
        if auth['max_compute_cost_cny'] is not None:
            raise compute.ComputeError('ENVIRONMENT_PRICE_UNKNOWN', '环境构建单价尚未核实，不能保证本 Run 金额上限')
        used = conn.execute('SELECT COUNT(*) FROM environment_saves WHERE run_id=?', (run_id,)).fetchone()[0]
        if used >= auth['max_environment_saves']:
            raise compute.ComputeError('ENVIRONMENT_LIMIT', '环境保存数量已用尽，unknown 计入数量')
        conn.execute('INSERT INTO environment_saves VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                     (operation_id, run_id, 'creating', None, request, smoke_command, digest, 'unknown', '{}', db.utcnow(), db.utcnow()))
        db.append_event_tx(conn, run_id, 'controller', 'environment.save_reserved',
                           {'operation_id': operation_id, 'recipe_sha256': digest, 'cost_status': 'unknown'})
    name = 'csenv' + hashlib.sha256(operation_id.encode()).hexdigest()[:24] if config.load_settings()['bohrium'].get('wenyon_executable') else 'cs-env-' + operation_id
    try:
        response = _api('POST', 'image/private', {'name': name,
            'projectId': project, 'device': 'container', 'desc': 'Public software environment; ' + digest,
            'buildType': 1, 'dockerfile': base64.b64encode(effective.encode()).decode()})
    except compute.ComputeError as exc:
        db.execute("UPDATE environment_saves SET status='failed',receipt_json=?,updated_at=? WHERE operation_id=?",
                   (json.dumps({'code': exc.code, 'remote_effect': 'none'}), db.utcnow(), operation_id))
        raise
    body = response.get('body') or {}
    data = body.get('data', body) if isinstance(body, dict) else {}
    resource_id = (data.get('id') or data.get('imageId')) if isinstance(body, dict) and isinstance(data, dict) and body.get('code') == 0 else None
    resource_id = str(resource_id) if resource_id else None
    if isinstance(body, dict) and body.get('code') not in (None, 0):
        resource_id = None
        response['status'] = 'failed'
    status = 'building' if resource_id else 'failed' if response['status'] == 'failed' else 'unknown'
    db.execute('UPDATE environment_saves SET status=?,resource_id=?,receipt_json=?,updated_at=? WHERE operation_id=?',
               (status, str(resource_id) if resource_id else None, json.dumps(response), db.utcnow(), operation_id))
    db.append_event(run_id, 'controller', 'environment.save_receipt',
                    {'operation_id': operation_id, 'status': status, 'resource_id': resource_id,
                     'recipe_sha256': digest, 'http_status': response.get('http_status'), 'cost_status': 'unknown'})
    return {'operation_id': operation_id, 'status': status, 'resource_id': resource_id,
            'recipe_sha256': digest, 'cost_status': 'unknown', 'automatic_resend': False}


def reconcile(operation_id):
    row = db.query_one('SELECT * FROM environment_saves WHERE operation_id=?', (operation_id,))
    if not row:
        return {'status': 'unknown', 'automatic_resend': False}
    if not row['resource_id']:
        listing = _api('GET', 'image/private?device=container&type=private&page=1&pageSize=100')
        body = listing.get('body') or {}
        data = body.get('data', body) if isinstance(body, dict) else {}
        names = {'cs-env-' + operation_id, 'csenv' + hashlib.sha256(operation_id.encode()).hexdigest()[:24]}
        matches = [item for item in data.get('items', []) if item.get('name', '').removesuffix(':latest') in names] if isinstance(data, dict) else []
        if len(matches) != 1 or not matches[0].get('id'):
            return {'status': 'unknown', 'automatic_resend': False}
        db.execute('UPDATE environment_saves SET resource_id=?,status=\'building\' WHERE operation_id=?', (str(matches[0]['id']), operation_id))
        row = db.query_one('SELECT * FROM environment_saves WHERE operation_id=?', (operation_id,))
    response = _api('GET', 'image/private/' + row['resource_id'])
    body = response.get('body') or {}
    data = body.get('data', body) if isinstance(body, dict) else {}
    # Numeric undocumented build states are retained as observations, not
    # promoted to a smoke pass. Only the documented available state verifies.
    verified = isinstance(body, dict) and body.get('code') == 0 and isinstance(data, dict) and (
        data.get('status') == 'available' or response.get('route', '').startswith('/openapi/v4/') and data.get('status') == 2)
    status = 'verified' if verified else row['status']
    db.execute('UPDATE environment_saves SET status=?,receipt_json=?,updated_at=? WHERE operation_id=?',
               (status, json.dumps(response), db.utcnow(), operation_id))
    event = db.append_event(row['run_id'], 'controller', 'environment.save_observed',
               {'operation_id': operation_id, 'status': status, 'resource_id': row['resource_id'],
                'native_status': data.get('status') if isinstance(data, dict) else None,
                'recipe_sha256': row['recipe_sha256'], 'receipt_sha256': response.get('sha256')})
    if verified:
        environment_facts.record('saved:' + operation_id, '可复用环境 ' + operation_id,
            {'resource_id': row['resource_id'], 'recipe': json.loads(row['recipe_json'])['recipe'],
             'smoke_command': row['smoke_command'], 'recipe_sha256': row['recipe_sha256'],
             'image': data.get('url'), 'source_receipt_sha256': response.get('sha256'), 'cost_status': 'unknown'}, event)
    return {'operation_id': operation_id, 'status': status, 'resource_id': row['resource_id'], 'cost_status': 'unknown'}
