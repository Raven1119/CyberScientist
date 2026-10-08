"""Invoke the official CLI once; remote unknowns remain reservations."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import zipfile

from . import config, db, observation, platform_contracts, trace_selection, native_logs
from .mailbox_platform import PlatformError, public_feedback

WORKER = 'http://47.92.88.121:443/api'


def account_attempts(platform, secret, challenge_id):
    identity = platform._http('GET', '/auth/me', token=secret)
    owner = identity.get('user', identity) if isinstance(identity, dict) else {}
    if owner.get('id') is None:
        raise ValueError('邮箱身份未确认')
    rows, seen, total = [], set(), None
    for page in range(1, 201):
        body = platform._http('GET', '/challenges/' + urllib.parse.quote(challenge_id, safe='')
            + f'/attempts?page={page}&limit=100&sort=newest', token=secret)
        if (not isinstance(body, dict) or not isinstance(body.get('attempts'), list)
                or type(body.get('total')) is not int or body['total'] < 0):
            raise ValueError('只读对账列表不完整')
        if total is None: total = body['total']
        if total != body['total']: raise ValueError('分页期间列表变化')
        added = 0
        for item in body['attempts']:
            if not isinstance(item, dict) or item.get('id') is None or item.get('authorId') is None:
                raise ValueError('只读对账条目缺少身份')
            key = str(item['id'])
            if key in seen: continue
            seen.add(key); added += 1
            if str(item['authorId']) == str(owner['id']): rows.append(item)
        if len(seen) == total:
            return {'owner_id': str(owner['id']), 'attempts': rows, 'complete': True}
        if len(seen) > total or not added: raise ValueError('只读分页未完整覆盖')
    raise ValueError('只读对账分页超过上限')


def _files(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)): raise ValueError('重复ZIP成员')
        root = trace_selection.bundle_root({name: b'' for name in names})
        manifest = json.loads(archive.read(root + 'arm_manifest.json'))
        if not isinstance(manifest, dict): raise ValueError('封存manifest须为对象')
        pointer = manifest.get('raw_messages')
        if (not isinstance(pointer, str) or pointer.startswith('/') or '..' in pointer.split('/')
                or '\\' in pointer or archive.getinfo(root + pointer).file_size > 128 * 1024**2):
            raise ValueError('封存包缺少有效原生会话记录')
        raw = archive.read(root + pointer)
        provenance = json.loads(archive.read(root + 'provenance/native_session.json'))
        if not isinstance(provenance, dict): raise ValueError('原生会话绑定须为对象')
        if provenance.get('sha256') != hashlib.sha256(raw).hexdigest():
            raise ValueError('封存原生会话哈希不符')
        if native_logs.contains_secrets(raw.decode()):
            raise ValueError('原始会话需脱敏；不得改写，请用干净Trial')
        first = json.loads(raw.splitlines()[0])
        if first.get('payload', {}).get('id') != provenance.get('session_id'):
            raise ValueError('原生会话身份不符')
        return manifest, raw, provenance


def pinned_cli():
    """Verify the shipped official artifact before use, without installing anything."""
    directory = config.WORKSPACE_ROOT / 'tools/playground-cli/0.1.40'
    integrity = json.loads((directory / 'integrity.json').read_text())
    if integrity['version'] != '0.1.40': raise ValueError('官方CLI版本不符')
    for name, expected in integrity['files'].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError('官方CLI完整性校验失败：' + name)
    return directory / 'dist/index.js'


def readiness(*, latest=False):
    executable = pinned_cli()
    command = [shutil.which('node') or str(Path.home()/'.local/bin/node'), str(executable), '--version']
    proc = subprocess.run(command, capture_output=True, text=True, timeout=10,
                          env=dict(os.environ, PLAYGROUND_NO_UPDATE_CHECK='1'))
    if proc.returncode or proc.stdout.strip() != '0.1.40': raise ValueError('官方CLI实际版本不符')
    result = {'version': '0.1.40', 'integrity': 'verified', 'update_available': None}
    if latest:
        import urllib.request
        try:
            with urllib.request.urlopen('https://play.bohrium.com/latest.json', timeout=10) as response:
                body = json.load(response)
            result.update(latest=body.get('latest'), update_available=body.get('latest') != '0.1.40',
                          notice='有新版本时仅提示；禁止自动升级')
        except (OSError, ValueError): result['latest_status'] = 'unknown'
    return result


def submit(platform, email, secret, package_path, challenge_id, meta):
    if not secret: raise PlatformError('缺少邮箱平台令牌；未发送', no_side_effect=True)
    settings = config.load_settings()
    executable = settings['playground'].get('cli_executable')
    try:
        executable = str(pinned_cli()) if not executable else executable
        if not Path(executable).is_file(): raise ValueError('官方CLI路径不存在')
        # Explicit fixture/custom paths remain usable in protocol tests. Production
        # settings point at the pinned artifact; no global CLI is selected implicitly.
        if 'tools/playground-cli/0.1.40' in str(Path(executable)):
            pinned_cli()
        content = meta['package_bytes']
        manifest, raw, provenance = _files(content)
        transport = getattr(platform, 'transport', None)
        if transport:
            from . import track_transport
            if transport['paths'] != track_transport.defaults(platform.base_url)['paths']:
                raise ValueError('官方CLI未实现此自定义赛道端点；须显式选api回退')
        baseline = account_attempts(platform, secret, challenge_id)
        if meta.get('run_id') and provenance.get('trial_id') != meta.get('trial_id'):
            raise ValueError('原生日志不是本次最终Trial的绑定快照')
        if meta.get('resume_attempt_id'):
            raise ValueError('CLI不自动续传旧API草稿；须显式处理原草稿')
    except (OSError, ValueError, KeyError, IndexError, TypeError, zipfile.BadZipFile, PlatformError) as exc:
        raise PlatformError(str(exc), no_side_effect=True) from exc
    on_stage = meta.get('on_stage') or (lambda *a: None)
    on_feedback = meta.get('on_feedback') or (lambda *a: None)
    on_package = meta.get('on_package') or (lambda *a: None)
    from . import submission_outputs
    with tempfile.TemporaryDirectory(prefix='cs-official-submit-') as temp:
        directory = Path(temp)
        native = directory / 'native.jsonl'; native.write_bytes(raw)
        outputs = directory / 'outputs'; outputs.mkdir()
        try:
            contract = meta.get('output_contract')
            if contract is None and meta.get('run_id'):
                contract = submission_outputs.contract_for_run(meta['run_id'])
            staged = submission_outputs.stage(content, outputs, manifest, contract=contract)
        except Exception as exc:
            raise PlatformError('输出契约自检失败：' + str(exc), no_side_effect=True) from exc
        on_feedback('output_staging', staged)
        env = {key: os.environ[key] for key in ('PATH','LANG','SSL_CERT_FILE','SSL_CERT_DIR','HTTP_PROXY','HTTPS_PROXY','NO_PROXY') if key in os.environ}
        env.update(HOME=temp, XDG_CONFIG_HOME=temp, PLAYGROUND_NO_UPDATE_CHECK='1',
            PLAYGROUND_CONFIG_PATH=str(directory/'absent-config.json'),
            PLAYGROUND_CREDENTIALS_PATH=str(directory/'absent-credentials.env'),
            PLAYGROUND_ALLOW_WORKER_API_OVERRIDE='1', PLAYGROUND_WORKER_API_BASE=WORKER,
            CS_PLAYGROUND_SUBMIT_TOKEN=secret)
        package = directory / 'official.zip'
        command = [executable, 'submit', '--api-base', platform.base_url,
            '--challenge-id', challenge_id, '--outputs', str(outputs), '--trace', str(native),
            '--raw-messages', str(native), '--model', meta.get('model_id') or meta.get('model') or provenance.get('model') or 'unknown',
            '--harness', meta.get('harness') or 'Codex', '--bundle-out', str(package),
            '--run-id', meta.get('submission_id') or hashlib.sha256(content).hexdigest(),
            '--token-env', 'CS_PLAYGROUND_SUBMIT_TOKEN', '--worker-token-env', 'CS_PLAYGROUND_SUBMIT_TOKEN']
        if executable.endswith('.js'): command = [shutil.which('node') or str(Path.home()/'.local/bin/node'), *command]
        try:
            preview = subprocess.run([*command, '--dry-run'], env=env, capture_output=True, text=True, timeout=600)
            if preview.returncode != 0: raise ValueError(observation.strip_secrets(preview.stderr)[:1000])
            preview_receipt = json.loads(preview.stdout)
            preview_bytes = package.read_bytes()
            preview_hash = hashlib.sha256(preview_bytes).hexdigest()
            if preview_receipt.get('bundle_sha256') != preview_hash: raise ValueError('试构建哈希不符')
            submission_outputs.verify_built(preview_bytes, staged['sha256'])
            on_package(preview_bytes, {'phase': 'preview', 'sha256': preview_hash})
        except Exception as exc:
            raise PlatformError('官方CLI试构建失败：' + str(exc), no_side_effect=True) from exc
        from . import trace_hints
        on_feedback('trace_hint', trace_hints.inspect(preview_bytes))
        if meta.get('run_id'):
            db.append_event(meta['run_id'], 'controller', 'submission.cli_baseline', {
                'submission_id': meta['submission_id'], 'owner_id': baseline['owner_id'],
                'attempt_ids': [str(x['id']) for x in baseline['attempts']],
                'challenge_id': challenge_id, 'package_sha256': preview_hash}, trial_id=meta.get('trial_id'))
        on_stage('create_sent')
        try:
            proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=600)
        except (subprocess.TimeoutExpired, OSError) as exc:
            # The CLI might have built a new artifact before its network request.
            if package.exists(): on_package(package.read_bytes(), {'phase': 'sent_unknown'})
            raise PlatformError('官方CLI在途状态unknown：' + type(exc).__name__) from exc
        diagnostic = public_feedback({'diagnostic_only': True, 'exit_code': proc.returncode,
            'stderr': observation.strip_secrets(proc.stderr), 'stdout_preview': observation.strip_secrets(proc.stdout)}, secret, *config.sensitive_values())
        # Private database retains the complete redacted streams for unknown replay.
        on_feedback('cli_process_full', diagnostic)
        on_feedback('cli_process', {k: v[:4000] if isinstance(v,str) else v for k,v in diagnostic.items()})
        built = package.read_bytes()
        digest = hashlib.sha256(built).hexdigest()
        on_package(built, {'phase': 'sent', 'sha256': digest, 'preview_sha256': preview_hash,
                           'same_archive_hash': digest == preview_hash})
        submission_outputs.verify_built(built, staged['sha256'])
        if native.read_bytes() != raw: raise PlatformError('CLI改变了原生会话字节；保留unknown')
        try: receipt = json.loads(proc.stdout)
        except ValueError: receipt = None
        if isinstance(receipt, dict):
            on_feedback('cli', public_feedback(receipt, secret, *config.sensitive_values()))
            attempt_id = receipt.get('attempt_id')
            if attempt_id is not None: on_stage('cli_receipt', str(attempt_id))
            if (proc.returncode == 0 and receipt.get('status') == 'submitted'
                    and receipt.get('schema_version') == 'playground-cli-submission/v0'
                    and receipt.get('challenge_id') == challenge_id
                    and receipt.get('bundle_sha256') == digest and attempt_id is not None
                    and receipt.get('worker_api_base') == WORKER and isinstance(receipt.get('bundle_response'), dict)
                    and not receipt['bundle_response'].get('error')
                    and receipt['bundle_response'].get('accepted') is not False
                    and receipt['bundle_response'].get('ok') is not False):
                return {'accepted': True, 'receipt': str(attempt_id), 'bundle_uploaded': True,
                        'transport': 'cli', 'package_sha256': digest,
                        'preview_sha256': preview_hash, 'same_archive_hash': digest == preview_hash,
                        'worker_job_id': receipt['bundle_response'].get('job_id') or receipt['bundle_response'].get('jobId')}
        match = re.search(r'--attempt-id\s+(\d+)', proc.stderr)
        if match: on_stage('cli_unknown', match[1])
        raise PlatformError('官方CLI未确认同包上传，保留unknown；须完整分页对账'
                            + f'；exit_code={proc.returncode}；' + diagnostic['stderr'][:300])


def reconcile_unknown(submission_id, platform, secret, challenge_id):
    row = db.query_one('SELECT * FROM submissions WHERE id=?', (submission_id,))
    if not row or row['status'] != 'unknown': raise ValueError('仅对账unknown提交')
    event = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='submission.cli_baseline' AND json_extract(payload,'$.submission_id')=? ORDER BY seq DESC LIMIT 1", (row['run_id'], submission_id))
    if not event: return {'status': 'unknown', 'retry_allowed': False, 'reason': '无CLI发送前基线'}
    baseline = json.loads(event['payload'])
    now = account_attempts(platform, secret, challenge_id)
    if now['owner_id'] != baseline['owner_id']: raise ValueError('邮箱身份变化，不能对账')
    candidates = [str(x['id']) for x in now['attempts'] if str(x['id']) not in baseline['attempt_ids']]
    matches = []
    for attempt_id in candidates:
        item = platform.fetch_attempt('', secret, attempt_id)
        if (isinstance(item, dict) and item.get('challengeId') == challenge_id
                and str(item.get('authorId')) == now['owner_id']
                and item.get('bundleSha256') == (row['official_package_sha256'] or row['package_sha256'])): matches.append(attempt_id)
    from datetime import datetime, timezone
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(row['created_at']).replace(tzinfo=timezone.utc)).total_seconds()
    inferred = not candidates and now.get('complete') is True and age >= 600
    result = {'status': 'matched' if len(matches) == 1 else 'not_stored_inferred' if inferred else 'absence_observed' if not candidates else 'ambiguous',
              'candidates': candidates, 'matches': matches, 'retry_allowed': False,
              'reason': '十分钟完整分页无新增仅为未存储推断；重发须新显式意图且最多一次'}
    if inferred:
        with db.transaction() as conn:
            conn.execute("UPDATE submissions SET stage='not_stored_inferred',reservation_released=1 WHERE id=? AND status='unknown' AND platform_ref IS NULL", (submission_id,))
        result['retry_allowed'] = not bool(row['retry_of'])
    if len(matches) == 1:
        db.execute("UPDATE submissions SET platform_ref=? WHERE id=? AND platform_ref IS NULL AND status='unknown'", (matches[0], submission_id))
    db.append_event(row['run_id'], 'controller', 'submission.cli_reconciled', result | {'submission_id': submission_id}, trial_id=row['trial_id'])
    return result
