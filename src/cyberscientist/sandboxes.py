"""Run-scoped Bohrium sandbox gateway. Cloud mutations are never replayed blindly."""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import compute, config, db
from .bohr_proxy import redact_value

LIVE = ('creating', 'active', 'unknown', 'deleting')
TERMINAL_RUN = ('finished', 'failed', 'cancelled')
FORBIDDEN = ('--never-timeout', '--inherit-auth', '--mount-user-storage',
             '--reserve-failed-sandbox', '--parent-sandbox-id')
RETRY_DELAYS = (2, 4, 8, 16, 30, 30)
IMAGE_PREPARATION_BUDGET = 45 * 60
IMAGE_PREPARATION_DELAYS = (2, 4, 8, 16, 30, 60, 120, 180, 240, 300)


def reserved_seconds(row) -> float:
    """Keep one frozen lifetime reserved while preparation/outcome is unknown."""
    if 'lifetime_version' in row.keys() and row['lifetime_version'] == 2:
        seconds = json.loads(row['request_json'])['timeout']
        if row['deleted_at'] and row['lifetime_started_at']:
            return min(seconds, max(0, (datetime.fromisoformat(row['deleted_at']) -
                datetime.fromisoformat(row['lifetime_started_at'])).total_seconds()))
        if row['deleted_at'] and row['status'] == 'failed':
            return 0
        return seconds
    return max(0, (datetime.fromisoformat(row['deleted_at'] or row['expires_at']) -
                   datetime.fromisoformat(row['created_at'])).total_seconds())


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _clean(value: Any) -> Any:
    secrets = list(config.sensitive_values())
    return redact_value(value, secrets)


def _receipt(value: dict, *, stdout_limit: int = 12000) -> dict:
    safe = _clean({k: value.get(k) for k in ('ok', 'exit_code', 'unknown', 'not_started',
                                           'stdout', 'stderr', 'truncated') if k in value})
    if isinstance(safe.get('stdout'),str):
        if len(safe['stdout']) > stdout_limit:
            safe['truncated'] = True
        safe['stdout']=safe['stdout'][:stdout_limit]
    if isinstance(safe.get('stderr'),str): safe['stderr']=safe['stderr'][-4000:]
    return safe


def _body(value: dict) -> Any:
    try:
        return json.loads(value.get('stdout') or '')
    except (ValueError, TypeError):
        return None


def _data(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get('data'), (dict, list)):
        return value['data']
    return value


