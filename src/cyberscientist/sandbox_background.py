"""Durable background commands; a lost launch reply never triggers a relaunch."""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import time

from . import compute, db, sandboxes


def _authorized(run_id: str, timeout: int) -> None:
    from . import power, run_clock
    run=compute._run(run_id)
    auth=db.query_one('SELECT * FROM authorizations WHERE id=?',(run['authorization_id'],))
    if power.shutdown_requested() or run['phase']!='running' or run['gate']!='open' or not run['current_trial_id']:
        raise compute.ComputeError('RUN_NOT_RUNNING','研究门禁或关机状态禁止新的后台计算')
    if not auth or run_clock.remaining(run,auth)<timeout+5:
        raise compute.ComputeError('AUTH_EXPIRED','后台命令超出本题现有授权时长')


def start(run_id: str, sandbox_id: str, command: str, timeout: int,
          operation_id: str) -> dict:
    box = sandboxes._owned(run_id, sandbox_id)
    run = compute._run(run_id)
    if run['phase'] != 'running' or run['gate'] != 'open':
        raise compute.ComputeError('RUN_NOT_RUNNING', '研究门禁关闭，不能启动后台命令')
    if (box['status'] != 'active' or not isinstance(command, str) or not command
            or len(command) > 8000 or type(timeout) is not int or timeout < 1
            or timeout + 5 > sandboxes._seconds_left(box)):
        raise compute.ComputeError('INVALID_COMMAND', '后台命令须在沙箱剩余寿命内结束')
    if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', operation_id):
        raise compute.ComputeError('INVALID_OPERATION', '后台执行需要稳定 operation_id')
    _authorized(run_id,timeout)
    digest = hashlib.sha256(sandboxes._json([command,timeout]).encode()).hexdigest()
    directory = '/tmp/cyberscientist-background/' + operation_id
    quoted = shlex.quote(directory)
    # Native timeout=0 applies only to the launch RPC. Bound the actual process
    # separately, and publish its exit code atomically after flushing the log.
    wrapper = (f'mkdir -p {quoted} && '
               f'timeout --signal=TERM --kill-after=5 {timeout} bash -c {shlex.quote(command)} '
               f'>{quoted}/output.log 2>&1; code=$?; '
               f'printf "%s\\n" "$code" >{quoted}/exit.tmp; '
               f'mv {quoted}/exit.tmp {quoted}/exit')
    with db.transaction() as conn:
        _authorized(run_id,timeout)
        if conn.execute('SELECT 1 FROM compute_jobs WHERE operation_id=?',(operation_id,)).fetchone():
            raise compute.ComputeError('OPERATION_CONFLICT','该操作已绑定Job，不能再启动沙箱命令')
        previous = conn.execute('SELECT * FROM compute_sandbox_operations WHERE operation_id=?',
                                (operation_id,)).fetchone()
        if previous:
            if (previous['run_id'] != run_id or previous['sandbox_id'] != sandbox_id
                    or previous['action'] != 'background' or previous['command_sha256'] != digest):
                raise compute.ComputeError('OPERATION_CONFLICT', '后台操作 ID 已绑定其他请求')
            return {'operation_id': operation_id, 'status': previous['status'],
                    'deduplicated': True, 'poll_action': 'poll'}
        conn.execute('INSERT INTO compute_sandbox_operations'
                     '(operation_id,run_id,sandbox_id,action,status,started_at,command_sha256)'
                     " VALUES(?,?,?,'background','running',?,?)",
                     (operation_id, run_id, sandbox_id, db.utcnow(), digest))
        db.append_event_tx(conn, run_id, 'controller', 'sandbox.background_started',
                           {'operation_id': operation_id, 'sandbox_id': sandbox_id,
                            'command': sandboxes._clean(command), 'timeout': timeout},
                           trial_id=box['trial_id'])
    started = time.monotonic()
    try:
        _authorized(run_id,timeout)
        receipt = compute._native(['sandbox', 'exec', sandbox_id, '--command', wrapper,
                                  '--background', '--timeout', '0', '--request-id', operation_id,
                                  '--no-interactive', '-o', 'json'], timeout=45)
    except Exception as exc:
        receipt = {'ok': False, 'unknown': True, 'stderr': type(exc).__name__}
    safe = sandboxes._receipt(receipt)
    # Launch acceptance is not command completion. Even an unknown launch can
    # be reconciled by its unique exit/log path without replaying the command.
    node = sandboxes._data(sandboxes._body(receipt))
    pid = node.get('pid') if isinstance(node, dict) else None
    status = 'running' if receipt.get('ok') and type(pid) is int and pid > 0 else 'unknown'
    raw = sandboxes._json({'launch': safe, 'pid': pid, 'directory': directory, 'timeout': timeout})
    db.execute("UPDATE compute_sandbox_operations SET status=CASE WHEN status IN ('completed','failed','cancelled') THEN status ELSE ? END,receipt_json=?,receipt_sha256=?"
               ' WHERE operation_id=?', (status, raw, hashlib.sha256(raw.encode()).hexdigest(), operation_id))
    status=db.query_one('SELECT status FROM compute_sandbox_operations WHERE operation_id=?',(operation_id,))[0]
    db.append_event(run_id, 'controller', 'sandbox.background_observed',
                    {'operation_id': operation_id, 'status': status, 'pid': pid,
                     'elapsed_seconds': round(time.monotonic() - started, 3)}, trial_id=box['trial_id'])
    return {'operation_id': operation_id, 'status': status, 'pid': pid,
            'log_path': directory + '/output.log', 'poll_action': 'poll'}


