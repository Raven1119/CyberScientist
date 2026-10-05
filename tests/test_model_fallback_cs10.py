import asyncio
import json
from datetime import datetime,timedelta,timezone
import pytest
from httpx import ASGITransport,AsyncClient
from cyberscientist import api,competition,config,db,evaluations,model_fallback,model_providers,resource_coordinator
from cyberscientist.controller import RunController
from test_competition import challenges,template


def setup(monkeypatch):
    settings=config.load_settings();settings['app']['mode']='connected'
    settings['executor'].update(runtime='codex',provider='codex',model_id='gpt-6.1-sol',reasoning_effort='high')
    settings['solver_roster']=[{'id':'flash','name':'Flash','runtime':'codex','provider':'deepseek','model_id':'deepseek-flash','reasoning_effort':'high'}]
    settings['deepseek_fallback']={'after_minutes':5,'solver_id':'flash'}
    config.save_settings(settings);monkeypatch.setattr(config,'deepseek_key',lambda:'fake-readonly-credential')
    challenges(4)
    return settings


def prolonged(choice,minutes=6):
    model_providers.record_throttle(choice,'HTTP 429 Too Many Requests Retry-After: 60')
    model_fallback.note(choice,'HTTP 429 Too Many Requests Retry-After: 60')
    row=db.query_one('SELECT payload_json FROM runtime_observations WHERE kind=?',(model_fallback._key(choice),))
    facts=json.loads(row['payload_json']);facts['first_at']=(datetime.now(timezone.utc)-timedelta(minutes=minutes)).isoformat();facts['requests']['legacy']['first_at']=facts['first_at']
    db.execute('UPDATE runtime_observations SET payload_json=? WHERE kind=?',(json.dumps(facts),model_fallback._key(choice)))


def frozen(run):return json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(run['id'],))['config_snapshot'])


def test_new_run_switches_after_threshold_existing_run_frozen_recovers_and_pi_never_changes(monkeypatch):
    settings=setup(monkeypatch);controller=RunController()
    original=controller.create_run('c0','connected');old=frozen(original)
    prolonged(settings['executor'],4)
    before=controller.create_run('c1','connected');assert frozen(before)['settings']['executor']['provider']=='codex'
    prolonged(settings['executor'],6)
    fallback=controller.create_run('c2','connected');state=frozen(fallback)
    assert state['settings']['executor']['provider']=='deepseek' and state['solver_fallback']['solver_entry']['id']=='flash'
    assert state['settings']['brain']['model_id']=='gpt-6-astra' and state['settings']['brain']['reasoning_effort']=='xhigh'
    assert frozen(original)==old
    model_fallback.recovered(settings['executor'])
    restored=controller.create_run('c3','connected');assert frozen(restored)['settings']['executor']['provider']=='codex'
    assert not db.query('SELECT * FROM authorizations') and not db.query('SELECT * FROM submissions')


async def test_competition_projects_fallback_before_admission_and_pi_provider_backoff_still_queues(monkeypatch):
    settings=setup(monkeypatch)
    round_value=competition.import_round(['c0'],mode='connected');competition.confirm(round_value['id'],template())
    prolonged(settings['executor'])
    class Controller(RunController):
        async def start_async(self,rid):
            self.captured=self._runtime_settings(rid)
            db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,))
    ctl=Controller();evaluation=db.query_one('SELECT * FROM eval_runs WHERE id=?',(round_value['id'],))
    await competition.advance_round(ctl,evaluation)
    assert not db.query('SELECT * FROM runs') # Global provider cooldown still covers the fixed Astra PI.
    past=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    db.execute('UPDATE model_provider_backoff SET retry_at=?',(past,))
    await competition.advance_round(ctl,evaluation)
    assert ctl.captured['executor']['provider']=='deepseek' and ctl.captured['brain']['model_id']=='gpt-6-astra'
    assert json.loads(db.query_one('SELECT template_json FROM eval_results')['template_json'])['model_config']['executor']['provider']=='codex'