def _sandbox_id(value: Any) -> str | None:
    node = _data(value)
    for part in (node, node.get('sandbox') if isinstance(node, dict) else None):
        if not isinstance(part, dict):
            continue
        for name in ('sandboxID', 'sandboxId', 'sandbox_id', 'id'):
            candidate = part.get(name)
            if isinstance(candidate, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{2,199}', candidate):
                return candidate
    return None


def observed_resources(receipt: dict, sandbox_id: str) -> dict:
    """Project native hardware only when bound to this sandbox's successful reply."""
    body = _body(receipt)
    if (not receipt.get('ok') or receipt.get('truncated')
            or not isinstance(body, dict) or body.get('ok') is False
            or _sandbox_id(body) != sandbox_id):
        return {}
    node = _data(body)
    if isinstance(node, dict) and isinstance(node.get('sandbox'), dict):
        node = node['sandbox']
    cpu, memory = node.get('cpuCount'), node.get('memoryMB')
    if (type(cpu) is not int or not 0 < cpu < 10000
            or type(memory) is not int or not 0 < memory < 10240000
            or memory % 1024):
        return {}
    result = {'cpu': f'{cpu}c{memory // 1024}g'}
    gpu = node.get('gpuCount')
    if type(gpu) is int and gpu >= 0:
        result['gpu_count'] = gpu
    return result


def _local_dns_denied(value: dict) -> bool:
    """A local socket denial during DNS lookup precedes any create request."""
    body = _body(value)
    error = body.get('error') if isinstance(body, dict) else None
    message = error.get('message') if isinstance(error, dict) else None
    return (error.get('code') == 'NETWORK_ERROR' if isinstance(error, dict) else False) and (
        isinstance(message, str) and 'lookup open.bohrium.com' in message
        and 'socket: operation not permitted' in message)


def _retry_reason(receipt: dict, action: str) -> str | None:
    body = _body(receipt)
    if (receipt.get('ok') or receipt.get('unknown') or receipt.get('truncated')
            or not isinstance(body, dict) or body.get('ok') is not False
            or body.get('data') is not None):
        return None
    error = body.get('error')
    if not isinstance(error, dict) or _sandbox_id(body):
        return None
    message = error.get('message', '')
    # These native refusals precede the remote mutation. A command exit,
    # generic timeout or lost reply is never evidence that execution did not start.
    if action == 'create' and error.get('http') == 400 and (
            error.get('code') == 'IMAGE_PREPARATION_IN_PROGRESS' or
            isinstance(message, str) and message.startswith('IMAGE_PREPARATION_IN_PROGRESS:')):
        return 'image_preparation'
    if action == 'exec' and error.get('code') in ('NETWORK_ERROR', 'COMMAND_FAILED') and (
            isinstance(message, str) and message.startswith('net/http: TLS handshake timeout')):
        return 'tls_handshake'
    return None


def _activate_lifetime(conn, run_id: str, operation_id: str, receipt: dict) -> None:
    """Use authoritative remote times when available; never extend a Run grant."""
    conn.execute('UPDATE compute_sandboxes SET unknown_slot_released=0 WHERE operation_id=?', (operation_id,))
    row = conn.execute('SELECT * FROM compute_sandboxes WHERE operation_id=?', (operation_id,)).fetchone()
    if row['lifetime_version'] != 2:
        return
    node = _data(_body(receipt))
    if isinstance(node, dict) and isinstance(node.get('sandbox'), dict):
        node = node['sandbox']
    started = datetime.fromisoformat(row['created_at'])
    expires = datetime.fromisoformat(row['expires_at'])
    observed_start = None
    try:
        remote_start = datetime.fromisoformat(node['startedAt'])
        remote_end = datetime.fromisoformat(node['endAt'])
        now = datetime.now(timezone.utc)
        if (remote_start.tzinfo and remote_end.tzinfo and started <= remote_start <= now
                and remote_start < remote_end):
            started = remote_start
            observed_start = started.isoformat()
            expires = min(remote_end, started + timedelta(seconds=json.loads(row['request_json'])['timeout']))
    except (KeyError, TypeError, ValueError):
        # Without confirmed times retain the earlier conservative deadline.
        pass
    current = conn.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
    auth = conn.execute('SELECT * FROM authorizations WHERE id=?', (current['authorization_id'],)).fetchone()
    from . import run_clock
    if auth:
        left = run_clock.remaining(current, auth)
        if math.isfinite(left):
            expires = min(expires, datetime.now(timezone.utc) + timedelta(seconds=max(0, left)))
    conn.execute('UPDATE compute_sandboxes SET lifetime_started_at=?,expires_at=? WHERE operation_id=?',
                 (observed_start, expires.isoformat(), operation_id))


def _observe_creation(image, operation_id, sid, receipt):
    if not image:
        return
    from . import sandbox_warmup
    try:
        sandbox_warmup.record_success(image, operation_id, sid, receipt)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning('Sandbox create observation failed: %s', type(exc).__name__)


def _retry_native(run_id: str, op: str, action: str, argv: list[str], *, timeout: int,
                  expires_at: str) -> dict:
    """Bounded retries of explicit pre-mutation failures, with one request ID."""
    started = time.monotonic(); waits = []; receipt = None
    deadline = datetime.fromisoformat(expires_at)
    requested_seconds = int(argv[argv.index('--timeout') + 1])
    attempt = 0
    while True:
        from . import power, run_clock
        if attempt:
            if action == 'create' and time.monotonic() - started >= IMAGE_PREPARATION_BUDGET:
                break
            current = compute._run(run_id)
            authorization = db.query_one('SELECT * FROM authorizations WHERE id=?', (current['authorization_id'],))
            room = (deadline - datetime.now(timezone.utc)).total_seconds()
            if (current['phase'] != 'running' or current['gate'] != 'open'
                    or power.shutdown_requested() or not authorization
                    or run_clock.remaining(current, authorization) < requested_seconds + timeout
                    or action == 'exec' and room < requested_seconds):
                break
        rpc_timeout = min(timeout, IMAGE_PREPARATION_BUDGET-(time.monotonic()-started)) if action == 'create' else timeout
        receipt = compute._native(argv, timeout=rpc_timeout)
        reason = _retry_reason(receipt, action)
        if not reason or reason != 'image_preparation' and attempt == len(RETRY_DELAYS):
            break
        budget = IMAGE_PREPARATION_BUDGET if reason == 'image_preparation' else 180
        delay = (IMAGE_PREPARATION_DELAYS[min(attempt, len(IMAGE_PREPARATION_DELAYS)-1)]
                 if reason == 'image_preparation' else RETRY_DELAYS[attempt])
        delay = min(delay, max(0, budget - (time.monotonic() - started)))
        run = compute._run(run_id)
        auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],))
        room = (deadline - datetime.now(timezone.utc)).total_seconds()
        if (run['phase'] != 'running' or run['gate'] != 'open' or not auth
                or action == 'exec' and room <= delay + requested_seconds
                or run_clock.remaining(run, auth) <= delay + requested_seconds + timeout
                or delay <= 0 or power.shutdown_requested()):
            break
        event = db.append_event(run_id, 'controller', 'sandbox.retry_wait',
            {'operation_id': op, 'action': action, 'reason': reason,
             'attempt': attempt + 1, 'wait_seconds': delay,
             'receipt_sha256': hashlib.sha256(_json(_receipt(receipt)).encode()).hexdigest()})
        waits.append({'reason': reason, 'seconds': delay})
        # Long preparation intervals remain interruptible; no next POST after pause.
        remaining_wait = delay
        waited = 0
        while remaining_wait > 0:
            step = min(remaining_wait, 5) if delay > 30 else remaining_wait
            time.sleep(step); remaining_wait -= step; waited += step
            fresh = compute._run(run_id)
            authorization = db.query_one('SELECT * FROM authorizations WHERE id=?', (fresh['authorization_id'],))
            if (fresh['phase'] != 'running' or fresh['gate'] != 'open'
                    or power.shutdown_requested() or not authorization
                    or run_clock.remaining(fresh, authorization) < requested_seconds + timeout):
                break
        waits[-1]['seconds'] = waited
        # Shutdown or a manual pause during the wait cancels the retry.
        fresh = compute._run(run_id)
        if remaining_wait or fresh['phase'] != 'running' or fresh['gate'] != 'open' or power.shutdown_requested():
            break
        attempt += 1
    if waits:
        fact = {'operation_id': op, 'action': action, 'waits': waits,
                'wait_seconds': sum(item['seconds'] for item in waits),
                'elapsed_seconds': round(time.monotonic() - started, 3),
                'native_ok': bool(receipt.get('ok')),
                'preparation_budget_seconds': IMAGE_PREPARATION_BUDGET if action == 'create' else None,
                'preparation_duration_seconds': None,
                'duration_basis': 'observed operation elapsed; exact platform preparation duration unknown'}
        event = db.append_event(run_id, 'controller', 'sandbox.environment_observed', fact)
        from . import environment_facts
        try:
            environment_facts.record('sandbox:retry:' + action, 'Bohrium 沙箱自动退避', fact, event)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning('Sandbox retry fact write failed: %s', type(exc).__name__)
    return receipt


def _remote_items(value: Any) -> list[dict]:
    node = _data(value)
    if isinstance(node, dict):
        node = node.get('items')
    return [item for item in node if isinstance(item, dict)] if isinstance(node, list) else []


def _owned(run_id: str, sandbox_id: str):
    row = db.query_one('SELECT * FROM compute_sandboxes WHERE run_id=? AND sandbox_id=?',
                       (run_id, sandbox_id))
    if not row:
        raise compute.ComputeError('NOT_OWNED', '沙箱未登记在本 Run，拒绝操作')
    return row


def _seconds_left(row) -> int:
    return math.floor((datetime.fromisoformat(row['expires_at']) -
                       datetime.now(timezone.utc)).total_seconds())


def _safe_path(run, value: str) -> Path:
    return compute._path(run, value)


def _hash_files(path: Path) -> list[dict]:
    paths = [path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_file())
    out = []
    for p in paths[:1000]:
        if p.is_symlink():
            continue
        out.append({'path': p.relative_to(path).as_posix() if p != path else p.name,
                    'bytes': p.stat().st_size, 'sha256': compute._file_sha256(p)})
    return out


def list_run(run_id: str) -> dict:
    compute._run(run_id)
    rows = db.query('SELECT * FROM compute_sandboxes WHERE run_id=? ORDER BY created_at', (run_id,))
    items = []
    now = datetime.now(timezone.utc)
    for row in rows:
        item = dict(row)
        if item['unknown_slot_released']: item['status'] = 'unknown_released'
        item['request'] = json.loads(item.pop('request_json'))
        item['receipt'] = json.loads(item.pop('receipt_json'))
        end = datetime.fromisoformat(item['deleted_at']) if item['deleted_at'] else now
        start = item['lifetime_started_at'] if item['lifetime_version'] == 2 else item['created_at']
        item['alive_minutes'] = max(0, (end - datetime.fromisoformat(start)).total_seconds() / 60) if start else 0
        item['lifetime_observed'] = bool(start)
        item['reserved_minutes'] = reserved_seconds(row) / 60
        items.append(item)
    return {'items': items, 'active_or_unknown': sum(row['status'] in LIVE and not row['unknown_slot_released'] for row in rows),
            'cumulative_minutes': sum(item['alive_minutes'] for item in items)}


