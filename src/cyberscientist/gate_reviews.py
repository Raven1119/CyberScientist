"""Audited, individual gate reviews; immutable content and scoped continuations."""
import contextvars
import hashlib
import importlib
import inspect
import json
from . import db, observation

_attempt = contextvars.ContextVar('gate_attempt', default=None)
_CALLS = {'cyberscientist.mailboxes': ('submit_experiment',),
          'cyberscientist.ops_submission': ('submit', 'preview'),
          'cyberscientist.compute': ('submit', 'cli')}


def redact(text):
    from . import native_logs
    text = observation.strip_secrets(str(text))
    text = native_logs._TOKEN.sub('[redacted]', text)
    return native_logs._BEARER.sub('Bearer [redacted]', text)


def invoke(function, *args, **kwargs):
    """Remember blocked original intents without storing credentials."""
    if _attempt.get() is not None:
        return function(*args, **kwargs)
    module, name = function.__module__, function.__name__
    if name not in _CALLS.get(module, ()):
        return function(*args, **kwargs)
    bound = inspect.signature(function).bind(*args, **kwargs).arguments
    body = bound.get('request') if module.endswith('ops_submission') else bound
    body = body or {}
    package_info = ([body.get('run_id'), body.get('trial_id'), body.get('package_path')]
                    if module.endswith(('mailboxes', 'ops_submission')) else None)
    request = {'module': module, 'function': name, 'args': args, 'kwargs': kwargs,
               'operation_id': body.get('operation_id'), 'package_info': package_info}
    serialized = json.dumps(request, sort_keys=True, ensure_ascii=False)
    from . import config, mailboxes
    if any(value and value in serialized for value in config.sensitive_values()):
        record('stored_credential', hashlib.sha256(serialized.encode()).hexdigest(),
               source='submission_intent', run_id=body.get('run_id'),
               exact_stored=True, context='[redacted stored credential]', risk='critical')
        raise ValueError('原提交意图包含凭据，不能登记自动续接')
    ident = hashlib.sha256(serialized.encode()).hexdigest()
    source_hash = None
    try:
        path = mailboxes._resolve_package(*package_info) if package_info else None
        if path:
            source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    except (ValueError, OSError, mailboxes.MailboxError):
        pass
    token = _attempt.set({'id': ident, 'request_json': serialized, 'source_hash': source_hash})
    try:
        result = function(*args, **kwargs)
        state = ('blocked' if isinstance(result, dict) and result.get('status') == 'failed'
                 else 'unknown' if isinstance(result, dict) and result.get('status') == 'unknown' else 'completed')
        db.execute('UPDATE gate_attempts SET status=?,updated_at=? WHERE id=?', (state, db.utcnow(), ident))
        return result
    except Exception:
        db.execute("UPDATE gate_attempts SET status='blocked',updated_at=? WHERE id=?", (db.utcnow(), ident))
        raise
    finally:
        _attempt.reset(token)


