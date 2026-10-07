"""Ordinary competition harvest, durable intent and no replay after uncertainty."""
from __future__ import annotations
import asyncio
import json
import math
from datetime import datetime, timezone, timedelta
from . import config, db, mailboxes, platform_scores, power

ACTIVE_TASKS: set[asyncio.Task] = set()


def validate(params: dict) -> dict:
    defaults = config.DEFAULT_SETTINGS['harvest']
    if not isinstance(params, dict) or set(params) - set(defaults):
        raise ValueError('自动收割参数无效')
    result = defaults | params
    for key in ('score_threshold', 'deadline_check_hours', 'safety_margin_minutes'):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{key} 须为非负有限数值')
    if type(result['experiments_done_at_leader']) is not bool:
        raise ValueError('experiments_done_at_leader 须为布尔值')
    return result


def _now():
    return datetime.now(timezone.utc)


def window(clock, params=None, now=None):
    params = params or validate(config.load_settings().get('harvest', {}))
    now = now or _now()
    end = clock.get('end')
    if isinstance(end, str):
        end = mailboxes._instant(end)
    if not end:
        return {'state': 'unknown', 'remaining_seconds': None, 'until_window_seconds': None}
    remaining = (end - now).total_seconds()
    return {'state': 'ended' if remaining <= 0 else 'safety_margin' if remaining <= params['safety_margin_minutes'] * 60
            else 'active' if remaining <= params['deadline_check_hours'] * 3600 else 'before_window',
            'remaining_seconds': remaining,
            'until_window_seconds': max(0, remaining - params['deadline_check_hours'] * 3600),
            'safety_margin_minutes': params['safety_margin_minutes']}


def topic_runs(conn, run):
    """Experiments share a topic only within the same imported track."""
    target=json.loads(mailboxes._challenge_key(conn,run['id']))
    rows=conn.execute('SELECT r.*,'+mailboxes._target_columns()+" FROM runs r JOIN challenges c ON c.id=r.challenge_id WHERE json_extract(r.config_snapshot,'$.competition.round_id') IS ?",
                      (json.loads(run['config_snapshot']).get('competition',{}).get('round_id'),)).fetchall()
    return [r for r in rows if [r['target_platform'],r['target_origin'],r['target_topic']]==target]


def _unstarted_topic_target(conn, round_id, challenge_id):
    row=conn.execute("SELECT json_extract(t.config_json,'$.mode') AS mode,"
        "json_extract(t.config_json,'$.mailbox_platform') AS platform,"
        "json_extract(t.config_json,'$.submission_transport.base_url') AS origin,"
        "COALESCE(NULLIF(json_extract(e.value,'$.platform_challenge_id'),''),NULLIF(c.platform_challenge_id,''),'local:'||c.id) AS topic"
        " FROM eval_runs t JOIN json_each(t.config_json,'$.entries') e JOIN challenges c ON c.id=json_extract(e.value,'$.challenge_id')"
        " WHERE t.id=? AND c.id=? LIMIT 1",(round_id,challenge_id)).fetchone()
    if not row:return None
    settings=config.load_settings()
    return [row['platform'] or settings['mailbox']['platform'],
            'demo' if row['mode']=='demo' else (row['origin'] or settings['playground']['base_url']).rstrip('/'),row['topic']]