def bounded_lifetime(run_id: str, requested: int) -> int:
    """Fit a controller scorer to existing time grants, never extend a grant.

    Creation checks the bounds again atomically. Unknown sandboxes continue to
    reserve their full lifetime, as in ordinary sandbox admission.
    """
    run = compute._run(run_id)
    auth = db.query_one('SELECT * FROM authorizations WHERE id=?',
                        (run['authorization_id'],))
    if not auth or not run['started_at']:
        raise compute.ComputeError('SANDBOX_BUDGET', '评分没有有效时长授权')
    from . import run_clock
    run_left = run_clock.remaining(run, auth)
    reserved = sum(reserved_seconds(row) for row in
                   db.query('SELECT * FROM compute_sandboxes WHERE run_id=?', (run_id,)))
    seconds = math.floor(min(requested, run_left - 5,
                             float('inf') if auth['unlimited_resources'] else auth['max_sandbox_minutes'] * 60 - reserved - 5))
    if seconds < 1:
        raise compute.ComputeError('SANDBOX_BUDGET', '评分沙箱时长额度已耗尽')
    return seconds


def bounded_execution_timeout(run_id: str, sandbox_id: str, requested: int) -> int:
    """Shrink a controller command to the current sandbox and Run deadlines.

    Recompute after staging/transfers. This never extends a sandbox or grant,
    retries a command, or changes explicit executor timeout validation.
    """
    if type(requested) is not int or requested < 1:
        raise compute.ComputeError('INVALID_COMMAND', '评分命令需要正整数超时')
    row = _owned(run_id, sandbox_id)
    if row['status'] != 'active':
        raise compute.ComputeError('SANDBOX_NOT_ACTIVE', '评分沙箱未处于 active')
    seconds = min(requested, _seconds_left(row) - 5)
    run = compute._run(run_id)
    auth = db.query_one('SELECT * FROM authorizations WHERE id=?',
                        (run['authorization_id'],))
    if auth and run['started_at'] and (auth['max_run_minutes'] > 0 or auth['unlimited_resources']):
        from . import run_clock
        remaining = run_clock.remaining(run, auth)
        seconds = min(seconds, math.floor(remaining) - 5)
    if seconds < 1:
        raise compute.ComputeError('SANDBOX_BUDGET', '评分命令的既有时长额度已耗尽')
    return seconds


def create(run_id: str, operation_id: str, request: dict, *, _session_id: str | None = None) -> dict:
    """Reserve the entire requested lifetime before a single remote create."""
    if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', operation_id):
        raise compute.ComputeError('INVALID_OPERATION', '沙箱创建需要稳定的 operation_id')
    if not isinstance(request, dict) or not set(request) <= {'template', 'image', 'cpu', 'gpu', 'timeout'}:
        raise compute.ComputeError('INVALID_COMMAND', '沙箱创建含不支持的参数')
    if _session_id is not None:
        # Backend scoring sessions cannot refer to another Run's persistent
        # workspace. This option is not exposed by the agent gateway.
        if _session_id != run_id:
            raise compute.ComputeError('INVALID_COMMAND', '评分工作区必须绑定本 Run')
        request = request | {'session_id': _session_id}
    timeout = request.get('timeout')
    if type(timeout) is not int or timeout < 1:
        raise compute.ComputeError('INVALID_TIMEOUT', '沙箱必须显式设置正数 --timeout 秒数')
    for name in ('template', 'image', 'cpu'):
        if name in request and (not isinstance(request[name], str) or not request[name].strip()
                                or request[name].startswith('-')):
            raise compute.ComputeError('INVALID_COMMAND', f'{name} 参数无效')
    if request.get('cpu') and not re.fullmatch(r'[1-9][0-9]*c[1-9][0-9]*g', request['cpu']):
        raise compute.ComputeError('INVALID_COMMAND', 'cpu 规格须形如 2c4g')
    gpu = request.get('gpu', False)
    if gpu is not False and gpu is not True and gpu not in ('4090', '5090', 'l20'):
        raise compute.ComputeError('INVALID_COMMAND', 'GPU 参数无效')
    if gpu and request.get('cpu') and not request.get('image'):
        raise compute.ComputeError('INVALID_COMMAND', 'GPU快捷模板不能同时指定CPU；自定义CPU规格需要显式镜像地址')
    project_id = compute._project_id(config.load_settings()['bohrium'].get('project_id'))
    now = db.utcnow()
    from . import compute_budget
    price = compute_budget.rate(run_id, 'sandbox', request.get('cpu', ''))
    with db.transaction() as conn:
        prior = conn.execute('SELECT * FROM compute_sandboxes WHERE operation_id=?',
                             (operation_id,)).fetchone()
        if prior:
            if prior['run_id'] != run_id or json.loads(prior['request_json']) != request:
                raise compute.ComputeError('OPERATION_CONFLICT', 'operation_id 已绑定其他沙箱请求')
            return {'operation_id': operation_id, 'sandbox_id': prior['sandbox_id'],
                    'status': 'unknown_released' if prior['unknown_slot_released'] else prior['status'], 'deduplicated': True}
        run = conn.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        from . import resource_coordinator
        resource_coordinator.require_compute_slot_tx(conn, 'sandbox', run_id=run_id)
        if not run or run['mode'] != 'connected' or run['phase'] != 'running' or run['gate'] != 'open' or not run['current_trial_id']:
            raise compute.ComputeError('RUN_NOT_RUNNING', 'Run 未运行或研究门禁关闭，不能创建沙箱')
        auth = conn.execute('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],)).fetchone()
        unlimited = bool(auth and auth['unlimited_resources'])
        if not auth or not unlimited and (auth['max_sandboxes'] <= 0 or auth['max_sandbox_minutes'] <= 0):
            raise compute.ComputeError('NOT_AUTHORIZED', '本 Run 未授权沙箱数量和累计分钟数')
        if gpu and not auth['allow_sandbox_gpu']:
            raise compute.ComputeError('GPU_NOT_AUTHORIZED', '沙箱 GPU 未单独授权')
        limits = compute.validate_limits(json.loads(auth['job_limits_json']))
        if not unlimited and request.get('cpu') and int(request['cpu'].split('c')[0]) > limits['max_cpu']:
            raise compute.ComputeError('RESOURCE_LIMIT', '沙箱CPU核心数超出本Run的机器授权')
        if not run['started_at'] or not unlimited and auth['max_run_minutes'] <= 0:
            raise compute.ComputeError('UNBOUNDED_SANDBOX', '沙箱需要本 Run 的时长上限')
        from . import run_clock
        run_left = run_clock.remaining(run, auth)
        if not math.isfinite(run_left):
            raise compute.ComputeError('UNBOUNDED_SANDBOX', '资源不限仍须设置赛道结束时间')
        rows = conn.execute('SELECT * FROM compute_sandboxes'
                            ' WHERE run_id=?', (run_id,)).fetchall()
        if not unlimited and sum(row['status'] in LIVE and not row['unknown_slot_released'] for row in rows) >= auth['max_sandboxes']:
            raise compute.ComputeError('SANDBOX_LIMIT', '已达到同时存在的沙箱上限')
        reserved = sum(reserved_seconds(row) for row in rows)
        if timeout > run_left or not unlimited and reserved + timeout > auth['max_sandbox_minutes'] * 60:
            raise compute.ComputeError('SANDBOX_BUDGET', '沙箱时长超过本 Run 剩余额度')
        expires = (datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat()
        compute_budget.reserve_tx(conn, run_id, 'sandbox', operation_id, timeout, price)
        conn.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,request_json,status,'
                     'created_at,expires_at,updated_at,lifetime_version) VALUES(?,?,?,?,?,?,?,?,2)',
                     (operation_id,run_id,run['current_trial_id'],_json(request),'creating',now,expires,now))
        db.append_event_tx(conn,run_id,'controller','sandbox.creating',
                           {'operation_id':operation_id,'expires_at':expires},trial_id=run['current_trial_id'])
    argv = ['sandbox','create','--timeout',str(timeout),'--project-id',str(project_id)]
    if _session_id is not None: argv += ['--session-id', _session_id]
    if request.get('template'): argv += ['-t',request['template']]
    if request.get('image'): argv += ['--image',request['image']]
    if request.get('cpu'): argv += ['--cpu',request['cpu']]
    if gpu: argv += ['--gpu',gpu if isinstance(gpu,str) else '4090']
    argv += ['--request-id',operation_id,'--yes','--no-interactive','-o','json']
    receipt = _retry_native(run_id, operation_id, 'create', argv,
                            timeout=240, expires_at=expires)
    sid = _sandbox_id(_body(receipt)) if receipt.get('ok') else None
    error = (_body(receipt) or {}).get('error') if isinstance(_body(receipt),dict) else None
    confirmed_not_started = isinstance(error,dict) and error.get('code') == 'CONFIRMATION_REQUIRED'
    rejected_arguments = (isinstance(error,dict) and error.get('code') == 'INVALID_ARGUMENTS'
                          and error.get('http') == 400 and error.get('retryable') is False)
    local_dns_denied = _local_dns_denied(receipt)
    status = ('active' if sid else 'failed' if (receipt.get('not_started')
              or confirmed_not_started or rejected_arguments or local_dns_denied) else 'unknown')
    with db.transaction() as conn:
        current_row = conn.execute('SELECT * FROM compute_sandboxes WHERE operation_id=?', (operation_id,)).fetchone()
        if current_row['sandbox_id'] is not None or current_row['status'] not in ('creating','unknown'):
            db.append_event_tx(conn, run_id, 'controller', 'sandbox.create_late_receipt',
                {'operation_id': operation_id, 'sandbox_id': sid,
                 'retained_status': current_row['status'], 'receipt': _receipt(receipt)},
                trial_id=run['current_trial_id'])
            return {'operation_id': operation_id, 'sandbox_id': current_row['sandbox_id'],
                    'status': current_row['status'], 'receipt': _receipt(receipt), 'deduplicated': True}
        conn.execute('UPDATE compute_sandboxes SET sandbox_id=?,status=?,deleted_at=?,receipt_json=?,updated_at=?'
                     ' WHERE operation_id=?', (sid,status,now if status == 'failed' else None,
                                                _json(_receipt(receipt)),db.utcnow(),operation_id))
        db.append_event_tx(conn,run_id,'controller',f'sandbox.{status}',
                           {'operation_id':operation_id,'sandbox_id':sid,
                            'exit_code':receipt.get('exit_code')},trial_id=run['current_trial_id'])
        if sid:
            _activate_lifetime(conn, run_id, operation_id, receipt)
        resources = observed_resources(receipt, sid) if sid else {}
        if resources:
            db.append_event_tx(conn, run_id, 'controller', 'sandbox.resources_observed',
                {'operation_id': operation_id, 'sandbox_id': sid, 'resources': resources,
                 'source': 'create_receipt'}, trial_id=run['current_trial_id'])
    if sid:
        _observe_creation(request.get('image'), operation_id, sid, receipt)
        from . import power, run_clock
        current = compute._run(run_id)
        auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (current['authorization_id'],))
        if (current['phase'] != 'running' or current['gate'] != 'open'
                or power.shutdown_requested() or not auth or run_clock.remaining(current, auth) <= 0):
            status = delete(run_id,sid)['status']
    return {'operation_id':operation_id,'sandbox_id':sid,'status':status,
            'receipt':_receipt(receipt)}


