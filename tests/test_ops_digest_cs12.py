import io,json,sys
from datetime import datetime, timezone,timedelta
import pytest
from cyberscientist import db,config,ops,ops_digest,cli,preflight
from test_ops_cs10 import runs
from test_deadline_harvest_cs12 import track


def test_digest_is_direct_compact_deduped_secret_safe_and_since_filters(monkeypatch):
    ctl,ids=runs();now=datetime.now(timezone.utc);cutoff=now-timedelta(minutes=10)
    config.update_secret('digest-fixture','private-ops-fixture-secret')
    for i in range(3):db.append_event(ids[0],'controller','prime.error',{'error':'private-ops-fixture-secret\nnetwork failure'})
    db.execute("UPDATE events SET recorded_at=? WHERE run_id=?",((now-timedelta(minutes=20)).isoformat(),ids[1]))
    db.execute('UPDATE runs SET created_at=? WHERE id=?',((now-timedelta(minutes=20)).isoformat(),ids[1]))
    ops_digest.record_session(ids[0],'brain','session-one',{'model':'gpt-6-astra','provider':'codex','fast_mode':{'enabled':True,'observed_tier':'priority'}})
    monkeypatch.setattr(ops,'status',lambda:pytest.fail('digest must not create full status'))
    monkeypatch.setattr(ops,'pending',lambda:pytest.fail('digest must not scan approval/config objects'))
    data=ops_digest.digest(cutoff.isoformat())
    assert data['line_count']==len(data['text'].splitlines())<=60
    assert ids[0] in data['text'] and ids[1] not in data['text']
    assert 'error x3' in data['text'] and 'private-ops-fixture-secret' not in data['text']
    assert 'unknown compute_jobs' in data['text'] and 'rates codex=' in data['text']
    with pytest.raises(ValueError):ops_digest.digest('not-time')
    with pytest.raises(ValueError):ops_digest.digest('2026-10-06')


def test_digest_many_runs_never_exceeds_sixty_and_reports_omission():
    ctl,ids=runs()
    for i in range(100):
        db.execute("INSERT INTO runs(id,challenge_id,mode,phase,config_snapshot,created_at) VALUES(?,'ops-ch','demo','finished','{}',?)",('digest-'+str(i),db.utcnow()))
    data=ops_digest.digest()
    assert len(data['text'].splitlines())<=60 and 'additional run/track rows=' in data['text']


@pytest.mark.asyncio
async def test_real_http_status_digest_projection_and_since_validation():
    import httpx
    from cyberscientist.api import create_app
    ctl,ids=runs()
    ops_digest.record_session(ids[0],'executor','native-thread',{'model':'gpt-6.1-sol','provider':'codex','fast_mode':{'enabled':True}})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),base_url='http://t') as client:
        status=(await client.get('/api/v1/ops/status')).json()
        assert 'tracks' in status and 'provider_rates' in status
        row=next(r for r in status['runs'] if r['id']==ids[0]);assert row['sessions'][0]['fast_mode']['enabled'] is True
        assert 'harvest_scores' in row and 'config_snapshot' not in row
        response=await client.get('/api/v1/ops/digest');assert response.status_code==200 and response.json()['line_count']<=60
        assert (await client.get('/api/v1/ops/digest?since=bad')).status_code==422


def test_cli_digest_prints_text_and_encodes_since(monkeypatch,capsys):
    calls=[]
    monkeypatch.setattr(cli.urllib.request,'urlopen',lambda request,**kwargs:calls.append(request.full_url) or io.BytesIO(json.dumps({'text':'OPS line\nsecond line'}).encode()))
    monkeypatch.setattr(sys,'argv',['cyberscientist','ops','digest','--since','2026-10-06T10:00:00+08:00'])
    cli.main();assert capsys.readouterr().out=='OPS line\nsecond line\n'
    assert 'since=2026-10-06T10%3A00%3A00%2B08%3A00' in calls[0]


