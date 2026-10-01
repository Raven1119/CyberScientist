"""Persistent, submission-free evaluation of ordinary connected Runs.

The database is the queue. A restart can reclaim pending work without replaying
completed Runs or an in-flight platform operation.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import statistics
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from . import compute, config, db, experience_context, local_scoring, mailboxes, sandboxes, skills

CATALOG = Path(__file__).resolve().parents[2] / 'evals' / 'catalog.json'
PUBLIC_SNAPSHOTS = CATALOG.parent / 'public_challenges'
LOW_CAP_MAX = 29
MID_CAP_MAX = 69
UNCAPPED_LOWER_FACTOR = .30
TERMINAL = {'finished', 'failed', 'cancelled'}
MATCHGATE_ID = 'flowforge-matchgate-swap-inverse-synthesis-v2-4019e745'
MATCHGATE_RESOURCE_SHA256 = '3ed0a9a79f63504b8a6d7c84022dee9bc458aaf15bc23096d4e60b5c3f316e74'
FIGQA_IDS = frozenset((
    'lab-bench-figqa-figqa-0177-b4156bee',
    'lab-bench-figqa-figqa-0178-23afc746',
))


class EvaluationError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def catalog(suite: str) -> list[dict[str, Any]]:
    if suite not in ('fast', 'hard'):
        raise EvaluationError('suite 必须是 fast 或 hard')
    entries = json.loads(CATALOG.read_text())['challenges']
    return [item for item in entries if item['tier'] == suite and item['included']
            and item['science_scorer']['status'] != 'unavailable']


def display_interval(science_score: float | None, qualified_cap: int | None) -> dict[str, Any]:
    """Advisory interval, never an assertion about hidden judge behavior."""
    if science_score is None:
        return {'lower': None, 'upper': None, 'basis': 'science_unknown'}
    if qualified_cap is not None and qualified_cap <= LOW_CAP_MAX:
        return {'lower': 0.0, 'upper': 0.0, 'basis': 'qualified_cap_le_29'}
    if qualified_cap is not None and qualified_cap <= MID_CAP_MAX:
        return {'lower': 0.0, 'upper': round(science_score * qualified_cap / 100, 4),
                'basis': 'qualified_cap_30_69'}
    return {'lower': round(science_score * UNCAPPED_LOWER_FACTOR, 4),
            'upper': science_score, 'basis': '裁判部分未复刻'}


def _historical_public_snapshot(slug: str) -> dict[str, Any]:
    manifest = json.loads((PUBLIC_SNAPSHOTS / 'manifest.json').read_text())
    expected = manifest['files'].get(slug)
    if not expected:
        raise EvaluationError(f'当前公开题面不可取回，且缺少固定历史快照: {slug}')
    path = PUBLIC_SNAPSHOTS / (slug + '.json')
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected['file_sha256']:
        raise EvaluationError(f'固定历史题面快照哈希不符: {slug}')
    data = json.loads(path.read_text())
    if (data.get('id') != slug or not isinstance(data.get('content'), str)
            or hashlib.sha256(data['content'].encode()).hexdigest() != expected['content_sha256']):
        raise EvaluationError(f'固定历史题面内容不符: {slug}')
    return data


def _ensure_challenge(item: dict[str, Any]) -> None:
    """Import the public challenge with the same stored fields as the URL flow."""
    cid = item['challenge_id']
    existing = db.query_one('SELECT platform_challenge_id FROM challenges WHERE id=?', (cid,))
    if existing:
        if existing['platform_challenge_id'] != item['platform_challenge_id']:
            raise EvaluationError(f'题目 {cid} 的平台标识与目录不一致')
        return
    from . import datasets, mailbox_platform
    settings = config.load_settings()
    pg = settings['playground']
    token = config.resolve_secret(pg.get('token_secret_ref') or '')
    try:
        data = mailbox_platform.fetch_platform_challenge(
            pg.get('base_url') or 'https://play.bohrium.com/api',
            item['platform_challenge_id'], token)
        source = 'current_public_get'
    except mailbox_platform.PlatformError:
        data = _historical_public_snapshot(item['platform_challenge_id'])
        source = 'pinned_historical_public_snapshot'
    content = (data.get('content') or '').strip()
    if not content:
        raise EvaluationError(f"公开题面为空: {item['platform_challenge_id']}")
    resources = data.get('resources')
    platform_snapshot = {key: data.get(key) for key in
                         ('status', 'roundStartAt', 'roundEndAt', 'scoring')}
    provenance = data.get('snapshot_provenance') if isinstance(data.get('snapshot_provenance'), dict) else {}
    platform_snapshot['fetched_at'] = provenance.get('captured_at') if provenance else db.utcnow()
    platform_snapshot['source_kind'] = source
    if provenance:
        platform_snapshot['source_sha256'] = provenance.get('source_sha256')
    with db.transaction() as conn:
        conn.execute('INSERT OR IGNORE INTO challenges(id,platform_challenge_id,origin,title,'
                     'content,content_hash,contract_status,imported_at,is_demo,resources_json,'
                     'platform_snapshot_json) VALUES(?,?,?,?,?, ?,\'unknown\',?,0,?,?)',
                     (cid, item['platform_challenge_id'],
                      ('https://play.bohrium.com/challenges/' if source == 'current_public_get'
                       else 'pinned-public-snapshot://') + item['platform_challenge_id'],
                      (data.get('title_zh') or data.get('title') or item['title']).strip(),
                      content, hashlib.sha256(content.encode()).hexdigest(), db.utcnow(),
                      json.dumps(resources, ensure_ascii=False) if isinstance(resources, list) else None,
                      json.dumps(platform_snapshot, ensure_ascii=False)))
    if isinstance(resources, list):
        datasets.register_resources(cid, resources)


def create_evaluation(suite: str, repeats: int = 2, label: str = '') -> dict[str, Any]:
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise EvaluationError('repeats 必须是 1–10 的整数')
    if not isinstance(label, str) or len(label) > 120:
        raise EvaluationError('label 最多 120 字符')
    prior = db.query_one("SELECT id,repeats FROM eval_runs WHERE suite=? AND label=? AND status='running'",
                         (suite, label))
    if prior:
        if prior['repeats'] != repeats:
            raise EvaluationError('同层同标签评测正在运行；请使用另一个 label')
        return get_evaluation(prior['id'])
    entries = catalog(suite)
    if not entries:
        raise EvaluationError('该层没有可运行题目')
    for item in entries:
        _ensure_challenge(item)
    settings = config.load_settings()
    frozen = {}
    for item in entries:
        cid = item['challenge_id']
        challenge = db.query_one('SELECT content_hash,platform_snapshot_json FROM challenges WHERE id=?',
                                 (cid,))
        public_snapshot = json.loads(challenge['platform_snapshot_json'] or '{}')
        frozen[cid] = {
            'challenge_content_sha256': challenge['content_hash'],
            'challenge_source': public_snapshot.get('source_kind', 'existing_import'),
            'experience_manifests': {role: experience_context.select(cid, role=role)
                                     for role in ('brain', 'executor', 'both')},
            'skills': {role: skills.effective_for(db.get_db(), settings, cid, role=role)
                       for role in ('brain', 'executor')},
        }
    config_snapshot = {
        'schema': 'cyberscientist-evaluation/v1', 'catalog_sha256': hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        'suite': suite, 'repeats': repeats, 'label': label,
        'entries': entries, 'frozen': frozen,
        'models': {role: {'runtime': 'codex', 'model_id': 'gpt-6-sol',
                          'reasoning_effort': 'xhigh'} for role in ('brain', 'executor')},
        'shadow_enabled': bool(settings.get('shadow', {}).get('enabled', False)),
        'settings_revision': settings.get('revision'),
    }
    eid = 'eval_' + uuid.uuid4().hex[:12]
    now = db.utcnow()
    with db.transaction() as conn:
        prior = conn.execute("SELECT id,repeats FROM eval_runs WHERE suite=? AND label=?"
                             " AND status='running'", (suite, label)).fetchone()
        if prior:
            if prior['repeats'] != repeats:
                raise EvaluationError('同层同标签评测正在运行；请使用另一个 label')
            return get_evaluation(prior['id'])
        conn.execute('INSERT INTO eval_runs(id,suite,repeats,label,status,config_json,created_at,updated_at)'
                     ' VALUES(?,?,?,?,?,?,?,?)',
                     (eid, suite, repeats, label, 'running', _canonical(config_snapshot), now, now))
        for item in entries:
            for repeat in range(1, repeats + 1):
                conn.execute('INSERT INTO eval_results(id,eval_id,challenge_id,repeat_index,status,'
                             'created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                             ('er_' + uuid.uuid4().hex[:12], eid, item['challenge_id'], repeat,
                              'pending', now, now))
    return get_evaluation(eid)


def _sandbox_usage(run_id: str) -> tuple[float, str]:
    """Read the latest resource ledger, including cleanup after Run completion."""
    now = datetime.fromisoformat(db.utcnow())
    rows = db.query('SELECT status,created_at,updated_at,deleted_at FROM compute_sandboxes'
                    ' WHERE run_id=?', (run_id,))
    minutes = 0.0
    for row in rows:
        end = (row['deleted_at'] if row['status'] in ('deleted', 'failed') and row['deleted_at']
               else row['updated_at'] if row['status'] == 'failed' else None)
        end_at = datetime.fromisoformat(end) if end else now
        minutes += max(0.0, (end_at - datetime.fromisoformat(row['created_at'])).total_seconds()) / 60
    status = ('confirmed' if all(row['status'] in ('deleted', 'failed') for row in rows)
              else 'lower_bound_pending_cleanup')
    return round(minutes, 3), status


def _job_usage(run_id: str) -> tuple[int, int]:
    """Count confirmed platform Jobs separately from ambiguous dispatches."""
    rows = db.query('SELECT platform_job_id,status FROM compute_jobs WHERE run_id=?', (run_id,))
    confirmed = sum(row['platform_job_id'] is not None for row in rows)
    unknown = sum(row['platform_job_id'] is None and row['status'] in ('unknown', 'submitting')
                  for row in rows)
    return confirmed, unknown


def get_evaluation(eval_id: str) -> dict[str, Any]:
    row = db.query_one('SELECT * FROM eval_runs WHERE id=?', (eval_id,))
    if not row:
        raise EvaluationError('评测不存在')
    results = db.query('SELECT * FROM eval_results WHERE eval_id=? ORDER BY challenge_id,repeat_index',
                       (eval_id,))
    output = []
    for result in results:
        item = dict(result)
        item['result'] = json.loads(result['result_json']) if result['result_json'] else None
        if item['result'] is not None and result['run_id']:
            minutes, minutes_status = _sandbox_usage(result['run_id'])
            item['result']['sandbox_minutes'] = minutes
            item['result']['sandbox_minutes_status'] = minutes_status
            confirmed_jobs, unknown_jobs = _job_usage(result['run_id'])
            item['result']['job_count'] = confirmed_jobs
            item['result']['job_unknown_count'] = unknown_jobs
        output.append(item)
    return {'id': row['id'], 'suite': row['suite'], 'label': row['label'],
            'status': row['status'], 'repeats': row['repeats'], 'created_at': row['created_at'],
            'ended_at': row['ended_at'],
            'results': output}


def list_evaluations() -> list[dict[str, Any]]:
    return [dict(row) for row in db.query(
        'SELECT id,suite,label,status,repeats,created_at,ended_at FROM eval_runs ORDER BY created_at DESC')]


def _marker(config_snapshot: dict[str, Any], item: dict[str, Any], result_id: str) -> dict[str, Any]:
    cid = item['challenge_id']
    frozen = config_snapshot['frozen'][cid]
    return {'enabled': True, 'result_id': result_id,
            'challenge_content_sha256': frozen['challenge_content_sha256'],
            'challenge_source': frozen['challenge_source'],
            'models': config_snapshot['models'], 'experience_manifests': frozen['experience_manifests'],
            'experience_sha256': _sha(frozen['experience_manifests']),
            'skills': frozen['skills'], 'skills_sha256': _sha(frozen['skills']),
            'switches': {'experience_enabled': True,
                         'shadow_enabled': config_snapshot['shadow_enabled'],
                         'models': config_snapshot['models'],
                         'skill_ids': {role: [skill['id'] for skill in frozen['skills'][role]]
                                       for role in ('brain', 'executor')}}}


def _limits(suite: str) -> dict[str, int]:
    return {'minutes': 60 if suite == 'fast' else 180,
            'jobs': 2 if suite == 'fast' else 5,
            'sandbox_minutes': 60 if suite == 'fast' else 180}


async def advance(controller: Any) -> None:
    """One idempotent scheduling pass, called periodically by the backend."""
    for evaluation in db.query("SELECT * FROM eval_runs WHERE status='running' ORDER BY created_at"):
        eid = evaluation['id']
        snapshot = json.loads(evaluation['config_json'])
        by_id = {item['challenge_id']: item for item in snapshot['entries']}
        for result in db.query('SELECT * FROM eval_results WHERE eval_id=? ORDER BY rowid', (eid,)):
            if result['status'] in ('complete', 'failed'):
                continue
            rid = result['run_id']
            if rid is None:
                try:
                    marker = _marker(snapshot, by_id[result['challenge_id']], result['id'])
                    marker['eval_id'] = eid
                    run = controller.create_run(result['challenge_id'], 'connected',
                                                snapshot['shadow_enabled'], eval_mode=marker)
                except Exception as exc:
                    if getattr(exc, 'code', '') == 'RUN_ACTIVE':
                        break
                    _failure(result['id'], type(exc).__name__ + ': ' + str(exc)[:180])
                    continue
                rid = run['id']
                db.execute('UPDATE eval_results SET run_id=?,status=\'created\',updated_at=? WHERE id=?',
                           (rid, db.utcnow(), result['id']))
            run = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
            if run['phase'] == 'created':
                limit = _limits(evaluation['suite'])
                if not run['authorization_id']:
                    controller.authorize(rid, 'connected', True, 0, limit['minutes'], 0,
                        'CS-UP-05 local-only evaluation; no platform submission',
                        max_jobs=limit['jobs'], allow_data_download=True,
                        max_sandboxes=2, max_sandbox_minutes=limit['sandbox_minutes'],
                        allow_sandbox_gpu=False)
                try:
                    await controller.start_async(rid)
                except Exception as exc:
                    current = db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))
                    if current and current['phase'] in ('created', 'blocked'):
                        db.execute("UPDATE runs SET phase='failed',ended_at=?,block_reason=? WHERE id=?",
                                   (db.utcnow(), '评测启动失败：' + type(exc).__name__, rid))
                    _failure(result['id'], type(exc).__name__ + ': ' + str(exc)[:180])
                    continue
                db.execute("UPDATE eval_results SET status='running',updated_at=? WHERE id=?",
                           (db.utcnow(), result['id']))
            elif run['phase'] == 'recovering':
                recovery = db.query_one(
                    "SELECT seq FROM events WHERE run_id=? AND type IN"
                    " ('run.needs_recovery','run.reopened') ORDER BY seq DESC LIMIT 1", (rid,))
                # One stable operation per recovery episode, not one forever:
                # reusing the prior episode's ID would acknowledge a resume
                # without rebuilding the now-lost native sessions.
                episode = recovery['seq'] if recovery else run['state_version']
                await controller.control(rid, 'resume', None,
                                         f'eval-resume-{rid}-{episode}')
                db.execute("UPDATE eval_results SET status='running',updated_at=? WHERE id=?",
                           (db.utcnow(), result['id']))
            elif run['phase'] == 'eval_scoring':
                db.execute("UPDATE eval_results SET status='scoring',updated_at=? WHERE id=?",
                           (db.utcnow(), result['id']))
                score_status, score_reason = await asyncio.to_thread(_score_run, rid, result['id'])
                controller._finalize_run(rid, run['end_reason'] or 'evaluation completed')
                _finish_result(result['id'], rid, scoring_status=score_status,
                               scoring_reason=score_reason)
            elif run['phase'] in TERMINAL:
                _finish_result(result['id'], rid)
            else:
                db.execute('UPDATE eval_results SET status=?,updated_at=? WHERE id=?',
                           (run['phase'], db.utcnow(), result['id']))
        pending = db.query_one("SELECT 1 FROM eval_results WHERE eval_id=?"
                               " AND status NOT IN ('complete','failed') LIMIT 1", (eid,))
        if not pending:
            failed = db.query_one("SELECT 1 FROM eval_results WHERE eval_id=?"
                                  " AND status='failed' LIMIT 1", (eid,))
            db.execute('UPDATE eval_runs SET status=?,ended_at=?,updated_at=? WHERE id=?',
                       ('complete_with_failures' if failed else 'complete',
                        db.utcnow(), db.utcnow(), eid))
            write_report(eid)


def _check_scorer_input_path(challenge_id: str, sealed: bytes) -> None:
    """Reject known unsupported package layouts before renting a scorer sandbox."""
    if challenge_id not in FIGQA_IDS:
        return
    with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
        names = archive.namelist()
    supported = [name for name in names if name == 'outputs/answer.txt'
                 or name.endswith('/outputs/answer.txt')]
    if len(supported) != 1:
        root_answer = 'answer.txt' in names
        raise EvaluationError('FigQA 评分器需唯一 outputs/answer.txt；'
                              + ('封存包只有根目录 answer.txt，科学分 unknown'
                                 if root_answer else '封存包缺少或重复该路径，科学分 unknown'))


def retry_authorized(run_id: str, result_id: str) -> bool:
    """A single local-only post-finish scorer repair; no research or submission."""
    result = db.query_one('SELECT status,result_json FROM eval_results WHERE id=? AND run_id=?',
                          (result_id, run_id))
    if not result or result['status'] != 'complete' or not result['result_json']:
        return False
    if json.loads(result['result_json']).get('science_score') is not None:
        return False
    if db.query_one("SELECT 1 FROM events WHERE run_id=?"
                    " AND type='evaluation.score_retry_finished'"
                    " AND json_extract(payload,'$.result_id')=? LIMIT 1", (run_id, result_id)):
        return False
    return bool(db.query_one("SELECT 1 FROM events WHERE run_id=?"
                             " AND type='evaluation.score_retry_started'"
                             " AND json_extract(payload,'$.result_id')=? LIMIT 1",
                             (run_id, result_id)))


def _score_run(run_id: str, result_id: str, *, retry: bool = False) -> tuple[str, str | None]:
    run = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    trial_id = run['current_trial_id']
    status, reason = 'unavailable', None
    if trial_id:
        try:
            score_op = 'eval-score-' + result_id + ('-retry' if retry else '')
            sandbox_op = 'eval-scorer-' + result_id + ('-retry' if retry else '')
            existing = db.query_one('SELECT id FROM local_scores WHERE sandbox_operation_id=?',
                                    (score_op,))
            if existing:
                return 'scored', None
            sealed_dir = config.WORKSPACE_DIR / 'runs' / run_id / 'eval'
            sealed_dir.mkdir(parents=True, exist_ok=True)
            sealed_path = sealed_dir / 'sealed_package.zip'
            if sealed_dir.is_symlink() or sealed_path.is_symlink():
                raise EvaluationError('评测封存路径含符号链接')
            if sealed_path.exists():
                from . import trace_diagnostics
                sealed = sealed_path.read_bytes()
                challenge = db.query_one('SELECT content FROM challenges WHERE id=?',
                                         (run['challenge_id'],))
                diagnostic = trace_diagnostics.diagnose_sealed_package(
                    sealed, challenge['content'] if challenge else '')
                preflight = {'sealed_bytes': sealed, 'error_code': None}
                if not db.query_one("SELECT 1 FROM events WHERE run_id=?"
                                    " AND type='evaluation.sealed'", (run_id,)):
                    db.append_event(run_id, 'controller', 'evaluation.sealed',
                                    {'sealed_package_sha256': hashlib.sha256(sealed).hexdigest(),
                                     'data_evidence_class': 'unknown', 'recovered': True},
                                    trial_id=trial_id)
            else:
                preflight = mailboxes.preflight_submission(
                    run_id, trial_id, None, allow_proxy_evidence=True)
                diagnostic = preflight['trace_diagnostics']
                admission_error = preflight['error_code']
                if admission_error and admission_error not in (
                        'TRACE_ADMISSION_BLOCKED', 'TRACE_ADMISSION_INDETERMINATE',
                        'PROXY_EVIDENCE'):
                    raise EvaluationError('封存准入失败: ' + preflight['error_code'])
                sealed_path.write_bytes(preflight['sealed_bytes'])
                db.append_event(run_id, 'controller', 'evaluation.sealed',
                                {'sealed_package_sha256': preflight['sealed_package_sha256'],
                                 'data_evidence_class': preflight['data_inputs']['evidence_class'],
                                 'admission_error_code': admission_error,
                                 'proxy_evidence_allowed_for_local_score': True},
                                trial_id=trial_id)
                if admission_error:
                    preflight = preflight | {'error_code': None}
            db.append_event(run_id, 'controller', 'evaluation.trace_diagnosed',
                            {'status': diagnostic.get('status'),
                             'checklist_score': diagnostic.get('checklist_score'),
                             'qualified_codes': [entry['code'] for entry in diagnostic.get('advisories', [])],
                             'advisory_cap': diagnostic.get('advisory_cap'),
                             'checklist_cap': diagnostic.get('checklist_cap'),
                             'reason': diagnostic.get('reason')}, trial_id=trial_id)
            _check_scorer_input_path(run['challenge_id'], preflight['sealed_bytes'])
            manifest = local_scoring.scorer_manifest(run['challenge_id'])
            public_resource = None
            if run['challenge_id'] == MATCHGATE_ID:
                public_resource = (config.WORKSPACE_ROOT / '.package-checks' / 'cs-up-05' /
                                   'matchgate-public' / 'out-net' / 'matchgate.zip')
                if not public_resource.is_file() or hashlib.sha256(public_resource.read_bytes()).hexdigest() != MATCHGATE_RESOURCE_SHA256:
                    raise EvaluationError('Matchgate 公开数据缺失或哈希不符；科学分 unknown')
            if run['challenge_id'] == 'flowforge-paired-block-boundary-projection-v10-fe06025a':
                from . import lean_runtime
                lean_runtime.validate_source()
            active = db.query_one('SELECT sandbox_id FROM compute_sandboxes WHERE run_id=?'
                                  " AND trial_id=? AND status='active' AND json_extract(request_json,'$.image')=?"
                                  ' ORDER BY created_at DESC LIMIT 1',
                                  (run_id, trial_id, manifest['image']))
            sid = active['sandbox_id'] if active else None
            if sid is None:
                hard = run['challenge_id'] in (MATCHGATE_ID,
                    'flowforge-paired-block-boundary-projection-v10-fe06025a')
                created = sandboxes.create(run_id, sandbox_op,
                    {'image': manifest['image'], 'cpu': '4c8g',
                     'timeout': 1800 if hard else 600})
                sid = created.get('sandbox_id') if created.get('status') == 'active' else None
            if not sid:
                raise EvaluationError('评分沙箱未确认 active')
            local = local_scoring.evaluate(run_id, trial_id, sid, score_op,
                                           preflight=preflight,
                                           public_resource_zip=public_resource,
                                           score_timeout=1200 if public_resource else 600 if
                                           run['challenge_id'].startswith('flowforge-paired-block') else 120)
            status = 'scored' if local.get('science_score') is not None else 'unavailable'
            db.append_event(run_id, 'controller', 'evaluation.local_scored',
                            {'local_score_id': local['id'], 'status': status}, trial_id=trial_id)
        except Exception as exc:
            reason = type(exc).__name__ + ': ' + str(exc)[:180]
            db.append_event(run_id, 'controller', 'evaluation.local_score_unavailable',
                            {'reason': reason}, trial_id=trial_id)
    else:
        reason = 'Run 未生成 Trial'
    return status, reason


def retry_unavailable_score(result_id: str) -> dict[str, Any]:
    """Retry one infrastructure-failed science score on the same sealed Run."""
    result = db.query_one('SELECT * FROM eval_results WHERE id=?', (result_id,))
    if not result or not result['run_id'] or result['status'] != 'complete':
        raise EvaluationError('需要已完成且封存的评测结果')
    rid = result['run_id']
    run = db.query_one('SELECT phase,authorization_id,started_at FROM runs WHERE id=?', (rid,))
    if not run or run['phase'] != 'finished' or not db.eval_mode(rid):
        raise EvaluationError('仅已完成的评测 Run 可重试本地评分')
    prior = json.loads(result['result_json'] or '{}')
    if prior.get('science_score') is not None:
        raise EvaluationError('科学分已确认，不重试')
    if db.query_one("SELECT 1 FROM events WHERE run_id=?"
                    " AND type='evaluation.score_retry_finished'"
                    " AND json_extract(payload,'$.result_id')=? LIMIT 1", (rid, result_id)):
        raise EvaluationError('该结果已完成一次补评分，不重复租用资源')
    sealed = config.WORKSPACE_DIR / 'runs' / rid / 'eval' / 'sealed_package.zip'
    if not sealed.is_file() or sealed.is_symlink():
        raise EvaluationError('原封存包不存在，不能重试')
    auth = db.query_one('SELECT max_run_minutes FROM authorizations WHERE id=?',
                        (run['authorization_id'],))
    remaining = (auth['max_run_minutes'] * 60 -
                 (datetime.fromisoformat(db.utcnow()) -
                  datetime.fromisoformat(run['started_at'])).total_seconds()) if auth and run['started_at'] else 0
    if remaining < 1800:
        raise EvaluationError('原 Run 授权不足 30 分钟，不能租新的评分沙箱')
    if not retry_authorized(rid, result_id):
        db.append_event(rid, 'controller', 'evaluation.score_retry_started',
                        {'result_id': result_id, 'sealed_package_sha256':
                         hashlib.sha256(sealed.read_bytes()).hexdigest(),
                         'prior_reason': prior.get('science_reason')})
    try:
        status, reason = _score_run(rid, result_id, retry=True)
    finally:
        try:
            sandboxes.cleanup_run(rid)
        except Exception as exc:
            db.append_event(rid, 'controller', 'sandbox.cleanup_unknown',
                            {'reason': type(exc).__name__, 'phase': 'eval_rescore'})
    _finish_result(result_id, rid, scoring_status=status, scoring_reason=reason)
    db.append_event(rid, 'controller', 'evaluation.score_retry_finished',
                    {'result_id': result_id, 'status': status, 'reason': reason})
    write_report(result['eval_id'])
    return get_evaluation(result['eval_id'])


def recover_matchgate_score_receipt(result_id: str) -> dict[str, Any]:
    """Record a completed scorer JSON obscured by dependency-install stdout.

    This reads the original local receipt and frozen inputs; it performs no
    sandbox, model, Job or platform operation.
    """
    result = db.query_one('SELECT * FROM eval_results WHERE id=?', (result_id,))
    if not result or not result['run_id'] or result['status'] != 'complete':
        raise EvaluationError('需要已结束的评测结果')
    rid = result['run_id']
    run = db.query_one('SELECT challenge_id,current_trial_id,phase FROM runs WHERE id=?', (rid,))
    if (not run or run['challenge_id'] != MATCHGATE_ID or run['phase'] != 'finished'
            or not db.eval_mode(rid)):
        raise EvaluationError('只允许恢复已结束的 Matchgate 评测回执')
    prior = json.loads(result['result_json'] or '{}')
    if prior.get('science_score') is not None:
        raise EvaluationError('科学分已记录')
    score_op = 'eval-score-' + result_id
    if db.query_one('SELECT 1 FROM local_scores WHERE sandbox_operation_id=?', (score_op,)):
        raise EvaluationError('原评分操作已记录')
    sealed_file = config.WORKSPACE_DIR / 'runs' / rid / 'eval' / 'sealed_package.zip'
    if not sealed_file.is_file() or sealed_file.is_symlink():
        raise EvaluationError('原封存包不存在')
    sealed = sealed_file.read_bytes()
    if hashlib.sha256(sealed).hexdigest() != prior.get('sealed_package_sha256'):
        raise EvaluationError('原封存包哈希改变')
    manifest = local_scoring.scorer_manifest(MATCHGATE_ID)
    stage = (config.WORKSPACE_DIR / 'runs' / rid / 'trials' / run['current_trial_id']
             / 'local_scorer' / score_op)
    expected = {'science_package.zip': local_scoring._science_package(sealed),
                'scorer.zip': local_scoring._archive(manifest['files'])}
    for name, content in expected.items():
        path = stage / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != content:
            raise EvaluationError('原评分输入与冻结包不符: ' + name)
    resource = stage / 'public_resource.zip'
    if (not resource.is_file() or resource.is_symlink()
            or hashlib.sha256(resource.read_bytes()).hexdigest() != MATCHGATE_RESOURCE_SHA256):
        raise EvaluationError('原公开资源哈希不符')
    sandbox = db.query_one('SELECT * FROM compute_sandboxes WHERE run_id=? AND operation_id=?',
                           (rid, 'eval-scorer-' + result_id))
    if (not sandbox or not sandbox['sandbox_id'] or sandbox['status'] != 'deleted'
            or json.loads(sandbox['request_json']).get('image') != manifest['image']):
        raise EvaluationError('原评分沙箱生命周期未确认')
    event = db.query_one("SELECT seq,occurred_at,payload FROM events WHERE run_id=?"
                         " AND type='sandbox.exec_completed'"
                         " AND json_extract(payload,'$.operation_id')=? ORDER BY seq DESC LIMIT 1",
                         (rid, score_op + '-run'))
    if not event or not sandbox['deleted_at'] or not (
            sandbox['created_at'] <= event['occurred_at'] <= sandbox['deleted_at']):
        raise EvaluationError('原评分执行事件与沙箱生命周期不匹配')
    execution = json.loads(event['payload'])
    command = execution.get('command') or ''
    suffix = ('CS_SCORER_VERSION=' + manifest['scorer_version']
              + ' python3 scorer/' + manifest['entrypoint'] + ' package.zip')
    if (execution.get('sandbox_id') != sandbox['sandbox_id']
            or execution.get('status') != 'completed' or execution.get('exit_code') != 0
            or '-r scorer/requirements.txt' not in command or not command.endswith(suffix)):
        raise EvaluationError('原评分执行回执不符合固定命令')
    output = execution.get('output')
    if not isinstance(output, str) or not output.strip():
        raise EvaluationError('原评分 stdout 为空')
    final_line = output.rstrip().splitlines()[-1]
    try:
        science = local_scoring._score_output(
            {'receipt': {'stdout': json.dumps({'data': {'stdout': final_line}})}},
            manifest['scorer_version'])
    except local_scoring.LocalScoreError as exc:
        raise EvaluationError('原评分末行不满足科学分契约') from exc
    local = local_scoring._record_score(MATCHGATE_ID, rid, run['current_trial_id'],
                                        score_op, sealed, manifest, science)
    db.append_event(rid, 'controller', 'evaluation.local_score_recovered',
                    {'result_id': result_id, 'source_event_seq': event['seq'],
                     'local_score_id': local['id'],
                     'sealed_package_sha256': prior['sealed_package_sha256'],
                     'scorer_version': manifest['scorer_version']})
    _finish_result(result_id, rid, scoring_status='scored')
    write_report(result['eval_id'])
    return get_evaluation(result['eval_id'])


def _failure(result_id: str, reason: str) -> None:
    db.execute("UPDATE eval_results SET status='failed',error=?,updated_at=? WHERE id=?",
               (reason, db.utcnow(), result_id))


def _usage(run_id: str, event_type: str) -> dict[str, int] | None:
    totals = []
    for row in db.query('SELECT payload FROM events WHERE run_id=? AND type=? ORDER BY seq',
                        (run_id, event_type)):
        raw = json.loads(row['payload'])
        usage = raw.get('usage') if isinstance(raw, dict) else None
        if not isinstance(usage, dict):
            continue
        total = usage.get('total') if isinstance(usage.get('total'), dict) else usage
        input_tokens = total.get('inputTokens', total.get('input_tokens'))
        output_tokens = total.get('outputTokens', total.get('output_tokens'))
        if type(input_tokens) is int and type(output_tokens) is int:
            totals.append({'input': input_tokens, 'output': output_tokens})
    if not totals:
        return None
    # Native updates are cumulative within a session; sum only monotonic deltas.
    output = {'input': 0, 'output': 0}
    previous = {'input': 0, 'output': 0}
    for item in totals:
        for key in output:
            output[key] += item[key] if item[key] < previous[key] else item[key] - previous[key]
            previous[key] = item[key]
    return output


def _finish_result(result_id: str, run_id: str, *, scoring_status: str | None = None,
                   scoring_reason: str | None = None) -> None:
    compute.mark_terminal_pending_unknown(run_id)
    row = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    local = db.query_one('SELECT * FROM local_scores WHERE run_id=?'
                         ' AND sandbox_operation_id IN (?,?) ORDER BY created_at DESC LIMIT 1',
                         (run_id, 'eval-score-' + result_id,
                          'eval-score-' + result_id + '-retry'))
    diagnostic = json.loads(local['trace_prediction_json']) if local else None
    preflight = db.query_one('SELECT payload FROM events WHERE run_id=?'
                             " AND type='evaluation.trace_diagnosed' ORDER BY seq DESC LIMIT 1", (run_id,))
    checklist = json.loads(preflight['payload']) if preflight else None
    seal = db.query_one('SELECT payload FROM events WHERE run_id=?'
                        " AND type='evaluation.sealed' ORDER BY seq DESC LIMIT 1", (run_id,))
    seal_info = json.loads(seal['payload']) if seal else {}
    score = local['science_score'] if local else None
    cap = checklist.get('advisory_cap') if checklist else None
    jobs, unknown_jobs = _job_usage(run_id)
    minutes, minutes_status = _sandbox_usage(run_id)
    events = db.query('SELECT type FROM events WHERE run_id=?', (run_id,))
    started = datetime.fromisoformat(row['started_at']) if row['started_at'] else None
    ended = datetime.fromisoformat(row['ended_at']) if row['ended_at'] else None
    marker = db.eval_mode(run_id) or {}
    result = {
        'run_id': run_id, 'config_sha256': hashlib.sha256(row['config_snapshot'].encode()).hexdigest(),
        'experience_sha256': marker.get('experience_sha256'),
        'challenge_content_sha256': marker.get('challenge_content_sha256'),
        'challenge_source': marker.get('challenge_source'),
        'sealed_package_sha256': seal_info.get('sealed_package_sha256'),
        'data_evidence_class': seal_info.get('data_evidence_class'),
        'admission_error_code': seal_info.get('admission_error_code'),
        'science_score': score, 'science_status': scoring_status or ('scored' if local else 'unavailable'),
        'science_reason': scoring_reason, 'scorer_version': local['scorer_version'] if local else None,
        'trace_checklist_score': checklist.get('checklist_score') if checklist else None,
        'trace_status': checklist.get('status') if checklist else 'unavailable',
        'trace_qualified_codes': checklist.get('qualified_codes', []) if checklist else [],
        'trace_qualified_cap': cap, 'trace_local_prediction': diagnostic,
        'display_interval': display_interval(score, cap),
        'wall_seconds': round((ended - started).total_seconds(), 3) if started and ended else None,
        'brain_tokens': _usage(run_id, 'brain.usage.updated'),
        'executor_tokens': _usage(run_id, 'prime.usage.updated'),
        'job_count': jobs, 'job_unknown_count': unknown_jobs,
        'sandbox_minutes': minutes,
        'sandbox_minutes_status': minutes_status, 'bohrium_amount': 'unknown',
        'attention_events': sum(e['type'] in (
            'run.stall_detected', 'run.needs_attention', 'run.paused',
            'trial.stalled', 'model.rate_limit_attention')
                                for e in events),
        'rate_limit_events': sum(e['type'] == 'model.rate_limited' for e in events),
        'final_status': row['phase'], 'failure_reason': row['block_reason'] or scoring_reason,
    }
    status = 'complete' if row['phase'] == 'finished' else 'failed'
    db.execute('UPDATE eval_results SET status=?,result_json=?,error=?,updated_at=? WHERE id=?',
               (status, _canonical(result), row['block_reason'], db.utcnow(), result_id))


def report(eval_id: str) -> dict[str, Any]:
    evaluation = get_evaluation(eval_id)
    rows = evaluation['results']
    by_challenge: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_challenge.setdefault(row['challenge_id'], []).append(row)
    challenge_stats = {}
    for cid, items in by_challenge.items():
        scores = [item['result']['science_score'] for item in items
                  if item['result'] and item['result']['science_score'] is not None]
        challenge_stats[cid] = {'count': len(items), 'scored_count': len(scores),
                                'science_mean': statistics.mean(scores) if scores else None,
                                'science_difference': abs(scores[1] - scores[0]) if len(scores) == 2 else None,
                                'science_sample_variance': statistics.variance(scores) if len(scores) > 1 else None}
    completed = [row['result'] for row in rows if row['result']]
    scored = [item['science_score'] for item in completed if item['science_score'] is not None]
    previous = db.query_one('SELECT id FROM eval_runs WHERE suite=? AND id<>? AND created_at<?'
                            ' ORDER BY created_at DESC LIMIT 1',
                            (evaluation['suite'], eval_id, evaluation['created_at']))
    previous_means: dict[str, float] = {}
    if previous:
        prior_rows = db.query('SELECT challenge_id,result_json FROM eval_results WHERE eval_id=?'
                              ' AND result_json IS NOT NULL', (previous['id'],))
        previous_scores: dict[str, list[float]] = {}
        for row in prior_rows:
            value = json.loads(row['result_json']).get('science_score')
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                previous_scores.setdefault(row['challenge_id'], []).append(float(value))
        previous_means = {cid: statistics.mean(values) for cid, values in previous_scores.items()}
    comparison = {cid: {'previous_science_mean': previous_means.get(cid),
                        'science_mean_delta': (stats['science_mean'] - previous_means[cid]
                                               if stats['science_mean'] is not None and
                                               cid in previous_means else None)}
                  for cid, stats in challenge_stats.items()}
    return {'evaluation': evaluation, 'challenge_stats': challenge_stats,
            'suite_summary': {'result_count': len(rows), 'completed_count': len(completed),
                              'scored_count': len(scored),
                              'science_mean': statistics.mean(scored) if scored else None},
            'previous_same_suite_eval_id': previous['id'] if previous else None,
            'previous_comparison': comparison,
            'interval_rule': {'cap_le_29': '[0,0]', 'cap_30_69': '[0,science*cap/100]',
                              'without_qualified_cap': '[science*0.30,science]',
                              'warning': '裁判部分未复刻'}}


def write_report(eval_id: str) -> tuple[Path, Path]:
    from . import observation

    data = report(eval_id)
    out = config.DATA_DIR / 'evals'
    out.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out / (eval_id + '.json'), out / (eval_id + '.md')
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    lines = [f"# Evaluation {eval_id}", '',
             f"Suite: {data['evaluation']['suite']} | status: {data['evaluation']['status']}", '',
             '轨迹 C 来自公开 v6 确定性检查表；与历史 v8 仅对可见代码作过条件比较。', '',
             '展示分区间：上限≤29 → 0；30–69 → [0, 科学分×上限/100]；'
             '无达标上限 → [科学分×0.30, 科学分]。裁判部分未复刻。', '',
             '| 题目 | 重复 | Run | 科学分 | 轨迹检查表 | 达标上限 | 展示分区间 | 耗时秒 | Job | 沙箱分钟 | 金额 | 状态 |',
             '|---|---:|---|---:|---:|---:|---|---:|---:|---:|---|---|']
    def shown(value: Any) -> str:
        if value is None:
            return 'unknown'
        return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    for row in data['evaluation']['results']:
        item = row['result'] or {}
        interval = item.get('display_interval') or {}
        interval_text = ('unknown' if interval.get('lower') is None or interval.get('upper') is None
                         else f"[{interval['lower']},{interval['upper']}]")
        lines.append('| ' + ' | '.join(str(value) for value in (
            row['challenge_id'], row['repeat_index'], row['run_id'] or 'unknown',
            shown(item.get('science_score')), shown(item.get('trace_checklist_score')),
            shown(item.get('trace_qualified_cap')), interval_text,
            shown(item.get('wall_seconds')),
            (f"{shown(item.get('job_count'))} (+{item['job_unknown_count']} unknown)"
             if item.get('job_unknown_count') else shown(item.get('job_count'))),
            shown(item.get('sandbox_minutes')),
            item.get('bohrium_amount', 'unknown'), item.get('final_status', row['status']))) + ' |')
    lines.extend(['', '## Run details', ''])
    for row in data['evaluation']['results']:
        item = row['result'] or {}
        reason = item.get('science_reason') or item.get('failure_reason')
        reason_text = observation.strip_secrets(str(reason)).replace('\n', ' ')[:180] if reason else 'none'
        lines.append(f"- {row['run_id'] or 'pending'}: source={shown(item.get('challenge_source'))}; "
                     f"science_status={shown(item.get('science_status'))}; reason={reason_text}; "
                     f"qualified_codes={item.get('trace_qualified_codes') or []}; "
                     f"brain_tokens={shown(item.get('brain_tokens'))}; "
                     f"executor_tokens={shown(item.get('executor_tokens'))}; "
                     f"sandbox_minutes_status={shown(item.get('sandbox_minutes_status'))}")
    lines.extend(['', '## Per-challenge statistics', ''])
    for cid, stats in data['challenge_stats'].items():
        lines.append(f"- {cid}: observed_mean={shown(stats['science_mean'])}, "
                     f"difference={shown(stats['science_difference'])}, "
                     f"sample_variance={shown(stats['science_sample_variance'])}, "
                     f"scored={stats['scored_count']}/{stats['count']}, "
                     f"delta_from_previous={shown(data['previous_comparison'][cid]['science_mean_delta'])}")
    summary = data['suite_summary']
    lines.extend(['', f"Observed suite science mean: {shown(summary['science_mean'])} "
                  f"(scored {summary['scored_count']}/{summary['result_count']}); "
                  f"previous same-suite eval: {data['previous_same_suite_eval_id'] or 'none'}", ''])
    md_path.write_text('\n'.join(lines))
    return md_path, json_path
