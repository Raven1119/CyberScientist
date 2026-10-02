"""Challenge-scoped science scoring through an owned Bohrium sandbox.

The host only validates files, extracts text features, and records comparisons.
The challenge scorer itself runs in the declared image through sandboxes.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import shlex
import uuid
import zipfile
from pathlib import Path
from typing import Any

from . import config, db, mailboxes, sandboxes, trace_selection
from .observation import strip_secrets

FEATURE_VERSION = 'trace-features-v1'
MODEL_VERSION = 'trace-placeholder-v1'
_OPERATION = re.compile(r'[A-Za-z0-9_-]{1,70}\Z')
_ENTRYPOINT = re.compile(r'[A-Za-z0-9_-]+\.py\Z')
_SCORE_REF = re.compile(r'(?<![A-Za-z0-9_])local_score:([A-Za-z0-9_]+)')


class LocalScoreError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def validate_runtime(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) - {
            'environment_id', 'adapter', 'project', 'public_resource', 'score_timeout', 'sandbox_timeout'}:
        raise LocalScoreError('INVALID_SCORER', '评分器运行环境声明无效')
    for name in ('score_timeout', 'sandbox_timeout'):
        if name in value and (type(value[name]) is not int or not 1 <= value[name] <= 3600):
            raise LocalScoreError('INVALID_SCORER', '评分器时限无效')
    if 'environment_id' in value and (not isinstance(value['environment_id'], str)
            or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', value['environment_id'])):
        raise LocalScoreError('INVALID_SCORER', '评分环境标识无效')
    if 'adapter' in value and (value['adapter'] != 'lean_project' or 'environment_id' not in value or 'project' not in value):
        raise LocalScoreError('INVALID_SCORER', '评分器环境适配器无效')
    project = value.get('project')
    if project is not None:
        if (not isinstance(project, dict) or set(project) != {'path', 'files'}
                or not isinstance(project['path'], str) or not project['path']
                or project['path'].startswith('/') or '\\' in project['path']
                or '..' in Path(project['path']).parts or not isinstance(project['files'], dict)
                or not 1 <= len(project['files']) <= 100
                or any(not isinstance(name, str) or not _ENTRYPOINT.fullmatch(name)
                       and not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name)
                       or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)
                       for name, digest in project['files'].items())):
            raise LocalScoreError('INVALID_SCORER', '固定公开项目声明无效')
    public = value.get('public_resource')
    if public is not None:
        if (not isinstance(public, dict) or set(public) != {
                'path', 'sha256', 'environment_variable', 'directory'}
                or not isinstance(public['sha256'], str)
                or not re.fullmatch(r'[a-f0-9]{64}', public['sha256'])
                or not isinstance(public['environment_variable'], str)
                or not re.fullmatch(r'CS_[A-Z0-9_]+', public['environment_variable'])
                or any(not isinstance(public[name], str) or not public[name]
                       or public[name].startswith('/') or '\\' in public[name]
                       or '..' in Path(public[name]).parts for name in ('path', 'directory'))):
            raise LocalScoreError('INVALID_SCORER', '公开评分资源声明无效')
    return value


def validate_comparison(value: Any) -> dict:
    """Only the reviewed scorer may declare monotone grading inputs."""
    if value is None:
        return {}
    if (not isinstance(value, dict) or set(value) != {'higher_is_better', 'verification'}
            or not isinstance(value['higher_is_better'], list)
            or not 1 <= len(value['higher_is_better']) <= 32
            or any(not isinstance(path, str) or len(path) > 300
                   or not path.startswith('/components/')
                   or len(path.split('/')) > 12
                   or not re.fullmatch(r'(?:/(?:[^/~]|~[01])+)+', path)
                   for path in value['higher_is_better'])
            or len(set(value['higher_is_better'])) != len(value['higher_is_better'])
            or not isinstance(value['verification'], str) or not value['verification'].strip()
            or len(value['verification']) > 1000):
        raise LocalScoreError('INVALID_SCORER', '评分器单调比较指标声明无效')
    return value


def scorer_manifest(challenge_id: str) -> dict[str, Any]:
    if not db.query_one('SELECT 1 FROM challenges WHERE id=?', (challenge_id,)):
        raise LocalScoreError('NOT_FOUND', '题目不存在')
    # Project-owned scorers are reviewable source; keep the original workspace
    # location for user-authored scorers and existing Runs.
    base = None
    for challenges_root in (config.WORKSPACE_ROOT / 'challenges',
                            config.WORKSPACE_DIR / 'challenges'):
        challenges_root = challenges_root.resolve()
        challenge_root = (challenges_root / challenge_id).resolve()
        candidate = (challenge_root / 'scorer').resolve()
        if (challenges_root in challenge_root.parents
                and challenge_root in candidate.parents and candidate.is_dir()):
            base = candidate
            break
    if base is None:
        raise LocalScoreError('SCORER_MISSING', '题目缺少 scorer/ 目录')
    files: dict[str, bytes] = {}
    total = 0
    for path in sorted(base.rglob('*')):
        if path.is_symlink():
            raise LocalScoreError('INVALID_SCORER', '评分器含符号链接')
        if path.is_dir():
            continue
        # Python's generated bytecode is local build state, not scorer source.
        # Including it would change scorer_version across machines and runs.
        if '__pycache__' in path.relative_to(base).parts or path.suffix in ('.pyc', '.pyo'):
            continue
        if not path.is_file() or base not in path.resolve().parents:
            raise LocalScoreError('INVALID_SCORER', '评分器含符号链接或越界文件')
        relative = path.relative_to(base).as_posix()
        if len(files) >= 100:
            raise LocalScoreError('INVALID_SCORER', '评分器文件超过 100 个')
        size = path.stat().st_size
        total += size
        if total > 10_000_000:
            raise LocalScoreError('INVALID_SCORER', '评分器文件总量超过 10 MB')
        files[relative] = path.read_bytes()
    try:
        manifest = json.loads(files['scorer.json'])
    except (KeyError, ValueError, UnicodeDecodeError) as exc:
        raise LocalScoreError('INVALID_SCORER', 'scorer.json 缺失或无法解析') from exc
    required = {'entrypoint', 'image', 'version', 'contract_version'}
    if (not isinstance(manifest, dict) or not required <= set(manifest)
            or not set(manifest) <= required | {'input_contract', 'runtime', 'comparison_contract'}):
        raise LocalScoreError('INVALID_SCORER', 'scorer.json 字段必须为 entrypoint/image/version/contract_version')
    entry, image = manifest['entrypoint'], manifest['image']
    if (not isinstance(entry, str) or not _ENTRYPOINT.fullmatch(entry)
            or entry not in files or not isinstance(image, str) or not image.strip()
            or not isinstance(manifest['version'], str) or not manifest['version'].strip()
            or len(manifest['version']) > 80
            or type(manifest['contract_version']) is not int or manifest['contract_version'] != 1):
        raise LocalScoreError('INVALID_SCORER', '评分器入口、镜像或契约版本无效')
    contract = manifest.get('input_contract')
    if contract is not None:
        if (not isinstance(contract, dict)
                or set(contract) != {'artifact_paths', 'required', 'verification'}
                or not isinstance(contract['artifact_paths'], list)
                or not 1 <= len(contract['artifact_paths']) <= 40
                or any(not isinstance(path, str) or not path or path.startswith('/')
                       or '\\' in path or '..' in Path(path).parts
                       for path in contract['artifact_paths'])
                or len(set(contract['artifact_paths'])) != len(contract['artifact_paths'])
                or type(contract['required']) is not bool
                or not isinstance(contract['verification'], str) or not contract['verification']):
            raise LocalScoreError('INVALID_SCORER', '评分器输入路径声明无效')
    runtime = validate_runtime(manifest.get('runtime', {}))
    comparison = validate_comparison(manifest.get('comparison_contract'))
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    if runtime.get('environment_id'):
        from . import runtime_environments
        try:
            environment = runtime_environments.recipe(runtime['environment_id'])
            hashes['@environment_recipe'] = environment['recipe_sha256']
            hashes['@environment_dockerfile'] = environment['dockerfile_sha256']
            image = runtime_environments.resolve(runtime['environment_id'])['image']
        except runtime_environments.EnvironmentUnavailable:
            pass
    version = hashlib.sha256(_canonical(hashes).encode()).hexdigest()
    return {'entrypoint': entry, 'image': image, 'version': manifest['version'], 'contract_version': 1,
            'scorer_version': version, 'file_hashes': hashes, 'files': files, 'runtime': runtime,
            **({'comparison_contract': comparison} if comparison else {}),
            **({'input_contract': contract} if contract is not None else {})}


def predict_trace(sealed: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    selected = trace_selection.select(files)
    if not selected.readable:
        raise LocalScoreError('INVALID_TRACE', '封存包轨迹不可读')
    rows = selected.rows
    counts = {kind: sum(row.get('step_type') == kind for row in rows)
              for kind in ('thought', 'decision', 'tool_call', 'tool_result',
                           'observation', 'error', 'artifact')}
    anchors = sum(bool(row.get('cs_ref') or row.get('cs_refs')) for row in rows)
    features = {'steps': len(rows), 'type_counts': counts,
                'narrative_chars': sum(len(str(row.get(field) or ''))
                                       for row in rows for field in ('title', 'body', 'code')),
                'tool_output_steps': sum(bool(row.get('tool_output')) for row in rows),
                'artifact_steps': counts['artifact'],
                'error_repair_pairs': sum(
                    row.get('step_type') == 'error' and
                    any(later.get('step_type') in ('decision', 'tool_call', 'observation')
                        for later in rows[index + 1:])
                    for index, row in enumerate(rows)),
                'anchored_fraction': anchors / len(rows) if rows else 0.0}
    # W2 has no controlled scores yet. The baseline is deliberately low-confidence.
    score = 70.0
    return {'trace_score': score, 'at_least_70': score >= 70,
            'at_least_80': score >= 80, 'confidence': 'low',
            'feature_version': FEATURE_VERSION, 'model_version': MODEL_VERSION,
            'features': features, 'notes': '占位预测；待受控提交校准'}


def _score_output(receipt: dict[str, Any], version: str) -> dict[str, Any]:
    try:
        wrapper = json.loads(receipt['receipt']['stdout'])
        data = wrapper.get('data', wrapper)
        output = json.loads(data['stdout'])
    except (AttributeError, KeyError, ValueError, TypeError) as exc:
        raise LocalScoreError('INVALID_SCORE_OUTPUT', '沙箱未返回单个有效评分 JSON') from exc
    try:
        serialized = json.dumps(output, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LocalScoreError('INVALID_SCORE_OUTPUT', '评分 JSON 含非有限数或不可序列化字段') from exc
    if not isinstance(output, dict) or set(output) != {
            'score', 'components', 'confidence', 'notes', 'scorer_version'}:
        raise LocalScoreError('INVALID_SCORE_OUTPUT', '评分结果字段不符合固定契约')
    score = output['score']
    if (type(score) not in (int, float) or not math.isfinite(score)
            or not 0 <= score <= 100 or not isinstance(output['components'], dict)
            or output['confidence'] not in ('high', 'medium', 'low', 'unknown')
            or not isinstance(output['notes'], str) or len(output['notes']) > 4000
            or len(serialized) > 12000
            or strip_secrets(serialized) != serialized
            or output['scorer_version'] != version):
        raise LocalScoreError('INVALID_SCORE_OUTPUT', '评分值、置信度、备注或版本不符合契约')
    return output


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[name])
    return buffer.getvalue()


def _manifest_science_sha(sealed: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
        names = archive.namelist()
        root = trace_selection.bundle_root({name: b'' for name in names})
        manifest = json.loads(archive.read(root + 'arm_manifest.json'))
    if not isinstance(manifest, dict):
        raise LocalScoreError('INVALID_PACKAGE', 'ARM manifest 不是对象')
    manifest.pop('trace', None)
    return hashlib.sha256(_canonical(manifest).encode()).hexdigest()


def _science_package(sealed: bytes) -> bytes:
    """Give the science scorer no trace bytes, so later trace-only reuse is sound."""
    with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise LocalScoreError('INVALID_PACKAGE', 'ARM 包有同名 ZIP 成员')
        if any(name.startswith('/') or '\\' in name or '..' in Path(name).parts for name in names):
            raise LocalScoreError('INVALID_PACKAGE', 'ARM 包成员路径越界')
        root = trace_selection.bundle_root({name: b'' for name in names})
        manifest_name = root + 'arm_manifest.json'
        manifest = json.loads(archive.read(manifest_name))
        if not isinstance(manifest, dict):
            raise LocalScoreError('INVALID_PACKAGE', 'ARM manifest 不是对象')
        manifest.pop('trace', None)
        files = {name: archive.read(name) for name in names
                 if not name.endswith('/') and name != manifest_name
                 and not name.startswith(root + 'traces/')
                 and not name.startswith(root + 'trace/')
                 and name != root + 'trace.json'}
        files[manifest_name] = _canonical(manifest).encode()
    return _archive(files)


def component_scores(science: dict[str, Any], comparison: dict | None = None) -> dict[str, float]:
    """Named higher-is-better score fields, excluding unrelated diagnostics.

    Nested objects use explicit score/points fields or *_score names.
    Other numeric fields require an explicit monotone-input declaration;
    their original values are preserved, never converted into formal points.
    """
    result = {'/score': float(science['score'])}

    def visit(value, path, named=False):
        if type(value) in (int, float) and math.isfinite(value) and named:
            result[path] = float(value)
        elif isinstance(value, dict):
            for key, item in value.items():
                part = str(key).replace('~', '~0').replace('/', '~1')
                visit(item, path + '/' + part,
                      named or key in ('score', 'points') or key.endswith('_score'))
    visit(science.get('components', {}), '/components')
    def selected(value, parts, path):
        if not parts:
            if type(value) in (int, float) and math.isfinite(value):
                result[path] = float(value)
            return
        token = parts[0].replace('~1', '/').replace('~0', '~')
        children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
        for key, item in children:
            if token == '*' or str(key) == token:
                escaped = str(key).replace('~', '~0').replace('/', '~1')
                selected(item, parts[1:], path + '/' + escaped)
    for pointer in validate_comparison(comparison).get('higher_is_better', []):
        selected(science, pointer.split('/')[1:], '')
    return result


def _registered_components(row: dict) -> dict[str, float]:
    # The registration freezes the reviewed contract beside the exact score
    # identity, so a later scorer edit cannot reinterpret earlier candidates.
    event = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='local_score.registered'"
                         " AND json_extract(payload,'$.local_score_id')=? ORDER BY seq DESC LIMIT 1",
                         (row['run_id'], row['id']))
    data = json.loads(event['payload']) if event else {}
    bound = (data.get('scorer_version') == row['scorer_version']
             and data.get('science_input_sha256') == row['science_input_sha256'])
    return component_scores(json.loads(row['science_result_json']),
                            data.get('comparison_contract') if bound else None)


def reuse_score(run_id: str, trial_id: str, operation_id: str, sealed: bytes,
                manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Reuse only exact deterministic scorer inputs within this Run."""
    digest = hashlib.sha256(_science_package(sealed)).hexdigest()
    source = db.query_one('SELECT * FROM local_scores WHERE run_id=?'
                          ' AND science_input_sha256=? AND scorer_version=?'
                          ' AND science_score IS NOT NULL ORDER BY created_at,id LIMIT 1',
                          (run_id, digest, manifest['scorer_version']))
    if not source:
        return None
    return _record_score(manifest.get('challenge_id') or source['challenge_id'],
                         run_id, trial_id, operation_id, sealed, manifest,
                         json.loads(source['science_result_json']),
                         source_local_score_id=source['id'])


