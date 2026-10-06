import json
from datetime import datetime, timezone, timedelta
import pytest
from cyberscientist import auto_harvest, config, db, mailboxes, alerts, competition
from test_auto_harvest import seed
from test_mailboxes import _make_run, _make_package, _set_scored


def track(rid, name, end):
    clock={'track_clock':{'start':(end-timedelta(hours=5)).isoformat(),'end':end.isoformat(),'source':'operator_override'}}
    db.execute("INSERT OR IGNORE INTO eval_runs(id,suite,repeats,label,status,config_json,created_at,updated_at) VALUES(?,'competition',1,?,'running',?,?,?)",(name,name,json.dumps(clock),db.utcnow(),db.utcnow()))
    s=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0]);s['competition']={'round_id':name}
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(s),rid))
    db.execute("INSERT INTO eval_results(id,eval_id,challenge_id,run_id,repeat_index,status,created_at,updated_at) VALUES(?,?,'MB_CH',?,(SELECT COUNT(*)+1 FROM eval_results WHERE eval_id=?),'running',?,?)",('item-'+rid,name,rid,name,db.utcnow(),db.utcnow()))


def another(score, name, end, seq):
    rid=_make_run(max_submissions=10);track(rid,name,end);_make_package(rid,'t'+seq,json.dumps({'value':seq}))
    src=mailboxes.submit_experiment(rid,'t'+seq,None,'exp-'+seq);_set_scored(src['id'],score)
    db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,))
    return rid,src


def harvests(): return db.query('SELECT * FROM submissions WHERE is_harvest=1 ORDER BY rowid')


def test_cross_run_best_improvements_pending_barrier_safety_and_track_isolation(monkeypatch):
    now=datetime.now(timezone.utc);end=now+timedelta(hours=1,minutes=40)
    monkeypatch.setattr(auto_harvest,'_now',lambda:now)
    rid,src=seed(64.8,limit=10);track(rid,'track-a',end)
    r2,s2=another(50,'track-a',end,'2');r3,s3=another(60,'track-a',end,'3')
    rb,sb=another(95,'track-b',now+timedelta(hours=5),'b')
    auto_harvest.advance_sync()
    assert len(harvests())==1 and harvests()[0]['source_submission_id']==src['id']
    assert harvests()[0]['package_sha256']==src['package_sha256']
    assert auto_harvest.topic_facts('track-a','MB_CH')['experiment_best']==64.8
    assert auto_harvest.topic_facts('track-b','MB_CH')['experiment_best']==95
    _set_scored(s2['id'],70);auto_harvest.advance_sync()
    assert len(harvests())==1 # unknown main score must be reconciled first
    _set_scored(harvests()[0]['id'],64.8);auto_harvest.advance_sync()
    assert len(harvests())==2 and harvests()[-1]['source_submission_id']==s2['id']
    _set_scored(harvests()[-1]['id'],70);auto_harvest.advance_sync()
    assert len(harvests())==2
    _set_scored(s3['id'],80)
    now=end-timedelta(minutes=10);auto_harvest.advance_sync()
    assert len(harvests())==2
    summaries=db.query("SELECT * FROM alerts WHERE kind='harvest.summary'")
    assert len(summaries)==2 and all(json.loads(s['payload'])['round_id']=='track-a' for s in summaries)
    facts=competition.get_round('track-a');assert facts['harvest_window']['state']=='safety_margin'
    assert facts['items'][0]['harvest_scores']['main_best']==70
    auto_harvest.advance_sync();assert len(db.query("SELECT * FROM alerts WHERE kind='harvest.summary'"))==2


def test_last_mailbox_quota_only_window_and_alert(monkeypatch):
    now=datetime.now(timezone.utc);rid,src=seed(100)
    settings=config.load_settings();settings['mailbox']['submission_limit']=1;config.save_settings(settings)
    track(rid,'track-last',now+timedelta(hours=5))
    auto_harvest.advance_sync();assert not harvests()
    clock=json.loads(db.query_one("SELECT config_json FROM eval_runs WHERE id='track-last'")[0]);clock['track_clock']['end']=(now+timedelta(minutes=50)).isoformat()
    db.execute("UPDATE eval_runs SET config_json=? WHERE id='track-last'",(json.dumps(clock),))
    auto_harvest.advance_sync();assert len(harvests())==1
    assert any('最后一次额度' in a['title'] for a in alerts.pending())