def test_activity_wins_over_old_history_and_errors_redact_before_truncation():
    _,ids=runs()
    config.update_secret('long-digest','prefix-'+'z9Q'*60+'-suffix')
    db.append_event(ids[0],'controller','prime.error',{'error':'prefix-'+'z9Q'*60+'-suffix'+' unavailable'})
    for i in range(60):
        db.execute("INSERT INTO runs(id,challenge_id,mode,phase,config_snapshot,created_at) VALUES(?,'ops-ch','demo','finished','{}','2020-01-01T00:00:00+00:00')",('old-'+str(i),))
    db.execute("UPDATE runs SET phase='running' WHERE id=?",(ids[0],))
    value=ops_digest.digest()['text']
    assert ids[0] in value and 'z9Q' not in value and '[REDACTED]' in value
    assert len(value.splitlines())<=60


def test_since_ignores_unchanged_poll_but_includes_real_confirmation_and_unknown(monkeypatch):
    from cyberscientist import mailboxes
    from test_mailboxes import _seed_challenge,_make_run,_make_package
    _seed_challenge();mailboxes.register_experiment(1);rid=_make_run();_make_package(rid)
    sub=mailboxes.submit_experiment(rid,'trial_mb1',None,'digest-pending')
    platform=mailboxes._platform()
    monkeypatch.setattr(platform,'fetch_score_details',lambda *a:{'scoringState':{'scoreIsFinal':False}},raising=False)
    monkeypatch.setattr(platform,'fetch_score',lambda *a:None)
    monkeypatch.setattr(mailboxes,'_platform',lambda *a,**k:platform)
    mailboxes.poll_scores(rid,manual=True)
    old=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    db.execute('UPDATE events SET recorded_at=?',(old,));db.execute('UPDATE runs SET created_at=?',(old,));db.execute('UPDATE submissions SET created_at=?',(old,))
    cutoff=datetime.now(timezone.utc)-timedelta(minutes=10)
    mailboxes.poll_scores(rid,manual=True)
    assert rid not in ops_digest.digest(cutoff.isoformat())['text']
    db.execute("UPDATE submissions SET status='unknown' WHERE id=?",(sub['id'],))
    db.append_event(rid,'controller','submission.unknown',{'submission_id':sub['id']})
    value=ops_digest.digest(cutoff.isoformat())['text']
    assert rid in value and 'unknown submissions count=1 ids='+sub['id'] in value
    db.execute('UPDATE events SET recorded_at=?',(old,))
    assert 'unknown submissions count=0' in ops_digest.digest(cutoff.isoformat())['text']
    db.execute("UPDATE submissions SET status='submitted' WHERE id=?",(sub['id'],))
    monkeypatch.setattr(platform,'fetch_score_details',lambda *a:{'scoringState':{'scoreIsFinal':True,'displayScore':42.0}})
    mailboxes.poll_scores(rid,manual=True)
    assert rid in ops_digest.digest(cutoff.isoformat())['text']


def test_native_retry_rate_wait_and_recovery_are_visible_without_backoff():
    from cyberscientist import model_fallback
    choice={'provider':'codex','model_id':'gpt-6.1-sol','runtime':'codex'}
    model_fallback.note(choice,'HTTP 429 Too Many Requests',will_retry=True,request_id='thread-one')
    assert not db.query('SELECT * FROM model_provider_backoff')
    value=ops_digest.rates()['native_throttle'][0]
    assert value['status']=='waiting' and value['provider']=='codex' and value['first_at']
    assert 'waiting' in ops_digest.digest()['text']
    model_fallback.recovered(choice,request_id='thread-one')
    assert ops_digest.rates()['native_throttle'][0]['status']=='recovered'


