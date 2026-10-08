"""Two real queue paths, scheduling overrides and frozen HTTP routing (all fake)."""
import json
from datetime import datetime,timedelta,timezone
import pytest
from httpx import ASGITransport,AsyncClient
from cyberscientist import api,competition,competition_prompts,config,db,evaluations,mailboxes,resource_coordinator,run_clock,track_clock,track_transport,protocol_drift
from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform,PlatformError
from test_competition import challenges,template,FakeController
from test_mailbox_platform import valid_arm_zip,FakeHTTP

REAL_PROBE=track_transport.probe


async def test_two_five_topic_tracks_queue_prompts_clocks_transports_and_shared_resources(monkeypatch,tmp_path):
    ids=challenges(10);past=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
    db.execute('UPDATE challenges SET platform_snapshot_json=?',(json.dumps({'roundEndAt':past,'status':'ended'}),))
    ctl=FakeController();ctl.throttled=True
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://fixture') as client:
        response=await client.post('/api/v1/rounds/import-many',json=[
            {'challenge_ids':ids[:5],'label':'材料赛道','mode':'demo','clock':{'duration_hours':5}},
            {'challenge_ids':ids[5:],'label':'全栈赛道','mode':'demo','clock':{'duration_hours':6}}])
        assert response.status_code==200
        tracks=response.json()['items'];a,b=tracks
        competition_prompts.publish(a['id'],'材料独立提示',competition_prompts.latest(a['id'])['version']);competition_prompts.publish(b['id'],'全栈独立提示',competition_prompts.latest(b['id'])['version'])
        custom=track_transport.defaults();custom['paths']={k:p.replace('/attempts','/track-b/attempts') for k,p in custom['paths'].items()};custom.update(verified=True,bundle_field='arm_zip');custom['paths']['create']='/track-b/challenges/{id}/attempts'
        updated=await client.put(f"/api/v1/rounds/{b['id']}/transport",json=custom)
        assert updated.status_code==200
        for value in tracks: competition.confirm(value['id'],template())
        await evaluations.advance(ctl)
        listed=(await client.get('/api/v1/rounds')).json()['items']
    assert len(listed)==2 and all(t['topic_count']==5 for t in listed)
    runs=db.query('SELECT * FROM runs');assert len(runs)==10
    assert sum(s['used'] for s in resource_coordinator.status()['sessions'])==20
    for run in runs:
        snap=json.loads(run['config_snapshot']);material=run['challenge_id'] in ids[:5]
        assert snap['competition']['user_prompt']['content_md']==('材料独立提示' if material else '全栈独立提示')
        assert snap['competition']['submission_transport']['bundle_field']==('bundle' if material else 'arm_zip')
        assert 4.9*3600<run_clock.remaining(run,db.query_one('SELECT * FROM authorizations WHERE run_id=?',(run['id'],)))<6.1*3600
        assert json.loads(snap['competition']['challenge_snapshot']['platform'] if isinstance(snap['competition']['challenge_snapshot']['platform'],str) else json.dumps(snap['competition']['challenge_snapshot']['platform']))['roundEndAt']==past
    # Old platform end remains an eligibility fact even with a future clock.
    assert all(t['track_clock']['platform_end']==past for t in [competition.get_round(a['id']),competition.get_round(b['id'])])
    chosen=[next(r for r in runs if r['challenge_id']==cid) for cid in ('c0','c5')]
    fake=FakeHTTP({('POST','/challenges/'):{'id':'attempt-a'},('POST','/track-b/challenges/'):{'id':'attempt-b'},
                   ('POST','/attempts/attempt-a/bundle'):{'bundleStatus':'valid'},('POST','/track-b/attempts/attempt-b/bundle'):{'bundleStatus':'valid'},
                   ('POST','/attempts/attempt-a/submit'):{'status':'submitted'},('POST','/track-b/attempts/attempt-b/submit'):{'status':'submitted'},
                   ('GET','/attempts/attempt-a/score'):{'scoringState':{'scoreIsFinal':True,'displayScore':11}},
                   ('GET','/track-b/attempts/attempt-b/score'):{'scoringState':{'scoreIsFinal':True,'displayScore':22}}})
    monkeypatch.setattr(BohriumPlaygroundPlatform,'_http',lambda self,*args,**kwargs:fake(*args,**kwargs))
    original=BohriumPlaygroundPlatform(config.load_settings()['playground']['base_url'])
    package=tmp_path/'arm.zip';package.write_bytes(valid_arm_zip())
    for run,attempt,score in zip(chosen,('attempt-a','attempt-b'),(11,22)):
        platform=mailboxes._platform_for_run(run['id'],original)
        receipt=platform.submit_package('fixture@fixture.invalid','fixture-credential',str(package),'topic-fixture')
        assert receipt['accepted'] and receipt['receipt']==attempt
        assert platform.fetch_score('fixture@fixture.invalid','fixture-credential',attempt)==score
    assert any(c['form_files']==[('arm_zip','arm.zip')] for c in fake.calls)
    competition.set_transport(b['id'],track_transport.defaults() | {'verified':True})
    assert track_transport.for_run(chosen[1]['id'])['paths']['bundle'].startswith('/track-b/')
    assert not db.query('SELECT * FROM submissions') and not db.query('SELECT * FROM compute_jobs')


