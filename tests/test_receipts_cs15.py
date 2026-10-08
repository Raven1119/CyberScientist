"""Synthetic worker shapes; private real receipt replay is recorded separately."""
import json
from datetime import datetime,timedelta,timezone
from cyberscientist import db,mailboxes,submission_receipts as receipts,score_wait,alerts,config
from test_auto_harvest import seed


def test_science_before_trace_and_final_confirmation_and_idempotent():
    rid,source=seed(10)
    db.execute("UPDATE submissions SET score_status='pending',score=NULL,score_confidence=NULL WHERE id=?",(source['id'],))
    science={'scoringState':{'scoreIsFinal':False,'displayScore':0},'scoringDetails':{'source':'harbor_worker','harbor_reward':1,'counts_toward_season':False},'scorecard':{'harbor_score':100}}
    def observe(body):
        with db.transaction() as conn:
            mailboxes._record_feedback(conn,conn.execute('SELECT * FROM submissions WHERE id=?',(source['id'],)).fetchone(),'attempt',body)
    assert score_wait.enter(rid)
    observe(science)
    row=db.query_one('SELECT * FROM submissions WHERE id=?',(source['id'],))
    assert row['harbor_score']==100 and row['harbor_reward']==1 and row['trace_score'] is None
    assert row['score'] is None and row['score_is_final']==0 and row['science_observed_at']
    assert score_wait.confirmed(rid)['id']==source['id']
    observe(science)
    complete=science|{'resultsJson':json.dumps({'trace_score':82.925,'trace_decision':'accept','trace_low_score_reasons':[{'code':'N11_OUTPUT_NOT_CAUSALLY_SUPPORTED','score_effect':-6}],'trace_missing_evidence':['not_visible']}),'scoringState':{'scoreIsFinal':True,'displayScore':100}}
    observe(complete)
    row=db.query_one('SELECT * FROM submissions WHERE id=?',(source['id'],))
    assert row['trace_score']==82.925 and row['trace_decision']=='accept' and row['score_is_final']==1
    events=[e['type'] for e in db.query("SELECT type FROM events WHERE run_id=? AND type IN ('submission.science_observed','submission.receipt_observed') ORDER BY seq",(rid,))]
    assert events==['submission.science_observed','submission.receipt_observed']
    assert len(json.dumps(receipts.summary(json.loads(row['receipt_details_json'])),ensure_ascii=False))<=1500


def test_display_zero_does_not_become_science_and_slow_scoring_alert():
    rid,source=seed(10)
    parsed=receipts.parse({'scoringState':{'scoreIsFinal':False,'displayScore':0}})
    assert 'harbor_score' not in parsed and 'harbor_reward' not in parsed
    db.execute("UPDATE submissions SET status='submitted',score_is_final=0,submitted_at=? WHERE id=?",((datetime.now(timezone.utc)-timedelta(hours=3)).isoformat(),source['id']))
    assert any(a['kind']=='submission.scoring_slow' for a in alerts.pending())
    alerts.pending();assert len(db.query("SELECT * FROM alerts WHERE kind='submission.scoring_slow'"))==1


def test_parser_boolean_and_nan_not_numbers():
    assert receipts.parse({'scorecard':{'harbor_reward':True,'harbor_score':float('nan')}})=={}


def test_early_science_queues_pi_without_shadow_or_final_score():
    rid,source=seed(10)
    with db.transaction() as conn:
        receipts.observe_tx(conn,source,{'scorecard':{'harbor_score':100},'scoringState':{'scoreIsFinal':False}})
    request=db.query_one("SELECT * FROM review_requests WHERE run_id=? AND trigger='submission_feedback'",(rid,))
    assert request and request['status']=='pending'