def topic_facts(round_id, challenge_id, *, conn=None):
    conn = conn or db.get_db()
    participant=conn.execute("SELECT id FROM runs WHERE challenge_id=? AND json_extract(config_snapshot,'$.competition.round_id') IS ? LIMIT 1",(challenge_id,round_id)).fetchone()
    target=None if participant else _unstarted_topic_target(conn,round_id,challenge_id)
    run_id=participant['id'] if participant else None
    all_rows=mailboxes._target_submissions(conn,run_id,target=target) if participant or target else []
    rows=[s for s in all_rows if s['target_round']==round_id]
    def confirmed(s):
        return (s['status']=='submitted' and s['score_status']=='scored' and s['score_confidence']=='confirmed'
                and not s['score_anomaly'] and s['scorecard_consistent']!=0
                and s['score'] is not None and math.isfinite(s['score']))
    exp = sorted((s for s in rows if s['role']=='experiment' and not s['is_harvest'] and confirmed(s)),
                 key=lambda s:(s['score'],s['created_at']), reverse=True)
    mailbox=conn.execute("SELECT id FROM mailboxes WHERE role='harvest' AND status='active'").fetchone()
    mains=mailboxes._target_submissions(conn,run_id,mailbox_id=mailbox['id'],target=target) if (participant or target) and mailbox else []
    main = [s['score'] for s in mains if confirmed(s)]
    return {'main_best': max(main) if main else None, 'experiment_best': exp[0]['score'] if exp else None,
            'best_submission_id': exp[0]['id'] if exp else None,
            'pending_submission_ids':[s['id'] for s in rows if s['reservation_released']==0
                                      and s['status'] in ('unknown','submitted') and not confirmed(s)]
                                     + [s['id'] for s in mains if not confirmed(s) and s['id'] not in {r['id'] for r in rows}],
            'no_confirmed_score': not exp and not main}


def _last_quota(conn, run):
    harvest=conn.execute("SELECT id FROM mailboxes WHERE role='harvest' AND status='active'").fetchone()
    return bool(harvest and config.load_settings()['mailbox']['submission_limit']-
                mailboxes._used_for(conn,harvest['id'],mailboxes._challenge_key(conn,run['id']))==1)


def automatic_constraints(conn, src, trigger, *, own_reservation=None):
    """Recheck clock, last mailbox quota and best score immediately before POST."""
    from . import track_clock
    run = conn.execute('SELECT * FROM runs WHERE id=?',(src['run_id'],)).fetchone()
    state = window(track_clock.for_run(run), trigger['params'])
    if state['state'] in ('safety_margin','ended'):
        raise mailboxes.MailboxError('HARVEST_CUTOFF', '已进入赛末安全余量；不新增自动收割')
    harvest = conn.execute("SELECT id FROM mailboxes WHERE role='harvest' AND status='active'").fetchone()
    if harvest:
        used = mailboxes._used_for(conn,harvest['id'],mailboxes._challenge_key(conn,run['id']))
        if own_reservation:
            reserved=conn.execute('SELECT reservation_released FROM submissions WHERE id=?',(own_reservation,)).fetchone()
            if reserved and not reserved[0]: used -= 1
        remaining=config.load_settings()['mailbox']['submission_limit']-used
        if remaining<=0 or (remaining==1 and state['state']!='active'):
            raise mailboxes.MailboxError('LAST_HARVEST_QUOTA','最后一次主邮箱额度只在赛末窗口使用')
    if trigger['reason']=='deadline_best':
        facts=topic_facts(json.loads(run['config_snapshot']).get('competition',{}).get('round_id'),run['challenge_id'],conn=conn)
        if state['state']!='active' or facts['best_submission_id']!=src['id']:
            raise mailboxes.MailboxError('TRIGGER_CHANGED','赛末窗口或同题最佳实验成绩已变化')


def _summaries(params):
    from . import alerts,track_clock
    for row in db.query("SELECT * FROM eval_runs WHERE suite='competition' AND status!='draft'"):
        clock=track_clock.from_snapshot(json.loads(row['config_json']))
        facts=window(clock,params)
        remaining=facts['remaining_seconds']
        if remaining is None or remaining<=0 or remaining>max(1800,params['deadline_check_hours']*3600): continue
        topics=sorted({r['challenge_id'] for r in db.query('SELECT challenge_id FROM eval_results WHERE eval_id=?',(row['id'],))})
        payload={'round_id':row['id'],'track':row['label'],'window':facts,
                 'topics':[{'challenge_id':c}|topic_facts(row['id'],c) for c in topics]}
        with db.transaction() as conn:
            for stage in ('window_start','last_30_minutes'):
                if stage=='last_30_minutes' and remaining>1800: continue
                if stage=='window_start' and remaining>params['deadline_check_hours']*3600: continue
                # Round-owned alerts work even when every topic is deferred/skipped.
                alerts._insert(conn,'harvest-summary:'+row['id']+':'+stage,
                               {'id':None,'challenge_id':None},'harvest.summary',
                               '赛末成绩汇总 · '+row['label']+' · '+stage,payload)