def test_astra_rate_limit_never_switches_pi_or_unthrottled_executor(monkeypatch):
    settings=setup(monkeypatch);prolonged(settings['brain'])
    chosen,facts=model_fallback.select(settings['executor'],settings)
    assert chosen['provider']=='codex' and facts['status']=='original'
    with pytest.raises(resource_coordinator.ResourceWait):
        with db.transaction() as conn:resource_coordinator.reserve_sessions_tx(conn,'fixed-pi',{'brain':settings['brain']})
    assert settings['brain']['model_id']=='gpt-6-astra'


def test_off_or_missing_key_does_not_switch_or_remove_history(monkeypatch):
    settings=setup(monkeypatch);prolonged(settings['executor']);before=model_fallback.facts()
    settings['features']['deepseek_fallback']=False
    assert model_fallback.select(settings['executor'],settings)[0]['provider']=='codex'
    settings['features']['deepseek_fallback']=True;monkeypatch.setattr(config,'deepseek_key',lambda:None)
    chosen,facts=model_fallback.select(settings['executor'],settings)
    assert chosen['provider']=='codex' and facts['status']=='unavailable' and model_fallback.facts()==before


async def test_native_will_retry_records_429_without_interrupting_same_turn_then_confirms_recovery():
    from cyberscientist.brains.codex import CodexBrain
    from cyberscientist.brains.base import SessionRef
    class RPC:
        async def request(self,*args,**kwargs):return {'turn':{'id':'same-turn'}}
        async def notifications(self):
            yield {'method':'error','params':{'threadId':'native-thread','willRetry':True,'error':{'code':429,'message':'Too Many Requests'}}}
            yield {'method':'item/completed','params':{'threadId':'native-thread','item':{'type':'agentMessage','text':'{"ok":true}'}}}
            yield {'method':'turn/completed','params':{'threadId':'native-thread','turn':{'id':'same-turn','status':'completed'}}}
    brain=CodexBrain('/fake/codex','gpt-6.1-sol','high');brain.rpc=RPC()
    events=brain._review_once(SessionRef('codex','native-thread'),{'protocol':'role_task','output_contract':{'type':'object','required':['ok'],'properties':{'ok':{'type':'boolean'}}}})
    event=await anext(events);assert event.type=='progress' and event.payload['will_retry']
    assert model_fallback.facts()[0]['status']=='waiting' and model_fallback.facts()[0]['will_retry']
    remaining=[event async for event in events]
    assert all(event.type!='error' for event in remaining) and model_fallback.facts()[0]['status']=='recovered'


