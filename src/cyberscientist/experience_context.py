"""Frozen, bounded experience delivery and reported adoption; never causal credit."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from . import config, db, experiences


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def select(challenge_id: str | None, budget: int | None = None, goal: str = "") -> list[dict]:
    if budget is None:
        budget = config.load_settings()["memory"]["max_injected_characters"]
    entries = experiences.active_experiences(challenge_id)
    # Ownership is decidable; free-text applicability is retained for model judgment.
    words = set(goal.casefold().split())
    entries.sort(key=lambda x: (x['scope'] != 'challenge',
        -len(words & set((x['title'] + ' ' + ' '.join(x.get('tags',[]))).casefold().split())), x['id']))
    selected = []
    for entry in entries:
        expires = entry.get('expires_at')
        if expires:
            try:
                if datetime.fromisoformat(expires.replace('Z', '+00:00')).replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    continue
            except ValueError:
                pass  # Unknown expiry formats remain labelled, not silently interpreted.
        item = {k: v for k, v in entry.items() if k not in ('full_content', 'current_hash')}
        item['body_md'] = entry['body_md'][:2500]
        item['body_truncated'] = len(entry['body_md']) > 2500
        if len(encode(selected + [item])) > budget:
            room = budget - len(encode(selected + [dict(item, body_md='')])) - 32
            if room < 100:
                continue
            item['body_md'] = item['body_md'][:room]
            item['body_truncated'] = True
        if len(encode(selected + [item])) <= budget:
            selected.append(item)
    return selected


def freeze(run_id: str, trial_id: str | None, boundary: str, items=None) -> dict:
    row = db.query_one('SELECT content_json FROM experience_contexts WHERE run_id=? AND boundary=?',
                       (run_id, boundary))
    if row:
        return json.loads(row['content_json'])
    run = db.query_one('SELECT challenge_id,intention FROM runs WHERE id=?', (run_id,))
    items = select(run['challenge_id'],goal=run['intention'] or '') if items is None else items
    with db.transaction() as conn:
        return freeze_tx(conn, run_id, trial_id, boundary, items)


def freeze_tx(conn, run_id, trial_id, boundary, items):
    existing = conn.execute('SELECT content_json FROM experience_contexts WHERE run_id=? AND boundary=?',
                            (run_id, boundary)).fetchone()
    if existing:
        return json.loads(existing['content_json'])
    context = {'id': 'ctx_' + uuid.uuid4().hex, 'run_id': run_id, 'trial_id': trial_id,
               'boundary': boundary, 'items': items,
               'sha256': hashlib.sha256(encode(items).encode()).hexdigest()}
    conn.execute('INSERT INTO experience_contexts(id,run_id,trial_id,boundary,content_json,created_at)'
                 ' VALUES(?,?,?,?,?,?)',
                 (context['id'],run_id,trial_id,boundary,encode(context),db.utcnow()))
    db.append_event_tx(conn,run_id,'controller','experience.presented',context,trial_id=trial_id)
    return context


def for_trial(run_id, trial_id):
    row = db.query_one('SELECT content_json FROM experience_contexts WHERE run_id=? AND boundary=?',
                       (run_id, f'trial:{trial_id}'))
    return json.loads(row['content_json']) if row else None


def adopt_tx(conn, run_id, trial_id, declarations, source, declaration_id):
    for declaration in declarations:
        row = conn.execute('SELECT * FROM experience_contexts WHERE id=? AND run_id=?',
                            (declaration['context_id'],run_id)).fetchone()
        items = json.loads(row['content_json'])['items'] if row else []
        match = next((it for it in items if it['id']==declaration['experience_id']
                      and it['revision_id']==declaration['revision_id']), None)
        if not match or (row['trial_id'] is not None and row['trial_id'] != trial_id):
            raise ValueError('采用声明不属于本 Trial 已交付的冻结版本')
        if conn.execute('SELECT 1 FROM experience_uses WHERE run_id=? AND declaration_id=?'
                        ' AND context_id=? AND experience_id=?',
                        (run_id,declaration_id,row['id'],match['id'])).fetchone():
            continue
        payload = {**declaration,'revision_hash':match['revision_hash'],
                   'declaration_id':declaration_id,'semantics':'reported','trial_id':trial_id}
        event = db.append_event_tx(conn,run_id,source,'experience.adopted',payload,trial_id=trial_id)
        conn.execute('INSERT INTO experience_uses(run_id,trial_id,context_id,experience_id,revision_id,'
                     ' revision_hash,declaration_id,adopted_seq,semantics) VALUES(?,?,?,?,?,?,?,?,?)',
                     (run_id,trial_id,row['id'],match['id'],match['revision_id'],match['revision_hash'],
                      declaration_id,event['seq'],'reported'))


def link_result_tx(conn, submission, score, score_seq):
    created = conn.execute("SELECT seq FROM events WHERE run_id=? AND type='submission.created'"
                           " AND json_extract(payload,'$.submission_id')=?",
                           (submission['run_id'],submission['id'])).fetchone()
    if not created:
        return
    uses = conn.execute('SELECT * FROM experience_uses WHERE run_id=? AND trial_id=? AND adopted_seq<?',
                        (submission['run_id'],submission['trial_id'],created['seq'])).fetchall()
    for use in uses:
        db.append_event_tx(conn,submission['run_id'],'controller','experience.result_linked',{
            'context_id':use['context_id'],'experience_id':use['experience_id'],
            'revision_id':use['revision_id'],'adopted_seq':use['adopted_seq'],
            'submission_id':submission['id'],'package_sha256':submission['package_sha256'],
            'score':score,'score_seq':score_seq,'semantics':'temporal_link_not_causal_credit'},
            trial_id=submission['trial_id'])


def retract_result_tx(conn, submission, reason):
    """Append a revision marker; old score links remain auditable."""
    db.append_event_tx(conn,submission['run_id'],'controller','experience.result_retracted',{
        'submission_id':submission['id'],'reason':reason,
        'semantics':'supersedes_previous_confirmed_links'},trial_id=submission['trial_id'])


def rebuild_uses(run_id):
    """Adoption projection can be reconstructed solely from append-only events."""
    with db.transaction() as conn:
        conn.execute('DELETE FROM experience_uses WHERE run_id=?',(run_id,))
        for row in conn.execute("SELECT * FROM events WHERE run_id=? AND type='experience.adopted' ORDER BY seq",(run_id,)).fetchall():
            p=json.loads(row['payload'])
            conn.execute('INSERT INTO experience_uses(run_id,trial_id,context_id,experience_id,revision_id,'
                         ' revision_hash,declaration_id,adopted_seq,semantics) VALUES(?,?,?,?,?,?,?,?,?)',
                         (run_id,row['trial_id'],p['context_id'],p['experience_id'],p['revision_id'],
                          p['revision_hash'],p['declaration_id'],row['seq'],p['semantics']))
