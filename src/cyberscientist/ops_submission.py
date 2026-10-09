"""Bounded old-task transport validation without opening a research Run."""
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import quote
from . import db, config, mailboxes, cli_submission


def preview(request):
    """Build with the official CLI; never reserve or create a submission."""
    run_id,trial_id=request['run_id'],request['trial_id']
    if not db.query_one('SELECT 1 FROM trials WHERE id=? AND run_id=?',(trial_id,run_id)):
        raise ValueError('Trial不属于此Run')
    platform=mailboxes._platform_for_run(run_id)
    row=db.query_one("SELECT * FROM mailboxes WHERE id=? AND status='active' AND platform=?",
                     (request.get('mailbox_id'),platform.name))
    if not row:raise ValueError('试构建需要明确可用的邮箱')
    package=mailboxes._resolve_package(run_id,trial_id,request['package_path'])
    checked=mailboxes.preflight_submission(run_id,trial_id,str(package))
    if checked['error_code']:
        raise ValueError('试构建封存预检失败：' + checked['error_code'])
    content=checked['sealed_bytes']
    from .mailbox_platform import PlatformError
    try:
        result=cli_submission.submit(platform,row['email'],config.resolve_secret(row['secret_ref']),
            str(package),mailboxes._run_challenge_id(run_id),
            {'package_bytes':content,'run_id':run_id,'trial_id':trial_id,'dry_run':True})
    except PlatformError as exc:
        raise ValueError(str(exc)) from exc
    return result | {'source_package_sha256':checked['source_package_sha256'],
                     'sealed_package_sha256':checked['sealed_package_sha256']}


def submit(request):
    grant = request['authorization']
    if (not isinstance(grant, dict) or type(grant.get('max_submissions')) is not int
            or not 1 <= grant['max_submissions'] <= 100
            or not isinstance(grant.get('expires_at'), str)
            or not grant.get('scope_id') or grant.get('ended_only') is not True
            or mailboxes._instant(grant.get('expires_at')) is None
            or mailboxes._instant(grant['expires_at']) <= datetime.now(timezone.utc)):
        raise ValueError('验证提交需要未到期的明确有界授权')
    run_id, trial_id, operation_id = (request[k] for k in ('run_id', 'trial_id', 'operation_id'))
    if not db.query_one('SELECT 1 FROM trials WHERE id=? AND run_id=?', (trial_id, run_id)):
        raise ValueError('Trial不属于此Run')
    platform = mailboxes._platform_for_run(run_id)
    challenge_id = mailboxes._run_challenge_id(run_id)
    if challenge_id not in grant['targets']:
        raise ValueError('题目不在验证授权范围')
    body = platform._http('GET', '/challenges/' + quote(challenge_id, safe=''))
    end = mailboxes._round_end(json.dumps(body))
    if not end or end > datetime.now(timezone.utc):
        raise ValueError('未只读确认题目已经结束')
    package = mailboxes._resolve_package(run_id, trial_id, request['package_path'])
    content = package.read_bytes()
    _, _, proof = cli_submission._files(content)
    if proof.get('trial_id') != trial_id:
        raise ValueError('验证包不是该Trial的原生绑定')
    binding = db.query_one("SELECT payload FROM events WHERE run_id=? AND trial_id=? AND source='controller' AND type='trial.native_session_bound' ORDER BY seq DESC LIMIT 1", (run_id, trial_id))
    if not binding or json.loads(binding['payload']).get('session_id') != proof.get('session_id'):
        raise ValueError('原生会话与控制器Trial绑定不符')
    digest = hashlib.sha256(content).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    grant_hash = hashlib.sha256(json.dumps(grant, sort_keys=True).encode()).hexdigest()
    with db.transaction() as conn:
        prior = conn.execute('SELECT * FROM submissions WHERE operation_id=?', (operation_id,)).fetchone()
        if prior:
            if prior['request_hash'] != fingerprint: raise ValueError('幂等键冲突')
            return dict(prior) | {'deduplicated': True}
        scope = conn.execute('SELECT * FROM submission_validation_scopes WHERE id=?', (grant['scope_id'],)).fetchone()
        if scope and scope['grant_sha256'] != grant_hash: raise ValueError('授权文件变化；不能重置额度')
        if not scope:
            conn.execute('INSERT INTO submission_validation_scopes VALUES(?,?,?,?)',
                         (grant['scope_id'], grant_hash, json.dumps(grant), db.utcnow()))
        count = conn.execute('SELECT COUNT(*) FROM submissions WHERE validation_scope=?', (grant['scope_id'],)).fetchone()[0]
        if count >= grant['max_submissions']: raise ValueError('验证授权额度已用尽')
        mailbox = conn.execute("SELECT * FROM mailboxes WHERE id=? AND role='experiment' AND status='active' AND platform=?", (request['mailbox_id'], platform.name)).fetchone()
        if not mailbox or not config.resolve_secret(mailbox['secret_ref'] or ''): raise ValueError('需要可用的实验账号')
        history = mailboxes._target_submissions(conn, run_id)
        if any(s['package_sha256'] == digest and s['mailbox_id'] != mailbox['id'] and not s['is_harvest'] for s in history):
            raise ValueError('同哈希必须使用原实验账号')
        sid = mailboxes._rid('sub')
        frozen = mailboxes._freeze(sid, package, content)
        conn.execute("INSERT INTO submissions(id,run_id,trial_id,mailbox_id,package_path,package_sha256,status,operation_id,created_at,request_hash,stage,validation_scope) VALUES(?,?,?,?,?,?,'unknown',?,?,?,'reserved',?)",
                     (sid, run_id, trial_id, mailbox['id'], frozen, digest, operation_id, db.utcnow(), fingerprint, grant['scope_id']))
        db.append_event_tx(conn, run_id, 'controller', 'submission.validation_authorized',
                           {'submission_id': sid, 'scope_id': grant['scope_id'], 'grant_sha256': grant_hash,
                            'ended_task_confirmed': True, 'slot': count + 1, 'limit': grant['max_submissions']}, trial_id=trial_id)
    return mailboxes._perform_submission(sid, platform, challenge_id)
