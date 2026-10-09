"""One persistent sandbox per Run, chosen by the PI, with same-image Job fallback."""
from __future__ import annotations

import hashlib
import json
import math
import shlex
import threading
import uuid
from collections import defaultdict
from pathlib import Path

from . import compute, config, db, environment_catalog, sandboxes

REMOTE = '/bohr-workspace'
_locks = defaultdict(threading.RLock)


def _record(run_id, fact):
    run = compute._run(run_id)
    db.append_event(run_id, 'controller', 'topic.workspace', fact, trial_id=run['current_trial_id'])
    return fact


def lifetime_ceiling() -> int:
    row = db.query_one("SELECT payload_json FROM runtime_observations WHERE kind='sandbox-lifetime-ceiling'")
    value = json.loads(row[0]).get('effective_ceiling_seconds') if row else None
    return value if type(value) is int and value > 0 else 3600


def _fingerprint(path):
    entries = []
    for p in sorted(Path(path).rglob('*')):
        if p.is_symlink():
            raise ValueError('工作目录含符号链接，不能确认完整同步')
        if p.is_file():
            entries.append([p.relative_to(path).as_posix(), compute._file_sha256(p), p.stat().st_size])
    return hashlib.sha256(json.dumps(entries, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def _remote_fingerprint(run_id, sid):
    # A small receipt covers every file, without truncating a large manifest.
    script = '''import hashlib,json,pathlib
root=pathlib.Path('/bohr-workspace')
assert root.is_dir()
entries=[]
for p in sorted(root.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  h=hashlib.sha256()
  with p.open('rb') as stream:
   for block in iter(lambda:stream.read(1048576),b''):h.update(block)
  entries.append([p.relative_to(root).as_posix(),h.hexdigest(),p.stat().st_size])
print(json.dumps({'sha256':hashlib.sha256(json.dumps(entries,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()}))
'''
    box = sandboxes._owned(run_id, sid)
    result = sandboxes.execute(run_id, sid, 'python3 -c ' + shlex.quote(script),
                              min(30, sandboxes._seconds_left(box) - 1))
    if result['status'] != 'completed' or result['exit_code'] != 0:
        raise ValueError('远端文件哈希未确认')
    node = sandboxes._data(sandboxes._body(result['receipt']))
    return json.loads(node['stdout'])['sha256']


def checkpoint(run_id, sid):
    """Copy an idle workspace before expiry; never resume a scientific command."""
    with _locks[run_id]:
        fact = current(run_id)
        if fact.get('sandbox_id') != sid or fact['mode'] != 'sandbox':
            return fact
        if db.query_one("SELECT 1 FROM compute_sandbox_operations WHERE sandbox_id=? AND action='background' AND status IN ('running','unknown')", (sid,)):
            return fact
        run = compute._run(run_id)
        destination = (config.WORKSPACE_DIR / 'challenges' / run['challenge_id'] /
                       'topic-workspaces' / run_id / uuid.uuid4().hex)
        observed = _remote_fingerprint(run_id, sid)
        result = sandboxes.transfer(run_id, 'read', sid, REMOTE, local_path=str(destination))
        if (result['status'] != 'completed' or not destination.is_dir()
                or _fingerprint(destination) != observed
                or _remote_fingerprint(run_id, sid) != observed):
            raise ValueError('工作文件同步没有得到一致哈希，保留旧沙箱和证据')
        return _record(run_id, fact | {'checkpoint': {'path': str(destination), 'sha256': observed}})


def enabled(run_id: str) -> bool:
    row = compute._run(run_id)
    return json.loads(row['config_snapshot']).get('sandbox_first_version') == 1


def current(run_id: str) -> dict:
    row = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='topic.workspace' ORDER BY seq DESC LIMIT 1", (run_id,))
    return json.loads(row['payload']) if row else {'mode': 'not_selected'}


def ensure(run_id: str) -> dict:
    with _locks[run_id]:
        return _ensure(run_id)


def _create(run_id, image, generation, checkpoint=None):
    run = compute._run(run_id)
    operation_id = 'topic_' + run_id + (f'_{generation}' if generation else '')
    fact = {'mode': 'job', 'image': image, 'operation_id': operation_id,
            'generation': generation, 'sandbox_id': None, 'workspace_path': REMOTE,
            'renewal': 'replace_same_image', 'checkpoint': checkpoint}
    try:
        auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],))
        if not auth:
            raise compute.ComputeError('NOT_AUTHORIZED', '本题没有有效的计算授权')
        from . import run_clock
        left = run_clock.remaining(run, auth)
        if not math.isfinite(left):
            raise compute.ComputeError('UNBOUNDED_SANDBOX', '沙箱需要Run结束时限')
        lifetime = sandboxes.bounded_lifetime(run_id, min(lifetime_ceiling(), int(left) - 300))
        result = sandboxes.create(run_id, operation_id,
                                 {'image': image, 'cpu': '2c4g', 'timeout': lifetime},
                                 _session_id=run_id)
        fact.update(sandbox_id=result.get('sandbox_id'), create_status=result['status'],
                    lifetime_seconds=lifetime, reason='创建状态=' + result['status'])
        if result['status'] == 'active':
            sid = result['sandbox_id']
            initialized = sandboxes.execute(run_id, sid, 'mkdir -p ' + REMOTE, min(30, lifetime - 1))
            if initialized['status'] != 'completed' or initialized['exit_code'] != 0:
                raise ValueError('沙箱工作目录未确认')
            if checkpoint:
                if _fingerprint(Path(checkpoint['path'])) != checkpoint['sha256']:
                    raise ValueError('本地工作快照已变化，拒绝恢复')
                restored = sandboxes.transfer(run_id, 'write', sid, REMOTE,
                                              local_path=checkpoint['path'])
                if restored['status'] != 'completed' or _remote_fingerprint(run_id, sid) != checkpoint['sha256']:
                    raise ValueError('新沙箱工作文件哈希未确认')
            fact['mode'] = 'sandbox'
    except (compute.ComputeError, ValueError, OSError, KeyError, TypeError) as exc:
        fact['reason'] = getattr(exc, 'code', type(exc).__name__) + ': ' + str(exc)
        if fact.get('sandbox_id'):
            sandboxes.delete(run_id, fact['sandbox_id'])
    return _record(run_id, fact)