def reconcile_interrupted(*, include_running: bool = True) -> None:
    # Submission receipts are reconciled separately; a started harvest is never resent.
    with db.transaction() as conn:
        for row in conn.execute("SELECT * FROM automatic_harvests WHERE status IN ('running','unknown')" if include_running else "SELECT * FROM automatic_harvests WHERE status='unknown'").fetchall():
            result = conn.execute('SELECT id,status FROM submissions WHERE operation_id=?', (row['operation_id'],)).fetchone()
            status = 'done' if result and result['status'] == 'submitted' else 'unknown'
            if row['status'] == status:
                continue
            conn.execute('UPDATE automatic_harvests SET status=?,error=?,updated_at=? WHERE source_submission_id=?',
                         (status, None if status == 'done' else '重启时收割尚未确认；不重发', db.utcnow(), row['source_submission_id']))
            db.append_event_tx(conn, row['run_id'], 'controller', 'harvest.' + status,
                               {'source_submission_id': row['source_submission_id'], 'reason': 'startup_reconciliation'})


def experiments_done(conn, run) -> bool:
    if run['phase'] != 'finished':
        return False
    participants=topic_runs(conn,run)
    if any(r['phase'] not in ('finished','cancelled','failed') for r in participants):
        return False
    if conn.execute("SELECT 1 FROM eval_results WHERE challenge_id=? AND run_id IS NULL AND status NOT IN ('complete','failed') LIMIT 1", (run['challenge_id'],)).fetchone():
        return False
    # An exhausted/interrupted Run cannot assert scientific work is complete.
    for participant in participants:
        if participant['end_reason'] in ('authorization_expired', 'brain_review_limit', 'runtime_error'):
            return False
    return True


def _trigger(run, source, params: dict) -> dict | None:
    from . import track_clock
    state=window(track_clock.for_run(run),params)
    if state['state'] in ('safety_margin','ended'): return None
    if state['state']=='active':
        facts=topic_facts(json.loads(run['config_snapshot']).get('competition',{}).get('round_id'),run['challenge_id'])
        if facts['best_submission_id']==source['id']:
            return {'reason':'deadline_best','score':source['score'],'params':params}
        return None
    if source['score'] >= params['score_threshold']:
        return {'reason': 'score_threshold', 'score': source['score'], 'params': params}
    if params['experiments_done_at_leader'] and experiments_done(db.get_db(), run):
        distribution = platform_scores.get(run['id'], fresh=True)
        leaders = distribution.get('top_10_scores') or []
        if distribution.get('status') == 'ok' and leaders and source['score'] >= max(leaders):
            return {'reason': 'experiments_done_at_leader', 'score': source['score'], 'leader': max(leaders), 'params': params}
    return None