def test_final_prepost_cutoff_prevents_create_and_releases_reservation(monkeypatch):
    now=datetime.now(timezone.utc);rid,src=seed(60);end=now+timedelta(minutes=40);track(rid,'cutoff',end)
    monkeypatch.setattr(auto_harvest,'_now',lambda:now)
    original=mailboxes._guard_submission_target
    def advance_clock(*args,**kwargs):
        nonlocal now
        now=end-timedelta(minutes=10)
        return original(*args,**kwargs)
    monkeypatch.setattr(mailboxes,'_guard_submission_target',advance_clock)
    auto_harvest.advance_sync();assert harvests()[0]['status']=='failed'
    assert harvests()[0]['platform_ref'] is None and harvests()[0]['reservation_released']==1


def test_safety_settings_default_and_persistent_api_roundtrip():
    assert auto_harvest.validate({})['safety_margin_minutes']==15
    for bad in (-1,float('nan'),True,'15'):
        with pytest.raises(ValueError):auto_harvest.validate({'safety_margin_minutes':bad})
    settings=config.load_settings();settings['harvest']=auto_harvest.validate({'safety_margin_minutes':23});config.save_settings(settings)
    db.init_db();assert config.load_settings()['harvest']['safety_margin_minutes']==23
    settings=config.load_settings();settings['run_defaults']['max_jobs']=9;config.save_settings(settings)
    assert config.load_settings()['harvest']['safety_margin_minutes']==23


def test_frozen_target_alias_best_and_main_score_quota_origin_isolation(monkeypatch):
    now=datetime.now(timezone.utc);end=now+timedelta(minutes=50)
    r1,s1=seed(64.8);track(r1,'aliases',end)
    r2,s2=another(80,'aliases',end,'alias')
    db.execute("INSERT INTO challenges(id,platform_challenge_id,origin,title,content,content_hash,imported_at,is_demo) VALUES('MB_ALIAS','MB','demo://local','alias','x','h',?,1)",(db.utcnow(),))
    db.execute("UPDATE runs SET challenge_id='MB_ALIAS' WHERE id=?",(r2,))
    assert auto_harvest.topic_facts('aliases','MB_CH')['experiment_best']==80
    auto_harvest.advance_sync();assert len(harvests())==1 and harvests()[0]['source_submission_id']==s2['id']
    _set_scored(harvests()[0]['id'],80)
    trigger={'reason':'deadline_best','score':64.8,'params':auto_harvest.validate({})}
    with pytest.raises(mailboxes.MailboxError):mailboxes._automatic_harvest_guard(db.get_db(),db.query_one('SELECT * FROM submissions WHERE id=?',(s1['id'],)),trigger)
    # Import refresh cannot move the already frozen topic quota.
    db.execute("UPDATE challenges SET platform_challenge_id='changed' WHERE id='MB_CH'")
    main=db.query_one("SELECT id FROM mailboxes WHERE role='harvest'")[0]
    assert mailboxes._used_for(db.get_db(),main,mailboxes._challenge_key(db.get_db(),r1))==1
    # A genuinely different platform origin with the same slug has its own score/quota.
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(r1,))[0]);snapshot['competition']['submission_transport']={'base_url':'https://other.example/api'}
    db.execute("UPDATE runs SET mode='connected',config_snapshot=? WHERE id=?",(json.dumps(snapshot),r1))
    assert mailboxes._used_for(db.get_db(),main,mailboxes._challenge_key(db.get_db(),r1))==0
    assert auto_harvest.topic_facts('aliases','MB_CH')['main_best'] is None
    mailboxes._automatic_harvest_guard(db.get_db(),db.query_one('SELECT * FROM submissions WHERE id=?',(s1['id'],)),trigger)


def test_thirty_minute_summary_is_independent_of_short_window(monkeypatch):
    now=datetime.now(timezone.utc);rid,src=seed(20);track(rid,'short-window',now+timedelta(minutes=29))
    settings=config.load_settings();settings['harvest']['deadline_check_hours']=.25;config.save_settings(settings)
    auto_harvest.advance_sync()
    summaries=db.query("SELECT dedupe_key FROM alerts WHERE kind='harvest.summary'")
    assert len(summaries)==1 and summaries[0][0].endswith('last_30_minutes')
    assert not harvests()


