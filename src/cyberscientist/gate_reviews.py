"""Audited, individual gate reviews. No mutation of provider-owned records."""
import hashlib
import json
from . import db, observation


def record(rule, content_hash, *, source, run_id=None, trial_id=None, line=None,
           exact_stored=False, context='', risk='high'):
    identity = json.dumps([run_id, trial_id, rule, content_hash, line], ensure_ascii=False)
    ident = 'gate_' + hashlib.sha256(identity.encode()).hexdigest()[:24]
    db.execute('INSERT OR IGNORE INTO gate_reviews(id,run_id,trial_id,rule,content_hash,source,line,exact_stored,context,risk,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
               (ident, run_id, trial_id, rule, content_hash, source, line, int(exact_stored),
                observation.strip_secrets(context), risk, 'pending', db.utcnow()))
    return dict(db.query_one('SELECT * FROM gate_reviews WHERE id=?', (ident,)))


def pending():
    return {'items': [dict(r) for r in db.query("SELECT * FROM gate_reviews WHERE status='pending' ORDER BY created_at,id")]}


def resolve(ident, *, reason, false_positive=False):
    if not false_positive or not isinstance(reason, str) or not reason.strip():
        raise ValueError('人工放行须声明误报并填写理由')
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM gate_reviews WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('复核项不存在')
        if row['exact_stored']:
            raise ValueError('命中已存凭据原文，禁止人工放行')
        conn.execute("UPDATE gate_reviews SET status='false_positive',reason=?,resolved_at=? WHERE id=?", (observation.strip_secrets(reason.strip()), db.utcnow(), ident))
        if row['run_id']:
            db.append_event_tx(conn, row['run_id'], 'user', 'gate.resolved', {'id': ident, 'rule': row['rule'], 'false_positive': True, 'reason': observation.strip_secrets(reason)}, trial_id=row['trial_id'])
    return dict(db.query_one('SELECT * FROM gate_reviews WHERE id=?', (ident,)))