def advance_sync() -> None:
    reconcile_interrupted(include_running=False)
    from . import features
    if power.shutdown_requested() or not features.enabled('auto_harvest'):
        return
    params = validate(config.load_settings().get('harvest', {}))
    _summaries(params)
    for run in db.query("SELECT * FROM runs WHERE phase IN ('running','waiting_score','finished')"):
        snapshot = json.loads(run['config_snapshot'])
        if snapshot.get('automatic_harvest_version') != 1:
            continue  # no retroactive irreversible authorization on historical Runs
        auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],))
        from . import run_limits
        if not auth or (not run_limits.track_unlimited(run, auth) and auth['max_submissions'] <= 0):
            continue
        from . import track_clock
        end = track_clock.for_run(run)['end']
        if end and end - timedelta(hours=params['deadline_check_hours']) <= _now():
            key = 'harvest_deadline_checked:' + run['id']
            with db.transaction() as conn:
                if not conn.execute('SELECT 1 FROM system_state WHERE key=?', (key,)).fetchone():
                    conn.execute('INSERT INTO system_state VALUES(?,?)', (key, db.utcnow()))
                    db.append_event_tx(conn, run['id'], 'controller', 'harvest.deadline_check', {'round_end': end.isoformat()})
        # Only this Run's experiment package may consume this Run's bounded authorization.
        sources = db.query("SELECT s.* FROM submissions s JOIN mailboxes m ON m.id=s.mailbox_id"
                           " WHERE s.run_id=? AND s.is_harvest=0 AND m.role='experiment'"
                           " AND s.status='submitted' AND s.score_status='scored' AND s.score_confidence='confirmed'"
                           " AND s.score IS NOT NULL ORDER BY s.score DESC,s.created_at DESC", (run['id'],))
        for src in sources:
            if src['score_anomaly'] or src['scorecard_consistent'] == 0 or not math.isfinite(src['score']):
                continue
            old = db.query_one('SELECT status FROM automatic_harvests WHERE source_submission_id=?', (src['id'],))
            if old and old['status'] != 'waiting':
                continue
            trigger = _trigger(run, src, params)
            if trigger is None:
                continue
            reason = trigger['reason']
            operation = 'auto-harvest-' + src['id']
            with db.transaction() as conn:
                if power.shutdown_requested() or not features.enabled('auto_harvest'):
                    return
                try:
                    mailboxes._check_budget(conn, run['id'], terminal_harvest=True)
                    current = conn.execute('SELECT * FROM submissions WHERE id=?', (src['id'],)).fetchone()
                    mailboxes._automatic_harvest_guard(conn, current, trigger)
                except mailboxes.MailboxError as exc:
                    if exc.code == 'LOWER_SCORE':
                        continue
                    if exc.code != 'HARVEST_PENDING':
                        continue
                    conn.execute("INSERT OR IGNORE INTO automatic_harvests VALUES(?,?,?,'waiting',?,NULL,NULL,?,?)",
                                 (src['id'], operation, run['id'], str(exc), db.utcnow(), db.utcnow()))
                    continue
                now = db.utcnow()
                conn.execute("INSERT OR IGNORE INTO automatic_harvests VALUES(?,?,?,'waiting',?,NULL,NULL,?,?)",
                             (src['id'], operation, run['id'], reason, now, now))
                changed = conn.execute("UPDATE automatic_harvests SET status='running',reason=?,result_json=?,updated_at=?"
                                       " WHERE source_submission_id=? AND status='waiting'", (reason, json.dumps(trigger), now, src['id']))
                if not changed.rowcount:
                    continue
                db.append_event_tx(conn, run['id'], 'controller', 'harvest.started',
                                   {'source_submission_id': src['id'], 'operation_id': operation, 'trigger': reason,
                                    'last_mailbox_quota': _last_quota(conn,run)})
            try:
                result = mailboxes.harvest_submit(src['id'], operation, True, True, automatic=True)
                status = 'done' if result['status'] == 'submitted' else result['status']
                error = result.get('error')
            except Exception as exc:
                from .observation import strip_secrets
                result = None
                status = 'failed' if isinstance(exc, mailboxes.MailboxError) else 'unknown'
                error = strip_secrets(str(exc))[:800]
            with db.transaction() as conn:
                conn.execute('UPDATE automatic_harvests SET status=?,result_json=?,error=?,updated_at=? WHERE source_submission_id=?',
                             (status, json.dumps({'submission_id': result['id'], 'status': result['status']}) if result else None,
                              error, db.utcnow(), src['id']))
                db.append_event_tx(conn, run['id'], 'controller', 'harvest.' + status,
                                   {'source_submission_id': src['id'], 'submission_id': result['id'] if result else None,
                                    'error': error, 'no_automatic_retry': status != 'done'})
            break


async def advance() -> None:
    """Keep the actual HTTP worker alive and visible until completion at shutdown."""
    if power.shutdown_requested() or any(not task.done() for task in ACTIVE_TASKS):
        return
    from . import resource_coordinator
    async def worker():
        owner = 'automatic-harvest-http'
        task = asyncio.current_task()
        resource_coordinator.register_auxiliary(owner, task)
        http = asyncio.create_task(asyncio.to_thread(advance_sync))
        try:
            while not http.done():
                try:
                    await asyncio.shield(http)
                except asyncio.CancelledError:
                    continue  # repeated cancellations cannot erase an in-flight HTTP worker
            http.result()
        finally:
            resource_coordinator.release_sessions(owner)
    task = asyncio.create_task(worker())
    ACTIVE_TASKS.add(task)
    task.add_done_callback(ACTIVE_TASKS.discard)


async def drain() -> None:
    tasks = [task for task in ACTIVE_TASKS if not task.done()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