def final_package_check(run_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare the full candidate against every registered per-component best."""
    current = _registered_components(candidate)
    best = {}
    for row in db.query('SELECT * FROM local_scores WHERE run_id=? AND scorer_version=?'
                         ' AND science_score IS NOT NULL ORDER BY created_at,id',
                         (run_id, candidate['scorer_version'])):
        for component, score in _registered_components(row).items():
            if component not in best or score > best[component]['best_score']:
                best[component] = {'component': component, 'best_score': score,
                    'candidate_local_score_id': row['id'],
                    'candidate_package_sha256': row['package_sha256'],
                    'candidate_artifact_hashes': json.loads(row['science_artifact_hashes_json'])}
    regressions = [value | {'current_score': current.get(component)}
                   for component, value in sorted(best.items())
                   if component not in current or current[component] < value['best_score']]
    facts = {'run_id': run_id, 'local_score_id': candidate['id'],
             'science_input_sha256': candidate['science_input_sha256'],
             'scorer_version': candidate['scorer_version'], 'regressions': regressions}
    # Trace-only reseals and duplicate score rows cannot invalidate confirmation;
    # changes to science, scorer or registered best scores do invalidate it.
    binding = {key: facts[key] for key in ('run_id', 'science_input_sha256', 'scorer_version')}
    binding['best'] = {key: value['best_score'] for key, value in sorted(best.items())}
    facts['confirmation_token'] = hashlib.sha256(_canonical(binding).encode()).hexdigest()
    return facts


def latest_final_check(run_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT payload FROM events WHERE run_id=?"
                        " AND type='brain.action_rejected'"
                        " AND json_type(payload,'$.final_package_check')='object'"
                        " ORDER BY seq DESC LIMIT 1", (run_id,))
    return {'final_package_check': json.loads(row['payload'])['final_package_check']} if row else {}


def score_candidate(run_id: str) -> dict[str, Any]:
    run = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    if not run or run['phase'] != 'running' or run['gate'] != 'open' or not run['current_trial_id']:
        raise LocalScoreError('RUN_NOT_RUNNING', '最终包评分需要正在运行的 Trial')
    manifest = scorer_manifest(run['challenge_id'])
    check = mailboxes.preflight_submission(run_id, run['current_trial_id'], None,
                                          allow_proxy_evidence=bool(db.eval_mode(run_id)))
    # Local evaluation measures science even if trace admission is blocked.
    if db.eval_mode(run_id) and check['error_code'] in (
            'TRACE_ADMISSION_BLOCKED', 'TRACE_ADMISSION_INDETERMINATE', 'PROXY_EVIDENCE'):
        check = check | {'error_code': None}
    if check['error_code']:
        raise LocalScoreError(check['error_code'], '最终包未通过本地预检')
    digest = hashlib.sha256(check['sealed_bytes'] +
                            manifest['scorer_version'].encode()).hexdigest()
    from . import evaluations
    row = evaluations.score_preflight(run, check, 'finish-score-' + digest[:30],
                                     'finish-scorer-' + digest[:30])
    current = db.query_one('SELECT phase,gate,current_trial_id FROM runs WHERE id=?', (run_id,))
    if (not current or current['phase'] != 'running' or current['gate'] != 'open'
            or current['current_trial_id'] != run['current_trial_id']):
        raise LocalScoreError('FINAL_PACKAGE_STATE_CHANGED', '最终包评分期间 Run/Trial 已变化')
    # Freeze the exact prospective candidate, including unchanged user artifacts.
    folder = config.WORKSPACE_DIR / 'runs' / run_id / 'final_candidate'
    if folder.is_symlink():
        raise LocalScoreError('INVALID_PACKAGE', '最终包路径含符号链接')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'sealed_package.zip'
    if path.is_symlink():
        raise LocalScoreError('INVALID_PACKAGE', '最终包路径含符号链接')
    path.write_bytes(check['sealed_bytes'])
    return row


def _record_score(challenge_id: str, run_id: str, trial_id: str, operation_id: str, sealed: bytes,
                  manifest: dict[str, Any], science: dict[str, Any],
                  *, source_local_score_id: str | None = None) -> dict[str, Any]:
    """Persist a verified sandbox score with its exact science and trace inputs."""
    science_hashes = mailboxes._science_artifact_hashes(sealed)
    manifest_science_sha = _manifest_science_sha(sealed)
    science_input_sha = hashlib.sha256(_science_package(sealed)).hexdigest()
    trace = predict_trace(sealed)
    predicted = science['score'] * max(0.0, min(1.0, (trace['trace_score'] - 30.0) / 40.0))
    package_sha = hashlib.sha256(sealed).hexdigest()
    score_id = 'ls_' + uuid.uuid4().hex[:12]
    comparison = validate_comparison(manifest.get('comparison_contract')) or None
    components = component_scores(science, comparison)
    with db.transaction() as conn:
        prior = conn.execute('SELECT * FROM local_scores WHERE sandbox_operation_id=?',
                             (operation_id,)).fetchone()
        if prior:
            if (prior['run_id'] != run_id or prior['trial_id'] != trial_id
                    or prior['package_sha256'] != package_sha
                    or prior['scorer_version'] != manifest['scorer_version']):
                raise LocalScoreError('OPERATION_CONFLICT', '评分操作 ID 已绑定不同输入')
            return dict(prior) | {'deduplicated': True}
        conn.execute('INSERT INTO local_scores(id,challenge_id,run_id,trial_id,package_sha256,'
                     'science_artifact_hashes_json,manifest_science_sha256,science_score,science_result_json,'
                     'trace_prediction_json,predicted_display_score,scorer_version,scorer_file_hashes_json,'
                     'feature_version,model_version,sandbox_operation_id,created_at,science_input_sha256,source_local_score_id)'
                     ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (score_id,challenge_id,run_id,trial_id,package_sha,
                      _canonical(science_hashes),manifest_science_sha,science['score'],_canonical(science),
                      _canonical(trace),predicted,manifest['scorer_version'],
                      _canonical(manifest['file_hashes']),FEATURE_VERSION,MODEL_VERSION,operation_id,db.utcnow(),
                      science_input_sha,source_local_score_id))
        db.append_event_tx(conn, run_id, 'controller', 'local_score.registered',
                    {'local_score_id': score_id, 'scorer_version': manifest['scorer_version'],
                     'science_input_sha256': science_input_sha,
                     'components': components,
                     'comparison_contract': comparison,
                     'artifact_hashes': science_hashes,
                     'source_local_score_id': source_local_score_id}, trial_id=trial_id)
    return dict(db.query_one('SELECT * FROM local_scores WHERE id=?', (score_id,)))


def evaluate(run_id: str, trial_id: str, sandbox_id: str,
             operation_id: str, package_path: str | None = None,
             *, preflight: dict[str, Any] | None = None,
             public_resource_zip: Path | None = None,
             score_timeout: int = 120,
             _controller_preflight: bool = False) -> dict[str, Any]:
    if not isinstance(operation_id, str) or not _OPERATION.fullmatch(operation_id):
        raise LocalScoreError('INVALID_OPERATION', '需要有界的稳定评分 operation_id')
    existing = db.query_one('SELECT * FROM local_scores WHERE sandbox_operation_id=?', (operation_id,))
    if existing:
        if existing['run_id'] != run_id or existing['trial_id'] != trial_id:
            raise LocalScoreError('OPERATION_CONFLICT', '评分 operation_id 已绑定其他 Run/Trial')
        return dict(existing) | {'deduplicated': True}
    run = db.query_one('SELECT challenge_id,current_trial_id,phase,gate FROM runs WHERE id=?', (run_id,))
    eval_retry = False
    if (run and run['phase'] == 'finished' and db.eval_mode(run_id)
            and operation_id.startswith('eval-score-') and operation_id.endswith('-retry')):
        from . import evaluations
        eval_retry = evaluations.retry_authorized(
            run_id, operation_id[len('eval-score-'):-len('-retry')])
    if not run or run['current_trial_id'] != trial_id or (run['phase'] not in ('running', 'eval_scoring') and not eval_retry) or run['gate'] != 'open':
        raise LocalScoreError('RUN_NOT_RUNNING', '本地评分需要当前运行中的 Trial')
    manifest = scorer_manifest(run['challenge_id'])
    sandbox = db.query_one('SELECT * FROM compute_sandboxes WHERE run_id=? AND sandbox_id=?',
                           (run_id, sandbox_id))
    if sandbox and json.loads(sandbox['request_json']).get('image') != manifest['image']:
        raise LocalScoreError('SCORER_IMAGE_MISMATCH', '评分沙箱镜像与声明不符')
    if preflight is not None and not db.eval_mode(run_id) and not _controller_preflight:
        raise LocalScoreError('INVALID_ARGUMENT', '冻结预检仅供评测或控制器使用')
    check = preflight if preflight is not None else mailboxes.preflight_submission(
        run_id, trial_id, package_path, allow_proxy_evidence=bool(db.eval_mode(run_id)))
    if db.eval_mode(run_id) and check['error_code'] in (
            'TRACE_ADMISSION_BLOCKED', 'TRACE_ADMISSION_INDETERMINATE', 'PROXY_EVIDENCE'):
        check = check | {'error_code': None}
    if check['error_code']:
        raise LocalScoreError(check['error_code'], '封存包未通过本地准入')
    sealed = check['sealed_bytes']
    reused = reuse_score(run_id, trial_id, operation_id, sealed, manifest)
    if reused:
        return reused
    sandbox = db.query_one('SELECT * FROM compute_sandboxes WHERE run_id=? AND sandbox_id=?',
                           (run_id, sandbox_id))
    if (not sandbox or sandbox['trial_id'] != trial_id or sandbox['status'] != 'active'
            or json.loads(sandbox['request_json']).get('image') != manifest['image']):
        raise LocalScoreError('SCORER_IMAGE_MISMATCH', '需要当前 Trial 在评分器声明镜像中的活跃沙箱')
    trial_dir = config.WORKSPACE_DIR / 'runs' / run_id / 'trials' / trial_id
    stage = trial_dir / 'local_scorer' / operation_id
    stage.mkdir(parents=True, exist_ok=True)
    package_file, scorer_file = stage / 'science_package.zip', stage / 'scorer.zip'
    scorer_bytes = _archive(manifest['files'])
    for path, raw in ((package_file, _science_package(sealed)), (scorer_file, scorer_bytes)):
        if path.exists() and path.read_bytes() != raw:
            raise LocalScoreError('OPERATION_CONFLICT', '评分操作 ID 对应的本地输入已变化')
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(raw)
    workspace = ('/bohr-workspace' if json.loads(sandbox['request_json']).get('session_id') == run_id
                 else '/tmp')
    remote = f'{workspace}/cs-local-scorer-{operation_id}'
    commands = [
        ('mkdir', lambda: sandboxes.execute(run_id, sandbox_id,
            'mkdir -p ' + shlex.quote(remote),
            sandboxes.bounded_execution_timeout(run_id, sandbox_id, 30), operation_id + '-mkdir')),
        ('scorer', lambda: sandboxes.transfer(run_id, 'write', sandbox_id,
            remote + '/scorer.zip', local_path=str(scorer_file),
            operation_id=operation_id + '-scorer')),
        ('package', lambda: sandboxes.transfer(run_id, 'write', sandbox_id,
            remote + '/package.zip', local_path=str(package_file),
            operation_id=operation_id + '-package')),
    ]
    for name, action in commands:
        result = action()
        if result['status'] != 'completed':
            raise LocalScoreError('SCORE_EXECUTION_UNKNOWN', f'沙箱 {name} 阶段未确认完成')
    resource_env = ''
    runtime = manifest.get('runtime', {})
    if runtime.get('adapter') == 'lean_project':
        from . import lean_runtime
        resource_env = lean_runtime.prepare(run_id, sandbox_id, stage, operation_id,
                                            environment_id=runtime['environment_id'], project=runtime['project'])
    if public_resource_zip is not None:
        if not db.eval_mode(run_id) and not _controller_preflight:
            raise LocalScoreError('INVALID_ARGUMENT', '公开评分数据仅供受控评分使用')
        staged_resource = stage / 'public_resource.zip'
        resource = public_resource_zip.read_bytes()
        if staged_resource.exists() and staged_resource.read_bytes() != resource:
            raise LocalScoreError('OPERATION_CONFLICT', '公开资源与已冻结版本不一致')
        if not staged_resource.exists():
            staged_resource.write_bytes(resource)
        transferred = sandboxes.transfer(run_id, 'write', sandbox_id,
            remote + '/public_resource.zip', local_path=str(staged_resource),
            operation_id=operation_id + '-resource')
        if transferred['status'] != 'completed':
            raise LocalScoreError('SCORE_EXECUTION_UNKNOWN', '公开资源传输未确认完成')
        unpacked = sandboxes.execute(run_id, sandbox_id,
            'cd ' + shlex.quote(remote) + ' && python3 -m zipfile -e public_resource.zip public',
            sandboxes.bounded_execution_timeout(run_id, sandbox_id, 120), operation_id + '-unpack')
        if unpacked['status'] != 'completed':
            raise LocalScoreError('SCORE_EXECUTION_UNKNOWN', '公开资源解压未确认完成')
        declared = runtime.get('public_resource')
        if declared:
            if hashlib.sha256(resource).hexdigest() != declared['sha256']:
                raise LocalScoreError('PUBLIC_RESOURCE_MISMATCH', '公开评分资源哈希不符')
            resource_env += declared['environment_variable'] + '=' + shlex.quote(
                remote + '/' + declared['directory']) + ' '
    dependency_command = ''
    if public_resource_zip is not None and 'requirements.txt' in manifest['files']:
        dependency_command = (' && python3 -m pip install --disable-pip-version-check'
                              ' --no-input --no-cache-dir -r scorer/requirements.txt 1>&2')
    command = ('cd ' + shlex.quote(remote) + ' && python3 -m zipfile -e scorer.zip scorer'
               + dependency_command
               + ' && ' + resource_env + 'CS_SCORER_VERSION=' + shlex.quote(manifest['scorer_version'])
               + ' python3 ' + shlex.quote('scorer/' + manifest['entrypoint']) + ' package.zip')
    result = sandboxes.execute(run_id, sandbox_id, command,
        sandboxes.bounded_execution_timeout(run_id, sandbox_id, score_timeout), operation_id + '-run')
    if result['status'] != 'completed':
        raise LocalScoreError('SCORE_EXECUTION_UNKNOWN', '沙箱评分执行未确认成功')
    science = _score_output(result, manifest['scorer_version'])
    return _record_score(run['challenge_id'], run_id, trial_id, operation_id,
                         sealed, manifest, science)


def bind_submission_tx(conn, submission_id: str, sealed: bytes) -> str | None:
    """Reuse a sandbox science result only when its exact science inputs match."""
    submission = conn.execute('SELECT * FROM submissions WHERE id=?', (submission_id,)).fetchone()
    if not submission or submission['is_harvest']:
        return None
    match = conn.execute('SELECT * FROM local_scores WHERE run_id=? AND trial_id=?'
                         ' AND package_sha256=? ORDER BY created_at DESC,id DESC LIMIT 1',
                         (submission['run_id'],submission['trial_id'],submission['package_sha256'])).fetchone()
    if match:
        return match['id']
    if not sealed.startswith(b'PK\x03\x04') or not conn.execute(
            'SELECT 1 FROM local_scores WHERE run_id=? AND trial_id=? LIMIT 1',
            (submission['run_id'],submission['trial_id'])).fetchone():
        return None
    science_hashes = _canonical(mailboxes._science_artifact_hashes(sealed))
    manifest_hash = _manifest_science_sha(sealed)
    reference = _SCORE_REF.search(submission['prediction_md'] or '')
    if reference:
        source = conn.execute('SELECT * FROM local_scores WHERE id=? AND run_id=? AND trial_id=?',
                              (reference.group(1),submission['run_id'],submission['trial_id'])).fetchone()
    else:
        source = conn.execute('SELECT * FROM local_scores WHERE run_id=? AND trial_id=?'
                              ' AND science_artifact_hashes_json=? AND manifest_science_sha256=?'
                              ' AND science_score IS NOT NULL ORDER BY created_at DESC,id DESC LIMIT 1',
                              (submission['run_id'],submission['trial_id'],science_hashes,manifest_hash)).fetchone()
    if (not source or source['science_artifact_hashes_json'] != science_hashes
            or source['manifest_science_sha256'] != manifest_hash
            or source['science_score'] is None):
        return None
    trace = predict_trace(sealed)
    predicted = source['science_score'] * max(0.0, min(1.0,
        (trace['trace_score'] - 30.0) / 40.0))
    score_id = 'ls_' + uuid.uuid4().hex[:12]
    conn.execute('INSERT INTO local_scores(id,challenge_id,run_id,trial_id,package_sha256,'
                 'science_artifact_hashes_json,manifest_science_sha256,source_local_score_id,'
                 'science_score,science_result_json,trace_prediction_json,predicted_display_score,'
                 'scorer_version,scorer_file_hashes_json,feature_version,model_version,created_at)'
                 ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (score_id,source['challenge_id'],source['run_id'],source['trial_id'],
                  submission['package_sha256'],science_hashes,manifest_hash,source['id'],
                  source['science_score'],source['science_result_json'],_canonical(trace),predicted,
                  source['scorer_version'],source['scorer_file_hashes_json'],
                  FEATURE_VERSION,MODEL_VERSION,db.utcnow()))
    return score_id


def calibrate_tx(conn, submission_id: str, *, source: str = 'realtime') -> None:
    if source not in ('realtime', 'historical'):
        raise ValueError('unknown calibration source')
    submission = conn.execute('SELECT s.*,r.challenge_id FROM submissions s JOIN runs r'
                              ' ON r.id=s.run_id WHERE s.id=?', (submission_id,)).fetchone()
    if not submission:
        return
    if submission['score_confidence'] != 'confirmed' or submission['score_status'] != 'scored':
        conn.execute('UPDATE score_calibration SET valid=0 WHERE submission_id=?', (submission_id,))
        return
    reference = _SCORE_REF.search(submission['prediction_md'] or '')
    if reference:
        local = conn.execute('SELECT * FROM local_scores WHERE id=? AND run_id=? AND trial_id=?'
                             ' AND package_sha256=?',
                             (reference.group(1),submission['run_id'],submission['trial_id'],
                              submission['package_sha256'])).fetchone()
        if not local:
            local = conn.execute('SELECT * FROM local_scores WHERE source_local_score_id=?'
                                 ' AND run_id=? AND trial_id=? AND package_sha256=?'
                                 ' ORDER BY created_at DESC,id DESC LIMIT 1',
                                 (reference.group(1),submission['run_id'],submission['trial_id'],
                                  submission['package_sha256'])).fetchone()
    else:
        local = conn.execute('SELECT * FROM local_scores WHERE challenge_id=? AND package_sha256=?'
                             ' ORDER BY created_at DESC,id DESC LIMIT 1',
                             (submission['challenge_id'],submission['package_sha256'])).fetchone()
    if not local:
        return
    trace = json.loads(local['trace_prediction_json'])['trace_score']
    predicted = local['predicted_display_score']
    actual = submission['score']
    harbor = submission['harbor_score']
    actual_trace = submission['trace_score']
    conn.execute('INSERT INTO score_calibration(submission_id,local_score_id,source,package_sha256,'
                 'predicted_display_score,platform_display_score,display_delta,'
                 'predicted_science_score,platform_science_score,science_delta,'
                 'predicted_trace_score,platform_trace_score,trace_delta,valid,confirmed_at)'
                 ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)'
                 ' ON CONFLICT(submission_id) DO UPDATE SET local_score_id=excluded.local_score_id,'
                 'source=excluded.source,'
                 'package_sha256=excluded.package_sha256,predicted_display_score=excluded.predicted_display_score,'
                 'platform_display_score=excluded.platform_display_score,display_delta=excluded.display_delta,'
                 'predicted_science_score=excluded.predicted_science_score,'
                 'platform_science_score=excluded.platform_science_score,science_delta=excluded.science_delta,'
                 'predicted_trace_score=excluded.predicted_trace_score,'
                 'platform_trace_score=excluded.platform_trace_score,trace_delta=excluded.trace_delta,'
                 'valid=1,confirmed_at=excluded.confirmed_at',
                 (submission_id,local['id'],source,submission['package_sha256'],predicted,actual,
                  predicted-actual if predicted is not None and actual is not None else None,
                  local['science_score'],harbor,
                  local['science_score']-harbor if harbor is not None else None,
                  trace,actual_trace,trace-actual_trace if actual_trace is not None else None,
                  db.utcnow()))


def list_challenge(challenge_id: str) -> dict[str, Any]:
    manifest = None
    try:
        descriptor = scorer_manifest(challenge_id)
        manifest = {key: descriptor[key] for key in ('entrypoint', 'image', 'version', 'contract_version',
                                                     'scorer_version', 'file_hashes')}
    except LocalScoreError as exc:
        if exc.code != 'SCORER_MISSING':
            raise
    scores = [dict(row) for row in db.query('SELECT * FROM local_scores WHERE challenge_id=?'
                                            ' ORDER BY created_at DESC', (challenge_id,))]
    calibrations = [dict(row) for row in db.query(
        'SELECT c.* FROM score_calibration c JOIN local_scores l ON l.id=c.local_score_id'
        ' WHERE l.challenge_id=? ORDER BY c.confirmed_at DESC', (challenge_id,))]
    return {'scorer': manifest, 'local_scores': scores, 'calibrations': calibrations}