def reconcile_create(run_id: str, operation_id: str) -> dict:
    row = db.query_one('SELECT * FROM compute_sandboxes WHERE run_id=? AND operation_id=?',
                       (run_id,operation_id))
    if not row:
        raise compute.ComputeError('NOT_FOUND','沙箱创建记录不存在')
    if row['unknown_slot_released']:
        return {'operation_id': operation_id, 'status': 'unknown_released', 'sandbox_id': None, 'cost': 'unknown'}
    if row['status'] not in ('creating','unknown'):
        return {'operation_id':operation_id,'status':row['status'],'sandbox_id':row['sandbox_id']}
    if row['sandbox_id'] is not None:
        # An ambiguous delete/liveness observation is not an unknown create.
        # Do not reactivate it and thereby permit a second delete mutation.
        return {'operation_id':operation_id,'status':row['status'],'sandbox_id':row['sandbox_id'],
                'notice':'已有资源ID的unknown不能当作创建对账；保留未知，不重发变更'}
    original_receipt = json.loads(row['receipt_json'] or '{}')
    if row['sandbox_id'] is None and _local_dns_denied(original_receipt):
        db.execute("UPDATE compute_sandboxes SET status='failed',deleted_at=created_at,updated_at=?"
                   " WHERE operation_id=?", (db.utcnow(), operation_id))
        db.append_event(run_id, 'controller', 'sandbox.failed',
                        {'operation_id': operation_id, 'sandbox_id': None,
                         'reason': 'local_dns_socket_denied'}, trial_id=row['trial_id'])
        return {'operation_id': operation_id, 'status': 'failed', 'sandbox_id': None,
                'receipt': original_receipt}
    receipt = compute._native(['sandbox','describe','--create-request-id',operation_id,
                               '--no-interactive','-o','json'])
    sid = _sandbox_id(_body(receipt)) if receipt.get('ok') else None
    original = _body(json.loads(row['receipt_json'])) if row['receipt_json'] else None
    original_error = original.get('error') if isinstance(original,dict) else None
    fresh = _body(receipt)
    fresh_error = fresh.get('error') if isinstance(fresh,dict) else None
    if (not sid and isinstance(fresh_error, dict) and fresh_error.get('code') == 'RESOURCE_NOT_FOUND'
            and fresh_error.get('http') == 404
            and (datetime.now(timezone.utc) - datetime.fromisoformat(row['created_at'])).total_seconds() >= 600):
        listing = compute._native(['sandbox','list','--no-interactive','-o','json'])
        node = _data(_body(listing))
        items = node.get('items') if isinstance(node, dict) else None
        complete = (listing.get('ok') and not listing.get('truncated') and isinstance(items, list)
                    and type(node.get('total')) is int and node['total'] == len(items))
        identified = complete and all(isinstance(item, dict) and
            (item.get('createRequestId') or item.get('requestId')) for item in items)
        absent = identified and all((item.get('createRequestId') or item.get('requestId')) != operation_id for item in items)
        if absent:
            with db.transaction() as conn:
                changed = conn.execute("UPDATE compute_sandboxes SET unknown_slot_released=1,updated_at=?"
                    " WHERE operation_id=? AND sandbox_id IS NULL AND unknown_slot_released=0 AND status IN ('creating','unknown')",
                    (db.utcnow(), operation_id))
                if changed.rowcount:
                    db.append_event_tx(conn, run_id, 'controller', 'sandbox.unknown_released',
                        {'operation_id': operation_id, 'reason': 'request_id_miss_and_complete_list_absence',
                         'cost': 'unknown', 'automatic_resend': False}, trial_id=row['trial_id'])
            return {'operation_id': operation_id, 'status': 'unknown_released', 'sandbox_id': None,
                    'cost': 'unknown', 'automatic_resend': False}
    if sid:
        with db.transaction() as conn:
            current_row = conn.execute('SELECT * FROM compute_sandboxes WHERE operation_id=?', (operation_id,)).fetchone()
            if current_row['sandbox_id'] is not None or current_row['status'] not in ('creating','unknown'):
                return {'operation_id': operation_id, 'status': current_row['status'],
                        'sandbox_id': current_row['sandbox_id'], 'deduplicated': True}
            conn.execute('UPDATE compute_sandboxes SET sandbox_id=?,status=?,receipt_json=?,updated_at=?'
                       ' WHERE operation_id=?',(sid,'active',_json(_receipt(receipt)),db.utcnow(),operation_id))
            _activate_lifetime(conn, run_id, operation_id, receipt)
        db.append_event(run_id,'controller','sandbox.active',
                        {'operation_id':operation_id,'sandbox_id':sid},trial_id=row['trial_id'])
        request = json.loads(row['request_json'])
        _observe_creation(request.get('image'), operation_id, sid, receipt)
        from . import power, run_clock
        current = compute._run(run_id)
        auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (current['authorization_id'],))
        if (current['phase'] != 'running' or current['gate'] != 'open'
                or power.shutdown_requested() or not auth or run_clock.remaining(current, auth) <= 0):
            return {'operation_id':operation_id,'status':delete(run_id,sid)['status'],
                    'sandbox_id':sid,'receipt':_receipt(receipt)}
    elif (isinstance(original_error,dict) and original_error.get('code') == 'INVALID_ARGUMENTS'
          and original_error.get('http') == 400
          and isinstance(fresh_error,dict) and fresh_error.get('code') == 'RESOURCE_NOT_FOUND'
          and fresh_error.get('http') == 404):
        # A rejected create plus an authoritative request-ID miss proves that
        # this reservation never represented a remote sandbox.
        db.execute("UPDATE compute_sandboxes SET status='failed',deleted_at=created_at,updated_at=?"
                   " WHERE operation_id=?", (db.utcnow(),operation_id))
        db.append_event(run_id,'controller','sandbox.failed',
                        {'operation_id':operation_id,'sandbox_id':None,
                         'reason':'invalid_arguments_request_not_found'},trial_id=row['trial_id'])
        return {'operation_id':operation_id,'status':'failed','sandbox_id':None,
                'receipt':_receipt(receipt)}
    elif row['status'] == 'creating':
        db.execute("UPDATE compute_sandboxes SET status='unknown',receipt_json=?,updated_at=?"
                   " WHERE operation_id=? AND status='creating' AND sandbox_id IS NULL",
                   (_json(_receipt(receipt)),db.utcnow(),operation_id))
    return {'operation_id':operation_id,'status':'active' if sid else 'unknown','sandbox_id':sid,
            'receipt':_receipt(receipt)}