def record_tx(conn, rule, content_hash, *, source, run_id=None, trial_id=None,
              line=None, exact_stored=False, context='', risk='high'):
    attempt = _attempt.get()
    identity = json.dumps([run_id, trial_id, rule, content_hash, line, attempt['id'] if attempt else None], ensure_ascii=False)
    ident = 'gate_' + hashlib.sha256(identity.encode()).hexdigest()[:24]
    conn.execute('INSERT OR IGNORE INTO gate_reviews(id,run_id,trial_id,rule,content_hash,source,line,exact_stored,context,risk,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                 (ident, run_id, trial_id, rule, content_hash, source, line, int(exact_stored), redact(context), risk, 'pending', db.utcnow()))
    if attempt:
        conn.execute("INSERT OR IGNORE INTO gate_attempts VALUES(?,?,?,'blocked',NULL,?,?)", (attempt['id'], attempt['request_json'], attempt['source_hash'], db.utcnow(), db.utcnow()))
        conn.execute('INSERT OR IGNORE INTO gate_attempt_links VALUES(?,?)', (ident, attempt['id']))
    return dict(conn.execute('SELECT * FROM gate_reviews WHERE id=?', (ident,)).fetchone())


def record_event(conn, run_id, trial_id, kind, payload, seq):
    if kind == 'job.preflight' and payload.get('status') != 'blocked':
        return
    if 'gate=' in str(payload.get('reason', '')):
        return
    rule = kind + ':' + str(payload.get('code') or payload.get('rejection_kind') or 'blocked')
    content_hash = payload.get('source_package_sha256') or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    record_tx(conn, rule, content_hash, run_id=run_id, trial_id=trial_id,
              source=f'event:{run_id}:{seq}', context=json.dumps(payload, ensure_ascii=False)[:4000], risk='high')


def record(rule, content_hash, *, source, run_id=None, trial_id=None, line=None,
           exact_stored=False, context='', risk='high'):
    with db.transaction() as conn:
        return record_tx(conn, rule, content_hash, source=source, run_id=run_id,
                         trial_id=trial_id, line=line, exact_stored=exact_stored, context=context, risk=risk)


def pending():
    return {'items': [dict(r) for r in db.query("SELECT * FROM gate_reviews WHERE status='pending' ORDER BY created_at,id")]}


def approved(rule, content_hash, *, run_id, trial_id):
    with db.transaction() as conn:
        item = record_tx(conn, rule, content_hash, source='package_preflight', run_id=run_id, trial_id=trial_id, context=rule)
    return item['status'] == 'false_positive' and not item['exact_stored']


def resolve(ident, *, reason, false_positive=False):
    if not false_positive or not isinstance(reason, str) or not reason.strip():
        raise ValueError('人工放行须声明误报并填写理由')
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM gate_reviews WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('复核项不存在')
        if row['exact_stored']:
            raise ValueError('命中已存凭据原文，禁止人工放行')
        conn.execute("UPDATE gate_reviews SET status='false_positive',reason=?,resolved_at=? WHERE id=?", (redact(reason.strip()), db.utcnow(), ident))
        if row['run_id']:
            db.append_event_tx(conn, row['run_id'], 'user', 'gate.resolved', {'id': ident, 'rule': row['rule'], 'false_positive': True, 'reason': redact(reason)}, trial_id=row['trial_id'])
    return dict(db.query_one('SELECT * FROM gate_reviews WHERE id=?', (ident,)))


async def continue_resolved(ident, controller=None):
    """Continue unchanged unsent work. A sent or unknown reservation is not replayed."""
    from . import mailboxes
    links = db.query('SELECT a.* FROM gate_attempts a JOIN gate_attempt_links l ON l.attempt_id=a.id WHERE l.gate_id=?', (ident,))
    results = []
    for attempt in links:
        with db.transaction() as conn:
            current = conn.execute('SELECT status FROM gate_attempts WHERE id=?', (attempt['id'],)).fetchone()
            if current['status'] not in ('blocked', 'queued'):
                continue
            if conn.execute("SELECT 1 FROM gate_reviews g JOIN gate_attempt_links l ON l.gate_id=g.id WHERE l.attempt_id=? AND g.status='pending'", (attempt['id'],)).fetchone():
                continue
            conn.execute("UPDATE gate_attempts SET status='accepted',updated_at=? WHERE id=?", (db.utcnow(), attempt['id']))
        request = json.loads(attempt['request_json'])
        try:
            module, name = request['module'], request['function']
            if name not in _CALLS.get(module, ()):
                raise ValueError('非受控的续接入口')
            function = getattr(importlib.import_module(module), name)
            args, kwargs = request['args'], request['kwargs']
            operation_id = request.get('operation_id')
            prior = db.query_one('SELECT * FROM submissions WHERE operation_id=?', (operation_id,)) if operation_id else None
            if prior and prior['status'] == 'submitted':
                db.execute("UPDATE gate_attempts SET status='completed',updated_at=? WHERE id=?", (db.utcnow(), attempt['id']))
                continue
            if prior:
                if prior['status'] != 'failed' or not prior['reservation_released'] or prior['platform_ref']:
                    raise ValueError('已发送或状态未知的原提交不能自动重放；先只读对账')
                retry_id = operation_id[:70] + '-review-' + ident[-12:]
                if module.endswith('ops_submission'):
                    if args: args[0] = dict(args[0], operation_id=retry_id)
                    else: kwargs['request'] = dict(kwargs['request'], operation_id=retry_id)
                else:
                    if 'operation_id' in kwargs: kwargs['operation_id'] = retry_id
                    else: args[3] = retry_id
            if attempt['source_hash']:
                path = mailboxes._resolve_package(*request['package_info'])
                if hashlib.sha256(path.read_bytes()).hexdigest() != attempt['source_hash']:
                    raise ValueError('原候选内容变化，不续接；需要新提交意图')
            token = _attempt.set(dict(attempt))
            try:
                result = await mailboxes.submit_async(function, *args, **kwargs)
            finally:
                _attempt.reset(token)
            status = result.get('status', 'completed') if isinstance(result, dict) else 'completed'
            state = 'blocked' if status == 'failed' else 'unknown' if status == 'unknown' else 'completed'
            db.execute('UPDATE gate_attempts SET status=?,updated_at=? WHERE id=?', (state, db.utcnow(), attempt['id']))
            results.append({'attempt_id': attempt['id'], 'status': status})
        except Exception as exc:
            db.execute("UPDATE gate_attempts SET status='blocked',error=?,updated_at=? WHERE id=?", (redact(str(exc))[:1000], db.utcnow(), attempt['id']))
            results.append({'attempt_id': attempt['id'], 'status': 'blocked', 'reason': redact(str(exc))[:1000]})
    row = db.query_one('SELECT * FROM gate_reviews WHERE id=?', (ident,))
    if controller and row and row['run_id']:
        db.append_event(row['run_id'], 'controller', 'gate.continuation', {'id': ident, 'results': results}, trial_id=row['trial_id'])
        controller.notify_run_change(row['run_id'])
    return results
