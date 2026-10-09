import json
from datetime import datetime,timedelta,timezone

import pytest

from cyberscientist import alerts,competition_panel,config,db,mailboxes,score_wait,submission_receipts
from cyberscientist.mailbox_platform import final_score
from test_auto_harvest import seed


@pytest.mark.parametrize('status',['pending_review','needs_review'])
def test_manual_review_keeps_polling_and_science_run_open(monkeypatch,status):
    rid,sub=seed(10)
    db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,))
    db.execute("UPDATE submissions SET score=NULL,score_status='pending',score_confidence=NULL,receipt_details_json='{}',"
        "harbor_score=NULL,science_observed_at=NULL,submitted_at=? WHERE id=?",
        ((datetime.now(timezone.utc)-timedelta(hours=3)).isoformat(),sub['id']))
    raw={'status':status,'scoringState':{'scoreIsFinal':False}}
    platform=mailboxes._platform();calls=[]
    monkeypatch.setattr(platform,'fetch_attempt',lambda *a:calls.append('attempt') or raw,raising=False)
    # Even a final display score must not close an explicitly pending review.
    monkeypatch.setattr(platform,'fetch_score_details',lambda *a:calls.append('score') or {
        'scoringState':{'scoreIsFinal':True,'displayScore':70}},raising=False)
    monkeypatch.setattr(mailboxes,'_platform',lambda:platform)
    for _ in range(2):
        result=mailboxes.poll_scores(run_id=rid,manual=True)
        assert result['updated']==0
    assert calls==['attempt','score','attempt','score']
    row=db.query_one('SELECT * FROM submissions WHERE id=?',(sub['id'],))
    assert row['score'] is None and row['status']=='submitted' and row['polling_stopped_at'] is None
    assert row['platform_status']==status
    assert db.query_one('SELECT phase FROM runs WHERE id=?',(rid,))[0]=='running'
    panel=competition_panel.view()['items'][0]
    assert panel['receipt']['platform_status']==status and panel['scoring_seconds'] is None
    pending=alerts.pending()
    assert any(item['kind']=='submission.manual_review' for item in pending)
    assert not any(item['kind']=='submission.scoring_slow' for item in pending)


@pytest.mark.parametrize('status',['pending_review','needs_review'])
def test_manual_review_is_not_final_even_with_conflicting_final_flag(status):
    assert final_score({'status':status,'scoringState':{'scoreIsFinal':True,'displayScore':100}}) is None
    assert final_score({'scoringState':{'state':status,'scoreIsFinal':True,'displayScore':100}}) is None


def test_manual_review_can_wake_legacy_score_wait_without_inventing_a_score():
    rid,sub=seed(10)
    db.execute("UPDATE submissions SET score_status='pending',score=NULL,score_confidence=NULL,science_observed_at=NULL WHERE id=?",(sub['id'],))
    assert score_wait.enter(rid)
    with db.transaction() as conn:
        submission_receipts.observe_tx(conn,conn.execute('SELECT * FROM submissions WHERE id=?',(sub['id'],)).fetchone(),
            {'status':'pending_review'})
    ready=score_wait.confirmed(rid)
    assert ready['id']==sub['id'] and ready['score'] is None
