"""Run-scoped Bohrium operations. Only this backend child receives account keys.

Reservations are committed before a create call; uncertain receipts keep both
quota and concurrency occupied. No cloud mutation is retried automatically.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import zipfile
from datetime import datetime, timezone

from . import config, db
from .bohr_proxy import redact

TERMINAL = {'Finished', 'Failed', 'Stopped'}
LEGACY_JOB_OPENAPI_HOST = 'https://openapi.dp.tech'
NEW_OPENAPI_HOST = 'https://open.bohrium.com'


def client_host_overrides(bohrium: dict, *, wenyon: bool) -> dict[str, str]:
    """Project legacy flat and per-client host settings without cross-routing CLIs."""
    raw = bohrium.get('host_overrides') or {}
    if not isinstance(raw, dict):
        raw = {}
    scope = raw.get('wenyon' if wenyon else 'legacy_job') or {}
    if not isinstance(scope, dict):
        scope = {}
    default = NEW_OPENAPI_HOST if wenyon else LEGACY_JOB_OPENAPI_HOST
    result = {'OPENAPI_HOST': default, 'TIEFBLUE_HOST': 'https://tiefblue.dp.tech'}
    for name in ('OPENAPI_HOST', 'TIEFBLUE_HOST'):
        flat = raw.get(name)
        scoped = scope.get(name)
        candidate = scoped if isinstance(scoped, str) and scoped.strip() else flat
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        value = candidate.strip().rstrip('/')
        if name == 'OPENAPI_HOST':
            # Flat settings predate two clients. A known new host must never
            # send bohr 1.1.0 to its incompatible old /openapi/v1/job route.
            if not wenyon and value.lower() == NEW_OPENAPI_HOST:
                continue
            if wenyon and value.lower() == LEGACY_JOB_OPENAPI_HOST:
                continue
            if wenyon and candidate is flat and value.lower() != NEW_OPENAPI_HOST:
                continue  # ambiguous legacy flat custom host belongs to the old CLI
        result[name] = value
    return result
DEFAULT_LIMITS = {'max_concurrent_jobs': 2, 'max_cpu': 16, 'max_memory_gb': 16,
                  'max_disk_gb': 10, 'allow_gpu': False}
_PROJECT_PARSE_ERROR = ('failed to parse config file: json: cannot unmarshal '
                        'string into Go struct field JobJson.project_id of type int')
log = logging.getLogger('cyberscientist.compute')


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
    wenyon = args[:1] in (['wenyon'], ['sandbox'])
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
               PROJECT_ID=str(settings.get('project_id', '')))
    env.update(client_host_overrides(settings, wenyon=wenyon))
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


def _submit_timeout(total_bytes: int) -> int:
    """A frozen input near 1 GiB can take much longer than a control RPC."""
    return 1200 if total_bytes > 256 * 1024**2 else 180


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
    if total > 256 * 1024**2 and (preflight or {}).get('confirmed_input_bytes') != total:
        from . import runtime_environments
        details = {'input_bytes': total, 'threshold_bytes': 256 * 1024**2,
                   'prebuilt_environments': runtime_environments.facts(),
                   'reservation_created': False,
                   'remedy': '检查预置环境；仍需上传时在 preflight.confirmed_input_bytes 明确确认当前字节数'}
        db.append_event(run_id, 'controller', 'job.input_warning',
                        {'operation_id': operation_id, **details}, trial_id=run['current_trial_id'])
        raise ComputeError('LARGE_INPUT_CONFIRMATION_REQUIRED', '输入超过 256 MiB；创建前需要确认', details)
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
            file_digest = hashlib.sha256()
            secret = key.encode() if key else b''
            overlap = b''
            with os.fdopen(os.open(src, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream, \
                    dest.open('xb') as output:
                for data in iter(lambda: stream.read(1024 * 1024), b''):
                    file_digest.update(data)
                    if secret and secret in overlap + data:
                        raise ValueError('Job 输入包含账号密钥')
                    overlap = (overlap + data)[-len(secret) + 1:] if len(secret) > 1 else b''
                    output.write(data)
            if file_digest.hexdigest() != sha:
                raise ValueError('冻结输入时文件改变')
        (staging / 'job.json').write_text(_json(effective))
        (staging / 'manifest.json').write_text(_json({'request_hash': digest, 'files': manifest}))
        # Pause may have arrived while copying; never dispatch from a stopped Run.
        current_run = _run(run_id)
        if current_run['phase'] != 'running' or current_run['gate'] != 'open' or current_run['current_trial_id'] != run['current_trial_id']:
            raise ValueError('冻结输入期间 Run 已暂停')
    except (OSError, ValueError, TypeError) as exc:
        receipt = {'ok': False, 'not_started': True, 'stderr': str(exc)[:500]}
    else:
        try:
            receipt = _native(['job', 'submit', '-i', str(staging / 'job.json'), '-p', str(staging / 'input')],
                              timeout=_submit_timeout(total))
        except Exception as exc:
            # A gateway/client error after dispatch cannot establish that no
            # remote Job exists. Keep the reservation and expose uncertainty.
            receipt = {'ok': False, 'unknown': True, 'exit_code': None,
                       'stdout': '', 'stderr': 'Bohrium 提交未确认: ' + type(exc).__name__}
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


def mark_terminal_pending_unknown(run_id: str) -> int:
    """A terminal Run cannot leave a create reservation claiming active dispatch."""
    with db.transaction() as conn:
        run = conn.execute('SELECT phase FROM runs WHERE id=?', (run_id,)).fetchone()
        if not run or run['phase'] not in ('finished', 'failed', 'cancelled'):
            return 0
        rows = conn.execute("SELECT operation_id,trial_id FROM compute_jobs"
                            " WHERE run_id=? AND status='submitting'", (run_id,)).fetchall()
        for row in rows:
            conn.execute("UPDATE compute_jobs SET status='unknown',updated_at=?"
                         " WHERE operation_id=? AND status='submitting'",
                         (db.utcnow(), row['operation_id']))
            db.append_event_tx(conn, run_id, 'controller', 'job.unknown',
                               {'operation_id': row['operation_id'],
                                'reason': 'Run 已终结而创建回执仍未确认；只读对账，不重发'},
                               trial_id=row['trial_id'])
        return len(rows)


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


def _job_page(page: int) -> dict:
    """One credential-injected read. Errors never expose a URL containing keys."""
    import httpx
    cfg = config.load_settings()['bohrium']
    key = config.resolve_secret(cfg.get('access_key_secret_ref', ''))
    if not key:
        raise ComputeError('MISSING_CREDENTIAL', 'Job 只读对账缺少后端密钥')
    host = client_host_overrides(cfg, wenyon=False)['OPENAPI_HOST']
    try:
        response = httpx.get(host + '/openapi/v1/job/list',
            params={'accessKey': key, 'groupId': -1, 'page': page, 'pageSize': 100}, timeout=15)
        response.raise_for_status()
        value = response.json()
    except Exception as exc:
        raise ComputeError('JOB_OBSERVATION_UNKNOWN', type(exc).__name__) from None
    if not isinstance(value, dict) or value.get('code') != 0:
        raise ComputeError('JOB_OBSERVATION_UNKNOWN', 'Job API 未确认成功')
    data = value.get('data')
    if (not isinstance(data, dict) or not isinstance(data.get('items'), list)
            or any(not isinstance(item, dict) for item in data['items'])
            or data.get('page') != page or type(data.get('totalPage')) is not int):
        raise ComputeError('JOB_OBSERVATION_UNKNOWN', 'Job API 分页结构未确认')
    # Account-wide metadata stays out of application events and research frames.
    fields = ('id', 'jobName', 'status', 'cost', 'spendTime', 'createTime')
    return {'items': [{field: item[field] for field in fields if field in item}
                      for item in data['items']],
            'page': page, 'total_pages': data['totalPage']}


def _read_job_pages(rows: list[dict], max_pages: int = 3) -> tuple[list[dict], dict]:
    remote, pages, failure = [], 0, None
    wanted = {row['spec']['job_name'] for row in rows}
    for page in range(1, max_pages + 1):
        try:
            result = _job_page(page)
        except ComputeError as exc:
            failure = exc.code
            break
        pages += 1
        remote.extend(result['items'])
        # A later failed page cannot erase facts already received on earlier pages.
        if wanted <= {item.get('jobName') for item in remote} or page >= result['total_pages']:
            break
    return remote, {'source': 'job_list_api', 'pages_received': pages,
                    'max_pages': max_pages, 'error_code': failure,
                    'status': 'partial' if failure or pages == max_pages else 'received',
                    'absence_does_not_prove_not_created': True}


def reconcile(run_id: str) -> dict:
    rows = list_jobs(run_id)['items']
    if not rows:
        return list_jobs(run_id)
    cfg = config.load_settings()['bohrium']
    use_api = bool(config.resolve_secret(cfg.get('access_key_secret_ref', '')))
    if use_api:
        remote, metadata = _read_job_pages(rows)
        receipt = {'ok': bool(metadata['pages_received']), 'stdout': _json(remote),
                   'observation': metadata}
    else:
        # Retain the native adapter for installations without configured API auth.
        receipt = _native(['job', 'list', '-n', '100', '--json'])
    try:
        remote = json.loads(receipt['stdout']) if receipt['ok'] and not receipt.get('truncated') else None
        if not isinstance(remote, list) or any(not isinstance(j, dict) for j in remote):
            raise ValueError('任务列表格式无效')
    except (ValueError, KeyError):
        db.append_event(run_id, 'controller', 'job.observation_unknown', {'receipt': receipt})
        return list_jobs(run_id) | {'observation': 'unknown'}
    from . import environment_facts
    bohrium_cfg=config.load_settings()['bohrium']
    host = client_host_overrides(bohrium_cfg,wenyon=False)['OPENAPI_HOST']
    host_fact = {'client':'legacy_job','host':host}
    try:
        if not db.eval_mode(run_id) and config.resolve_secret(bohrium_cfg.get('access_key_secret_ref','')) and \
                environment_facts.needs_refresh('bohrium:legacy_job:host',host_fact):
            event=db.append_event(run_id,'controller','environment.host_observed',
                                  {'client':'legacy_job','host':host,
                                   'receipt_sha256':hashlib.sha256(receipt['stdout'].encode()).hexdigest()})
            environment_facts.record('bohrium:legacy_job:host','Bohrium Job 客户端主机',host_fact,event)
    except Exception:
        log.exception('Could not record Job host environment fact')
    return _settle_observations(run_id, rows, remote, use_api, receipt.get('observation'))


def _settle_observations(run_id: str, rows: list[dict], remote: list[dict],
                         use_api: bool, observation: dict | None) -> dict:
    """Persist only owned exact matches from an already received read-only page."""
    for row in rows:
        name = row['spec']['job_name']
        matches = [j for j in remote if j.get('jobName') == name and (
            row['platform_job_id'] is None or j.get('id') == row['platform_job_id'])]
        if len(matches) != 1:
            db.append_event(run_id, 'controller', 'job.reservation_unresolved',
                            {'operation_id': row['operation_id'], 'matches': len(matches),
                             'observation': observation, 'status': row['status']},
                            trial_id=row['trial_id'])
            continue
        found = dict(matches[0])
        # Old API codes: 2 was matched to Finished receipts; -1 was matched
        # to an owned Failed describe receipt. The CLI's separate numeric
        # status field is not the list API code. Other codes stay unknown.
        if use_api and type(found.get('status')) is int:
            found['status'] = {2: 'Finished', -1: 'Failed'}.get(found['status'], found['status'])
        if found.get('status') not in TERMINAL | {'Running', 'Pending', 'Scheduling'}:
            continue  # Absence never releases a reservation or authorizes a retry.
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
            if use_api:
                from decimal import Decimal, InvalidOperation
                try:
                    amount = Decimal(str(found.get('cost')))
                    if not amount.is_finite() or amount < 0:
                        raise ValueError()
                except (InvalidOperation, ValueError):
                    amount = None
                billing = {'native_amount': str(amount) if amount is not None else None,
                           'currency': None, 'status': 'platform_reported' if amount is not None else 'unknown',
                           'source': '/openapi/v1/job/list:cost', 'observed_at': db.utcnow(),
                           'spend_seconds': found.get('spendTime')}
                stored = json.loads(current['receipt_json'] or '{}')
                stored['billing'] = billing
                conn.execute('UPDATE compute_jobs SET receipt_json=? WHERE operation_id=?',
                             (_json(stored), row['operation_id']))
                db.append_event_tx(conn, run_id, 'controller', 'job.cost_observed',
                                   {'operation_id': row['operation_id'], 'billing': billing},
                                   trial_id=row['trial_id'])
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


def costs(run_id: str) -> dict:
    """Report incomplete native amounts without claiming a currency or total bill."""
    from decimal import Decimal
    rows = list_jobs(run_id)['items']
    billed = [row.get('receipt', {}).get('billing', {}) for row in rows]
    values = [item['native_amount'] for item in billed
              if item.get('native_amount') is not None]
    from . import sandbox_costs
    return {'sandbox_estimate': sandbox_costs.estimate(run_id),
            'status': 'partial' if values else 'unknown',
            'job_native_amount_total': str(sum((Decimal(value) for value in values), Decimal(0)))
                                       if values else None,
            'currency': None, 'job_cost_count': len(values), 'job_count': len(rows),
            'sandbox_amount': None, 'total_amount': None,
            'notice': '平台 cost 字段；币种、沙箱费用和未回执任务费用尚未确认，不是总账单'}


def recover_pending() -> None:
    rows = db.query("SELECT * FROM compute_jobs WHERE status IN ('submitting','stopping')")
    for row in rows:
        try:
            with db.transaction() as conn:
                current = conn.execute("SELECT status FROM compute_jobs WHERE operation_id=?",
                                       (row['operation_id'],)).fetchone()
                if not current or current['status'] != row['status']:
                    continue
                status = 'unknown' if row['status'] == 'submitting' else 'stop_unknown'
                conn.execute('UPDATE compute_jobs SET status=?,updated_at=? WHERE operation_id=?',
                             (status, db.utcnow(), row['operation_id']))
                db.append_event_tx(conn, row['run_id'], 'controller', 'job.recovered',
                    {'operation_id': row['operation_id'], 'status': status,
                     'notice': '后端重启；保留占位，仅查询远端，不重发变更'}, trial_id=row['trial_id'])
        except Exception:
            log.exception('Job recovery failed for Run %s operation %s',
                          row['run_id'], row['operation_id'])
            # Preserve the reservation and refuse to infer create/stop success.
            status = 'unknown' if row['status'] == 'submitting' else 'stop_unknown'
            try:
                db.execute('UPDATE compute_jobs SET status=?,updated_at=?'
                           ' WHERE operation_id=? AND status=?',
                           (status, db.utcnow(), row['operation_id'], row['status']))
            except Exception:
                log.exception('Job %s recovery fallback failed', row['operation_id'])


def cli(run_id: str, args: list[str], cwd: str) -> dict:
    """Compatibility surface for the Run-local bohr shim; never execute arbitrary argv."""
    import argparse
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ComputeError('INVALID_COMMAND', '命令参数格式错误')
    run = _run(run_id)
    work = _path(run, cwd)
    if args[:1] == ['sandbox']:
        from . import sandboxes
        return sandboxes.cli(run_id, args, cwd)
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
            retrieval = stored.get('retrieval') or {}
            # CS-EV-01a stored only the last operation. Preserve it when moving
            # to per-operation receipts, including evidence of a past download.
            if 'operation' in retrieval:
                old = retrieval
                retrieval = {old['operation']: {key: old.get(key) for key in
                             ('status', 'files', 'exit_code')}}
                if old['operation'] == 'download' and old.get('status') == 'retrieved':
                    retrieval['download_ever_retrieved'] = True
            retrieval['download_ever_retrieved'] = bool(
                retrieval.get('download_ever_retrieved') or
                (args[1] == 'download' and retrieved))
            retrieval[args[1]] = {'status': status, 'files': files if retrieved else [],
                                  'exit_code': receipt.get('exit_code')}
            stored['retrieval'] = retrieval
            summary = 'retrieved' if retrieval['download_ever_retrieved'] else status
            with db.transaction() as conn:
                conn.execute('UPDATE compute_jobs SET retrieval_status=?,receipt_json=?,updated_at=?'
                             ' WHERE operation_id=?', (summary, _json(stored), db.utcnow(), row['operation_id']))
                db.append_event_tx(conn, run_id, 'controller',
                                   'job.retrieved' if retrieved else 'job.retrieval_failed',
                                   {'operation_id': row['operation_id'], 'platform_job_id': jid,
                                    'retrieval_status': status, 'operation': args[1],
                                    'files': files if retrieved else [],
                                    'receipt': {'exit_code': receipt.get('exit_code'),
                                                'ok': receipt.get('ok'),
                                                'stderr': redact(receipt.get('stderr', '')[:1000], [key])}},
                                   trial_id=row['trial_id'])
        if args[1] == 'download' and row['purpose'] == 'probe' and retrieved:
            facts_path = dest / 'results' / 'facts.json'
            try:
                if facts_path.is_file():
                    facts = json.loads(facts_path.read_text())
                else:
                    # bohr 1.1.0 downloads <job_id>/out.zip; inspect the
                    # declared member without extracting any archive paths.
                    with zipfile.ZipFile(dest / str(jid) / 'out.zip') as archive:
                        matches = [item for item in archive.infolist()
                                   if item.filename == 'results/facts.json']
                        if len(matches) != 1 or matches[0].file_size > 2_000_000:
                            raise ValueError('facts.json 缺失、重复或过大')
                        facts = json.loads(archive.read(matches[0]))
                if not isinstance(facts.get('packages'), dict):
                    raise ValueError('packages 缺失')
                digest = hashlib.sha256(_json(facts).encode()).hexdigest()
                db.execute('INSERT OR IGNORE INTO image_facts(image_address,facts_sha256,facts_json,source_operation_id,observed_at)'
                           ' VALUES(?,?,?,?,?)', (json.loads(row['spec_json'])['image_address'], digest,
                                                  _json(facts), row['operation_id'], db.utcnow()))
                event=db.append_event(run_id, 'controller', 'image_facts.observed',
                                      {'operation_id': row['operation_id'], 'facts_sha256': digest})
                from . import environment_facts
                image=json.loads(row['spec_json'])['image_address']
                if config.resolve_secret(config.load_settings()['bohrium'].get('access_key_secret_ref','')):
                    try:
                        environment_facts.record('bohrium:image:'+image,'镜像环境 '+image,
                                                 {'image_address':image,'facts_sha256':digest,
                                                  'packages':facts['packages']},event)
                    except Exception:
                        log.exception('Could not record image environment fact')
            except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
                db.append_event(run_id, 'controller', 'image_facts.unknown',
                                {'operation_id': row['operation_id'], 'reason': 'facts.json 解析失败'})
        return receipt
    if args in (['version'], ['project', 'list', '--json'], ['image', 'list', '--json'], ['machine', 'list', '--json']):
        return _native(args)
    raise ComputeError('UNSUPPORTED_COMMAND', '此操作未开放；请使用受控 Job 接口')