async def test_clock_start_restore_invalid_and_separate_platform_submission_guard(monkeypatch):
    ids=challenges(1);rid=competition.import_round(ids,mode='demo')['id']
    before=competition.get_round(rid)['track_clock']['end']
    now=datetime.now(timezone.utc)
    competition.set_clock(rid,{'start':(now+timedelta(hours=1)).isoformat(),'end':(now+timedelta(hours=6)).isoformat()})
    competition.confirm(rid,template());ctl=FakeController();ctl.throttled=True;await evaluations.advance(ctl)
    assert not db.query('SELECT * FROM runs')
    old=db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0]
    with pytest.raises(ValueError):competition.set_clock(rid,{'duration_hours':float('nan')})
    assert db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0]==old
    competition.set_clock(rid,{'use_platform':True});assert competition.get_round(rid)['track_clock']['end']==before
    await evaluations.advance(ctl);run=db.query_one('SELECT * FROM runs')
    competition.set_clock(rid,{'duration_hours':5});assert 4.9*3600<run_clock.remaining(run,db.query_one('SELECT * FROM authorizations WHERE run_id=?',(run['id'],)))<5.1*3600
    # Old-topic-only authorization uses the actual platform end, not the rehearsal clock.
    snap=json.loads(run['config_snapshot']);snap['settings']['policy']['require_ended_submission']=True
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(snap),run['id']))
    db.execute('UPDATE challenges SET platform_challenge_id=?,is_demo=0 WHERE id=?',('fixture-public','c0'))
    platform=BohriumPlaygroundPlatform(config.load_settings()['playground']['base_url'])
    monkeypatch.setattr(platform,'_http',lambda *a,**k:{'status':'closed','roundEndAt':(now-timedelta(days=1)).isoformat()})
    mailboxes._guard_submission_target(run['id'],platform,'fixture-public')
    monkeypatch.setattr(platform,'_http',lambda *a,**k:{'roundEndAt':(now+timedelta(days=1)).isoformat()})
    with pytest.raises(PlatformError,match='结束'):
        mailboxes._guard_submission_target(run['id'],platform,'fixture-public')


def test_probe_recognizes_only_observed_public_docs_and_manual_review(monkeypatch):
    doc='\n'.join(f'{method} {path}' for method,path in track_transport.PATHS.values())
    monkeypatch.setattr(protocol_drift,'_read_public',lambda name,path,*a,**k:({'accepted_versions':['1.1']} if name=='track_protocol' else doc,{'http_status':200,'sha256':'fixture'}))
    observed=REAL_PROBE('connected')
    assert not observed['verified'] and observed['evidence']['default_transport_documented']
    monkeypatch.setattr(protocol_drift,'_read_public',lambda *a,**k:(_ for _ in ()).throw(TimeoutError('fixture timeout')))
    assert REAL_PROBE('connected')['status']=='unknown' and not REAL_PROBE('connected')['verified']
    rid=competition.import_round(challenges(1),mode='connected')['id']
    competition.set_transport(rid,track_transport.defaults() | {'verified':False})
    with pytest.raises(ValueError,match='尚未核对'):competition.confirm(rid,template())
    competition.set_transport(rid,track_transport.defaults() | {'verified':True});competition.confirm(rid,template())


@pytest.mark.parametrize('field,value',[('base_url','https://elsewhere.invalid/api'),('paths',{}),('bundle_format','unknown'),('protocol_version','9'),('topic_link','https://elsewhere.invalid/{id}')])
def test_invalid_transport_never_writes_or_leaks_credentials(field,value):
    rid=competition.import_round(challenges(1),mode='demo')['id'];before=db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0]
    with pytest.raises(ValueError):competition.set_transport(rid,track_transport.defaults() | {field:value,'verified':True})
    assert db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0]==before


