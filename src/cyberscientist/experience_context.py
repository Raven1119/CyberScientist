"""Frozen, bounded experience delivery and reported adoption; never causal credit."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from . import config, db, experiences


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def terms(text: str) -> set[str]:
    lowered = text.casefold()
    result = set(re.findall(r'[a-z0-9][a-z0-9_.+-]*', lowered))
    for phrase in re.findall(r'[\u4e00-\u9fff]+', lowered):
        result.add(phrase)
        result.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    return result


def effective(challenge_id: str | None) -> list[dict]:
    result = []
    for entry in experiences.active_experiences(challenge_id):
        if entry.get('expires_at'):
            try:
                expires = datetime.fromisoformat(entry['expires_at'].replace('Z', '+00:00'))
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires < datetime.now(timezone.utc):
                    continue
            except ValueError:
                pass
        result.append(entry)
    return result


def index(challenge_id: str | None, *, entries=None) -> list[dict]:
    values = effective(challenge_id) if entries is None else entries
    return [{key: entry.get(key, '') for key in ('id', 'title', 'applicability', 'kind', 'audience', 'scope', 'revision_id', 'revision_hash')}
            for entry in values]


def select(challenge_id: str | None, budget: int | None = None, goal: str = "",
           role: str = 'both', *, _entries=None) -> list[dict]:
    if budget is None:
        budget = config.load_settings()["memory"]["max_injected_characters"]
    entries = list(effective(challenge_id) if _entries is None else _entries)
    budget = max(0, budget - len(encode(index(challenge_id, entries=entries))))
    if role in ('brain','executor'):
        entries = [entry for entry in entries if entry.get('audience','both') in (role,'both')]
    words = terms(goal)
    def relevance(entry):
        matches = words & terms(entry['title'] + ' ' + entry.get('applicability', '') + ' ' + ' '.join(entry.get('tags', [])) + ' ' + entry['body_md'][:600])
        return sum(4 if re.match(r'[a-z0-9]', token) else 1 for token in matches)
    entries.sort(key=lambda entry: (-relevance(entry), entry['scope'] != 'challenge', entry['id']))
    selected = []
    for entry in entries:
        item = {k: v for k, v in entry.items() if k not in ('full_content', 'current_hash')}
        item['body_md'] = entry['body_md']
        item['body_truncated'] = False
        if len(encode(selected + [item])) > budget:
            room = budget - len(encode(selected + [dict(item, body_md='')])) - 32
            if room < 100:
                continue
            item['body_md'] = item['body_md'][:room]
            item['body_truncated'] = True
        if len(encode(selected + [item])) <= budget:
            selected.append(item)
    return selected


def run_goal(run_id: str, trial_id: str | None = None) -> str:
    run = db.query_one('SELECT challenge_id,objective_md,intention,current_trial_id FROM runs WHERE id=?', (run_id,))
    challenge = db.query_one('SELECT content FROM challenges WHERE id=?', (run['challenge_id'],))
    trial = db.query_one('SELECT goal FROM trials WHERE id=?', (trial_id or run['current_trial_id'],))
    return '\n'.join(text for text in (run['objective_md'], run['intention'],
                                       challenge['content'] if challenge else None,
                                       trial['goal'] if trial else None) if text)


def freeze(run_id: str, trial_id: str | None, boundary: str, items=None,
           role: str = 'both') -> dict:
    row = db.query_one('SELECT content_json FROM experience_contexts WHERE run_id=? AND boundary=?',
                       (run_id, boundary))
    if row:
        return json.loads(row['content_json'])
    run = db.query_one('SELECT challenge_id,intention FROM runs WHERE id=?', (run_id,))
    all_entries = effective(run['challenge_id'])
    if items is None:
        items = select(run['challenge_id'], goal=run_goal(run_id, trial_id), role=role, _entries=all_entries)
    with db.transaction() as conn:
        return freeze_tx(conn, run_id, trial_id, boundary, items, index(run['challenge_id'], entries=all_entries))


def freeze_tx(conn, run_id, trial_id, boundary, items, index_items=None):
    existing = conn.execute('SELECT content_json FROM experience_contexts WHERE run_id=? AND boundary=?',
                            (run_id, boundary)).fetchone()
    if existing:
        return json.loads(existing['content_json'])
    context = {'id': 'ctx_' + uuid.uuid4().hex, 'run_id': run_id, 'trial_id': trial_id,
               'boundary': boundary, 'items': items, 'index': index_items if index_items is not None else index(None, entries=items),
               'index_sha256': hashlib.sha256(encode(index_items if index_items is not None else index(None, entries=items)).encode()).hexdigest(),
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
