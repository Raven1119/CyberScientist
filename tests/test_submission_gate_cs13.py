import json
from datetime import datetime, timedelta, timezone
import pytest
from cyberscientist import submission_gate as gate, config, db, mailboxes, features, auto_harvest
from test_auto_harvest import seed
from test_mailboxes import _make_package, _extra_run, _set_scored


def policy():
    settings=config.load_settings();settings['submission_policy']=dict(config.DEFAULT_SETTINGS['submission_policy'],same_topic_minutes=30);config.save_settings(settings)


def test_same_topic_queue_due_and_restart_no_unknown_replay(monkeypatch):
    policy();now=datetime.now(timezone.utc);monkeypatch.setattr(gate,'_now',lambda:now)
    rid,first=seed(20,limit=5)
    _make_package(rid,'second','{"value":2}')
    second=mailboxes.submit_experiment(rid,'second',None,'queued')
    assert second['status']=='queued' and second['platform_ref'] is None
    assert gate.items()[0]['reason']=='同账号同题提交间隔'
    db.init_db();gate.advance_sync()
    assert db.query_one('SELECT status FROM submissions WHERE id=?',(second['id'],))[0]=='queued'
    now+=timedelta(minutes=30,seconds=1);gate.advance_sync()
    result=db.query_one('SELECT * FROM submissions WHERE id=?',(second['id'],))
    assert result['status']=='submitted' and result['package_sha256']==second['package_sha256']
    db.execute("UPDATE submissions SET status='unknown' WHERE id=?",(second['id'],))
    gate.advance_sync(); assert db.query_one('SELECT status FROM submissions WHERE id=?',(second['id'],))[0]=='unknown'


def test_cross_topic_burst_is_durable(monkeypatch):
    policy();now=datetime.now(timezone.utc);monkeypatch.setattr(gate,'_now',lambda:now)
    rid,first=seed(20,limit=10)
    for i in range(1,5):
        other=_extra_run(i)
        result=mailboxes.submit_experiment(other,'trial_mb1',None,'burst-'+str(i))
        assert result['status']==('queued' if i==4 else 'submitted')
    assert len(gate.items())==1 and '突发' in gate.items()[0]['reason']


def test_harvest_precedes_experiment_after_resume(monkeypatch):
    rid,source=seed(100,limit=5)
    features.switch('auto_submission',False)
    _make_package(rid,'second','{"value":2}')
    experiment=mailboxes.submit_experiment(rid,'second',None,'exp-wait')
    auto_harvest.advance_sync()
    assert len(gate.items())==2 and gate.items()[0]['is_harvest']==1
    sent=[];original=mailboxes._perform_submission
    def perform(sid,*args,**kw):
        sent.append(db.query_one('SELECT is_harvest FROM submissions WHERE id=?',(sid,))[0]);return original(sid,*args,**kw)
    monkeypatch.setattr(mailboxes,'_perform_submission',perform)
    features.switch('auto_submission',True);gate.advance_sync();auto_harvest.reconcile_interrupted()
    assert sent==[1,0] and not gate.items()
    assert db.query_one('SELECT status FROM automatic_harvests')[0]=='done'


@pytest.mark.parametrize('response',[{'resultsJson':{'error_code':'missing_worker_submission'}},{'scored_by':'nonstandard-submission-guard:v8'},{'scoringDetails':{'source':'nonstandard-submission-guard'}},{'resultsJson':'{"error_code":"missing_worker_submission"}'}])
def test_nonstandard_feedback_persists_barrier_and_popup_and_recovers(response):
    rid,source=seed(20)
    with db.transaction() as conn:
        mailboxes._record_feedback(conn,db.query_one('SELECT * FROM submissions WHERE id=?',(source['id'],)),'attempt',response)
    assert gate.paused() and not features.enabled('auto_submission')
    gate.synchronize_pause();assert config.load_settings()['features']['auto_submission'] is False
    db.init_db();assert gate.paused()
    assert db.query_one("SELECT COUNT(*) FROM alerts WHERE kind='submission.nonstandard'")[0]==1
    assert db.query_one('SELECT phase FROM runs WHERE id=?',(rid,))[0]=='running'
    features.switch('auto_submission',True);assert not gate.paused() and features.enabled('auto_submission')
    with db.transaction() as conn:
        row=conn.execute('SELECT * FROM submissions WHERE id=?',(source['id'],)).fetchone()
        assert not mailboxes._record_feedback(conn,row,'attempt',response)
    assert not gate.paused() and features.enabled('auto_submission')
    with db.transaction() as conn:
        assert mailboxes._record_feedback(conn,row,'attempt',{**response,'revision':2})
    assert gate.paused()
    gate.synchronize_pause();assert not features.enabled('auto_submission')


