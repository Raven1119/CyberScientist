"""Run-scoped Bohrium operations. Only this backend child receives account keys.

Reservations are committed before a create call; uncertain receipts keep both
quota and concurrency occupied. No cloud mutation is retried automatically.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

from . import config, db
from .bohr_proxy import redact

TERMINAL = {'Finished', 'Failed', 'Stopped'}
DEFAULT_LIMITS = {'max_concurrent_jobs': 2, 'max_cpu': 16, 'max_memory_gb': 16,
                  'max_disk_gb': 10, 'allow_gpu': False}
_PROJECT_PARSE_ERROR = ('failed to parse config file: json: cannot unmarshal '
                        'string into Go struct field JobJson.project_id of type int')


class ComputeError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def validate_limits(value: dict | None) -> dict:
    if value is not None and (not isinstance(value, dict) or set(value) - DEFAULT_LIMITS.keys()):
        raise ComputeError('INVALID_LIMITS', '不支持的资源授权字段')
    limits = DEFAULT_LIMITS | (value or {})
    for key in ('max_concurrent_jobs', 'max_cpu', 'max_memory_gb', 'max_disk_gb'):
        if type(limits[key]) is not int or limits[key] < 1:
            raise ComputeError('INVALID_LIMITS', '资源上限必须为正整数')
    if limits['allow_gpu'] is not False:
        raise ComputeError('INVALID_LIMITS', '本版本只支持 CPU 授权')
    return limits


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _project_id(value: object) -> int:
    """Normalize the settings/API value to bohr 1.1.0's integer JobJson field."""
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]*', value):
        return int(value)
    raise ComputeError('INVALID_PROJECT', 'Bohrium 项目 ID 必须是正整数')


def _local_project_parse_failure(receipt: dict) -> bool:
    """The native CLI rejected its input JSON before it could create a Job."""
    return (receipt.get('ok') is False and not receipt.get('unknown')
            and _PROJECT_PARSE_ERROR in
            (receipt.get('stdout', '') + '\n' + receipt.get('stderr', '')))


def _run(run_id):
    run = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    if not run:
        raise ComputeError('NOT_FOUND', 'Run 不存在')
    return run


