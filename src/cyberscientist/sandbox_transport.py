"""Bohr 2.7.8 custom CPU create with its validated v4 payload and longer HTTP wait.

No fallback/replay after POST. The CLI remains the protocol source and all other
sandbox actions use it; dry-run is local validation, never another reservation.
"""
from __future__ import annotations

import json
import subprocess
import time
import httpx
from .bohr_proxy import redact, redact_value

PATH = '/openapi/v4/sandbox_work/sandboxes'


def create(args, executable, env, key, host, timeout, *, before_send=None):
    started = time.monotonic()
    request_id = args[args.index('--request-id')+1]
    try:
        probe = subprocess.run([executable, *args, '--dry-run'], env=env,
            capture_output=True, text=True, errors='replace', timeout=min(30, timeout))
        envelope = json.loads(probe.stdout)
        operations = envelope['data']['operations']
        if probe.returncode or envelope.get('ok') is not True or len(operations) != 1:
            raise ValueError('dry-run rejected')
        operation = operations[0]
        payload = operation['body']
        if (operation['method'] != 'POST' or operation['path'] != PATH
                or payload['timeout'] != int(args[args.index('--timeout')+1])
                or payload['projectId'] != int(args[args.index('--project-id')+1])
                or payload['metadata']['e2b.agents.kruise.io/image'] != args[args.index('--image')+1]):
            raise ValueError('unexpected create protocol')
    except Exception as exc:
        return {'ok': False, 'not_started': True, 'exit_code': None, 'stdout': '',
                'stderr': '沙箱创建协议未通过本机CLI验证：' + type(exc).__name__}
    if before_send is not None and not before_send():
        return {'ok': False, 'not_started': True, 'exit_code': None, 'stdout': '',
                'stderr': '创建发送前门禁、关机或剩余授权已不满足；未发送POST'}
    remaining = timeout - (time.monotonic() - started)
    if remaining <= 0:
        return {'ok': False, 'not_started': True, 'exit_code': None, 'stdout': '',
                'stderr': '本次创建总等待预算已在本地验证耗尽；未发送POST'}
    try:
        # Never forward credentials on a redirect or perform HTTP retries.
        with httpx.Client(timeout=remaining, follow_redirects=False) as client:
            response = client.post(host.rstrip('/')+PATH, json=payload,
                headers={'Authorization': 'Bearer '+key, 'X-Request-ID': request_id})
        raw = response.json()
        success = 200 <= response.status_code < 300 and isinstance(raw, dict) and bool(raw.get('sandboxID'))
        message = raw.get('message', '') if isinstance(raw, dict) else ''
        # Raw v4 refusal observed by CLI is an explicit pre-execution state.
        no_resource = isinstance(raw, dict) and raw.get('data') is None and not any(
            raw.get(name) for name in ('sandboxID','sandboxId','sandbox_id','id','sandbox'))
        preparing = no_resource and response.status_code == 400 and (
            isinstance(raw, dict) and raw.get('code') == 'IMAGE_PREPARATION_IN_PROGRESS'
            or isinstance(message, str) and message.startswith('IMAGE_PREPARATION_IN_PROGRESS'))
        safe = redact_value(raw, [key])
        body = {'ok': success, 'data': safe if success else None,
                'meta': {'request_id': request_id, 'transport': 'bohr-dry-run/v4-long-http'}}
        if not success and not preparing:
            body['unconfirmed_response'] = safe
        if not success:
            body['error'] = {'code': 'IMAGE_PREPARATION_IN_PROGRESS' if preparing else 'CREATE_NOT_CONFIRMED',
                'http': response.status_code, 'message': message if preparing else '创建回执未确认；先只读对账'}
        return {'ok': success, 'exit_code': 0 if success else 1,
                'unknown': not success and not preparing,
                'stdout': redact(json.dumps(body), [key]), 'stderr': '',
                'transport': 'bohr-dry-run/v4-long-http'}
    except Exception as exc:
        return {'ok': False, 'unknown': True, 'exit_code': None, 'stdout': '',
                'stderr': '沙箱创建结果unknown，先只读对账：' + type(exc).__name__,
                'transport': 'bohr-dry-run/v4-long-http'}