def test_old_disabled_harvest_mailbox_does_not_block_new_actual_mailbox():
    now=datetime.now(timezone.utc);rid,src=seed(65);track(rid,'mailbox-switch',now+timedelta(minutes=45))
    auto_harvest.advance_sync();old=harvests()[0];_set_scored(old['id'],80)
    db.execute("UPDATE mailboxes SET status='disabled' WHERE id=?",(old['mailbox_id'],))
    new=mailboxes.add_harvest('new-main@example.test','new-fixture-secret')
    facts=auto_harvest.topic_facts('mailbox-switch','MB_CH');assert facts['main_best'] is None
    with db.transaction() as conn:
        mailboxes._automatic_harvest_guard(conn,db.query_one('SELECT * FROM submissions WHERE id=?',(src['id'],)),{'reason':'deadline_best','score':65,'params':auto_harvest.validate({})})
        assert mailboxes._used_for(conn,new['id'],mailboxes._challenge_key(conn,rid))==0
    # Replacing credentials for the very same email keeps its real quota and unknown barrier.
    db.execute("UPDATE mailboxes SET status='disabled' WHERE id=?",(new['id'],))
    same=mailboxes.add_harvest('OWNED@example.com','changed-fixture-secret')
    assert auto_harvest.topic_facts('mailbox-switch','MB_CH')['main_best']==80
    assert mailboxes._used_for(db.get_db(),same['id'],mailboxes._challenge_key(db.get_db(),rid))==1


def test_native_adapter_validation_crosses_cutoff_before_create_zero_post(monkeypatch):
    from cyberscientist import mailbox_platform
    now=datetime.now(timezone.utc);end=now+timedelta(minutes=40);rid,src=seed(65);track(rid,'adapter-cutoff',end)
    monkeypatch.setattr(auto_harvest,'_now',lambda:now)
    platform=mailbox_platform.BohriumPlaygroundPlatform('https://fixture.example/api')
    platform.name='demo';platform.is_demo=True
    calls=[]
    monkeypatch.setattr(platform,'_http',lambda method,*a,**k:calls.append(method) or {'id':'must-not-create'})
    monkeypatch.setattr(mailboxes,'_platform_for_run',lambda *a,**k:platform)
    original=mailbox_platform._inline_trace
    def slow_validation(trace):
        nonlocal now
        now=end-timedelta(minutes=10)
        return original(trace)
    monkeypatch.setattr(mailbox_platform,'_inline_trace',slow_validation)
    auto_harvest.advance_sync()
    assert calls==[] and len(harvests())==1
    assert harvests()[0]['reservation_released']==1 and harvests()[0]['platform_ref'] is None


def test_experiment_account_promoted_to_main_uses_its_all_history_and_unknown_barrier():
    now=datetime.now(timezone.utc);rid,src=seed(65);end=now+timedelta(minutes=45);track(rid,'account-role',end)
    email=db.query_one('SELECT email FROM mailboxes WHERE id=?',(src['mailbox_id'],))[0]
    db.execute("UPDATE mailboxes SET status='disabled' WHERE role='harvest'")
    mailboxes.add_harvest(email,'promoted-fixture-secret')
    assert auto_harvest.topic_facts('account-role','MB_CH')['main_best']==65
    auto_harvest.advance_sync();assert not harvests() # score is already on the actual main account
    db.execute("UPDATE mailboxes SET status='disabled' WHERE id=?",(src['mailbox_id'],))
    mailboxes.register_experiment(1)
    r2,s2=another(70,'account-role',end,'promoted')
    assert s2['mailbox_id']!=src['mailbox_id']
    db.execute("UPDATE submissions SET status='unknown' WHERE id=?",(src['id'],))
    trigger={'reason':'deadline_best','score':70,'params':auto_harvest.validate({})}
    with pytest.raises(mailboxes.MailboxError) as caught:
        mailboxes._automatic_harvest_guard(db.get_db(),db.query_one('SELECT * FROM submissions WHERE id=?',(s2['id'],)),trigger)
    assert caught.value.code=='HARVEST_PENDING'


@pytest.mark.asyncio
async def test_safety_setting_http_partial_save_restart_other_page_save():
    import httpx
    from cyberscientist.api import create_app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),base_url='http://fixture') as client:
        original=(await client.get('/api/v1/settings')).json()
        response=await client.put('/api/v1/settings',json={'base_revision':original['revision'],'settings':{'harvest':{'safety_margin_minutes':23}}})
        assert response.status_code==200 and response.json()['harvest']['safety_margin_minutes']==23
    db.init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),base_url='http://fixture') as client:
        current=(await client.get('/api/v1/settings')).json();assert current['harvest']['safety_margin_minutes']==23
        response=await client.put('/api/v1/settings',json={'base_revision':current['revision'],'settings':{'run_defaults':{'stall_seconds':222}}})
        assert response.status_code==200 and response.json()['harvest']['safety_margin_minutes']==23