def _path(run, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ComputeError('INVALID_PATH', '需要工作目录路径')
    path = Path(value).resolve()
    roots = [config.WORKSPACE_DIR / 'runs' / run['id'] / 'trials' / (run['current_trial_id'] or '_none'),
             config.WORKSPACE_DIR / 'challenges' / run['challenge_id']]
    if not any(path.is_relative_to(root.resolve()) for root in roots):
        raise ComputeError('INVALID_PATH', '路径必须位于当前 Trial 或题目工作目录')
    return path


def _native(args: list[str], *, timeout: int = 90) -> dict:
    settings = config.load_settings()['bohrium']
    key = config.resolve_secret(settings.get('access_key_secret_ref', ''))
    wenyon = args[:1] == ['wenyon']
    executable = (settings.get('wenyon_executable') if wenyon else None) or settings['executable']
    env = {k: v for k, v in os.environ.items() if not k.startswith(('CS_', 'BOHR_', 'PLAYGROUND_'))
           and k not in ('ACCESS_KEY', 'OPENAPI_HOST', 'TIEFBLUE_HOST')}
    if wenyon and settings.get('wenyon_home'):
        home = Path(settings['wenyon_home'])
        env['HOME'] = str(home)
        # Keep the companion CLI's Vouch/XDG session in the same isolated home.
        for name, relative in (('XDG_CONFIG_HOME', '.config'),
                               ('XDG_STATE_HOME', '.local/state'),
                               ('XDG_CACHE_HOME', '.cache'),
                               ('XDG_RUNTIME_DIR', '.run')):
            directory = home / relative
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            env[name] = str(directory)
    env.update(BOHR_ACCESS_KEY=key, ACCESS_KEY=key,
               PROJECT_ID=str(settings.get('project_id', '')),
               OPENAPI_HOST='https://open.bohrium.com', TIEFBLUE_HOST='https://tiefblue.dp.tech')
    env.update(settings.get('host_overrides') or {})
    try:
        result = subprocess.run([executable, *args], env=env, capture_output=True,
                                text=True, errors='replace', timeout=timeout)
        out, err = redact(result.stdout, [key]), redact(result.stderr, [key])
        # bohr 1.1.0 can print an error while returning zero.
        success = result.returncode == 0 and not re.search(
            r'(?im)^\s*(error:|unknown (?:shorthand )?flag|panic:)|json: cannot unmarshal object into Go struct field RespErr\.error of type string',
            out + '\n' + err)
        return {'exit_code': result.returncode, 'ok': success,
                'stdout': out[:2_000_000], 'stderr': err[-12000:],
                'truncated': len(out) > 2_000_000}
    except subprocess.TimeoutExpired:
        return {'exit_code': None, 'ok': False, 'unknown': True,
                'stdout': '', 'stderr': 'Bohrium 请求超时；先对账，不重试变更请求'}
    except OSError as exc:
        return {'exit_code': None, 'ok': False, 'not_started': True,
                'stdout': '', 'stderr': redact(str(exc), [key])[:1000]}


def list_jobs(run_id: str) -> dict:
    _run(run_id)
    items = []
    for row in db.query('SELECT * FROM compute_jobs WHERE run_id=? ORDER BY created_at', (run_id,)):
        item = dict(row)
        item['spec'] = json.loads(item.pop('spec_json'))
        item['receipt'] = json.loads(item.pop('receipt_json'))
        items.append(item)
    return {'items': items, 'reserved_jobs': sum(j['status'] != 'not_started' for j in items),
            'active_or_unknown': sum(j['status'] not in TERMINAL | {'not_started'} for j in items)}


def _authorized(conn, run_id):
    run = conn.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
    if not run or run['phase'] != 'running' or run['gate'] != 'open' or not run['current_trial_id']:
        raise ComputeError('RUN_NOT_RUNNING', 'Run 未运行或研究门禁关闭；禁止新增算力')
    if json.loads(run['config_snapshot']).get('compute_policy_version') != 1:
        raise ComputeError('LEGACY_RUN', '升级前的 Run 未有完整算力账本；先核清旧任务，再用新 Run 授权计算')
    auth = conn.execute('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],)).fetchone()
    if run['mode'] != 'connected' or not auth or auth['max_jobs'] <= 0:
        raise ComputeError('NOT_AUTHORIZED', '本轮没有真实算力授权')
    if not auth['max_run_minutes'] or not run['started_at']:
        raise ComputeError('UNBOUNDED_JOB', '真实算力需要明确的本轮时长上限')
    remaining = auth['max_run_minutes'] * 60 - (datetime.now(timezone.utc) - datetime.fromisoformat(run['started_at'])).total_seconds()
    if remaining < 60:
        raise ComputeError('AUTH_EXPIRED', '本轮算力授权已到期')
    limits = DEFAULT_LIMITS | json.loads(auth['job_limits_json'])
    rows = conn.execute('SELECT status FROM compute_jobs WHERE run_id=?', (run_id,)).fetchall()
    if sum(r['status'] != 'not_started' for r in rows) >= auth['max_jobs']:
        raise ComputeError('JOB_LIMIT', '已达到 Job 总数上限（包括失败与 unknown）')
    if any(r['status'] in ('submitting', 'unknown') for r in rows):
        raise ComputeError('CREATE_UNKNOWN', '仍有未完成或未知的创建请求，必须先对账')
    if sum(r['status'] not in TERMINAL | {'not_started'} for r in rows) >= limits['max_concurrent_jobs']:
        raise ComputeError('CONCURRENCY_LIMIT', '运行中及未知任务已占满并发额度')
    return run, limits, remaining


def submit(run_id: str, operation_id: str, spec: dict, input_directory: str,
           preflight: dict | None = None) -> dict:
    if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', operation_id):
        raise ComputeError('INVALID_OPERATION', '需要稳定且安全的 operation_id')
    run = _run(run_id)
    source = _path(run, input_directory)
    if not source.is_dir():
        raise ComputeError('INVALID_PATH', '输入目录不存在')
    from . import datasets
    try:
        data_refs = datasets.input_refs(source)
    except datasets.DataError as exc:
        raise ComputeError(exc.code, str(exc)) from exc
    allowed = {'job_name', 'command', 'log_file', 'backward_files', 'project_id', 'machine_type',
               'image_address', 'job_type', 'disk_size', 'max_reschedule_times', 'max_run_time',
               'nnode', 'result_path', 'dataset_path'}
    if not isinstance(spec, dict) or set(spec)-allowed:
        raise ComputeError('INVALID_SPEC', 'Job 配置含未支持字段')
    if preflight is not None and not isinstance(preflight, dict):
        raise ComputeError('INVALID_PREFLIGHT', 'preflight 必须是对象')
    key = config.resolve_secret(config.load_settings()['bohrium'].get('access_key_secret_ref', ''))
    if key and key in _json(spec):
        raise ComputeError('SECRET_INPUT', 'Job 配置不能包含账号密钥')
    manifest = []
    total = 0
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ComputeError('INVALID_PATH', 'Job 输入不能包含符号链接')
        if path.is_file():
            if path.name in ('.env', 'secrets.json', 'auth.json', 'id_rsa', 'id_ed25519'):
                raise ComputeError('SECRET_INPUT', '输入目录含凭据文件')
            total += path.stat().st_size
            if total > 1024**3:
                raise ComputeError('DATA_TOO_LARGE_FOR_INPUT', '输入超过 1 GiB；Wenyon 到 dataset_path 的挂载映射尚未验证')
            with path.open('rb') as stream:
                sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            manifest.append((str(path.relative_to(source)), sha))
    from . import job_preflight
    files = {rel: (source / rel).read_bytes() for rel, _ in manifest
             if Path(rel).suffix in ('.py', '.txt') and (source / rel).stat().st_size <= 2_000_000}
    options = preflight or {}
    try:
        report = job_preflight.check_sources(files, str(spec.get('command') or ''),
            options.get('entry'), options.get('allow_network_install') is True)
        if preflight is not None and options.get('purpose') != 'probe':
            row = db.query_one('SELECT facts_json FROM image_facts WHERE image_address=?'
                               ' ORDER BY observed_at DESC LIMIT 1', (spec.get('image_address'),))
            facts = json.loads(row['facts_json']) if row else None
            report = job_preflight.check_image_facts(report, str(spec.get('image_address') or ''),
                options.get('api_checks') or [], facts)
        else:
            report['api_checked'] = False
        db.append_event(run_id, 'controller', 'job.preflight',
                        {'operation_id': operation_id, 'status': 'passed', 'report': report},
                        trial_id=run['current_trial_id'])
    except job_preflight.PreflightError as exc:
        db.append_event(run_id, 'controller', 'job.preflight',
                        {'operation_id': operation_id, 'status': 'rejected',
                         'code': exc.code, 'details': exc.details},
                        trial_id=run['current_trial_id'])
        raise ComputeError(exc.code, str(exc), exc.details) from exc
    digest = hashlib.sha256(_json([spec, manifest, str(source)]).encode()).hexdigest()
    # Persist a reservation before materializing/dispatching, under the SQLite writer lock.
    with db.transaction() as conn:
        old = conn.execute('SELECT * FROM compute_jobs WHERE operation_id=?', (operation_id,)).fetchone()
        if old:
            if old['run_id'] != run_id or old['request_hash'] != digest:
                raise ComputeError('CONFLICT', '操作 ID 已绑定其他请求，不能覆盖或重发')
            return dict(old) | {'deduplicated': True}
        run, limits, remaining = _authorized(conn, run_id)
        machine = re.fullmatch(r'c(\d+)_m(\d+)_cpu', str(spec.get('machine_type', '')))
        if not machine or not (1 <= int(machine[1]) <= limits['max_cpu'] and 1 <= int(machine[2]) <= limits['max_memory_gb']):
            raise ComputeError('RESOURCE_LIMIT', '当前受控入口仅接受授权范围内的 CPU 机型')
        minutes = spec.get('max_run_time')
        if type(minutes) is not int or not 1 <= minutes <= math.floor(remaining / 60):
            raise ComputeError('RESOURCE_LIMIT', 'Job 时限必须小于本轮剩余授权')
        disk = spec.get('disk_size', 10)
        if type(disk) is not int or not 1 <= disk <= limits['max_disk_gb']:
            raise ComputeError('RESOURCE_LIMIT', '磁盘配置超出授权')
        if spec.get('nnode', 1) != 1 or spec.get('max_reschedule_times', 0) != 0:
            raise ComputeError('RESOURCE_LIMIT', '仅支持单节点，禁止平台自动重调度重跑')
        if any(not isinstance(spec.get(k), str) or not spec[k].strip() for k in ('command', 'image_address')):
            raise ComputeError('INVALID_SPEC', '需要计算命令和完整镜像地址')
        project = _project_id(config.load_settings()['bohrium']['project_id'])
        if _project_id(spec.get('project_id', project)) != project:
            raise ComputeError('INVALID_PROJECT', 'Job 必须属于配置的授权项目')
        effective = dict(spec, project_id=project, nnode=1, max_reschedule_times=0, job_type='container', disk_size=disk,
                         job_name=f"cs-{run_id}-{hashlib.sha256(operation_id.encode()).hexdigest()[:16]}")
        now = db.utcnow()
        conn.execute('INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,spec_json,input_directory,status,created_at,updated_at,data_refs_json,purpose)'
                     " VALUES(?,?,?,?,?,?,'submitting',?,?,?,?)", (operation_id, run_id, run['current_trial_id'], digest,
                     _json(effective), str(source), now, now, _json(data_refs),
                     'probe' if options.get('purpose') == 'probe' else 'compute'))
        db.append_event_tx(conn, run_id, 'controller', 'job.reserved',
                           {'operation_id': operation_id, 'job_name': effective['job_name'],
                            'data_refs': data_refs}, trial_id=run['current_trial_id'])
    staging = config.DATA_DIR / 'job-inputs' / operation_id
    try:
        staging.mkdir(parents=True, exist_ok=False)
        (staging / 'input').mkdir()
        # Copy only the pre-hashed manifest. O_NOFOLLOW closes the final-path
        # symlink race; re-resolve parent directories before opening each file.
        for rel, sha in manifest:
            src = source / rel
            if not src.resolve().is_relative_to(source) or src.is_symlink():
                raise ValueError('冻结输入期间路径改变')
            dest = staging / 'input' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with os.fdopen(os.open(src, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
                data = stream.read()
            if hashlib.sha256(data).hexdigest() != sha:
                raise ValueError('冻结输入时文件改变')
            if key and key.encode() in data:
                raise ValueError('Job 输入包含账号密钥')
            dest.write_bytes(data)
        (staging / 'job.json').write_text(_json(effective))
        (staging / 'manifest.json').write_text(_json({'request_hash': digest, 'files': manifest}))
        # Pause may have arrived while copying; never dispatch from a stopped Run.
        current_run = _run(run_id)
        if current_run['phase'] != 'running' or current_run['gate'] != 'open' or current_run['current_trial_id'] != run['current_trial_id']:
            raise ValueError('冻结输入期间 Run 已暂停')
    except (OSError, ValueError) as exc:
        receipt = {'ok': False, 'not_started': True, 'stderr': str(exc)[:500]}
    else:
        receipt = _native(['job', 'submit', '-i', str(staging / 'job.json'), '-p', str(staging / 'input')], timeout=180)
        if _local_project_parse_failure(receipt):
            receipt['not_started'] = True
    matches = re.findall(r'\bJobId:\s*(\d+)', receipt.get('stdout', ''), re.I)
    job_id = int(matches[0]) if len(set(matches)) == 1 else None
    status = 'accepted' if job_id else ('not_started' if receipt.get('not_started') else 'unknown')
    with db.transaction() as conn:
        current = conn.execute('SELECT * FROM compute_jobs WHERE operation_id=?', (operation_id,)).fetchone()
        if current['platform_job_id'] is not None:
            job_id, status = current['platform_job_id'], current['status']
        conn.execute('UPDATE compute_jobs SET platform_job_id=?,status=?,receipt_json=?,updated_at=? WHERE operation_id=?',
                     (job_id, status, _json(receipt), db.utcnow(), operation_id))
        db.append_event_tx(conn, run_id, 'controller', 'job.' + status,
                           {'operation_id': operation_id, 'platform_job_id': job_id, 'status': status, 'receipt': receipt}, trial_id=run['current_trial_id'])
    return {'operation_id': operation_id, 'platform_job_id': job_id, 'status': status, 'receipt': receipt}


def resolve_local_parse_failure(run_id: str, operation_id: str) -> dict:
    """Explicitly settle only the known bohr project-ID decode failure.

    This does not turn a missing remote-list match or a timeout into proof of
    non-creation. All other unknown operations retain their reservation.
    """
    _run(run_id)
    with db.transaction() as conn:
        row = conn.execute(
            'SELECT * FROM compute_jobs WHERE run_id=? AND operation_id=?',
            (run_id, operation_id)).fetchone()
        if not row:
            raise ComputeError('NOT_FOUND', '受控 Job 操作不存在')
        if row['status'] == 'not_started':
            return {'operation_id': operation_id, 'status': 'not_started',
                    'deduplicated': True}
        receipt = json.loads(row['receipt_json'] or '{}')
        spec = json.loads(row['spec_json'])
        if (row['status'] != 'unknown' or row['platform_job_id'] is not None
                or type(spec.get('project_id')) is not str
                or not _local_project_parse_failure(receipt)):
            raise ComputeError('INSUFFICIENT_EVIDENCE',
                               '只有本地项目 ID JSON 解码失败可确认为未启动')
        conn.execute(
            "UPDATE compute_jobs SET status='not_started',updated_at=?"
            " WHERE run_id=? AND operation_id=? AND status='unknown'",
            (db.utcnow(), run_id, operation_id))
        db.append_event_tx(conn, run_id, 'controller', 'job.not_started_confirmed', {
            'operation_id': operation_id, 'basis': 'native_project_id_json_decode_failure',
            'receipt_sha256': hashlib.sha256(row['receipt_json'].encode()).hexdigest(),
            'notice': '仅释放本地解析失败的占位；其他 unknown 操作仍禁止重试'},
            trial_id=row['trial_id'])
    return {'operation_id': operation_id, 'status': 'not_started'}


def reconcile(run_id: str) -> dict:
    rows = list_jobs(run_id)['items']
    if not rows:
        return list_jobs(run_id)
    receipt = _native(['job', 'list', '-n', '100', '--json'])
    try:
        remote = json.loads(receipt['stdout']) if receipt['ok'] and not receipt.get('truncated') else None
        if not isinstance(remote, list) or any(not isinstance(j, dict) for j in remote):
            raise ValueError('任务列表格式无效')
    except (ValueError, KeyError):
        db.append_event(run_id, 'controller', 'job.observation_unknown', {'receipt': receipt})
        return list_jobs(run_id) | {'observation': 'unknown'}
    for row in rows:
        name = row['spec']['job_name']
        matches = [j for j in remote if j.get('jobName') == name and (
            row['platform_job_id'] is None or j.get('id') == row['platform_job_id'])]
        if len(matches) != 1 or matches[0].get('status') not in TERMINAL | {'Running', 'Pending', 'Scheduling'}:
            continue  # Absence never releases a reservation or authorizes a retry.
        found = matches[0]
        if type(found.get('id')) is not int:
            continue
        status = found['status']
        # An observation racing the create receipt may bind the ID first.
        with db.transaction() as conn:
            current = conn.execute('SELECT * FROM compute_jobs WHERE operation_id=?', (row['operation_id'],)).fetchone()
            if current['status'] in TERMINAL or (current['status'] in ('stopping', 'stop_unknown') and status not in TERMINAL):
                status = current['status']
            conn.execute('UPDATE compute_jobs SET platform_job_id=?,status=?,observed_at=?,updated_at=? WHERE operation_id=?',
                         (found['id'], status, db.utcnow(), db.utcnow(), row['operation_id']))
            if current['status'] != status:
                db.append_event_tx(conn, run_id, 'controller', 'job.observed',
                                   {'operation_id': row['operation_id'], 'platform_job_id': found['id'],
                                    'status': status, 'remote': found}, trial_id=row['trial_id'])
    return list_jobs(run_id) | {'observation': 'received'}


def stop(run_id: str, operation_id: str) -> dict:
    row = db.query_one('SELECT * FROM compute_jobs WHERE operation_id=? AND run_id=?', (operation_id, run_id))
    if not row:
        raise ComputeError('NOT_FOUND', '任务不属于本 Run')
    if row['status'] in TERMINAL | {'stopping', 'stop_unknown', 'not_started'}:
        return {'status': row['status'], 'deduplicated': True}
    if not row['platform_job_id']:
        raise ComputeError('CREATE_UNKNOWN', '尚无远端 ID，请先对账')
    with db.transaction() as conn:
        changed = conn.execute("UPDATE compute_jobs SET status='stopping',updated_at=? WHERE operation_id=?"
                               " AND status NOT IN ('stopping','stop_unknown','Finished','Failed','Stopped')",
                               (db.utcnow(), operation_id)).rowcount
        if not changed:
            return {'status': 'stopping', 'deduplicated': True}
        db.append_event_tx(conn, run_id, 'controller', 'job.stop_requested', {'operation_id': operation_id})
    receipt = _native(['job', 'terminate', str(row['platform_job_id'])])
    # Even exit 0 and a success message are only receipts, not terminal state.
    db.execute("UPDATE compute_jobs SET status=CASE WHEN status='stopping' THEN 'stop_unknown' ELSE status END,receipt_json=?,updated_at=? WHERE operation_id=?",
               (_json(receipt), db.utcnow(), operation_id))
    db.append_event(run_id, 'controller', 'job.stop_receipt', {'operation_id': operation_id, 'receipt': receipt})
    return reconcile(run_id)


def recover_pending() -> None:
    with db.transaction() as conn:
        for row in conn.execute("SELECT * FROM compute_jobs WHERE status IN ('submitting','stopping')").fetchall():
            status = 'unknown' if row['status'] == 'submitting' else 'stop_unknown'
            conn.execute('UPDATE compute_jobs SET status=?,updated_at=? WHERE operation_id=?',
                         (status, db.utcnow(), row['operation_id']))
            db.append_event_tx(conn, row['run_id'], 'controller', 'job.recovered',
                {'operation_id': row['operation_id'], 'status': status,
                 'notice': '后端重启；保留占位，仅查询远端，不重发变更'}, trial_id=row['trial_id'])


def cli(run_id: str, args: list[str], cwd: str) -> dict:
    """Compatibility surface for the Run-local bohr shim; never execute arbitrary argv."""
    import argparse
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ComputeError('INVALID_COMMAND', '命令参数格式错误')
    run = _run(run_id)
    work = _path(run, cwd)
    if args[:3] == ['wenyon', 'dataset', 'download']:
        from . import datasets
        parser = argparse.ArgumentParser(exit_on_error=False, add_help=False)
        parser.add_argument('dataset_id'); parser.add_argument('--version', required=True)
        parser.add_argument('--output-dir'); parser.add_argument('--output')
        parser.add_argument('--cs-operation-id')
        try:
            opts, unknown = parser.parse_known_args(args[3:])
            if unknown or not opts.dataset_id or not opts.version:
                raise ValueError()
        except (ValueError, argparse.ArgumentError):
            raise ComputeError('INVALID_COMMAND', '受控下载格式：bohr wenyon dataset download ID --version V --output-dir DIR --output json')
        key = f'wenyon:{opts.dataset_id}@{opts.version}'
        op = opts.cs_operation_id or 'data_' + hashlib.sha256(_json([run_id,key]).encode()).hexdigest()[:32]
        try:
            return datasets.materialize(run['challenge_id'], key, op, run_id)
        except datasets.DataError as exc:
            raise ComputeError(exc.code, str(exc)) from exc
    if args[:2] == ['job', 'submit']:
        parser = argparse.ArgumentParser(exit_on_error=False, add_help=False)
        parser.add_argument('-i', '--input'); parser.add_argument('-p', '--input_directory')
        parser.add_argument('--cs-operation-id')
        try:
            opts, unknown = parser.parse_known_args(args[2:])
            if unknown or not opts.input or not opts.input_directory:
                raise ValueError()
            spec = json.loads(_path(run, str(work / opts.input)).read_text())
            directory = str(_path(run, str(work / opts.input_directory)))
        except (ValueError, OSError, argparse.ArgumentError):
            raise ComputeError('INVALID_COMMAND', '受控提交格式：bohr job submit -i job.json -p input/ [--cs-operation-id ID]')
        op = opts.cs_operation_id or 'job_' + hashlib.sha256(_json([run_id, run['current_trial_id'], spec, directory]).encode()).hexdigest()[:40]
        return submit(run_id, op, spec, directory)
    if args[:2] == ['job', 'list']:
        return reconcile(run_id)
    if len(args) >= 2 and args[0] == 'job' and args[1] in ('describe', 'log', 'download', 'terminate'):
        parser = argparse.ArgumentParser(exit_on_error=False, add_help=False)
        parser.add_argument('-j', '--job_id', type=int); parser.add_argument('-o', '--output')
        parser.add_argument('--json', action='store_true'); parser.add_argument('id', type=int, nargs='?')
        try:
            opts, unknown = parser.parse_known_args(args[2:]); jid = opts.job_id or opts.id
            if unknown or not jid:
                raise ValueError()
        except (ValueError, argparse.ArgumentError):
            raise ComputeError('INVALID_COMMAND', '需要本 Run 的 Job ID')
        row = db.query_one('SELECT * FROM compute_jobs WHERE run_id=? AND platform_job_id=?', (run_id, jid))
        if not row:
            raise ComputeError('NOT_OWNED', 'Job 未登记在本 Run，拒绝操作')
        if args[1] == 'terminate':
            return stop(run_id, row['operation_id'])
        command = ['job', args[1], '-j', str(jid)]
        if opts.output:
            dest = _path(run, str(work / opts.output)); dest.mkdir(parents=True, exist_ok=True)
            command += ['-o', str(dest)]
        if args[1] in ('log', 'download') and not opts.output:
            raise ComputeError('INVALID_PATH', '日志/结果下载必须显式指定 -o 工作目录')
        if opts.json:
            command.append('--json')
        before = ({p.relative_to(dest).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
                   for p in dest.rglob('*') if p.is_file() and not p.is_symlink()}
                  if args[1] in ('log', 'download') else {})
        receipt = _native(command)
        if args[1] in ('log', 'download'):
            key = config.resolve_secret(config.load_settings()['bohrium'].get('access_key_secret_ref', ''))
            files = []
            for path in sorted(dest.rglob('*')):
                if not path.is_file() or path.is_symlink():
                    continue
                rel = path.relative_to(dest).as_posix()
                if before.get(rel) == (path.stat().st_size, path.stat().st_mtime_ns):
                    continue
                files.append({'path': redact(rel, [key]), 'sha256': _file_sha256(path),
                              'bytes': path.stat().st_size})
            retrieved = bool(receipt.get('ok') and files)
            status = 'retrieved' if retrieved else 'failed'
            stored = json.loads(row['receipt_json'] or '{}')
            stored['retrieval'] = {'operation': args[1], 'status': status,
                                   'files': files if retrieved else [],
                                   'exit_code': receipt.get('exit_code')}
            with db.transaction() as conn:
                conn.execute('UPDATE compute_jobs SET retrieval_status=?,receipt_json=?,updated_at=?'
                             ' WHERE operation_id=?', (status, _json(stored), db.utcnow(), row['operation_id']))
                db.append_event_tx(conn, run_id, 'controller',
                                   'job.retrieved' if retrieved else 'job.retrieval_failed',
                                   {'operation_id': row['operation_id'], 'platform_job_id': jid,
                                    'retrieval_status': status, 'operation': args[1],
                                    'files': files if retrieved else [],
                                    'receipt': {'exit_code': receipt.get('exit_code'),
                                                'ok': receipt.get('ok'),
                                                'stderr': redact(receipt.get('stderr', '')[:1000], [key])}},
                                   trial_id=row['trial_id'])
        if args[1] == 'download' and row['purpose'] == 'probe' and receipt.get('ok') and opts.output:
            facts_path = dest / 'results' / 'facts.json'
            try:
                facts = json.loads(facts_path.read_text())
                if not isinstance(facts.get('packages'), dict):
                    raise ValueError('packages 缺失')
                digest = hashlib.sha256(_json(facts).encode()).hexdigest()
                db.execute('INSERT OR IGNORE INTO image_facts(image_address,facts_sha256,facts_json,source_operation_id,observed_at)'
                           ' VALUES(?,?,?,?,?)', (json.loads(row['spec_json'])['image_address'], digest,
                                                  _json(facts), row['operation_id'], db.utcnow()))
                db.append_event(run_id, 'controller', 'image_facts.observed',
                                {'operation_id': row['operation_id'], 'facts_sha256': digest})
            except (OSError, ValueError, KeyError, TypeError):
                db.append_event(run_id, 'controller', 'image_facts.unknown',
                                {'operation_id': row['operation_id'], 'reason': 'facts.json 解析失败'})
        return receipt
    if args in (['version'], ['project', 'list', '--json'], ['image', 'list', '--json'], ['machine', 'list', '--json']):
        return _native(args)
    raise ComputeError('UNSUPPORTED_COMMAND', '此操作未开放；请使用受控 Job 接口')
