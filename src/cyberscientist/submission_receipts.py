"""Parse observed worker fields without deriving science from display scores."""
import json
import math
from . import db


def _object(value):
    if isinstance(value, str):
        try: value=json.loads(value)
        except ValueError: return {}
    return value if isinstance(value,dict) else {}


def parse(body):
    body=_object(body)
    results=_object(body.get('resultsJson'))
    card=_object(body.get('scorecard'))
    details=_object(body.get('scoringDetails'))
    state=_object(body.get('scoringState'))
    result={}
    for key in ('harbor_reward','harbor_score','trace_score','trace_factor'):
        sources=(card,results,details,body) if key!='trace_factor' else (details,results,card,body)
        for source in sources:
            value=source.get(key)
            if type(value) in (int,float) and math.isfinite(value): result[key]=value;break
    for key in ('trace_decision','scored_by'):
        for source in (results,details,card,body):
            if isinstance(source.get(key),str): result[key]=source[key];break
    if isinstance(details.get('source'),str): result['scoring_source']=details['source']
    if type(details.get('counts_toward_season')) is bool: result['counts_toward_season']=details['counts_toward_season']
    if type(state.get('scoreIsFinal')) is bool: result['score_is_final']=state['scoreIsFinal']
    if type(state.get('displayScore')) in (int,float) and math.isfinite(state['displayScore']): result['display_score']=state['displayScore']
    if isinstance(details.get('summary'),str): result['judge_summary']=details['summary']
    for source,key,target in ((results,'trace_low_score_reasons','deductions'),(results,'trace_missing_evidence','missing_evidence')):
        if isinstance(source.get(key),list): result[target]=source[key]
    return result


def summary(value):
    """Bounded PI payload; original fields stay in private database feedback."""
    short={k:value.get(k) for k in ('harbor_reward','harbor_score','trace_score','trace_factor','trace_decision','scoring_source','score_is_final','display_score')}
    short={k:v[:100] if isinstance(v,str) else v for k,v in short.items()}
    short['deductions']=[{'code':str(d.get('code'))[:100],'score_effect':d.get('score_effect') if type(d.get('score_effect')) in (float,int) else None} for d in value.get('deductions',[])[:12] if isinstance(d,dict)]
    short['missing_evidence']=[str(v)[:100] for v in value.get('missing_evidence',[])[:4]]
    short['judge_summary']=str(value.get('judge_summary') or '')[:150]
    encoded=json.dumps(short,ensure_ascii=False)
    while len(encoded)>1500 and short['deductions']:
        short['deductions'].pop();encoded=json.dumps(short,ensure_ascii=False)
    return short


def observe_tx(conn,row,body):
    incoming=parse(body)
    if not incoming:return False
    current=conn.execute('SELECT * FROM submissions WHERE id=?',(row['id'],)).fetchone()
    previous=json.loads(current['receipt_details_json'] or '{}')
    merged=previous|incoming
    if merged==previous:return False
    from . import trace_hints
    trace_hints.record_tx(conn,row,merged)
    when=db.utcnow()
    columns={key:incoming[key] for key in ('harbor_reward','harbor_score','trace_score','trace_factor','trace_decision','scoring_source','scored_by','counts_toward_season','score_is_final') if key in incoming}
    columns.update(receipt_details_json=json.dumps(merged,ensure_ascii=False),receipt_observed_at=when)
    science_changed=any(key in incoming and previous.get(key)!=incoming[key] for key in ('harbor_reward','harbor_score'))
    if science_changed:columns['science_observed_at']=current['science_observed_at'] or when
    conn.execute('UPDATE submissions SET '+','.join(key+'=?' for key in columns)+' WHERE id=?',(*columns.values(),row['id']))
    payload={'submission_id':row['id'],'platform_ref':row['platform_ref'],'receipt_summary':summary(merged)}
    if science_changed:
        db.append_event_tx(conn,row['run_id'],'controller','submission.science_observed',payload,trial_id=row['trial_id'])
    has_receipt=(merged.get('score_is_final') is True or merged.get('trace_score') is not None
                 or merged.get('trace_decision') is not None)
    if has_receipt and merged.get('harbor_score') is None and not conn.execute(
            "SELECT 1 FROM events WHERE run_id=? AND type='submission.harbor_missing'"
            " AND json_extract(payload,'$.submission_id')=?",(row['run_id'],row['id'])).fetchone():
        db.append_event_tx(conn,row['run_id'],'controller','submission.harbor_missing',
            payload | {'reason':'回执没有 harbor 科学分，可能是赛后补交的评分路径；科学分保持 unknown。'},
            trial_id=row['trial_id'])
    trace_changed=any(k in incoming and previous.get(k)!=incoming[k] for k in ('trace_score','trace_decision','deductions','missing_evidence'))
    if trace_changed:
        db.append_event_tx(conn,row['run_id'],'controller','submission.receipt_observed',payload,trial_id=row['trial_id'])
    if science_changed or trace_changed:
        run=conn.execute('SELECT phase FROM runs WHERE id=?',(row['run_id'],)).fetchone()
        if run and run['phase']=='running' and not conn.execute("SELECT 1 FROM review_requests WHERE run_id=? AND source='lifecycle' AND trigger='submission_feedback' AND status='pending'",(row['run_id'],)).fetchone():
            from . import collab
            collab._enqueue_request_tx(conn,row['run_id'],source='lifecycle',blocking=False,trigger='submission_feedback')
    return True