def reconcile_pending_creates() -> None:
    """Bounded, read-only reconciliation; released creates are never resent."""
    for row in db.query("SELECT run_id,operation_id,created_at,updated_at FROM compute_sandboxes"
                        " WHERE sandbox_id IS NULL AND unknown_slot_released=0 AND status IN ('creating','unknown')"):
        now = datetime.now(timezone.utc)
        if ((now-datetime.fromisoformat(row['created_at'])).total_seconds() >= 600
                and (now-datetime.fromisoformat(row['updated_at'])).total_seconds() >= 60):
            reconcile_create(row['run_id'], row['operation_id'])
            db.execute('UPDATE compute_sandboxes SET updated_at=? WHERE operation_id=?',
                       (db.utcnow(), row['operation_id']))


def execute(run_id: str, sandbox_id: str, command: str, timeout: int,
            operation_id: str | None = None) -> dict:
    row = _owned(run_id,sandbox_id)
    if row['status'] != 'active':
        raise compute.ComputeError('SANDBOX_NOT_ACTIVE','沙箱未处于 active')
    if not isinstance(command,str) or not command or len(command)>8000 or type(timeout) is not int or timeout<1 or timeout>_seconds_left(row):
        raise compute.ComputeError('INVALID_COMMAND','命令或超时无效，须在沙箱剩余存活时间内')
    op = operation_id or 'sx_'+uuid.uuid4().hex
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',op):
        raise compute.ComputeError('INVALID_OPERATION','执行操作 ID 无效')
    with db.transaction() as conn:
        current = conn.execute('SELECT status FROM compute_sandboxes WHERE run_id=? AND sandbox_id=?',
                               (run_id,sandbox_id)).fetchone()
        if not current or current['status'] != 'active':
            raise compute.ComputeError('SANDBOX_NOT_ACTIVE','沙箱已不在 active 状态')
        previous = conn.execute('SELECT * FROM compute_sandbox_operations WHERE operation_id=?',(op,)).fetchone()
        if previous:
            raise compute.ComputeError('OPERATION_CONFLICT','执行操作 ID 已使用；不自动重复执行')
        conn.execute('INSERT INTO compute_sandbox_operations(operation_id,run_id,sandbox_id,action,status,started_at,command_sha256)'
                     ' VALUES(?,?,?,?,?,?,?)',(op,run_id,sandbox_id,'exec','running',db.utcnow(),
                                               hashlib.sha256(command.encode()).hexdigest()))
        db.append_event_tx(conn,run_id,'controller','sandbox.exec_started',
                           {'operation_id':op,'sandbox_id':sandbox_id,'command':_clean(command)},
                           trial_id=row['trial_id'])
    started = time.monotonic()
    try:
        receipt = _retry_native(run_id, op, 'exec',
            ['sandbox','exec',sandbox_id,'--command',command,'--timeout',str(timeout),
             '--request-id',op,'--no-interactive','-o','json'],
            timeout=timeout+30, expires_at=row['expires_at'])
    except Exception as exc:
        receipt = {'ok': False, 'unknown': True, 'exit_code': None,
                   'stdout': '', 'stderr': '沙箱执行回执未确认: ' + type(exc).__name__}
    duration = round(time.monotonic()-started,3)
    safe = _receipt(receipt, stdout_limit=48000)
    body = _body(receipt)
    outcome = _data(body)
    remote_exit = outcome.get('exit_code') if isinstance(outcome,dict) else None
    remote_error = outcome.get('error') if isinstance(outcome,dict) else None
    effective_exit = remote_exit if type(remote_exit) is int else receipt.get('exit_code')
    output = outcome.get('stdout') if isinstance(outcome,dict) else None
    stderr = outcome.get('stderr') if isinstance(outcome,dict) else None
    if not isinstance(output,str): output=safe.get('stdout','')
    if not isinstance(stderr,str): stderr=safe.get('stderr','')
    status = ('completed' if receipt.get('ok') and effective_exit == 0 and not remote_error
              and (not isinstance(body, dict) or body.get('ok') is not False)
              else 'unknown' if receipt.get('unknown') else 'failed')
    with db.transaction() as conn:
        serialized = _json(safe)
        conn.execute('UPDATE compute_sandbox_operations SET status=?,completed_at=?,receipt_json=?,receipt_sha256=?'
                     ' WHERE operation_id=?',(status,db.utcnow(),serialized,
                                             hashlib.sha256(serialized.encode()).hexdigest(),op))
        db.append_event_tx(conn,run_id,'controller','sandbox.exec_completed',
                           {'operation_id':op,'sandbox_id':sandbox_id,'command':_clean(command),
                            'exit_code':effective_exit,'duration_seconds':duration,
                            'status':status,
                            'output':_clean(output)[:4000],
                            'stderr':_clean(stderr)[-1000:]},trial_id=row['trial_id'])
    return {'operation_id':op,'status':status,'exit_code':effective_exit,
            'duration_seconds':duration,'receipt':safe}


