"""Persisted acknowledgements; event cursor and alerts advance atomically."""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from . import db, run_clock


def _insert(conn, key, run, kind, title, payload):
    from .mailbox_platform import public_feedback
    from . import config
    safe = public_feedback(payload, *config.sensitive_values())
    conn.execute('INSERT OR IGNORE INTO alerts(id,dedupe_key,run_id,challenge_id,kind,title,payload,created_at)'
                 ' VALUES(?,?,?,?,?,?,?,?)', ('alert_' + uuid.uuid4().hex[:12], key, run['id'], run['challenge_id'],
                                            kind, title, json.dumps(safe, ensure_ascii=False), db.utcnow()))


def synchronize() -> None:
    with db.transaction() as conn:
        cursor = conn.execute("SELECT value FROM system_state WHERE key='alerts_event_cursor'").fetchone()
        rows = conn.execute('SELECT rowid AS event_row,* FROM events WHERE rowid>? ORDER BY rowid',
                            (int(cursor['value']) if cursor else 0,)).fetchall()
        for event in rows:
            run = conn.execute('SELECT * FROM runs WHERE id=?', (event['run_id'],)).fetchone()
            if not run:
                continue
            kind = event['type']
            payload = json.loads(event['payload'])
            title = {'method.major_change': '研究方法大改', 'run.blocked': '研究遇到阻塞', 'run.paused': '研究已暂停', 'run.failed': '研究运行出错',
                     'run.needs_attention': '研究需要关注', 'run.runtime_error': '研究运行出错', 'harvest.done': '自动收割已受理',
                     'harvest.failed': '自动收割失败', 'harvest.unknown': '自动收割状态不明'}.get(kind)
            if kind=='harvest.started' and payload.get('last_mailbox_quota'):
                title='自动收割开始：使用本题主邮箱最后一次额度'
            if kind.endswith(('.error', '.failed')) or kind in ('submission.unknown', 'prime.crashed') or (kind == 'job.observed' and payload.get('status') == 'Failed'):
                title = '研究操作出错或状态不明'
            if kind in ('submission.scored', 'submission.score_corrected'):
                sub = conn.execute('SELECT * FROM submissions WHERE id=?', (payload.get('submission_id'),)).fetchone()
                if sub and sub['score_confidence'] == 'confirmed' and sub['score'] is not None and not sub['score_anomaly']:
                    prior = conn.execute("SELECT MAX(s.score) FROM submissions s JOIN runs r ON r.id=s.run_id"
                                         " WHERE r.challenge_id=? AND s.id<>? AND s.score_confidence='confirmed'"
                                         " AND s.score_status='scored'", (run['challenge_id'], sub['id'])).fetchone()[0]
                    if prior is None or sub['score'] > prior:
                        title = '刷新最好平台成绩'
                        payload = payload | {'confirmed_score': sub['score']}
            if kind == 'local_score.registered':
                score = conn.execute('SELECT * FROM local_scores WHERE id=?', (payload.get('local_score_id'),)).fetchone()
                if score and score['science_score'] is not None and score['score_source'] in ('system', 'executor_verified'):
                    prior = conn.execute("SELECT MAX(science_score) FROM local_scores WHERE challenge_id=? AND id<>?"
                                         " AND scorer_version=? AND score_source IN ('system','executor_verified')",
                                         (run['challenge_id'], score['id'], score['scorer_version'])).fetchone()[0]
                    if prior is None or score['science_score'] > prior:
                        title = '刷新最好本地正式成绩'
                        payload = payload | {'science_score': score['science_score'], 'scorer_version': score['scorer_version']}
            if title:
                _insert(conn, 'event:' + event['event_id'], run, kind, title, payload)
        if rows:
            conn.execute("INSERT OR REPLACE INTO system_state VALUES('alerts_event_cursor',?)", (str(rows[-1]['event_row']),))
        now = datetime.now(timezone.utc)
        from .mailboxes import _instant
        for sub in conn.execute("SELECT * FROM submissions WHERE status='submitted' AND COALESCE(score_is_final,0)=0").fetchall():
            started=_instant(sub['submitted_at'] or sub['science_observed_at'])
            if started and (now-started).total_seconds()>7200:
                run=conn.execute('SELECT * FROM runs WHERE id=?',(sub['run_id'],)).fetchone()
                if run:_insert(conn,'scoring-slow:'+sub['id'],run,'submission.scoring_slow','平台评分已超过两小时',{'submission_id':sub['id'],'minutes':(now-started).total_seconds()/60})
        for rate in conn.execute("SELECT * FROM model_rate_limits WHERE state IN ('waiting','in_flight')").fetchall():
            from .mailboxes import _instant
            started = _instant(rate['first_at'])
            run = conn.execute('SELECT * FROM runs WHERE id=?', (rate['run_id'],)).fetchone()
            if run and run['gate'] != 'awaiting_method_approval' and started and (now - started).total_seconds() > 600:
                _insert(conn, f"rate:{run['id']}:{rate['role']}:{rate['first_at']}", run,
                        'model.long_rate_limit', '模型限速已超过十分钟', {'role': rate['role'], 'retry_at': rate['retry_at']})
        for rate in conn.execute('SELECT * FROM model_provider_backoff').fetchall():
            from .mailboxes import _instant
            started = _instant(rate['first_at'])
            retry = _instant(rate['retry_at'])
            if not started or not retry or retry <= now or (now - started).total_seconds() <= 600:
                continue
            for run in conn.execute("SELECT * FROM runs WHERE phase IN ('running','waiting_score') AND gate!='awaiting_method_approval'").fetchall():
                choices = json.loads(run['config_snapshot']).get('settings', {})
                if any((choices.get(role, {}).get('provider') or choices.get(role, {}).get('runtime')) == rate['provider'] for role in ('brain', 'executor', 'reviewer', 'post_review')):
                    _insert(conn, f"provider:{run['id']}:{rate['provider']}:{rate['first_at']}", run,
                            'model.long_rate_limit', '模型提供方限速已超过十分钟',
                            {'provider': rate['provider'], 'retry_at': rate['retry_at']})
        for run in conn.execute("SELECT * FROM runs WHERE phase IN ('running','waiting_score') AND gate!='awaiting_method_approval'").fetchall():
            auth = conn.execute('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],)).fetchone()
            if auth and (auth['max_run_minutes'] or auth['unlimited_resources']) and run['started_at']:
                remaining = run_clock.remaining(run, auth)
                if remaining <= (300 if auth['unlimited_resources'] else min(300, auth['max_run_minutes'] * 6)):
                    _insert(conn, 'budget:' + auth['id'], run, 'authorization.near_exhaustion',
                            '本轮时间授权即将耗尽', {'remaining_seconds': remaining})


def pending() -> list[dict]:
    synchronize()
    return [dict(row) | {'payload': json.loads(row['payload'])} for row in
            db.query('SELECT * FROM alerts WHERE acknowledged_at IS NULL ORDER BY created_at,id LIMIT 100')]


def acknowledge(alert_id: str) -> dict:
    db.execute('UPDATE alerts SET acknowledged_at=COALESCE(acknowledged_at,?) WHERE id=?', (db.utcnow(), alert_id))
    row = db.query_one('SELECT id,acknowledged_at FROM alerts WHERE id=?', (alert_id,))
    if not row:
        raise ValueError('弹窗不存在')
    return dict(row)
