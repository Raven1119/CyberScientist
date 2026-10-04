"""Register only backend-owned command receipts against immutable input plans."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import shlex
import zlib

from . import config, db, local_scoring, mailboxes, runtime_environments


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _error(code, message, **details):
    raise local_scoring.LocalScoreError(code, message, details)


def _current(run_id, trial_id):
    row = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    if (not row or row['phase'] != 'running' or row['gate'] != 'open'
            or row['current_trial_id'] != trial_id):
        _error('RUN_NOT_RUNNING', '评分准备/登记需要当前运行中的 Trial')
    return row


def _prepared(operation_id, sandbox_id, stored):
    plan = stored['plan']
    if stored.get('channel') == 'job':
        return {'status': 'prepared', 'channel': 'job', 'operation_id': operation_id,
                'input_directory': stored['stage'], 'command': stored['job_command'],
                'backward_files': ['results'], 'image_address': stored['image'],
                'inputs': plan['inputs'], 'required_environment_identity': plan['identity'],
                'preparation': '通过 research_job 提交固定命令；Job 结束后 register_job 由系统下载并核验，未取得完整回执不登记分数。'}
    return {'status': 'prepared', 'operation_id': operation_id, 'sandbox_id': sandbox_id,
            'command': stored['command'], 'inputs': plan['inputs'],
            'required_environment_identity': plan['identity'],
            'scorer_requirements': stored.get('scorer_requirements'),
            'public_project': stored.get('public_project'),
            'transfers': [{'local_path': str(Path(stored['stage']) / name),
                           'remote_path': plan['remote'] + '/' + name} for name in plan['inputs']],
            'preparation': '环境由执行器准备；mkdir/传输/执行使用受控沙箱工具。执行本命令后以 execution_operation_id 登记回执；未知执行不自动重发。'}


def prepare(run_id: str, trial_id: str, operation_id: str, sandbox_id: str,
            package_path=None, environment_paths=None, *, channel="sandbox") -> dict:
    if not isinstance(operation_id, str) or not local_scoring._OPERATION.fullmatch(operation_id):
        _error('INVALID_OPERATION', '需要稳定的有界评分 operation_id')
    run = _current(run_id, trial_id)
    sandbox = db.query_one('SELECT * FROM compute_sandboxes WHERE run_id=? AND sandbox_id=?',
                           (run_id, sandbox_id))
    if channel not in ('job', 'sandbox'):
        _error('INVALID_CHANNEL', '评分通道必须为 job 或 sandbox')
    if channel == 'sandbox' and (not sandbox or sandbox['trial_id'] != trial_id or sandbox['status'] != 'active'):
        _error('NOT_OWNED', '需要本 Trial 拥有的活跃沙箱')
    request = {'package_path': package_path, 'environment_paths': dict(environment_paths or {})}
    if channel == 'job':
        request['channel'] = 'job'
    existing = db.query_one('SELECT * FROM executor_score_plans WHERE operation_id=?', (operation_id,))
    if existing:
        stored = json.loads(existing['plan_json'])
        if (existing['run_id'] != run_id or existing['trial_id'] != trial_id
                or existing['sandbox_id'] != sandbox_id or stored.get('request') != request):
            _error('OPERATION_CONFLICT', '评分计划已绑定不同请求')
        if _hash(existing['plan_json'].encode()) != existing['plan_sha256']:
            _error('SCORE_PLAN_MISMATCH', '冻结计划完整性不符')
        return _prepared(operation_id, sandbox_id, stored)
    manifest = local_scoring.scorer_manifest(run['challenge_id'])
    check = mailboxes.preflight_submission(run_id, trial_id, package_path,
                                           allow_proxy_evidence=True)
    if check['error_code'] and not (check['error_code'] in (
            'TRACE_ADMISSION_BLOCKED', 'TRACE_ADMISSION_INDETERMINATE', 'PROXY_EVIDENCE')):
        _error(check['error_code'], '候选包未通过封存预检')
    cached = local_scoring.reuse_score(run_id, trial_id, operation_id, check['sealed_bytes'], manifest)
    if cached:
        return {'status': 'registered', 'local_score': cached, 'reused': True}
    runtime = manifest.get('runtime', {})
    paths = dict(environment_paths or {})
    if (not isinstance(paths, dict) or set(paths) - {'lean_bin', 'mathlib_root', 'project_root'}
            or any(not isinstance(value, str) or not value.startswith('/') or '..' in Path(value).parts
                   or not re.fullmatch(r'[/A-Za-z0-9_.-]{1,400}', value) for value in paths.values())):
        _error('INVALID_ENVIRONMENT_PATH', '环境路径必须是有界绝对路径')
    recipe = runtime_environments.recipe(runtime['environment_id']) if runtime.get('environment_id') else {}
    identity = recipe.get('identity', {})
    checks = recipe.get('identity_checks', {})
    if set(checks) != set(identity):
        _error('ENVIRONMENT_IDENTITY_UNDECLARED', '声明的环境缺少完整的身份检查', required=identity)
    if channel == 'sandbox' and not identity and json.loads(sandbox['request_json']).get('image') != manifest['image']:
        _error('SCORER_IMAGE_MISMATCH', '未声明身份检查时仍须使用评分器声明的镜像')
    for key in ('lean_bin', 'mathlib_root'):
        if recipe.get(key) and key not in paths:
            paths[key] = recipe[key]
    if runtime.get('project') and 'project_root' not in paths:
        _error('ENVIRONMENT_PROJECT_PATH_REQUIRED', '需指定固定公开项目所在的沙箱路径')
    stage = config.WORKSPACE_DIR / 'runs' / run_id / 'trials' / trial_id / 'executor_scorer' / operation_id
    local_scoring._stage_score_inputs(stage, check['sealed_bytes'], manifest)
    inputs = {name: _hash((stage / name).read_bytes())
              for name in ('scorer.zip', 'science_package.zip')}
    public = runtime.get('public_resource')
    if public:
        source = (config.WORKSPACE_ROOT / public['path']).resolve()
        if (not source.is_relative_to(config.WORKSPACE_ROOT.resolve()) or source.is_symlink()
                or not source.is_file() or _hash(source.read_bytes()) != public['sha256']):
            _error('PUBLIC_RESOURCE_MISMATCH', '声明的公开资源缺失或哈希不符')
        target = stage / 'public_resource.zip'
        if target.exists() and _hash(target.read_bytes()) != public['sha256']:
            _error('OPERATION_CONFLICT', '已冻结的公开资源被修改')
        target.write_bytes(source.read_bytes())
        inputs['public_resource.zip'] = public['sha256']
    plan = {'input_layout': channel, 'remote': 'input' if channel == 'job' else '/tmp/cs-executor-score-' + operation_id, 'inputs': inputs,
            'identity': identity, 'identity_checks': checks, 'environment_paths': paths,
            'project_files': runtime.get('project', {}).get('files', {}),
            'scorer_files': manifest['file_hashes'], 'scorer_version': manifest['scorer_version'],
            'entrypoint': manifest['entrypoint'], 'public_resource': public,
            'score_timeout': runtime.get('score_timeout', 120)}
    program = (Path(__file__).with_name('scoring_runner.py')).read_bytes()
    compressed = base64.b64encode(zlib.compress(program, 9)).decode()
    encoded = base64.b64encode(local_scoring._canonical(plan).encode()).decode()
    script = 'import base64,zlib;exec(zlib.decompress(base64.b64decode(' + repr(compressed) + ')))'
    command = 'python3 -I -c ' + shlex.quote(script) + ' ' + shlex.quote(encoded)
    if len(command) > 8000:
        _error('INVALID_SCORER', '可信评分命令超过受控沙箱通道上限')
    stored = {'plan': plan, 'command': command, 'stage': str(stage), 'request': request,
              'scorer_requirements': manifest['files'].get('requirements.txt', b'').decode('utf-8', errors='replace')[:4000],
              'public_project': runtime.get('project'),
              'sealed_sha256': _hash(check['sealed_bytes']), 'runner_sha256': _hash(program),
              'channel': channel, 'image': manifest['image']}
    if channel == 'job':
        stored['job_command'] = 'mkdir -p results; ' + command + ' > results/score.json; ' + 'cs_score_exit=$?; printf \'{"exit_code":%s}\\n\' "$cs_score_exit" > results/execution.json; exit "$cs_score_exit"'
    raw = local_scoring._canonical(stored)
    with db.transaction() as conn:
        old = conn.execute('SELECT * FROM executor_score_plans WHERE operation_id=?', (operation_id,)).fetchone()
        if old and (old['run_id'] != run_id or old['trial_id'] != trial_id
                    or old['sandbox_id'] != sandbox_id or old['plan_json'] != raw):
            _error('OPERATION_CONFLICT', '评分计划已绑定不同输入、环境或沙箱')
        if not old:
            conn.execute('INSERT INTO executor_score_plans VALUES(?,?,?,?,?,?,?)',
                         (operation_id, run_id, trial_id, sandbox_id, raw, _hash(raw.encode()), db.utcnow()))
            db.append_event_tx(conn, run_id, 'controller', 'local_score.executor_plan_created',
                               {'operation_id': operation_id, 'inputs': inputs,
                                'command_sha256': _hash(command.encode()), 'runner_sha256': _hash(program)},
                               trial_id=trial_id)
    return _prepared(operation_id, sandbox_id, stored)


def register(run_id: str, trial_id: str, operation_id: str, execution_operation_id: str) -> dict:
    run = _current(run_id, trial_id)
    row = db.query_one('SELECT * FROM executor_score_plans WHERE operation_id=? AND run_id=? AND trial_id=?',
                       (operation_id, run_id, trial_id))
    if not row or _hash(row['plan_json'].encode()) != row['plan_sha256']:
        _error('SCORE_PLAN_MISMATCH', '后端评分计划不存在或完整性不符')
    stored = json.loads(row['plan_json'])
    plan = stored['plan']
    executed = db.query_one('SELECT * FROM compute_sandbox_operations WHERE operation_id=?'
                            ' AND run_id=? AND sandbox_id=? AND action=\'exec\'',
                            (execution_operation_id, run_id, row['sandbox_id']))
    if (not executed or executed['command_sha256'] != _hash(stored['command'].encode())):
        _error('SCORE_COMMAND_MISMATCH', '未找到该沙箱中执行固定评分命令的受控回执')
    if not executed['receipt_sha256'] or _hash(executed['receipt_json'].encode()) != executed['receipt_sha256']:
        _error('SCORE_RECEIPT_MISMATCH', '通道回执完整性不符')
    receipt = json.loads(executed['receipt_json'])
    if executed['status'] != 'completed' or receipt.get('ok') is not True or receipt.get('truncated'):
        _error('SCORE_EXECUTION_UNCONFIRMED', '执行未确认完成或输出被截断', receipt=receipt)
    try:
        wrapper = json.loads(receipt['stdout'])
        data = wrapper.get('data', wrapper)
        output = json.loads(data['stdout'])
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        _error('INVALID_SCORE_OUTPUT', '回执不包含单个有效的评分 JSON')
    if type(data.get('exit_code')) is not int or data['exit_code'] != 0:
        _error('SCORE_EXIT_NONZERO', '评分进程退出码未确认成功')
    if wrapper.get('ok') is False:
        _error('SCORE_EXECUTION_UNCONFIRMED', '原生服务未确认评分执行成功')
    return _verify_output(run_id, trial_id, operation_id, execution_operation_id, run, stored, output, executed['receipt_sha256'], 'sandbox')


def _verify_output(run_id, trial_id, operation_id, execution_operation_id, run, stored, output, receipt_sha256, channel):
    plan = stored['plan']
    if not isinstance(output, dict) or set(output) != {'schema_version', 'inputs', 'environment_identity', 'science'}:
        _error('INVALID_SCORE_OUTPUT', '可信评分输出契约不符')
    if type(output['schema_version']) is not int or output['schema_version'] != 1 or output['inputs'] != plan['inputs']:
        _error('SCORE_INPUT_MISMATCH', '评分器、科学包或公开数据 ZIP 哈希不符')
    if output['environment_identity'] != plan['identity']:
        _error('SCORE_ENVIRONMENT_MISMATCH', '同一次执行中的环境身份不符合声明')
    stage = Path(stored['stage'])
    if any((stage / name).is_symlink() or _hash((stage / name).read_bytes()) != digest
           for name, digest in plan['inputs'].items()):
        _error('SCORE_INPUT_MISMATCH', '本机冻结输入已变化')
    sealed = (stage / 'sealed_package.zip').read_bytes()
    manifest = local_scoring.scorer_manifest(run['challenge_id'])
    if _hash(sealed) != stored['sealed_sha256'] or manifest['scorer_version'] != plan['scorer_version']:
        _error('SCORE_INPUT_MISMATCH', '封存包或已审查评分器版本已变化')
    scientific_receipt = {'receipt': {'stdout': json.dumps({'data': {'stdout': json.dumps(output['science'])}})}}
    science = local_scoring._score_output(scientific_receipt, plan['scorer_version'])
    result = local_scoring._record_score(run['challenge_id'], run_id, trial_id, operation_id,
                                         sealed, manifest, science, score_source='executor_verified')
    db.append_event(run_id, 'controller', 'local_score.executor_receipt_verified',
                    {'local_score_id': result['id'], 'execution_operation_id': execution_operation_id,
                     'receipt_sha256': receipt_sha256, 'inputs': plan['inputs'],
                     'environment_identity': output['environment_identity'], 'execution_channel': channel}, trial_id=trial_id)
    return result



def register_job(run_id: str, trial_id: str, operation_id: str, execution_operation_id: str) -> dict:
    """The backend downloads output; callers cannot supply scores or receipts."""
    from . import compute
    import zipfile
    run = _current(run_id, trial_id)
    row = db.query_one('SELECT * FROM executor_score_plans WHERE operation_id=? AND run_id=? AND trial_id=?',
                       (operation_id, run_id, trial_id))
    if not row or _hash(row['plan_json'].encode()) != row['plan_sha256']:
        _error('SCORE_PLAN_MISMATCH', 'Job 评分计划缺失或完整性不符')
    stored = json.loads(row['plan_json'])
    job = db.query_one('SELECT * FROM compute_jobs WHERE operation_id=? AND run_id=? AND trial_id=?',
                       (execution_operation_id, run_id, trial_id))
    if not job or stored.get('channel') != 'job' or job['status'] != 'Finished' or not job['platform_job_id']:
        _error('SCORE_EXECUTION_UNCONFIRMED', '需要本 Trial 已确认结束的 Job')
    spec = json.loads(job['spec_json'])
    if spec.get('command') != stored['job_command']:
        _error('SCORE_COMMAND_MISMATCH', 'Job 未执行系统固定评分命令')
    if not stored['plan']['identity'] and spec.get('image_address') != stored['image']:
        _error('SCORE_ENVIRONMENT_MISMATCH', 'Job 镜像身份不符')
    prior = db.query_one('SELECT * FROM local_scores WHERE sandbox_operation_id=?', (operation_id,))
    if prior:
        return dict(prior) | {'deduplicated': True}
    destination = Path(stored['stage']) / 'job_output'
    destination.mkdir(exist_ok=True)
    native = compute.cli(run_id, ['job', 'download', '-j', str(job['platform_job_id']), '-o', str(destination)], str(Path(stored['stage'])))
    updated = db.query_one('SELECT receipt_json FROM compute_jobs WHERE operation_id=?', (execution_operation_id,))
    retrieval = json.loads(updated['receipt_json']).get('retrieval', {}).get('download', {})
    files = retrieval.get('files') or []
    if not native.get('ok') or retrieval.get('status') != 'retrieved':
        _error('SCORE_EXECUTION_UNCONFIRMED', '系统未确认下载完整输出')
    def read_member(name):
        direct = destination / name
        if direct.is_file() and not direct.is_symlink():
            captured = next((item for item in files if item['path'] == name), None)
            raw = direct.read_bytes()
            if not captured or captured['sha256'] != _hash(raw) or len(raw) > 2_000_000:
                _error('SCORE_RECEIPT_MISMATCH', '系统下载文件哈希不符')
            return raw
        archive_path = destination / str(job['platform_job_id']) / 'out.zip'
        captured = next((item for item in files if item['path'] == str(job['platform_job_id']) + '/out.zip'), None)
        if not captured or not archive_path.is_file() or archive_path.is_symlink() or captured['sha256'] != compute._file_sha256(archive_path):
            _error('SCORE_RECEIPT_MISMATCH', '系统下载 ZIP 哈希不符')
        with zipfile.ZipFile(archive_path) as archive:
            matches = [item for item in archive.infolist() if item.filename == name]
            if len(matches) != 1 or matches[0].file_size > 2_000_000:
                _error('INVALID_SCORE_OUTPUT', 'Job 输出缺失、重复或超过上限')
            return archive.read(matches[0])
    try:
        raw = read_member('results/score.json')
        exit_raw = read_member('results/execution.json')
        output = json.loads(raw)
        exit_data = json.loads(exit_raw)
    except (ValueError, OSError, zipfile.BadZipFile):
        _error('INVALID_SCORE_OUTPUT', 'Job 输出不是单个有效 JSON')
    if not isinstance(exit_data, dict) or type(exit_data.get('exit_code')) is not int or exit_data['exit_code'] != 0:
        _error('SCORE_EXIT_NONZERO', '固定评分进程退出码未确认成功')
    captured = {'output': output, 'execution': exit_data, 'retrieval': retrieval,
                'job_operation_id': execution_operation_id, 'command_sha256': _hash(spec['command'].encode())}
    canonical = local_scoring._canonical(captured)
    db.execute('INSERT OR IGNORE INTO job_score_receipts VALUES(?,?,?,?,?,?)',
               (operation_id, run_id, execution_operation_id, canonical, _hash(canonical.encode()), db.utcnow()))
    return _verify_output(run_id, trial_id, operation_id, execution_operation_id, run, stored, output, _hash(canonical.encode()), 'job')