def _ensure(run_id: str) -> dict:
    prior = current(run_id)
    if prior['mode'] != 'not_selected':
        if prior['mode'] == 'renewing':
            old = sandboxes._owned(run_id, prior['sandbox_id'])
            if old['status'] == 'deleted':
                return _create(run_id, prior['image'], prior['generation'] + 1, prior.get('checkpoint'))
            return prior
        if prior.get('sandbox_id'):
            box = sandboxes._owned(run_id, prior['sandbox_id'])
            if box['status'] != 'active' or sandboxes._seconds_left(box) < 30:
                if prior['mode'] == 'sandbox' and sandboxes._seconds_left(box) < 30:
                    return _rotate(run_id, prior)
                return prior | {'mode': 'job', 'reason': '沙箱已由操作者清理或不可用'}
        return prior
    run = compute._run(run_id)
    choice = environment_catalog.current(run_id)
    if choice['mode'] != 'catalog':
        return {'mode': 'not_selected', 'reason': 'PI须先选择包含镜像的环境目录起点'}
    entry = environment_catalog.get(choice['entry_id'])
    image = entry.get('image')
    if not image:
        return {'mode': 'not_selected', 'reason': '所选环境未提供镜像'}
    return _create(run_id, image, 0)


def _rotate(run_id, fact):
    run = compute._run(run_id)
    from . import power
    if run['phase'] != 'running' or run['gate'] != 'open' or power.shutdown_requested():
        return fact | {'mode': 'job', 'reason': '门禁关闭，不新建沙箱'}
    if not fact.get('checkpoint'):
        return _record(run_id, fact | {'mode': 'job', 'reason': '到期前没有确认的工作文件快照；使用显式Job输入，不假称完整恢复'})
    fact = _record(run_id, fact | {'mode': 'renewing'})
    box = sandboxes._owned(run_id, fact['sandbox_id'])
    if box['status'] == 'active':
        sandboxes.delete(run_id, fact['sandbox_id'])
    return _ensure(run_id)