def transfer(run_id: str, action: str, sandbox_id: str, remote_path: str,
             *, local_path: str | None = None, content: str | None = None,
             operation_id: str | None = None) -> dict:
    row = _owned(run_id,sandbox_id)
    if row['status'] != 'active' or _seconds_left(row)<1:
        raise compute.ComputeError('SANDBOX_NOT_ACTIVE','沙箱未处于 active 或已到期')
    if action not in ('read','write') or not isinstance(remote_path,str) or not remote_path.startswith('/') or '..' in Path(remote_path).parts:
        raise compute.ComputeError('INVALID_PATH','远端路径无效')
    run = compute._run(run_id)
    argv = ['sandbox','files',action,sandbox_id,remote_path]
    path = _safe_path(run,local_path) if local_path else None
    if action=='write':
        if (path is None)==(content is None):
            raise compute.ComputeError('INVALID_COMMAND','write 必须且只能提供 source 或 content')
        if path:
            if not path.exists() or path.is_symlink():
                raise compute.ComputeError('INVALID_PATH','源文件不存在或是符号链接')
            argv += ['--source',str(path)]
            session_id = json.loads(row['request_json']).get('session_id')
            if (session_id == run_id and
                    (remote_path == '/bohr-workspace' or remote_path.startswith('/bohr-workspace/'))):
                # Native multipart transport for the Run-bound mount avoids
                # the short filesystem HTTP deadline on large science ZIPs.
                # No new dataset, user-storage mount or credential propagation.
                argv += ['--ti', '--session-id', session_id]
        elif not isinstance(content,str) or len(content)>8192:
            raise compute.ComputeError('INVALID_COMMAND','内联内容不合法或过长')
        else: argv += ['--content',content]
    else:
        if path is None or content is not None:
            raise compute.ComputeError('INVALID_PATH','read 必须指定 Trial 或题目目录中的 destination')
        path.parent.mkdir(parents=True,exist_ok=True)
        argv += ['--destination',str(path)]
    before = _hash_files(path) if path and path.exists() and action=='read' else []
    op = operation_id or 'sf_'+uuid.uuid4().hex
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',op):
        raise compute.ComputeError('INVALID_OPERATION','文件操作 ID 无效')
    input_files = (_hash_files(path) if path and action=='write' else
                   [{'path':'inline-content','bytes':len(content.encode()),
                     'sha256':hashlib.sha256(content.encode()).hexdigest()}]
                   if content is not None else [])
    with db.transaction() as conn:
        current = conn.execute('SELECT status FROM compute_sandboxes WHERE run_id=? AND sandbox_id=?',
                               (run_id,sandbox_id)).fetchone()
        if not current or current['status'] != 'active':
            raise compute.ComputeError('SANDBOX_NOT_ACTIVE','沙箱已不在 active 状态')
        if conn.execute('SELECT 1 FROM compute_sandbox_operations WHERE operation_id=?',(op,)).fetchone():
            raise compute.ComputeError('OPERATION_CONFLICT','文件操作 ID 已使用；不自动重复传输')
        conn.execute('INSERT INTO compute_sandbox_operations(operation_id,run_id,sandbox_id,action,status,started_at)'
                     ' VALUES(?,?,?,?,?,?)',(op,run_id,sandbox_id,'files.'+action,'running',db.utcnow()))
    argv += ['--no-interactive','-o','json']
    try:
        receipt = compute._native(argv,timeout=min(330,max(30,_seconds_left(row))))
    except Exception as exc:
        receipt = {'ok': False, 'unknown': True, 'exit_code': None,
                   'stdout': '', 'stderr': '沙箱传输回执未确认: ' + type(exc).__name__}
    files = input_files if action=='write' else (_hash_files(path) if path and path.exists() else [])
    if action=='read' and files==before: files=[]
    files = _clean(files)
    status = 'completed' if receipt.get('ok') else 'unknown' if receipt.get('unknown') else 'failed'
    safe = {'status':status,'files':files,'receipt':_receipt(receipt)}
    with db.transaction() as conn:
        conn.execute('UPDATE compute_sandbox_operations SET status=?,completed_at=?,receipt_json=?'
                     ' WHERE operation_id=?',(status,db.utcnow(),_json(safe),op))
        db.append_event_tx(conn,run_id,'controller','sandbox.files_'+action,
                           {'operation_id':op,'sandbox_id':sandbox_id,'remote_path':_clean(remote_path),
                            'status':status,'files':files},trial_id=row['trial_id'])
    return {'operation_id':op,**safe}


