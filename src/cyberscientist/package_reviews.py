"""PI-invoked fresh-context advisory, bound to immutable package inputs."""
from __future__ import annotations
import asyncio
import hashlib
import json
from pathlib import Path
import jsonschema
from . import config, db, mailboxes, observation, resource_coordinator

SCHEMA = {'type': 'object', 'additionalProperties': False,
          'properties': {'verdict': {'enum': ['pass', 'issues']},
                         'issues': {'type': 'array', 'items': {'type': 'string'}},
                         'summary_md': {'type': 'string'}},
          'required': ['verdict', 'issues', 'summary_md']}


def get(operation_id: str, run_id: str) -> dict | None:
    row = db.query_one('SELECT * FROM package_reviews WHERE operation_id=? AND run_id=?', (operation_id, run_id))
    if not row:
        return None
    return {'operation_id': operation_id, 'status': row['status'],
            'source_sha256': row['source_sha256'], 'sealed_sha256': row['sealed_sha256'],
            'result': json.loads(row['result_json']) if row['result_json'] else None,
            'error': row['error'], 'advisory_only': True}


def reconcile_interrupted() -> None:
    db.execute("UPDATE package_reviews SET status='unknown',error='已开始审查被中断，不自动重发',updated_at=? WHERE status='running'", (db.utcnow(),))


