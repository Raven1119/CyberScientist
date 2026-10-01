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


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _clean(value: Any) -> Any:
    secrets = list(config.load_secrets().values())
    return redact_value(value, secrets)


def _receipt(value: dict) -> dict:
    safe = _clean({k: value.get(k) for k in ('ok', 'exit_code', 'unknown', 'not_started',
                                           'stdout', 'stderr', 'truncated') if k in value})
    if isinstance(safe.get('stdout'),str): safe['stdout']=safe['stdout'][:12000]
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
        item['request'] = json.loads(item.pop('request_json'))
        item['receipt'] = json.loads(item.pop('receipt_json'))
        end = datetime.fromisoformat(item['deleted_at']) if item['deleted_at'] else now
        item['alive_minutes'] = max(0, (end - datetime.fromisoformat(item['created_at'])).total_seconds() / 60)
        items.append(item)
    return {'items': items, 'active_or_unknown': sum(row['status'] in LIVE for row in rows),
            'cumulative_minutes': sum(item['alive_minutes'] for item in items)}


def create(run_id: str, operation_id: str, request: dict) -> dict:
    """Reserve the entire requested lifetime before a single remote create."""
    if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', operation_id):
        raise compute.ComputeError('INVALID_OPERATION', '沙箱创建需要稳定的 operation_id')
    if not isinstance(request, dict) or not set(request) <= {'template', 'image', 'cpu', 'gpu', 'timeout'}:
        raise compute.ComputeError('INVALID_COMMAND', '沙箱创建含不支持的参数')
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
    project_id = compute._project_id(config.load_settings()['bohrium'].get('project_id'))
    now = db.utcnow()
    with db.transaction() as conn:
        prior = conn.execute('SELECT * FROM compute_sandboxes WHERE operation_id=?',
                             (operation_id,)).fetchone()
        if prior:
            if prior['run_id'] != run_id or json.loads(prior['request_json']) != request:
                raise compute.ComputeError('OPERATION_CONFLICT', 'operation_id 已绑定其他沙箱请求')
            return {'operation_id': operation_id, 'sandbox_id': prior['sandbox_id'],
                    'status': prior['status'], 'deduplicated': True}
        run = conn.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        eval_scoring = (run and run['phase'] == 'eval_scoring' and db.eval_mode(run_id))
        eval_retry = False
        if (run and run['phase'] == 'finished' and db.eval_mode(run_id)
                and operation_id.startswith('eval-scorer-') and operation_id.endswith('-retry')):
            from . import evaluations
            eval_retry = evaluations.retry_authorized(
                run_id, operation_id[len('eval-scorer-'):-len('-retry')])
        if not run or run['mode'] != 'connected' or (run['phase'] != 'running' and not eval_scoring and not eval_retry) or run['gate'] != 'open' or not run['current_trial_id']:
            raise compute.ComputeError('RUN_NOT_RUNNING', 'Run 未运行或研究门禁关闭，不能创建沙箱')
        auth = conn.execute('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],)).fetchone()
        if not auth or auth['max_sandboxes'] <= 0 or auth['max_sandbox_minutes'] <= 0:
            raise compute.ComputeError('NOT_AUTHORIZED', '本 Run 未授权沙箱数量和累计分钟数')
        if gpu and not auth['allow_sandbox_gpu']:
            raise compute.ComputeError('GPU_NOT_AUTHORIZED', '沙箱 GPU 未单独授权')
        if not run['started_at'] or auth['max_run_minutes'] <= 0:
            raise compute.ComputeError('UNBOUNDED_SANDBOX', '沙箱需要本 Run 的时长上限')
        run_left = auth['max_run_minutes'] * 60 - (datetime.now(timezone.utc) -
                   datetime.fromisoformat(run['started_at'])).total_seconds()
        rows = conn.execute('SELECT status,created_at,expires_at,deleted_at FROM compute_sandboxes'
                            ' WHERE run_id=?', (run_id,)).fetchall()
        if sum(row['status'] in LIVE for row in rows) >= auth['max_sandboxes']:
            raise compute.ComputeError('SANDBOX_LIMIT', '已达到同时存在的沙箱上限')
        reserved = sum((datetime.fromisoformat(row['expires_at']) -
                        datetime.fromisoformat(row['created_at'])).total_seconds()
                       if row['deleted_at'] is None else
                       max(0, (datetime.fromisoformat(row['deleted_at']) -
                               datetime.fromisoformat(row['created_at'])).total_seconds())
                       for row in rows)
        if timeout > run_left or reserved + timeout > auth['max_sandbox_minutes'] * 60:
            raise compute.ComputeError('SANDBOX_BUDGET', '沙箱时长超过本 Run 剩余额度')
        expires = (datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat()
        conn.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,request_json,status,'
                     'created_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                     (operation_id,run_id,run['current_trial_id'],_json(request),'creating',now,expires,now))
        db.append_event_tx(conn,run_id,'controller','sandbox.creating',
                           {'operation_id':operation_id,'expires_at':expires},trial_id=run['current_trial_id'])
    argv = ['sandbox','create','--timeout',str(timeout),'--project-id',str(project_id)]
    if request.get('template'): argv += ['-t',request['template']]
    if request.get('image'): argv += ['--image',request['image']]
    if request.get('cpu'): argv += ['--cpu',request['cpu']]
    if gpu: argv += ['--gpu',gpu if isinstance(gpu,str) else '4090']
    argv += ['--request-id',operation_id,'--yes','--no-interactive','-o','json']
    receipt = compute._native(argv, timeout=min(240,max(90,timeout)))
    sid = _sandbox_id(_body(receipt)) if receipt.get('ok') else None
    error = (_body(receipt) or {}).get('error') if isinstance(_body(receipt),dict) else None
    confirmed_not_started = isinstance(error,dict) and error.get('code') == 'CONFIRMATION_REQUIRED'
    rejected_arguments = (isinstance(error,dict) and error.get('code') == 'INVALID_ARGUMENTS'
                          and error.get('http') == 400 and error.get('retryable') is False)
    local_dns_denied = _local_dns_denied(receipt)
    status = ('active' if sid else 'failed' if (receipt.get('not_started')
              or confirmed_not_started or rejected_arguments or local_dns_denied) else 'unknown')
    with db.transaction() as conn:
        conn.execute('UPDATE compute_sandboxes SET sandbox_id=?,status=?,deleted_at=?,receipt_json=?,updated_at=?'
                     ' WHERE operation_id=?', (sid,status,now if status == 'failed' else None,
                                                _json(_receipt(receipt)),db.utcnow(),operation_id))
        db.append_event_tx(conn,run_id,'controller',f'sandbox.{status}',
                           {'operation_id':operation_id,'sandbox_id':sid,
                            'exit_code':receipt.get('exit_code')},trial_id=run['current_trial_id'])
        resources = observed_resources(receipt, sid) if sid else {}
        if resources:
            db.append_event_tx(conn, run_id, 'controller', 'sandbox.resources_observed',
                {'operation_id': operation_id, 'sandbox_id': sid, 'resources': resources,
                 'source': 'create_receipt'}, trial_id=run['current_trial_id'])
    if sid and compute._run(run_id)['phase'] in TERMINAL_RUN and not eval_retry:
        status = delete(run_id,sid)['status']
    return {'operation_id':operation_id,'sandbox_id':sid,'status':status,
            'receipt':_receipt(receipt)}


def reconcile_create(run_id: str, operation_id: str) -> dict:
    row = db.query_one('SELECT * FROM compute_sandboxes WHERE run_id=? AND operation_id=?',
                       (run_id,operation_id))
    if not row:
        raise compute.ComputeError('NOT_FOUND','沙箱创建记录不存在')
    if row['status'] not in ('creating','unknown'):
        return {'operation_id':operation_id,'status':row['status'],'sandbox_id':row['sandbox_id']}
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
    if sid:
        db.execute('UPDATE compute_sandboxes SET sandbox_id=?,status=?,receipt_json=?,updated_at=?'
                   ' WHERE operation_id=?',(sid,'active',_json(_receipt(receipt)),db.utcnow(),operation_id))
        db.append_event(run_id,'controller','sandbox.active',
                        {'operation_id':operation_id,'sandbox_id':sid},trial_id=row['trial_id'])
        if compute._run(run_id)['phase'] in TERMINAL_RUN:
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
                   ' WHERE operation_id=?',(_json(_receipt(receipt)),db.utcnow(),operation_id))
    return {'operation_id':operation_id,'status':'active' if sid else 'unknown','sandbox_id':sid,
            'receipt':_receipt(receipt)}


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
        conn.execute('INSERT INTO compute_sandbox_operations(operation_id,run_id,sandbox_id,action,status,started_at)'
                     ' VALUES(?,?,?,?,?,?)',(op,run_id,sandbox_id,'exec','running',db.utcnow()))
        db.append_event_tx(conn,run_id,'controller','sandbox.exec_started',
                           {'operation_id':op,'sandbox_id':sandbox_id,'command':_clean(command)},
                           trial_id=row['trial_id'])
    started = time.monotonic()
    receipt = compute._native(['sandbox','exec',sandbox_id,'--command',command,'--timeout',
                               str(timeout),'--no-interactive','-o','json'],timeout=timeout+30)
    duration = round(time.monotonic()-started,3)
    safe = _receipt(receipt)
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
              else 'unknown' if receipt.get('unknown') else 'failed')
    with db.transaction() as conn:
        conn.execute('UPDATE compute_sandbox_operations SET status=?,completed_at=?,receipt_json=?'
                     ' WHERE operation_id=?',(status,db.utcnow(),_json(safe),op))
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
    receipt = compute._native(argv,timeout=min(330,max(30,_seconds_left(row))))
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


def reconcile_startup() -> dict:
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
        elif row['phase'] in TERMINAL_RUN and db.query_one(
                "SELECT status FROM compute_sandboxes WHERE sandbox_id=?",(sid,))['status']=='active':
            cleaned.append(delete(row['run_id'],sid))
    if orphan:
        import logging
        logging.getLogger('cyberscientist.sandboxes').warning(
            'Unowned Bohrium sandboxes observed; no deletion: %s',orphan[:20])
    return {'status':'ok','unowned_sandbox_ids':orphan,'cleaned':cleaned}


def dispatch(run_id: str, body: dict) -> dict:
    action=body.get('action')
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