def delete(run_id: str, sandbox_id: str) -> dict:
    row = _owned(run_id,sandbox_id)
    if row['status']=='deleted':
        return {'sandbox_id':sandbox_id,'status':'deleted','deduplicated':True}
    if row['status'] in ('deleting','unknown'):
        return {'sandbox_id':sandbox_id,'status':'unknown','deduplicated':True,
                'notice':'删除结果未确认；先对账，不重发删除'}
    if row['status'] not in LIVE:
        raise compute.ComputeError('SANDBOX_NOT_ACTIVE','沙箱不是可删除状态')
    with db.transaction() as conn:
        current = conn.execute('SELECT status FROM compute_sandboxes WHERE operation_id=?',
                               (row['operation_id'],)).fetchone()
        if not current or current['status'] != 'active':
            return {'sandbox_id':sandbox_id,'status':'unknown','deduplicated':True}
        run=conn.execute('SELECT phase FROM runs WHERE id=?',(run_id,)).fetchone()
        terminal=run and (run['phase'] in TERMINAL_RUN or _seconds_left(row)<=30)
        if terminal:
            conn.execute("UPDATE compute_sandbox_operations SET status='unknown' WHERE run_id=? AND sandbox_id=? AND action='background' AND status='running'",(run_id,sandbox_id))
        if conn.execute("SELECT 1 FROM compute_sandbox_operations WHERE run_id=?"
                        " AND sandbox_id=? AND status='running' LIMIT 1",
                        (run_id,sandbox_id)).fetchone():
            raise compute.ComputeError('SANDBOX_BUSY','沙箱仍有执行或传输操作；完成后再删除')
        conn.execute("UPDATE compute_sandboxes SET status='deleting',updated_at=?"
                     " WHERE operation_id=?", (db.utcnow(),row['operation_id']))
    receipt = compute._native(['sandbox','delete',sandbox_id,'--force','--no-interactive','-o','json'])
    if not receipt.get('ok'):
        db.execute("UPDATE compute_sandboxes SET status='unknown',receipt_json=?,updated_at=? WHERE operation_id=?",
                   (_json(_receipt(receipt)),db.utcnow(),row['operation_id']))
        db.append_event(run_id,'controller','sandbox.delete_unknown',
                        {'operation_id':row['operation_id'],'sandbox_id':sandbox_id},trial_id=row['trial_id'])
        return {'sandbox_id':sandbox_id,'status':'unknown','receipt':_receipt(receipt)}
    # A successful delete request is not proof that reclamation has finished.
    check = compute._native(['sandbox','list','--no-interactive','-o','json'])
    if check.get('ok') and _body(check) is not None:
        items = _remote_items(_body(check))
        present = [item for item in items if _sandbox_id(item)==sandbox_id]
        settled = not present
        status = 'deleted' if settled else 'deleting'
    else:
        settled = False
        status = 'unknown'
    db.execute('UPDATE compute_sandboxes SET status=?,deleted_at=?,receipt_json=?,updated_at=?'
               ' WHERE operation_id=?',(status,db.utcnow() if settled else None,
                                         _json({'delete':_receipt(receipt),'list':_receipt(check)}),
                                         db.utcnow(),row['operation_id']))
    db.append_event(run_id,'controller','sandbox.'+status if status != 'unknown' else 'sandbox.delete_unknown',
                    {'operation_id':row['operation_id'],'sandbox_id':sandbox_id},trial_id=row['trial_id'])
    return {'sandbox_id':sandbox_id,'status':status,'receipt':_receipt(receipt)}


def reconcile_deletions() -> dict:
    """Read-only settlement of previously accepted deletes; never resend them."""
    rows=db.query("SELECT * FROM compute_sandboxes WHERE status='deleting'")
    if not rows: return {'status':'ok','settled':0}
    receipt=compute._native(['sandbox','list','--no-interactive','-o','json'])
    if not receipt.get('ok') or _body(receipt) is None:
        return {'status':'unknown','settled':0,'receipt':_receipt(receipt)}
    ids={_sandbox_id(item) for item in _remote_items(_body(receipt))}
    settled=0
    for row in rows:
        if row['sandbox_id'] in ids: continue
        db.execute("UPDATE compute_sandboxes SET status='deleted',deleted_at=?,updated_at=?"
                   " WHERE operation_id=? AND status='deleting'",
                   (db.utcnow(),db.utcnow(),row['operation_id']))
        db.append_event(row['run_id'],'controller','sandbox.deleted',
                        {'operation_id':row['operation_id'],'sandbox_id':row['sandbox_id']},
                        trial_id=row['trial_id'])
        settled+=1
    return {'status':'ok','settled':settled}


def inspect(run_id: str, action: str, sandbox_id: str | None = None) -> dict:
    compute._run(run_id)
    if action=='list': return list_run(run_id)
    if action=='describe':
        _owned(run_id,sandbox_id or '')
        args=['sandbox','describe',sandbox_id,'--no-interactive','-o','json']
    elif action in ('quota','machine.list','template.list'):
        args=['sandbox',*action.split('.'),'--no-interactive','-o','json']
    else: raise compute.ComputeError('INVALID_ACTION','不支持的只读沙箱操作')
    receipt=compute._native(args)
    parsed=_body(receipt)
    if action in ('quota','machine.list','template.list') and receipt.get('ok') and isinstance(parsed,dict):
        try:
            from . import environment_facts
            event=db.append_event(run_id,'controller','sandbox.environment_observed',
                                  {'action':action,'receipt_sha256':hashlib.sha256(
                                      (receipt.get('stdout') or '').encode()).hexdigest()})
            environment_facts.record('sandbox:'+action,'Bohrium 沙箱 '+action,
                                     _data(parsed),event)
            host=compute.client_host_overrides(config.load_settings()['bohrium'],wenyon=True)['OPENAPI_HOST']
            environment_facts.record('sandbox:host','Bohrium 沙箱客户端主机',
                                     {'host':host,'cli_version':(parsed.get('meta') or {}).get('cli_version')},event)
        except Exception:
            import logging
            logging.getLogger('cyberscientist.sandboxes').exception('Could not record sandbox environment fact')
    return {'status':'ok' if receipt.get('ok') else 'unknown','receipt':_receipt(receipt)}


def cleanup_run(run_id: str) -> list[dict]:
    out=[]
    for row in db.query("SELECT sandbox_id FROM compute_sandboxes WHERE run_id=?"
                        " AND sandbox_id IS NOT NULL AND status='active'",(run_id,)):
        out.append(delete(run_id,row['sandbox_id']))
    return out


