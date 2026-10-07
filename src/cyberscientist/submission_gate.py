"""Durable submission scheduling and account-wide transport safety barrier."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from . import config, db


def validate(value):
    defaults = config.DEFAULT_SETTINGS['submission_policy']
    if not isinstance(value, dict) or set(value)-set(defaults): raise ValueError('提交间隔参数无效')
    result = defaults | value
    for name, number in result.items():
        if type(number) is not int or number < (1 if name=='cross_topic_limit' else 0):
            raise ValueError('提交间隔须为非负整数，跨题上限须为正整数')
    return result


def _now(): return datetime.now(timezone.utc)


def paused():
    row = db.query_one("SELECT value FROM system_state WHERE key='auto_submission_paused'")
    return bool(row and row[0]=='1')


def observe_feedback_tx(conn, row, response):
    def hit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('resultsJson','scoringDetails') and isinstance(item,str):
                    try:
                        if hit(json.loads(item)): return True
                    except ValueError: pass
                if key=='error_code' and item=='missing_worker_submission': return True
                if key in ('scored_by','source') and isinstance(item,str) and 'nonstandard-submission-guard' in item: return True
                if hit(item): return True
        elif isinstance(value, list): return any(hit(x) for x in value)
        return False
    if not hit(response): return
    conn.execute("INSERT OR REPLACE INTO system_state VALUES('auto_submission_paused','1')")
    from . import alerts
    run=conn.execute('SELECT * FROM runs WHERE id=?',(row['run_id'],)).fetchone()
    message='提交链路问题，不是科学或轨迹问题；自动提交和收割已暂停，科研继续。请核对正式 Worker 链路后在前端恢复。'
    alerts._insert(conn,'nonstandard-submission:'+row['id'],run,'submission.nonstandard',message,{'submission_id':row['id']})
    existing=conn.execute("SELECT 1 FROM events WHERE run_id=? AND type='submission.nonstandard' AND json_extract(payload,'$.submission_id')=?",(row['run_id'],row['id'])).fetchone()
    if not existing: db.append_event_tx(conn,row['run_id'],'controller','submission.nonstandard',{'submission_id':row['id'],'message':message},trial_id=row['trial_id'])


def synchronize_pause():
    if paused():
        from . import features
        settings=config.load_settings()
        if settings['features'].get('auto_submission',True): features.switch('auto_submission',False)


def _when(conn, row, now):
    from . import mailboxes
    policy=validate(config.load_settings().get('submission_policy',{}))
    target=mailboxes._challenge_key(conn,row['run_id'])
    history=conn.execute("SELECT s.*,m.email,m.platform,q.dispatched_at FROM submissions s JOIN mailboxes m ON m.id=s.mailbox_id LEFT JOIN submission_queue q ON q.submission_id=s.id WHERE lower(m.email)=lower(?) AND m.platform=? AND s.id!=? AND (q.dispatched_at IS NOT NULL OR s.submitted_at IS NOT NULL OR (s.status='unknown' AND s.stage NOT IN ('reserved','queued','prepared'))) AND s.reservation_released=0",(row['email'],row['platform'],row['id'])).fetchall()
    due=now; reasons=[];recent=[]
    for old in history:
        stamp=old['dispatched_at'] or old['submitted_at'] or old['created_at']
        at=datetime.fromisoformat(stamp)
        if at.tzinfo is None: at=at.replace(tzinfo=timezone.utc)
        if mailboxes._challenge_key(conn,old['run_id'])==target:
            limit=at+timedelta(minutes=policy['same_topic_minutes'])
            if limit>due: due=limit;reasons.append('同账号同题提交间隔')
        if at+timedelta(minutes=policy['cross_topic_minutes'])>now:recent.append(at)
    recent.sort()
    if len(recent)>=policy['cross_topic_limit']:
        limit=recent[-policy['cross_topic_limit']]+timedelta(minutes=policy['cross_topic_minutes'])
        if limit>due:due=limit;reasons.append('同账号跨题提交突发上限')
    return due, '；'.join(reasons)


def admit(sid, resume_attempt_id=None, continuation_operation_id=None):
    from . import features, power
    with db.transaction() as conn:
        row=conn.execute('SELECT s.*,m.email,m.platform FROM submissions s JOIN mailboxes m ON m.id=s.mailbox_id WHERE s.id=?',(sid,)).fetchone()
        old=conn.execute('SELECT * FROM submission_queue WHERE submission_id=?',(sid,)).fetchone()
        if (old and resume_attempt_id and continuation_operation_id
                and row['stage']=='draft_continuing' and old['continuation_operation_id']!=continuation_operation_id):
            conn.execute("UPDATE submission_queue SET state='queued',resume_attempt_id=?,continuation_operation_id=? WHERE submission_id=?",(resume_attempt_id,continuation_operation_id,sid))
            old=conn.execute('SELECT * FROM submission_queue WHERE submission_id=?',(sid,)).fetchone()
        if old and old['state']!='queued': return False
        now=_now(); due,reason=_when(conn,row,now)
        if paused() or not features.enabled('auto_submission'):reason='自动提交已暂停'
        elif power.shutdown_requested():reason='安全关机门禁'
        elif not row['is_harvest'] and conn.execute("SELECT 1 FROM submission_queue q JOIN submissions s ON s.id=q.submission_id JOIN mailboxes m ON m.id=s.mailbox_id WHERE q.state='queued' AND s.is_harvest=1 AND lower(m.email)=lower(?) AND m.platform=? LIMIT 1",(row['email'],row['platform'])).fetchone():reason='收割优先';due=max(due,now+timedelta(seconds=1))
        blocked=due>now or reason in ('自动提交已暂停','安全关机门禁','收割优先')
        if not old:
            conn.execute("INSERT INTO submission_queue(submission_id,state,not_before,reason,resume_attempt_id,continuation_operation_id,updated_at) VALUES(?,'queued',?,?,?,?,?)",(sid,due.isoformat(),reason,resume_attempt_id,continuation_operation_id,db.utcnow()))
        if blocked:
            changed=not old or old['reason']!=reason or old['not_before']!=due.isoformat()
            conn.execute("UPDATE submission_queue SET not_before=?,reason=?,updated_at=? WHERE submission_id=?",(due.isoformat(),reason,db.utcnow(),sid))
            conn.execute("UPDATE submissions SET status='queued',stage='queued' WHERE id=?",(sid,))
            if changed:db.append_event_tx(conn,row['run_id'],'controller','submission.queued',{'submission_id':sid,'reason':reason,'not_before':due.isoformat(),'is_harvest':bool(row['is_harvest'])},trial_id=row['trial_id'])
            return False
        conn.execute("UPDATE submission_queue SET state='sending',dispatched_at=?,reason='',updated_at=? WHERE submission_id=?",(now.isoformat(),db.utcnow(),sid))
        return True


def items():
    return [dict(r) for r in db.query("SELECT q.*,s.run_id,s.mailbox_id,s.is_harvest,r.challenge_id,m.email FROM submission_queue q JOIN submissions s ON s.id=q.submission_id JOIN runs r ON r.id=s.run_id JOIN mailboxes m ON m.id=s.mailbox_id WHERE q.state='queued' ORDER BY s.is_harvest DESC,q.not_before,s.created_at")]


def reconcile_interrupted():
    with db.transaction() as conn:
        for row in conn.execute("SELECT submission_id FROM submission_queue WHERE state='sending'").fetchall():
            conn.execute("UPDATE submission_queue SET state='unknown',reason='重启时发送结果未知；不重发',updated_at=? WHERE submission_id=?",(db.utcnow(),row['submission_id']))
            conn.execute("UPDATE submissions SET status='unknown' WHERE id=? AND status='queued'",(row['submission_id'],))


def advance_sync():
    from . import mailboxes, features, power
    if power.shutdown_requested() or paused() or not features.enabled('auto_submission'):return
    for item in items():
        if datetime.fromisoformat(item['not_before'])>_now():continue
        row=db.query_one('SELECT * FROM submissions WHERE id=?',(item['submission_id'],))
        # Revalidate frozen bytes, authorization, target and harvest constraints
        # in the same existing send path; unknown/sending operations never enter.
        with db.transaction() as conn:
            try:mailboxes._check_budget(conn,row['run_id'],existing_submission_id=row['id'],terminal_harvest=bool(row['is_harvest']))
            except mailboxes.MailboxError as exc:
                conn.execute("UPDATE submission_queue SET state='cancelled',reason=?,updated_at=? WHERE submission_id=?",(str(exc),db.utcnow(),row['id']))
                conn.execute("UPDATE submissions SET status='failed',reservation_released=1,error=? WHERE id=?",(str(exc),row['id']))
                continue
        mailboxes._perform_submission(row['id'],mailboxes._platform_for_run(row['run_id']),mailboxes._run_challenge_id(row['run_id']),resume_attempt_id=item['resume_attempt_id'],continuation_operation_id=item['continuation_operation_id'])
