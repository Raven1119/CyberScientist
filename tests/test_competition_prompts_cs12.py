"""Explicit adoption, per-topic launches, frozen prompts and deadline proofs."""
import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime,timedelta,timezone
from threading import Event
from types import SimpleNamespace
import pytest
from httpx import ASGITransport,AsyncClient
from cyberscientist import api,collab,competition,competition_prompts as prompts,config,db,evaluations,maintenance,run_clock,runtime_facts,resource_coordinator
from cyberscientist.brains.base import BrainEvent,SessionRef
from cyberscientist.controller import RunController,ControllerError
from test_competition import FakeController,template,challenges
from test_triage_import_cs10 import seed,valid_result


def prompt_text(version):
    return f'全赛道建议版本{version}\n## public-0\n只给第一题的建议{version}\n## public-1\n只给暂缓题的建议{version}\n## public-2\n跳过题的建议{version}\n'


def set_end(round_id,value):
    snapshot=json.loads(db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(round_id,))[0])
    snapshot['track_clock']['end']=value
    for item in snapshot['entries']: item['challenge_snapshot']['platform']['roundEndAt']=value
    db.execute('UPDATE eval_runs SET config_json=? WHERE id=?',(json.dumps(snapshot),round_id))


async def review_once(ctl,rid,seen):
    class Brain:
        async def review(self,session,packet):
            seen.append(packet)
            yield BrainEvent('review_result',{'result':{'schema_version':1,'message_type':'review_result','frame_id':packet['frame_id'],'disposition':'silent','private_note_md':'fixture','watchlist':[],'guidance':None}})
    with db.transaction() as conn:
        reqid=collab._enqueue_request_tx(conn,rid,source='requested',blocking=False,trigger='manual')
    req=db.query_one('SELECT * FROM review_requests WHERE id=?',(reqid,))
    await ctl._run_one_review_impl(rid,req,Brain(),SessionRef('fixture','readonly'))
    assert db.query_one('SELECT status FROM review_requests WHERE id=?',(reqid,))[0]=='done'


