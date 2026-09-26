"""Pair pre-submission hypotheses with confirmed score observations."""
from __future__ import annotations

import json

from . import db


def outcomes(run_id: str, limit: int = 12, through_seq: int | None = None) -> list[dict]:
    rows=db.query("SELECT id,prediction_md,score,harbor_score,trace_score,"
                  "prediction_verdict,prediction_note_md,is_harvest,score_confidence FROM submissions"
                  " WHERE run_id=? AND prediction_md IS NOT NULL ORDER BY created_at,id",(run_id,))
    snapshots=None
    if through_seq is not None:
        snapshots={}
        for event in db.query("SELECT payload FROM events WHERE run_id=? AND seq<=?"
                              " AND type IN ('submission.scored','submission.score_corrected')"
                              " ORDER BY seq",(run_id,through_seq)):
            payload=json.loads(event['payload'])
            sid=payload.get('submission_id')
            if sid:
                snapshots[sid]=payload if payload.get('score_confidence')=='confirmed' else None
    paired=[]
    previous=None
    for row in rows:
        snap=snapshots.get(row['id']) if snapshots is not None else None
        if snapshots is not None and snap is None: continue
        if snapshots is None and row['score_confidence']!='confirmed': continue
        values={key:(snap.get(key) if snap is not None else row[key])
                for key in ('score','harbor_score','trace_score')}
        def delta(key):
            return (values[key]-previous[key] if previous is not None
                    and values[key] is not None and previous[key] is not None else None)
        paired.append({'submission_id':row['id'],'prediction_md':row['prediction_md'],
                       'displayScore':values['score'],'harbor_score':values['harbor_score'],
                       'trace_score':values['trace_score'],
                       'component_changes':{'displayScore':delta('score'),
                                            'harbor_score':delta('harbor_score'),
                                            'trace_score':delta('trace_score')},
                       'prediction_verdict':row['prediction_verdict'],
                       'prediction_note_md':row['prediction_note_md'],
                       'is_harvest':bool(row['is_harvest'])})
        previous=values
    return paired[-limit:]


def record_verdicts_tx(conn, run_id: str, verdicts: list[dict], source_id: str) -> None:
    for item in verdicts:
        from .observation import strip_secrets
        note=strip_secrets(item['note_md'])
        if conn.execute("SELECT 1 FROM events WHERE run_id=? AND type='prediction.verdict_recorded'"
                        " AND json_extract(payload,'$.source_id')=?"
                        " AND json_extract(payload,'$.submission_id')=? LIMIT 1",
                        (run_id,source_id,item['submission_id'])).fetchone():
            continue
        row=conn.execute("SELECT prediction_md,score_confidence,prediction_verdict,"
                         "prediction_note_md FROM submissions WHERE id=? AND run_id=?",
                         (item['submission_id'],run_id)).fetchone()
        if not row or not row['prediction_md'] or row['score_confidence']!='confirmed':
            db.append_event_tx(conn,run_id,'controller','prediction.verdict_rejected',
                               {'submission_id':item['submission_id'],
                                'reason':'该 Run 没有相应已确认评分的预测'})
            continue
        if row['prediction_verdict']==item['verdict'] and row['prediction_note_md']==note:
            continue
        conn.execute("UPDATE submissions SET prediction_verdict=?,prediction_note_md=? WHERE id=?",
                     (item['verdict'],note,item['submission_id']))
        db.append_event_tx(conn,run_id,'brain','prediction.verdict_recorded',
                           {'submission_id':item['submission_id'],
                            'verdict':item['verdict'],'note_md':note,
                            'source_id':source_id})