async def review(controller, run_id: str, trial_id: str, operation_id: str,
                 package_path: str | None = None) -> dict:
    if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 100:
        raise ValueError('审查需要稳定 operation_id（最多100字）')
    if observation.strip_secrets(operation_id) != operation_id:
        raise ValueError('审查幂等键不能含密钥')
    run = controller._require_run(run_id)
    if not db.query_one('SELECT 1 FROM trials WHERE id=? AND run_id=?', (trial_id, run_id)):
        raise ValueError('审查 Trial 不属于本 Run')
    source = mailboxes._resolve_package(run_id, trial_id, package_path).resolve()
    base = (config.WORKSPACE_DIR / 'runs' / run_id / 'trials' / trial_id).resolve()
    if not source.is_relative_to(base):
        raise ValueError('审查包必须在本 Trial 内')
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    previous = db.query_one('SELECT * FROM package_reviews WHERE operation_id=?', (operation_id,))
    if previous:
        if previous['run_id'] != run_id or previous['trial_id'] != trial_id or previous['source_sha256'] != source_sha:
            raise ValueError('审查幂等键内容冲突')
        if previous['status'] != 'pending':
            return get(operation_id, run_id)
        packet = json.loads(previous['packet_json'])
    else:
        checked = await asyncio.to_thread(mailboxes.preflight_submission, run_id, trial_id, package_path)
        if checked['source_package_sha256'] != source_sha:
            raise ValueError('包在审查冻结期间变化，请使用新的操作键')
        sealed = checked.pop('sealed_bytes')
        checked.pop('projected_steps', None)
        if _contains_secret(sealed):
            raise ValueError('审查包包含密钥，未复制或启动模型')
        root = config.WORKSPACE_DIR / 'package_reviews' / hashlib.sha256((run_id + trial_id + operation_id + source_sha + checked['sealed_package_sha256']).encode()).hexdigest()
        root.mkdir(parents=True, exist_ok=True)
        package = root / ('sealed.zip' if sealed.startswith(b'PK') else 'sealed.json')
        _write_snapshot(package, sealed)
        exact = db.query('SELECT * FROM local_scores WHERE run_id=? AND trial_id=? AND package_sha256 IN (?,?)',
                         (run_id, trial_id, source_sha, checked['sealed_package_sha256']))
        matching = list(exact)
        if not matching and sealed.startswith(b'PK'):
            from . import local_scoring
            hashes = local_scoring._canonical(mailboxes._science_artifact_hashes(sealed))
            manifest_sha = local_scoring._manifest_science_sha(sealed)
            matching = db.query("SELECT * FROM local_scores WHERE run_id=? AND trial_id=? AND science_artifact_hashes_json=? AND manifest_science_sha256=? AND score_source IN ('system','executor_verified')",
                                (run_id, trial_id, hashes, manifest_sha))
        matching = [r for r in matching if r['score_source'] in ('system', 'executor_verified')]
        challenge = controller._challenge_for_run(run)
        packet = {'protocol': 'role_task', 'task': 'package_review',
                  'instructions': '在全新只读上下文审查这些材料。只读题面、交付契约、封存包、已登记评分与轨迹诊断；'
                    '核对文件/格式/路径、科学结论、干净环境复跑证据和轨迹 accept 条件。缺证写问题，不能当通过。'
                    '只用工具读当前导出材料，不访问其他 Run、经验、会话或凭据；不执行科学计算/评分，不提交。'
                    '问题清单仅供 PI 决定，不能新增硬门禁。',
                  'challenge': observation.strip_secrets(challenge['content']),
                  'delivery_contract': checked['artifact_contract'],
                  'sealed_package': {'path': str(package), 'sha256': checked['sealed_package_sha256'], 'source_sha256': source_sha},
                  'local_scores': [dict(r) for r in matching if r['score_source'] in ('system', 'executor_verified')],
                  'local_score_status': 'observed' if matching else 'unknown',
                  'trace_diagnostics': checked['trace_diagnostics'], 'admission': checked['admission'],
                  'output_contract': SCHEMA}
        packet = json.loads(observation.strip_secrets(json.dumps(packet, ensure_ascii=False)))
        _write_snapshot(root / 'materials.json', json.dumps(packet, ensure_ascii=False, indent=2).encode())
        with db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO package_reviews VALUES(?,?,?,?,?,'pending',?,NULL,NULL,?,?)",
                (operation_id, run_id, trial_id, source_sha, checked['sealed_package_sha256'], json.dumps(packet, ensure_ascii=False), db.utcnow(), db.utcnow()))
            registered = conn.execute('SELECT * FROM package_reviews WHERE operation_id=?', (operation_id,)).fetchone()
            if registered['run_id'] != run_id or registered['trial_id'] != trial_id or registered['source_sha256'] != source_sha:
                raise ValueError('审查幂等键冲突')
            packet = json.loads(registered['packet_json'])
    controller._require_model_authorization(run_id)
    auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],))
    from . import run_clock
    if run['phase'] not in ('running', 'created') or (auth and auth['max_run_minutes'] and run_clock.remaining(run, auth) <= 0):
        raise ValueError('当前 Run 未授权新的审查调用')
    settings = controller._runtime_settings(run_id)
    original = settings['brain']
    settings['brain'] = dict(settings['reviewer'])
    if not settings['brain'].get('executable') and original['runtime'] == settings['brain']['runtime']:
        settings['brain']['executable'] = original.get('executable', '')
    owner = 'package-review-' + operation_id
    brain = session = None
    started = False
    with db.transaction() as conn:
        if not conn.execute("UPDATE package_reviews SET status='running',updated_at=? WHERE operation_id=? AND status='pending'", (db.utcnow(), operation_id)).rowcount:
            return get(operation_id, run_id)
    try:
        resource_coordinator.reserve_auxiliary(owner, settings)
        brain = controller._make_brain(settings)
        session = await brain.open({'working_directory': str(Path(packet['sealed_package']['path']).parent), 'instructions': packet['instructions']})
        live = controller._require_run(run_id)
        if live['phase'] not in ('running', 'created') or (auth and auth['max_run_minutes'] and run_clock.remaining(live, auth) <= 0):
            raise ValueError('审查启动时原授权已结束，未发起模型 turn')
        started = True
        db.append_event(run_id, 'controller', 'package.review_started', {'operation_id': operation_id, 'sealed_sha256': packet['sealed_package']['sha256']}, trial_id=trial_id)
        result = None
        timeout = settings['run_defaults']['brain_review_timeout_seconds']
        if auth and auth['max_run_minutes']:
            timeout = min(timeout, max(1, run_clock.remaining(live, auth)))
        async with asyncio.timeout(timeout):
            async for event in brain.review(session, packet):
                if event.type == 'task_result':
                    result = json.loads(observation.strip_secrets(json.dumps(event.payload['result'], ensure_ascii=False)))
                elif event.type == 'error':
                    raise ValueError(observation.strip_secrets(str(event.payload.get('message', '审查失败'))))
                elif event.type == 'usage':
                    db.append_event(run_id, 'brain', 'reviewer.usage.updated', json.loads(observation.strip_secrets(json.dumps(event.payload))))
        jsonschema.validate(result, SCHEMA)
        if result['verdict'] == 'pass' and result['issues']:
            raise ValueError('审查 verdict 与问题清单不一致')
        with db.transaction() as conn:
            conn.execute("UPDATE package_reviews SET status='done',result_json=?,updated_at=? WHERE operation_id=?", (json.dumps(result, ensure_ascii=False), db.utcnow(), operation_id))
            db.append_event_tx(conn, run_id, 'controller', 'package.review_done', {'operation_id': operation_id, 'result': result, 'advisory_only': True}, trial_id=trial_id)
    except resource_coordinator.ResourceWait:
        db.execute("UPDATE package_reviews SET status='pending',updated_at=? WHERE operation_id=?", (db.utcnow(), operation_id))
    except BaseException as exc:
        from .model_providers import record_throttle
        record_throttle(settings['brain'], exc)
        status = 'unknown' if isinstance(exc, (asyncio.CancelledError, asyncio.TimeoutError)) and started else 'failed'
        error = observation.strip_secrets(str(exc))[:1000] or type(exc).__name__
        db.execute('UPDATE package_reviews SET status=?,error=?,updated_at=? WHERE operation_id=?', (status, error, db.utcnow(), operation_id))
        db.append_event(run_id, 'controller', 'package.review_' + status, {'operation_id': operation_id, 'error': error, 'advisory_only': True}, trial_id=trial_id)
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        try:
            if session:
                try: await brain.close(session)
                except Exception as exc: resource_coordinator.close_failed(owner, exc)
        finally: resource_coordinator.release_sessions(owner)
    return get(operation_id, run_id)


def _contains_secret(content: bytes) -> bool:
    import io
    import zipfile
    values = [v.encode() for v in config.sensitive_values() if len(v) > 7]
    if any(v in content for v in values):
        return True
    if not content.startswith(b'PK') or not values:
        return False
    overlap = max(map(len, values))
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for item in archive.infolist():
            with archive.open(item) as member:
                tail = b''
                while block := member.read(65536):
                    combined = tail + block
                    if any(v in combined for v in values):
                        return True
                    tail = combined[-overlap:]
    return False


def _write_snapshot(path: Path, content: bytes) -> None:
    import os
    import uuid
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('审查快照路径不能含符号链接')
    with config.mutation_lock:
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError('不可变审查快照内容冲突')
            return
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_bytes(content)
            temporary.chmod(0o444)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
