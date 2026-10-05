"""Persisted score wait: original Run/authorization, no model polling."""
from . import config, db, run_clock


def enabled():
    return config.load_settings().get('features', {}).get('await_score', True)


def pending(run_id):
    return db.query_one("SELECT * FROM submissions WHERE run_id=? AND is_harvest=0"
        " AND status='submitted' AND COALESCE(score_confidence,'')!='confirmed' ORDER BY created_at DESC LIMIT 1", (run_id,))


def enter(run_id):
    if not enabled() or not (submission := pending(run_id)):
        return False
    with db.transaction() as conn:
        changed = conn.execute("UPDATE runs SET phase='waiting_score',gate='open',block_reason='等待平台确认评分',"
            "state_version=state_version+1 WHERE id=? AND phase='running'", (run_id,)).rowcount
        if changed:
            conn.execute("INSERT OR REPLACE INTO system_state(key,value) VALUES(?,?)", ('await_score:' + run_id, submission['id']))
            conn.execute("UPDATE trials SET status='done' WHERE id=? AND run_id=? AND status IN ('active','stalled')", (submission['trial_id'], run_id))
            conn.execute("UPDATE trials SET status='interrupted' WHERE run_id=? AND id!=? AND status IN ('active','stalled')", (run_id, submission['trial_id']))
            conn.execute("UPDATE review_requests SET status='obsolete',updated_at=? WHERE run_id=? AND status='pending'", (db.utcnow(), run_id))
            db.append_event_tx(conn, run_id, 'controller', 'run.waiting_score', {
                'submission_id': submission['id'], 'active_time_charged': False,
                'notice': '停止原生会话；确认出分后在原Run唤醒PI决定下一步'})
    if changed:
        # Freeze old wall-clock Runs as well, without losing their prior elapsed time.
        row = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
        if not row['clock_version']:
            run_clock.start(run_id)
        run_clock.freeze(run_id)
    return bool(changed)


def confirmed(run_id):
    marker = db.query_one('SELECT value FROM system_state WHERE key=?', ('await_score:' + run_id,))
    if not marker:
        return None
    return db.query_one("SELECT * FROM submissions WHERE id=? AND run_id=? AND score_status='scored'"
        " AND score_confidence='confirmed'", (marker['value'], run_id))