@pytest.mark.parametrize('role',['brain','executor'])
async def test_session_observation_failure_never_closes_or_orphans_native(monkeypatch,role):
    from test_codex_fast_cs12 import TierRpc
    from cyberscientist.brains.codex import CodexBrain
    from cyberscientist.prime.codex_exec import CodexExecutor
    _,ids=runs()
    module='cyberscientist.brains.codex' if role=='brain' else 'cyberscientist.prime.codex_exec'
    created=[]
    class Rpc(TierRpc):
        async def stop(self):
            raise RuntimeError('close refused fixture')
    monkeypatch.setattr(module+'.JsonRpcStdio',Rpc)
    runtime=(CodexBrain if role=='brain' else CodexExecutor)('/bin/true','gpt-6.1-sol','high',fast_mode=True)
    original=db.append_event
    monkeypatch.setattr(db,'append_event',lambda *a,**k:(_ for _ in ()).throw(OSError('observation database write failed')))
    session=await (runtime.open({'run_id':ids[0]}) if role=='brain' else runtime.start({'run_id':ids[0]}))
    rpc=runtime.rpc if role=='brain' else runtime._sessions[session].rpc
    assert rpc is not None
    monkeypatch.setattr(db,'append_event',original)
    monkeypatch.setattr(Rpc,'stop',TierRpc.stop)
    await runtime.close(session)
    assert rpc.stopped


@pytest.mark.parametrize('role',['brain','executor'])
async def test_native_session_acknowledgement_enters_actual_ops_projection(monkeypatch,role):
    from test_codex_fast_cs12 import TierRpc
    from cyberscientist.brains.codex import CodexBrain
    from cyberscientist.prime.codex_exec import CodexExecutor
    _,ids=runs()
    module='cyberscientist.brains.codex' if role=='brain' else 'cyberscientist.prime.codex_exec'
    monkeypatch.setattr(module+'.JsonRpcStdio',TierRpc)
    runtime=(CodexBrain if role=='brain' else CodexExecutor)('/bin/true','gpt-6.1-sol','high',fast_mode=True)
    session=await (runtime.open({'run_id':ids[0],'ops_role':'reviewer'}) if role=='brain' else runtime.start({'run_id':ids[0]}))
    try:
        facts=next(r for r in ops.status()['runs'] if r['id']==ids[0])['sessions'][0]
        assert facts['role']==('reviewer' if role=='brain' else 'executor') and facts['reasoning_effort']=='high'
        assert facts['fast_mode']['enabled'] is True and facts['fast_mode']['observed_tier']=='priority'
    finally:await runtime.close(session)


def test_track_selfcheck_exposes_prompt_confirmation_budget_and_mailbox(monkeypatch):
    from test_preflight_cs10 import seed_mailboxes,fake_checks
    seed_mailboxes();fake_checks(monkeypatch)
    ready=preflight.track_checks();assert ready['status']=='pass'
    row=ready['facts']['tracks'][0]
    assert row['transport_verified'] and row['prompt_filled'] and row['unlimited_resources'] and row['harvest_mailbox_matches']
    db.execute("DELETE FROM competition_prompt_versions WHERE eval_id='ready-track'")
    raw=json.loads(db.query_one("SELECT config_json FROM eval_runs WHERE id='ready-track'")[0]);raw['submission_transport']['evidence']={};raw['submission_transport']['base_url']='https://different-platform.invalid/api';raw['template']['authorization']['unlimited_resources']=False
    db.execute("UPDATE eval_runs SET config_json=? WHERE id='ready-track'",(json.dumps(raw),))
    result=preflight.track_checks();assert result['status']=='warn'
    row=result['facts']['tracks'][0]
    assert not any(row[key] for key in ['transport_verified','prompt_filled','unlimited_resources','harvest_mailbox_matches'])
    assert result['facts']['missing_prompt']==['ready-track'] and result['facts']['missing_mailbox']==['ready-track']