async def test_prompt_adoption_launches_updates_and_unlimited_clock_end_to_end(monkeypatch):
    rnd,_=seed(3);rid=rnd['id'];initial=prompts.publish(rid,prompt_text(1),0)
    assert initial['sha256']==hashlib.sha256(prompt_text(1).encode()).hexdigest()
    seen_triage=[]
    class Helper:
        async def open(self,spec):return SessionRef('fixture','triage')
        async def close(self,session):pass
        async def review(self,session,packet):
            seen_triage.append(packet)
            yield BrainEvent('task_result',{'result':valid_result() | {'priority':42,'data_complete':True}})
    ctl=FakeController();ctl.throttled=True;monkeypatch.setattr(ctl,'_make_brain',lambda settings:Helper())
    await competition.triage(rid,ctl)
    assert len(seen_triage)==3 and all(p['user_prompt']['version']==1 for p in seen_triage)
    assert all(row['priority']==0 for row in db.query('SELECT * FROM eval_results'))
    assert not db.query('SELECT * FROM runs') and not db.query('SELECT * FROM authorizations')
    competition.adopt_suggestions(rid)
    item_ids={row['challenge_id']:row['id'] for row in db.query('SELECT * FROM eval_results')}
    competition.update_item(rid,item_ids['c1'],launch_state='deferred')
    competition.update_item(rid,item_ids['c2'],launch_state='skipped')
    base=template();base['authorization']['unlimited_resources']=True
    manual={'solver_id':None,'model_config':{'executor':{'runtime':'codex','provider':'codex','model_id':'gpt-6.1-sol','reasoning_effort':'high'}}}
    competition.save_template(rid,base)
    competition.confirm(rid,base,{'c0':manual})
    # Update while the immediate item is queued: its original snapshot stays v1.
    prompts.publish(rid,prompt_text(2),1)
    await evaluations.advance(ctl)
    first=db.query_one("SELECT * FROM runs WHERE challenge_id='c0'")
    assert len(db.query('SELECT * FROM runs'))==1
    frozen=json.loads(first['config_snapshot'])['competition']['user_prompt']
    assert frozen['version']==1 and '第一题' in frozen['content_md'] and '暂缓题' not in frozen['content_md']
    assert json.loads(first['config_snapshot'])['settings']['executor']['provider']=='codex'
    cold=ctl._lifecycle_packet(first,'run_start',sparse=True)['user_prompt']
    assert cold['frozen_version']==1 and '版本1' in cold['initial_content_md'] and cold['label']=='用户更新' and '版本2' in cold['diff_md']
    reviews=[];await review_once(ctl,first['id'],reviews)
    prompts.publish(rid,prompt_text(3),2)
    await review_once(ctl,first['id'],reviews)
    assert reviews[-1]['user_prompt']['label']=='用户更新' and '版本3' in reviews[-1]['user_prompt']['diff_md']
    assert json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(first['id'],))[0])['competition']['user_prompt']==frozen
    new_template=base | {'solver_id':'fixture-ds'}
    competition.save_template(rid,new_template)
    before=dict(db.query_one('SELECT * FROM eval_results WHERE id=?',(item_ids['c1'],)))
    with pytest.raises(competition.CompetitionError,match='启动暂缓题'):
        competition.update_item(rid,item_ids['c1'],launch_state='immediate',priority=1)
    assert dict(db.query_one('SELECT * FROM eval_results WHERE id=?',(item_ids['c1'],)))==before
    competition.start_deferred(rid,item_ids['c1'])
    prompts.publish(rid,prompt_text(4),3)
    await evaluations.advance(ctl)
    second=db.query_one("SELECT * FROM runs WHERE challenge_id='c1'")
    state=json.loads(second['config_snapshot'])
    assert state['competition']['user_prompt']['version']==3
    assert state['settings']['executor']['provider']=='deepseek'
    assert not db.query_one("SELECT 1 FROM runs WHERE challenge_id='c2'")
    auth=db.query_one('SELECT * FROM authorizations WHERE run_id=?',(first['id'],))
    end=datetime.fromisoformat(json.loads(db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0])['track_clock']['end']).timestamp()
    now=datetime.now(timezone.utc).timestamp()
    assert auth['max_run_minutes']==0 and run_clock.remaining(first,auth,now+7200)>3*3600
    monkeypatch.setattr(run_clock.time,'time',lambda:now+7200)
    assert not ctl._run_minutes_exceeded(first) and runtime_facts.facts(first['id'])['remaining']['run_seconds']>3*3600
    budget=ctl.run_snapshot(first['id'])['budget']
    assert all(budget[key] is None for key in ('max_jobs','max_sandboxes','max_sandbox_minutes','max_trials','max_brain_reviews','max_environment_saves','max_compute_cost_cny','max_submissions','run_minutes_limit'))
    assert budget['model_turns']['limit'] is None
    monkeypatch.setattr(run_clock.time,'time',lambda:end+.1)
    assert ctl._run_minutes_exceeded(first)
    assert not db.query('SELECT * FROM compute_jobs') and not db.query('SELECT * FROM submissions')


async def test_prompt_template_roundtrip_survives_restart_and_other_page_save():
    rnd,_=seed(1);rid=rnd['id']
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://local') as client:
        result=await client.put(f'/api/v1/rounds/{rid}/prompt',json={'content_md':'可验证的用户建议','base_version':0})
        assert result.status_code==200 and result.json()['user_prompt']['version']==1
        saved=await client.put(f'/api/v1/rounds/{rid}/template',json={'template':template()})
        assert saved.status_code==200 and saved.json()['template']['authorization']['unlimited_resources']
        stale=await client.put(f'/api/v1/rounds/{rid}/prompt',json={'content_md':'旧页面改写','base_version':0})
        assert stale.status_code==409
        assert (await client.post(f'/api/v1/rounds/{rid}/triage-import',json={'items':[]})).status_code==422
        assert (await client.put(f'/api/v1/rounds/{rid}/prompt',json=[])).status_code==422
    db.get_db().close();del db._local.conn;db.init_db();db.init_db()
    settings=config.load_settings();settings['revision']+=1;settings['shadow']['enabled']=False;config.save_settings(settings)
    again=competition.get_round(rid)
    assert again['user_prompt']['content_md']=='可验证的用户建议' and again['template']['authorization']['unlimited_resources']
    assert len(db.query('SELECT * FROM competition_prompt_versions'))==1