def maintain_due():
    """Capture idle work before expiry, replace only after deletion is confirmed."""
    results = []
    for row in db.query("SELECT id FROM runs WHERE phase='running' AND gate='open'"):
        rid = row['id']
        with _locks[rid]:
            fact = current(rid)
            if fact['mode'] == 'renewing':
                results.append(_ensure(rid)); continue
            if fact['mode'] != 'sandbox':
                continue
            box = sandboxes._owned(rid, fact['sandbox_id'])
            left = sandboxes._seconds_left(box)
            if box['status'] == 'active' and 60 < left <= 300 and not fact.get('checkpoint'):
                try:
                    from . import sandbox_background
                    for operation in db.query("SELECT operation_id FROM compute_sandbox_operations WHERE sandbox_id=? AND action='background' AND status IN ('running','unknown')", (fact['sandbox_id'],)):
                        sandbox_background.poll(rid, operation['operation_id'])
                    fact = checkpoint(rid, fact['sandbox_id'])
                except (compute.ComputeError, ValueError, OSError, KeyError, TypeError) as exc:
                    db.append_event(rid, 'controller', 'topic.workspace_sync_failed', {'error_type': type(exc).__name__})
            if left < 30:
                results.append(_rotate(rid, fact))
    return results


def work(run_id: str, body: dict) -> dict:
    with _locks[run_id]:
        return _work(run_id, body)


def _work(run_id: str, body: dict) -> dict:
    """A work request includes its Job spec/input so fallback needs no second call."""
    op=body.get('operation_id')
    previous=db.query_one("SELECT * FROM compute_sandbox_operations WHERE operation_id=? AND action='background'",(op,))
    if previous:
        from . import sandbox_background
        expected=sandbox_background.command_digest(body.get('command'), body.get('timeout'),
            json.loads(previous['receipt_json'] or '{}').get('cwd'))
        if previous['run_id']!=run_id or previous['command_sha256']!=expected:
            raise compute.ComputeError('OPERATION_CONFLICT','本题工作操作已绑定其他请求')
        return {'operation_id':op,'status':previous['status'],'deduplicated':True,'backend':'sandbox','poll_action':'poll','automatic_replay':False}
    previous_job=db.query_one('SELECT * FROM compute_jobs WHERE operation_id=?',(op,))
    if previous_job:
        if previous_job['run_id']!=run_id:
            raise compute.ComputeError('OPERATION_CONFLICT','工作操作不属于本Run')
        return compute.submit(run_id,op,body.get('spec'),body.get('input_directory'),body.get('preflight'))
    fact = ensure(run_id)
    if fact['mode'] in ('not_selected', 'renewing'):
        return fact
    if (fact['mode'] == 'sandbox' and type(body.get('timeout')) is int
            and body['timeout'] + 300 > sandboxes._seconds_left(sandboxes._owned(run_id, fact['sandbox_id']))):
        fact = fact | {'mode': 'job', 'reason': '命令将占用到期同步窗口，改用同镜像Job'}
    if fact['mode'] == 'sandbox':
        from . import sandbox_background
        if body.get('input_directory'):
            staged = sandboxes.transfer(run_id, 'write', fact['sandbox_id'], REMOTE,
                                        local_path=body['input_directory'])
            if staged['status'] != 'completed':
                raise compute.ComputeError('WORKSPACE_SYNC_UNKNOWN', '工作输入同步未确认；未执行命令')
        _record(run_id, fact | {'checkpoint': None})
        return sandbox_background.start(run_id, fact['sandbox_id'], body.get('command'),
                                        body.get('timeout'), body.get('operation_id'), cwd=REMOTE)
    spec = body.get('spec')
    if not isinstance(spec, dict) or not body.get('input_directory'):
        raise compute.ComputeError('FALLBACK_SPEC_REQUIRED', '沙箱创建未确认；请为同镜像Job提供spec、input_directory，unknown沙箱保留预留')
    if spec.get('image_address') != fact['image'] or spec.get('command') != body.get('command'):
        raise compute.ComputeError('FALLBACK_IMAGE_MISMATCH', '自动回退必须使用PI选定的同镜像、同命令')
    result = compute.submit(run_id, body.get('operation_id'), spec, body['input_directory'], body.get('preflight'))
    db.append_event(run_id, 'controller', 'topic.job_fallback',
                    {'operation_id': body.get('operation_id'), 'image': fact['image'],
                     'reason': fact['reason'], 'sandbox_reservation_retained': fact.get('create_status') == 'unknown'})
    return result | {'fallback': 'job', 'fallback_reason': fact['reason']}