async def test_confirmed_clock_cannot_clear_deadline_and_preflight_reads_override():
    from cyberscientist import preflight
    ids=challenges(1);db.execute('UPDATE challenges SET platform_snapshot_json=?',('{}',))
    rnd=competition.import_round(ids,mode='demo',clock={'duration_hours':5});rid=rnd['id']
    competition.confirm(rid,template());ctl=FakeController();ctl.throttled=True;await evaluations.advance(ctl)
    run=db.query_one('SELECT * FROM runs');before=db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0]
    with pytest.raises(ValueError,match='不能清空'):competition.set_clock(rid,{'use_platform':True})
    assert db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0]==before
    auth=db.query_one('SELECT * FROM authorizations WHERE run_id=?',(run['id'],))
    assert 4.9*3600<run_clock.remaining(run,auth)<5.1*3600
    # W9 readiness requires prompt, protocol evidence and matching main account
    # as well as the W3 clock. Supply those facts without relaxing clock checks.
    from cyberscientist import competition_prompts,mailboxes,config
    competition_prompts.publish(rid,'fixture user prompt',competition_prompts.latest(rid)['version'])
    snapshot=json.loads(db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0])
    snapshot['submission_transport']=track_transport.defaults(config.load_settings()['playground']['base_url']) | {'verified':True,'evidence':{'source':'synthetic_fixture'}}
    db.execute('UPDATE eval_runs SET config_json=? WHERE id=?',(json.dumps(snapshot),rid))
    config.update_secret('clock-fixture-main','clock-fixture-only')
    db.execute("INSERT INTO mailboxes(id,role,email,platform,secret_ref,status,created_at) VALUES('clock-main','harvest','clock@example.test',?,'local:clock-fixture-main','active',?)",(config.load_settings()['mailbox']['platform'],db.utcnow()))
    facts=preflight.track_checks();assert facts['status']=='pass'
    assert facts['facts']['tracks'][0]['clock']['source']=='operator_override'
    assert facts['facts']['tracks'][0]['clock']['platform_end'] is None


def test_platform_change_rejects_same_platform_name_before_any_request(monkeypatch):
    original=BohriumPlaygroundPlatform('https://platform-b.invalid/api',operator_token='fixture-b-token')
    frozen=track_transport.defaults('https://platform-a.invalid/api') | {'verified':True}
    calls=[];monkeypatch.setattr(BohriumPlaygroundPlatform,'_http',lambda *a,**k:calls.append((a,k)))
    with pytest.raises(PlatformError,match='凭据的平台地址不同') as exc:track_transport.TrackPlatform(frozen,original)
    assert exc.value.no_side_effect and not calls


def test_nested_arm_and_protocol_mismatch_use_existing_native_client(monkeypatch,tmp_path):
    import io,zipfile
    stream=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(valid_arm_zip())) as source,zipfile.ZipFile(stream,'w') as target:
        for name in source.namelist():target.writestr('bundle-root/'+name,source.read(name))
    package=tmp_path/'nested.zip';package.write_bytes(stream.getvalue())
    fake=FakeHTTP({('POST','/challenges/'):{'id':'nested'},('POST','/attempts/nested/bundle'):{'bundleStatus':'valid'},('POST','/attempts/nested/submit'):{'status':'submitted'}})
    monkeypatch.setattr(BohriumPlaygroundPlatform,'_http',lambda self,*a,**k:fake(*a,**k))
    base=BohriumPlaygroundPlatform(config.load_settings()['playground']['base_url'])
    platform=track_transport.TrackPlatform(track_transport.defaults() | {'verified':True},base)
    assert platform.submit_package('fixture@fixture.invalid','fixture-token',str(package),'nested-topic')['accepted']
    before=len(fake.calls);platform.transport['protocol_version']='1.0'
    with pytest.raises(PlatformError,match='版本'):platform.submit_package('fixture@fixture.invalid','fixture-token',str(package),'nested-topic')
    assert len(fake.calls)==before


def test_native_track_http_does_not_follow_credential_redirect():
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            calls.append(self.path)
            self.send_response(302);self.send_header('Location',f'http://localhost:{self.server.server_port}/sink');self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}/api'
    try:
        platform=track_transport.TrackPlatform(track_transport.defaults(base) | {'verified':True},BohriumPlaygroundPlatform(base))
        with pytest.raises(PlatformError,match='302'):platform.fetch_score('fixture@fixture.invalid','fixture-token','id')
        assert calls==['/api/attempts/id/score']
    finally:server.shutdown();server.server_close();thread.join(2)