def poll(run_id: str, operation_id: str) -> dict:
    row = db.query_one("SELECT * FROM compute_sandbox_operations WHERE operation_id=? AND run_id=?"
                       " AND action='background'", (operation_id, run_id))
    if not row:
        raise compute.ComputeError('NOT_OWNED', '后台操作不属于本 Run')
    box = sandboxes._owned(run_id, row['sandbox_id'])
    if box['status'] != 'active' or sandboxes._seconds_left(box) < 2:
        return {'operation_id': operation_id, 'status': row['status'] if row['status'] in ('completed', 'failed') else 'unknown',
                'notice': '沙箱不可读；不重发后台命令'}
    directory = shlex.quote('/tmp/cyberscientist-background/' + operation_id)
    command = (f'if test -f {directory}/exit; then printf "CS_BACKGROUND_EXIT="; '
               f'cat {directory}/exit; elif test -d {directory}; then printf "CS_BACKGROUND_PENDING\\n"; '
               f'else printf "CS_BACKGROUND_UNKNOWN\\n"; fi; '
               f'if test -f {directory}/output.log; then tail -c 12000 {directory}/output.log; fi')
    result = sandboxes.execute(run_id, row['sandbox_id'], command,
                               min(30, sandboxes._seconds_left(box)), 'poll_' + __import__('uuid').uuid4().hex)
    node = sandboxes._data(sandboxes._body(result['receipt']))
    output = node.get('stdout', '') if isinstance(node, dict) else ''
    # The backend-owned first line precedes all untrusted command log output.
    first, _, log = output.partition('\n')
    match = re.fullmatch(r'CS_BACKGROUND_EXIT=(\d{1,3})', first)
    exit_code = int(match.group(1)) if match else None
    status = ('completed' if exit_code == 0 else 'failed' if exit_code is not None
              else 'running' if first == 'CS_BACKGROUND_PENDING' and result['status'] == 'completed'
              else 'unknown')
    if exit_code is not None and result['status'] == 'completed':
        db.execute('UPDATE compute_sandbox_operations SET status=?,completed_at=? WHERE operation_id=?',
                   (status, db.utcnow(), operation_id))
    elif result['status'] != 'completed':
        status = 'unknown'
    db.append_event(run_id, 'controller', 'sandbox.background_polled',
                    {'operation_id': operation_id, 'status': status, 'exit_code': exit_code,
                     'log': sandboxes._clean(log)}, trial_id=box['trial_id'])
    return {'operation_id': operation_id, 'status': status, 'exit_code': exit_code,
            'log': sandboxes._clean(log), 'log_truncated_to_bytes': 12000}