def test_topics_without_runs_are_projected_for_deferred_and_skipped_tracks():
    from test_triage_import_cs10 import seed
    from cyberscientist import competition
    rnd,_=seed(3);rid=rnd['id']
    competition.update_item(rid,rnd['items'][1]['id'],launch_state='deferred')
    competition.update_item(rid,rnd['items'][2]['id'],launch_state='skipped')
    data=ops.status();topics=next(t for t in data['tracks'] if t['id']==rid)['topics']
    assert len(topics)==3 and {t['launch_state'] for t in topics}=={'immediate','deferred','skipped'}
    assert all(t['harvest_scores']['main_best'] is None and t['harvest_scores']['experiment_best'] is None for t in topics)
    text=ops_digest.digest()['text']
    assert all(t['challenge_id'] in text for t in topics) and 'deferred no_run' in text and 'skipped no_run' in text
    old=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    db.execute('UPDATE eval_runs SET updated_at=?',(old,));db.execute('UPDATE eval_results SET updated_at=?',(old,))
    cutoff=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
    assert rid not in ops_digest.digest(cutoff)['text']
    db.execute('UPDATE eval_results SET updated_at=? WHERE id=?',(db.utcnow(),topics[1]['id']))
    text=ops_digest.digest(cutoff)['text'];assert topics[1]['challenge_id'] in text and topics[2]['challenge_id'] not in text


@pytest.mark.asyncio
async def test_unstarted_topic_reads_frozen_target_main_history_and_unknown():
    from test_auto_harvest import seed
    from test_mailboxes import _set_scored
    from cyberscientist import competition,mailboxes,auto_harvest
    rid,source=seed(64.8,limit=10)
    main=mailboxes.harvest_submit(source['id'],'old-confirmed-main',True);_set_scored(main['id'],64.8)
    db.execute("INSERT INTO submissions(id,run_id,mailbox_id,package_path,package_sha256,status,score_status,is_harvest,created_at) VALUES('older-main-unknown',?,?,?,'fixture-hash','unknown','unknown',1,?)",(rid,main['mailbox_id'],'fixture-path',db.utcnow()))
    rnd=competition.import_round(['MB_CH'],mode='demo');item=rnd['items'][0]
    competition.update_item(rnd['id'],item['id'],launch_state='deferred')
    # Import refresh cannot move the new track's frozen slug.
    db.execute("UPDATE challenges SET platform_challenge_id='changed-alias' WHERE id='MB_CH'")
    facts=auto_harvest.topic_facts(rnd['id'],'MB_CH')
    assert facts['main_best']==64.8 and facts['experiment_best'] is None
    assert 'older-main-unknown' in facts['pending_submission_ids']
    topics=next(t for t in ops.status()['tracks'] if t['id']==rnd['id'])['topics']
    assert topics[0]['harvest_scores']==facts and 'deferred no_run local=None main=64.8' in ops_digest.digest()['text']
    raw=json.loads(db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rnd['id'],))[0]);raw['mode']='connected';raw['submission_transport']['base_url']='https://different-origin.example/api'
    db.execute('UPDATE eval_runs SET config_json=? WHERE id=?',(json.dumps(raw),rnd['id']))
    isolated=auto_harvest.topic_facts(rnd['id'],'MB_CH')
    assert isolated['main_best'] is None and not isolated['pending_submission_ids']
    raw['mode']='demo';db.execute('UPDATE eval_runs SET config_json=? WHERE id=?',(json.dumps(raw),rnd['id']))
    from test_competition import FakeController
    from test_triage_import_cs10 import template
    from cyberscientist import evaluations
    competition.confirm(rnd['id'],template());competition.start_deferred(rnd['id'],item['id'])
    ctl=FakeController();ctl.throttled=True;await evaluations.advance(ctl)
    started=competition.get_round(rnd['id'])['items'][0]
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(started['run_id'],))[0])
    assert snapshot['challenge_platform_id']==raw['entries'][0]['platform_challenge_id']=='MB'
    assert snapshot['settings']['mailbox']['platform']==raw['mailbox_platform']
    assert db.query_one('SELECT phase FROM runs WHERE id=?',(started['run_id'],))[0]=='running'
    after=auto_harvest.topic_facts(rnd['id'],'MB_CH')
    assert after==facts