def expire_due() -> list[dict]:
    out=[]
    cutoff=(datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat()
    for row in db.query("SELECT run_id,sandbox_id FROM compute_sandboxes WHERE status='active'"
                        " AND expires_at<=? AND sandbox_id IS NOT NULL",(cutoff,)):
        out.append(delete(row['run_id'],row['sandbox_id']))
    return out


def reconcile_startup(*, cleanup_terminal: bool = True) -> dict:
    """One read-only remote list; delete known terminal-Run boxes, report unknown IDs."""
    db.execute("UPDATE compute_sandbox_operations SET status='unknown',completed_at=?"
               " WHERE status='running'",(db.utcnow(),))
    bohrium=config.load_settings()['bohrium']
    if not config.resolve_secret(bohrium.get('access_key_secret_ref','')):
        return {'status':'unknown','reason':'sandbox_credentials_missing'}
    receipt=compute._native(['sandbox','list','--no-interactive','-o','json'])
    if not receipt.get('ok') or _body(receipt) is None:
        return {'status':'unknown','receipt':_receipt(receipt)}
    items=_remote_items(_body(receipt))
    active_ids={_sandbox_id(item) for item in items}
    for row in db.query("SELECT * FROM compute_sandboxes WHERE status='deleting'"):
        if row['sandbox_id'] not in active_ids:
            db.execute("UPDATE compute_sandboxes SET status='deleted',deleted_at=?,updated_at=?"
                       " WHERE operation_id=?",(db.utcnow(),db.utcnow(),row['operation_id']))
            db.append_event(row['run_id'],'controller','sandbox.deleted',
                            {'operation_id':row['operation_id'],'sandbox_id':row['sandbox_id']},
                            trial_id=row['trial_id'])
    known={row['sandbox_id']:row for row in db.query(
        'SELECT s.sandbox_id,s.run_id,r.phase FROM compute_sandboxes s JOIN runs r ON r.id=s.run_id'
        ' WHERE s.sandbox_id IS NOT NULL')}
    orphan=[]; cleaned=[]
    for item in items:
        sid=_sandbox_id(item)
        if not sid: continue
        row=known.get(sid)
        if row is None:
            orphan.append(sid)
        elif cleanup_terminal and row['phase'] in TERMINAL_RUN and db.query_one(
                "SELECT status FROM compute_sandboxes WHERE sandbox_id=?",(sid,))['status']=='active':
            cleaned.append(delete(row['run_id'],sid))
    if orphan:
        import logging
        logging.getLogger('cyberscientist.sandboxes').warning(
            'Unowned Bohrium sandboxes observed; no deletion: %s',orphan[:20])
    return {'status':'ok','unowned_sandbox_ids':orphan,'cleaned':cleaned}


def dispatch(run_id: str, body: dict) -> dict:
    action=body.get('action')
    if action in ('background','poll'):
        from . import sandbox_background
        if action == 'poll': return sandbox_background.poll(run_id,body.get('operation_id'))
        return sandbox_background.start(run_id,body.get('sandbox_id',''),body.get('command'),body.get('timeout'),body.get('operation_id'))
    if action in ('ensure','work'):
        from . import topic_workspace
        return topic_workspace.ensure(run_id) if action == 'ensure' else topic_workspace.work(run_id,body)
    if action in ('exec','files.write') and not body.get('operation_id'):
        raise compute.ComputeError('INVALID_OPERATION','MCP 变更请求需稳定的 operation_id')
    if action=='create': return create(run_id,body.get('operation_id'),body.get('request') or {})
    if action=='reconcile': return reconcile_create(run_id,body.get('operation_id'))
    if action=='exec': return execute(run_id,body.get('sandbox_id',''),body.get('command'),body.get('timeout'),body.get('operation_id'))
    if action in ('files.read','files.write'):
        return transfer(run_id,action.split('.')[1],body.get('sandbox_id',''),body.get('remote_path',''),
                        local_path=body.get('local_path'),content=body.get('content'),
                        operation_id=body.get('operation_id'))
    if action=='delete': return delete(run_id,body.get('sandbox_id',''))
    if action in ('list','describe','quota','machine.list','template.list'):
        return inspect(run_id,action,body.get('sandbox_id'))
    raise compute.ComputeError('INVALID_ACTION','不支持的沙箱操作')


def cli(run_id: str, args: list[str], cwd: str) -> dict:
    """Run-local bohr shim syntax, normalized into the same guarded actions."""
    import argparse
    if not isinstance(args,list) or not all(isinstance(a,str) for a in args) or args[:1]!=['sandbox']:
        raise compute.ComputeError('INVALID_COMMAND','沙箱命令参数无效')
    if any(arg in FORBIDDEN or arg.startswith('--wenyon-') for arg in args):
        raise compute.ComputeError('FORBIDDEN_FLAG','沙箱挂载、继承认证、无限期或保留失败实例未开放')
    run=compute._run(run_id)
    compute._path(run,cwd)
    path=args[1:]
    if not path: raise compute.ComputeError('INVALID_COMMAND','缺少 sandbox 子命令')
    def parse(parser,rest):
        parser.add_argument('-o','--output',choices=['json','auto'])
        parser.add_argument('--no-interactive',action='store_true')
        try:
            opts,unknown=parser.parse_known_args(rest)
        except (argparse.ArgumentError,SystemExit,ValueError) as exc:
            raise compute.ComputeError('INVALID_COMMAND','沙箱命令格式错误') from exc
        if unknown: raise compute.ComputeError('INVALID_COMMAND','沙箱命令含未开放的参数')
        return opts
    def parser(): return argparse.ArgumentParser(add_help=False,exit_on_error=False)
    action=path[0]
    if action=='create':
        p=parser();p.add_argument('template',nargs='?');p.add_argument('-t','--template',dest='named_template')
        p.add_argument('--timeout',type=int);p.add_argument('--image');p.add_argument('--cpu')
        p.add_argument('--gpu',nargs='?',const=True);p.add_argument('--cs-operation-id')
        p.add_argument('--request-id')
        o=parse(p,path[1:])
        if o.template and o.named_template:
            raise compute.ComputeError('INVALID_COMMAND','模板只能指定一次')
        request={'timeout':o.timeout}
        for key,value in (('template',o.template or o.named_template),('image',o.image),
                          ('cpu',o.cpu),('gpu',o.gpu)):
            if value is not None: request[key]=value
        op=o.cs_operation_id or o.request_id or 'sx_'+hashlib.sha256(_json([run_id,run['current_trial_id'],request]).encode()).hexdigest()[:40]
        return create(run_id,op,request)
    if action=='exec':
        p=parser();p.add_argument('sandbox_id');p.add_argument('-c','--command',required=True)
        p.add_argument('--timeout',type=int,required=True);p.add_argument('--cs-operation-id')
        o=parse(p,path[1:])
        return execute(run_id,o.sandbox_id,o.command,o.timeout,o.cs_operation_id)
    if action=='files' and len(path)>1 and path[1] in ('read','write'):
        operation=path[1];p=parser();p.add_argument('sandbox_id');p.add_argument('remote_path')
        p.add_argument('--source');p.add_argument('-D','--destination');p.add_argument('--content')
        p.add_argument('--cs-operation-id')
        o=parse(p,path[2:]);local=o.source if operation=='write' else o.destination
        if local: local=str(Path(cwd,local).resolve())
        if (operation=='write' and o.destination) or (operation=='read' and (o.source or o.content)):
            raise compute.ComputeError('INVALID_COMMAND','文件命令参数不匹配')
        return transfer(run_id,operation,o.sandbox_id,o.remote_path,local_path=local,
                        content=o.content,operation_id=o.cs_operation_id)
    if action=='delete':
        p=parser();p.add_argument('sandbox_id');o=parse(p,path[1:])
        return delete(run_id,o.sandbox_id)
    if action=='describe':
        p=parser();p.add_argument('sandbox_id');o=parse(p,path[1:])
        return inspect(run_id,'describe',o.sandbox_id)
    if path in (['list'],['quota'],['machine','list'],['template','list']):
        return inspect(run_id,'.'.join(path))
    raise compute.ComputeError('UNSUPPORTED_COMMAND','此沙箱子命令未开放')