async def test_fallback_configuration_roundtrip_and_invalid_entry_rejected(monkeypatch):
    setup(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://fixture') as client:
        current=(await client.get('/api/v1/settings')).json()
        response=await client.put('/api/v1/settings',json={'base_revision':current['revision'],'settings':{'deepseek_fallback':{'after_minutes':2,'solver_id':'flash'}}})
        assert response.status_code==200;revision=response.json()['revision']
        assert (await client.put('/api/v1/settings',json={'base_revision':revision,'settings':{'deepseek_fallback':{'after_minutes':True}}})).status_code==422
        response=await client.put('/api/v1/settings',json={'base_revision':revision,'settings':{'skills':{'always_on':[]}}})
        assert response.json()['deepseek_fallback']=={'after_minutes':2,'solver_id':'flash'}
        db.init_db();assert config.load_settings()['deepseek_fallback']=={'after_minutes':2,'solver_id':'flash'}


def test_new_provider_episode_resets_first_at_but_native_unresolved_episode_persists():
    choice={'runtime':'codex','provider':'codex','model_id':'gpt-6.1-sol'}
    prolonged(choice)
    old=model_fallback.facts()[0]['first_at']
    past=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    db.execute('UPDATE model_provider_backoff SET retry_at=?,first_at=?',(past,old))
    model_providers.record_throttle(choice,'HTTP 429 Too Many Requests', request_id='legacy')
    assert db.query_one('SELECT first_at FROM model_provider_backoff')['first_at']>old
    assert model_fallback.facts()[0]['first_at']==old


async def test_native_executor_internal_retry_stays_busy_and_records_request_model():
    from cyberscientist.prime.codex_exec import CodexExecutor,_Session
    release=asyncio.Event()
    class RPC:
        async def notifications(self):
            yield {'method':'error','params':{'threadId':'executor-thread','willRetry':True,'error':{'code':429,'message':'rate limit'}}}
            await release.wait()
            yield {'method':'turn/completed','params':{'threadId':'executor-thread','turn':{'id':'executor-turn','status':'completed'}}}
    executor=CodexExecutor('/fake/codex','gpt-6.1-sol','high')
    session=_Session(RPC(),'executor-thread');session.turn_id='executor-turn';session.busy=True
    pump=asyncio.create_task(executor._pump(session))
    event=await session.queue.get()
    assert event['type']=='execution.progress' and event['will_retry'] and session.busy
    assert model_fallback.facts()[0]['model_id']=='gpt-6.1-sol' and model_fallback.facts()[0]['status']=='waiting'
    release.set();await pump
    assert not session.busy and model_fallback.facts()[0]['status']=='recovered'
    assert (await session.queue.get())['type']=='executor.turn_completed'


async def test_competition_freezes_prechecked_projection_even_if_recovered_at_create(monkeypatch):
    settings=setup(monkeypatch);round_value=competition.import_round(['c0'],mode='connected')
    competition.confirm(round_value['id'],template());prolonged(settings['executor'])
    db.execute('UPDATE model_provider_backoff SET retry_at=?',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),))
    admissions=[];real_reserve=resource_coordinator.reserve_sessions_tx
    def reserve(conn,owner,choices):admissions.append(json.loads(json.dumps(choices)));return real_reserve(conn,owner,choices)
    monkeypatch.setattr(resource_coordinator,'reserve_sessions_tx',reserve)
    class Controller(RunController):
        def create_run(self,*args,**kwargs):
            model_fallback.recovered(settings['executor'])
            return super().create_run(*args,**kwargs)
        async def start_async(self,rid):db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,))
    await competition.advance_round(Controller(),db.query_one('SELECT * FROM eval_runs WHERE id=?',(round_value['id'],)))
    state=json.loads(db.query_one('SELECT config_snapshot FROM runs')['config_snapshot'])
    assert admissions[0]['executor']['provider']=='deepseek' and state['settings']['executor']['provider']=='deepseek'
    assert state['solver_fallback']['status']=='fallback' and state['competition']['solver_entry']['id']=='flash'


def test_old_concurrent_completion_cannot_clear_other_requests_continuous_429(monkeypatch):
    settings=setup(monkeypatch);choice=settings['executor'];old_ticket=model_fallback.ticket(choice)
    model_fallback.note(choice,'HTTP 429',request_id='B')
    row=db.query_one('SELECT payload_json FROM runtime_observations WHERE kind=?',(model_fallback._key(choice),));facts=json.loads(row['payload_json'])
    old=(datetime.now(timezone.utc)-timedelta(minutes=8)).isoformat();facts['requests']['B']['first_at']=old;facts['first_at']=old
    db.execute('UPDATE runtime_observations SET payload_json=? WHERE kind=?',(json.dumps(facts),model_fallback._key(choice)))
    model_fallback.recovered(choice,request_id='A',started_generation=old_ticket)
    assert model_fallback.select(choice,settings)[1]['status']=='fallback'
    model_fallback.note(choice,'HTTP 429',request_id='B')
    assert model_fallback.facts()[0]['first_at']==old
    model_fallback.note(choice,'HTTP 429',request_id='C')
    model_fallback.recovered(choice,request_id='C')
    assert model_fallback.select(choice,settings)[1]['status']=='fallback'
    model_fallback.recovered(choice,request_id='B')
    assert model_fallback.select(choice,settings)[0]['provider']=='codex'


def test_successful_fresh_request_confirms_same_generation_only(monkeypatch):
    settings=setup(monkeypatch);choice=settings['executor'];prolonged(choice)
    generation=model_fallback.ticket(choice)
    model_fallback.recovered(choice,request_id='fresh',started_generation=generation)
    assert model_fallback.select(choice,settings)[0]['provider']=='codex'
    model_fallback.note(choice,'HTTP 429',request_id='legacy')
    assert model_fallback.select(choice,settings)[1]['status']=='fallback'