def test_start_and_invalid_item_update_are_atomic():
    rnd,_=seed(1);rid=rnd['id'];item=rnd['items'][0]['id']
    before=dict(db.query_one('SELECT * FROM eval_results WHERE id=?',(item,)))
    with pytest.raises(ValueError):competition.update_item(rid,item,priority=20,paused=True,launch_state='bad')
    assert dict(db.query_one('SELECT * FROM eval_results WHERE id=?',(item,)))==before
    competition.update_item(rid,item,launch_state='deferred');competition.confirm(rid,template())
    old=dict(db.query_one('SELECT * FROM eval_results WHERE id=?',(item,)))
    db.execute("CREATE TEMP TRIGGER fail_round_start BEFORE UPDATE ON eval_runs BEGIN SELECT RAISE(ABORT,'fixture atomic failure'); END")
    with pytest.raises(sqlite3.IntegrityError):competition.start_deferred(rid,item)
    assert dict(db.query_one('SELECT * FROM eval_results WHERE id=?',(item,)))==old
    db.execute('DROP TRIGGER fail_round_start')
    competition.start_deferred(rid,item)
    assert db.query_one('SELECT launch_state,prompt_json FROM eval_results WHERE id=?',(item,))[0]=='immediate'


async def test_missing_or_expired_track_clock_never_dispatches_native(monkeypatch):
    rnd=competition.import_round(challenges(1),mode='connected');rid=rnd['id'];set_end(rid,None)
    with pytest.raises(ValueError,match='结束时间'):competition.confirm(rid,template())
    set_end(rid,(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat());competition.confirm(rid,template())
    set_end(rid,(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    ctl=FakeController();ctl.throttled=True;await evaluations.advance(ctl)
    assert not ctl.started and not db.query('SELECT * FROM runs')
    assert competition.get_round(rid)['status']=='complete'


async def test_old_unlimited_queue_keeps_original_finite_authorization():
    rnd=competition.import_round(challenges(1),mode='demo');rid=rnd['id'];competition.confirm(rid,template())
    snapshot=json.loads(db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0]);snapshot.pop('budget_policy')
    db.execute('UPDATE eval_runs SET config_json=? WHERE id=?',(json.dumps(snapshot),rid))
    row=db.query_one('SELECT * FROM eval_results');old=json.loads(row['template_json']);old['authorization']['max_run_minutes']=60
    source=json.dumps(old);db.execute('UPDATE eval_results SET template_json=? WHERE id=?',(source,row['id']))
    ctl=FakeController();ctl.throttled=True;await evaluations.advance(ctl)
    run=db.query_one('SELECT * FROM runs');auth=db.query_one('SELECT * FROM authorizations')
    assert auth['max_run_minutes']==60
    assert run_clock.remaining(run,auth,datetime.now(timezone.utc).timestamp()+7200)<0
    assert db.query_one('SELECT template_json FROM eval_results')[0]==source


def test_public_data_ready_alert_is_real_observation_not_implicit_start(monkeypatch):
    rnd,_=seed(1);rid=rnd['id'];item=rnd['items'][0]['id'];competition.update_item(rid,item,launch_state='deferred')
    details={'id':'c0','content':'数据待发布','resources':[],'platform':{},'title':'fixture','source':'current_public_get'}
    monkeypatch.setattr(competition,'_challenge_snapshot',lambda cid:dict(details))
    competition.refresh_data(rid);assert not db.query('SELECT * FROM alerts')
    details['content']='请使用随题训练集训练模型'
    competition.refresh_data(rid);assert not db.query('SELECT * FROM alerts')
    assert db.query_one('SELECT data_ready FROM eval_results WHERE id=?',(item,))[0]==0
    details.update(content='公开资源已发布',resources=[{'role':'task-public-data','url':'https://example.org/fixture.dat'}])
    competition.refresh_data(rid);competition.refresh_data(rid)
    assert len(db.query("SELECT * FROM alerts WHERE kind='competition.data_ready'"))==1
    assert not db.query('SELECT * FROM runs') and competition.get_round(rid)['items'][0]['launch_state']=='deferred'


async def test_disabled_run_goal_and_new_objective_comes_from_question():
    challenges(1);ctl=api.controller;rid=ctl.create_run('c0',mode='demo')['id']
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://local') as client:
        payload={'scope':'demo','allow_model_calls':False,'max_run_minutes':10,'objective':'旧入口目标'}
        rejected=await client.post(f'/api/v1/runs/{rid}/authorize',json=payload)
        assert rejected.status_code==410 and '已停用' in rejected.text and not db.query('SELECT * FROM authorizations')
        payload.pop('objective');payload['note']='授权备注不能覆盖研究目标'
        assert (await client.post(f'/api/v1/runs/{rid}/authorize',json=payload)).status_code==200
    assert db.query_one('SELECT objective_md FROM runs WHERE id=?',(rid,))[0]=='合成测试题'


async def test_unlimited_run_after_hours_ends_via_normal_native_cleanup(monkeypatch):
    rnd=competition.import_round(challenges(1),mode='demo');competition.confirm(rnd['id'],template())
    starter=FakeController();starter.throttled=True;await evaluations.advance(starter)
    row=db.query_one('SELECT * FROM runs');rid=row['id']
    db.execute('UPDATE runs SET clock_version=1,active_elapsed_seconds=7200 WHERE id=?',(rid,))
    run_clock.start(rid)
    end=datetime.now(timezone.utc)+timedelta(seconds=.15);set_end(rnd['id'],end.isoformat())
    ctl=RunController();closed=[]
    class Brain:
        async def open(self,spec):return SessionRef('fixture','pi')
        async def close(self,session):closed.append('pi')
    class Prime:
        async def start(self,spec):return 'fixture-executor'
        async def events(self,session):await asyncio.Event().wait();yield {}
        async def abort(self,session):return SimpleNamespace(status='confirmed',detail='fixture stopped')
        async def close(self,session):closed.append('executor')
    monkeypatch.setattr(ctl,'_make_brain',lambda settings:Brain())
    monkeypatch.setattr(ctl,'_make_prime',lambda settings:Prime())
    monkeypatch.setattr(ctl,'_enqueue_lifecycle',lambda *a,**k:None)
    # Exercise the real idempotent ledger insertion, without a model turn.
    monkeypatch.setattr(maintenance,'schedule',lambda coro:coro.close())
    assert not ctl._run_minutes_exceeded(row)
    queue=asyncio.Queue();ctl._signals[rid]=queue
    task=asyncio.create_task(ctl._run_loop(rid,queue));ctl._tasks[rid]=task
    try:
        await asyncio.wait_for(task,2)
        result=db.query_one('SELECT phase,end_reason FROM runs WHERE id=?',(rid,))
        assert tuple(result)==('finished','authorization_expired')
        assert {'pi','executor'}<=set(closed)
        endings=db.query('SELECT reason FROM run_post_reviews WHERE run_id=?',(rid,))
        assert len(endings)==1 and endings[0]['reason']=='authorization_expired'
        assert not db.query('SELECT * FROM submissions') and not db.query('SELECT * FROM compute_jobs')
    finally:
        if not task.done():task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.parametrize('lifespan',[False,True])
async def test_cancelled_data_refresh_stays_owned_until_thread_finishes(monkeypatch,lifespan):
    from cyberscientist import power,machine_catalog
    rid=competition.import_round(challenges(1),mode='demo')['id']
    entered,release,closed=Event(),Event(),Event();exiting=asyncio.Event()
    def refresh(*args): entered.set();assert release.wait(5);closed.set();return {}
    monkeypatch.setattr(competition,'refresh_data',refresh);monkeypatch.setattr(machine_catalog,'refresh',lambda:None)
    app=api.create_app()
    async def host():
        async def work():
            async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as client:
                request=asyncio.create_task(client.post(f'/api/v1/rounds/{rid}/refresh-data'))
                assert await asyncio.to_thread(entered.wait,1)
                request.cancel()
                with pytest.raises(asyncio.CancelledError): await request
            exiting.set()
            if not lifespan: assert (await power.safe_shutdown(api.controller,timeout=.1))['can_shutdown']
        if lifespan:
            async with app.router.lifespan_context(app): await work()
        else: await work()
    task=asyncio.create_task(host())
    try:
        await asyncio.wait_for(exiting.wait(),2);await asyncio.sleep(.02)
        assert not task.done() and resource_coordinator.auxiliary_tasks() and not closed.is_set()
        release.set();await asyncio.wait_for(task,2)
        assert closed.is_set() and not resource_coordinator.auxiliary_tasks()
    finally:release.set();await asyncio.gather(task,return_exceptions=True)


async def test_deferred_preserves_explicit_topic_choice_but_inherits_current_track_defaults():
    rnd,_=seed(2);rid=rnd['id'];items={i['challenge_id']:i['id'] for i in rnd['items']}
    for ident in items.values():competition.update_item(rid,ident,launch_state='deferred')
    prompts.publish(rid,prompt_text(1),0)
    base=template() | {'pi_notes':'global old','solver_note':'global solver old'}
    base['authorization']['unlimited_resources']=False
    choice={'solver_id':'fixture-ds','pi_notes':'topic explicit PI notes','authorization':dict(base['authorization'],max_jobs=7)}
    competition.confirm(rid,base,{'c0':choice})
    current=template() | {'pi_notes':'global new','solver_note':'global solver new'}
    current['authorization'].update(max_jobs=9,unlimited_resources=False)
    competition.save_template(rid,current);prompts.publish(rid,prompt_text(2),1)
    db.get_db().close();del db._local.conn;db.init_db()
    for ident in items.values():competition.start_deferred(rid,ident)
    ctl=FakeController();ctl.throttled=True;await evaluations.advance(ctl)
    from cyberscientist import planning
    for cid,provider,jobs,notes in [('c0','deepseek',7,'topic explicit PI notes'),('c1','codex',9,'global new')]:
        row=db.query_one('SELECT * FROM runs WHERE challenge_id=?',(cid,));snap=json.loads(row['config_snapshot'])
        assert snap['settings']['executor']['provider']==provider
        assert snap['competition']['user_prompt']['version']==2
        auth=db.query_one('SELECT * FROM authorizations WHERE run_id=?',(row['id'],))
        assert auth['max_jobs']==jobs
        brief=planning.startup(row['id'],dict(db.query_one('SELECT * FROM challenges WHERE id=?',(cid,))))
        assert brief['user_transactional_guidance']['pi_notes']==notes
        assert snap['competition']['solver_note']=='global solver new'


@pytest.mark.parametrize('models,code',[(None,200),({'unrecognized_role':{}},422),('invalid',422)])
async def test_topic_model_input_is_validated_before_any_confirmation_write(models,code):
    rnd,_=seed(1);rid=rnd['id']
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://local') as client:
        response=await client.post(f'/api/v1/rounds/{rid}/confirm',json={'template':template(),'overrides':{'c0':{'model_config':models}}})
    assert response.status_code==code
    if code==422:
        assert db.query_one('SELECT status FROM eval_runs WHERE id=?',(rid,))[0]=='draft'
        assert db.query_one('SELECT template_json FROM eval_results WHERE eval_id=?',(rid,))[0] is None


@pytest.mark.parametrize('base_auth,topic_auth,code',[(None,{},200),({},None,200),({},'invalid',422),({},[],422)])
async def test_topic_authorization_input_is_validated_before_confirmation_write(base_auth,topic_auth,code):
    rnd,_=seed(1);rid=rnd['id'];base=template() | {'authorization':base_auth}
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://local') as client:
        response=await client.post(f'/api/v1/rounds/{rid}/confirm',json={'template':base,'overrides':{'c0':{'authorization':topic_auth}}})
    assert response.status_code==code
    if code==422:
        assert db.query_one('SELECT status FROM eval_runs WHERE id=?',(rid,))[0]=='draft'
        assert db.query_one('SELECT template_json FROM eval_results WHERE eval_id=?',(rid,))[0] is None