def test_defaults_and_policy_validation():
    assert config.DEFAULT_SETTINGS['submission_policy']=={'same_topic_minutes':0,'cross_topic_minutes':30,'cross_topic_limit':4}
    for value in ({'cross_topic_limit':0},{'same_topic_minutes':-1},{'same_topic_minutes':True},{'unknown':1}):
        with pytest.raises(ValueError):gate.validate(value)
    db.init_db();db.init_db()


@pytest.mark.parametrize('response',[
    {'resultsJson': {'error_code': 'missing_worker_submission'}},
    {'scored_by': 'nonstandard-submission-guard:v8'},
    {'scoringDetails': {'source': 'nonstandard-submission-guard'}},
    {'resultsJson': '{"error_code":"missing_worker_submission"}'},
])
def test_recovered_historical_guard_status_update_keeps_receipt_without_repausing(response):
    rid, source = seed(20)
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM submissions WHERE id=?', (source['id'],)).fetchone()
        assert mailboxes._record_feedback(conn, row, 'attempt', response)
    assert gate.paused()
    features.switch('auto_submission', True)

    updated = {**response, 'status': 'scored'}
    with db.transaction() as conn:
        assert mailboxes._record_feedback(conn, row, 'attempt', updated)
    gate.synchronize_pause()
    assert not gate.paused() and features.enabled('auto_submission')
    observed = db.query_one(
        "SELECT payload FROM events WHERE run_id=? AND type='submission.platform_feedback'"
        " ORDER BY seq DESC LIMIT 1", (rid,))
    assert json.loads(observed['payload'])['response'] == updated
    receipt = db.query_one('SELECT receipt_details_json FROM submissions WHERE id=?', (source['id'],))
    assert json.loads(receipt['receipt_details_json'])['platform_status'] == 'scored'

    # A changed guard observation after recovery still closes the submission gate.
    with db.transaction() as conn:
        assert mailboxes._record_feedback(conn, row, 'attempt', {**updated, 'revision': 2})
    assert gate.paused()


async def test_settings_feature_and_queue_http_roundtrip():
    from httpx import ASGITransport, AsyncClient
    from cyberscientist import api
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://fixture') as client:
        saved=await client.put('/api/v1/settings',json={'base_revision':config.load_settings()['revision'],'settings':{'submission_policy':{'same_topic_minutes':31,'cross_topic_limit':3},'features':{'judge_replica_hint':True}}})
        assert saved.status_code==200,saved.text
        assert (await client.get('/api/v1/settings')).json()['submission_policy']['same_topic_minutes']==31
        assert (await client.get('/api/v1/features')).json()['features']['judge_replica_hint']
        switched=await client.put('/api/v1/features/auto_submission',json={'enabled':False})
        assert switched.status_code==200
        assert not (await client.get('/api/v1/features')).json()['features']['auto_submission']
        assert (await client.get('/api/v1/submission_queue')).json()['items']==[]
    db.init_db()
    assert config.load_settings()['features']['auto_submission'] is False
    assert config.load_settings()['submission_policy']['cross_topic_limit']==3


def test_restart_marks_interrupted_sender_unknown_without_replay():
    rid,source=seed(20)
    db.execute("UPDATE submission_queue SET state='sending' WHERE submission_id=?",(source['id'],))
    gate.reconcile_interrupted()
    assert db.query_one('SELECT state FROM submission_queue WHERE submission_id=?',(source['id'],))[0]=='unknown'
    assert not gate.items()
