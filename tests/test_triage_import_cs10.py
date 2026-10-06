import asyncio
import json
import pytest
from httpx import ASGITransport, AsyncClient
from cyberscientist import competition, competition_triage as helpers, config, db, evaluations, features, planning, resource_coordinator
from cyberscientist.brains.base import BrainEvent, SessionRef
from cyberscientist.controller import RunController
from test_competition import challenges, template


def seed(n=10, mode='demo'):
    ids=challenges(n)
    for i,cid in enumerate(ids):
        db.execute('UPDATE challenges SET platform_challenge_id=? WHERE id=?',(f'public-{i}',cid))
    settings=config.load_settings()
    settings['solver_roster']=[{'id':'fixture-ds','name':'事务助手','runtime':'codex','provider':'deepseek','model_id':'deepseek-flash','reasoning_effort':'high','note':'明确环境步骤'}]
    config.save_settings(settings)
    rnd=competition.import_round(ids,mode=mode)
    items=[{'platform_challenge_id':f'public-{i}','priority':i,'solver_entry':'fixture-ds','data_status':f'用户报告{i}','pi_notes':f'数据风险{i}；环境建议{i}'} for i in range(n)]
    return rnd,items


def historical_import(round_id,items):
    from cyberscientist import challenge_models
    snapshot=json.loads(db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(round_id,))[0])
    settings=config.load_settings()
    snapshot['user_triage']={f'c{i}':{**item,'solver_entry':challenge_models.solver(item['solver_entry'],settings),'source':'operator_json'} for i,item in enumerate(items)}
    raw=json.dumps(items)
    with db.transaction() as conn:
        import uuid,hashlib
        conn.execute('INSERT INTO competition_triage_imports VALUES(?,?,?,?,?)',('historical_'+uuid.uuid4().hex,round_id,raw,hashlib.sha256(raw.encode()).hexdigest(),db.utcnow()))
        conn.execute('UPDATE eval_runs SET config_json=? WHERE id=?',(json.dumps(snapshot),round_id))
        for i,item in enumerate(items):conn.execute('UPDATE eval_results SET priority=? WHERE eval_id=? AND challenge_id=?',(item['priority'],round_id,f'c{i}'))


@pytest.mark.asyncio
async def test_ten_imports_atomic_queue_frozen_user_guidance_and_no_implicit_authorization():
    from cyberscientist.api import create_app
    rnd,items=seed()
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://t') as client:
        response=await client.post(f"/api/v1/rounds/{rnd['id']}/triage-import",json={'items':items})
        assert response.status_code==422 and '已停用' in response.text
    historical_import(rnd['id'],items)
    assert [i['priority'] for i in competition.get_round(rnd['id'])['items']]==list(range(9,-1,-1))
    assert not db.query('SELECT * FROM runs') and not db.query('SELECT * FROM authorizations')
    before=dict(db.query_one('SELECT * FROM competition_triage_imports'))
    db.init_db();db.init_db()
    assert dict(db.query_one('SELECT * FROM competition_triage_imports'))==before
    competition.confirm(rnd['id'],template())
    class Controller(RunController):
        def __init__(self):super().__init__();self.started=[]
        async def start_async(self,rid):
            self.started.append(rid)
            db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,))
            return self.run_snapshot(rid)
    ctl=Controller();await evaluations.advance(ctl)
    assert len(ctl.started)==10
    assert [db.query_one('SELECT challenge_id FROM runs WHERE id=?',(r,))[0] for r in ctl.started]==[f'c{i}' for i in range(9,-1,-1)]
    for rid in ctl.started:
        row=db.query_one('SELECT * FROM runs WHERE id=?',(rid,));i=int(row['challenge_id'][1:])
        snapshot=json.loads(row['config_snapshot'])
        assert snapshot['settings']['brain']['model_id']=='gpt-6-astra'
        assert snapshot['settings']['executor']['provider']=='deepseek'
        context=planning.startup(rid,dict(db.query_one('SELECT * FROM challenges WHERE id=?',(row['challenge_id'],))))
        assert context['user_transactional_guidance']['pi_notes']==items[i]['pi_notes']
        assert context['user_transactional_guidance']['source']=='operator_json'
        assert '不是已验证事实' in context['user_transactional_guidance']['notice']


@pytest.mark.parametrize('mutation',[
    lambda a:a[-1].update(platform_challenge_id='foreign'),
    lambda a:a[-1].update(solver_entry='missing'),
    lambda a:a[-1].update(priority=1.0),
    lambda a:a[-1].update(priority=True),
    lambda a:a[-1].update(allow_model_calls=True),
    lambda a:a[-1].update(pi_notes='sk-'+'x'*45),
    lambda a:a[-1].update(platform_challenge_id=a[0]['platform_challenge_id']),
])
def test_invalid_last_item_cannot_partially_write(mutation):
    rnd,items=seed();before=dict(db.query_one('SELECT * FROM eval_runs'))
    mutation(items)
    with pytest.raises(competition.CompetitionError):competition.import_triage(rnd['id'],items)
    assert dict(db.query_one('SELECT * FROM eval_runs'))==before
    assert not db.query('SELECT * FROM competition_triage_imports')
    assert all(row[0]==0 for row in db.query('SELECT priority FROM eval_results'))


def test_import_revisions_retained_override_explicit_and_confirmed_round_rejects():
    rnd,items=seed(1);historical_import(rnd['id'],items)
    items[0]['pi_notes']='第二版事务提示';historical_import(rnd['id'],items)
    assert len(db.query('SELECT * FROM competition_triage_imports'))==2
    result=competition.confirm(rnd['id'],template(),{'c0':{'pi_notes':'明确用户覆盖','authorization':template()['authorization']}})
    assert result['items'][0]['template']['pi_notes']=='明确用户覆盖'
    assert result['items'][0]['template']['solver_id']=='fixture-ds'
    with pytest.raises(competition.CompetitionError,match='已停用'):competition.import_triage(rnd['id'],items)


def test_imported_solver_can_be_explicitly_cleared_for_manual_executor():
    rnd,items=seed(1);historical_import(rnd['id'],items)
    override={'solver_id':None,'model_config':{'executor':{'runtime':'codex','provider':'codex','model_id':'gpt-6.1-sol','reasoning_effort':'xhigh'}}}
    result=competition.confirm(rnd['id'],template(),{'c0':override})['items'][0]['template']
    assert result['solver_id'] is None and result['solver_entry'] is None
    assert result['model_config']['executor']['provider']=='codex'
    assert result['pi_notes']==items[0]['pi_notes']


def valid_result():
    return {'difficulty':'easy','estimated_minutes':1,'estimated_cost_cny':None,'recommended_model':'deepseek-flash','recommended_solver_id':'fixture-ds','reason':'fixture建议'}


@pytest.mark.asyncio
async def test_helpers_parallel_three_and_lower_effort_only_after_timeout(monkeypatch):
    rnd,_=seed(6);monkeypatch.setattr(helpers,'TIMEOUT',.03)
    ctl=RunController();opened=[];closed=[];active=0;peak=0
    class Brain:
        def __init__(self,settings):self.effort=settings['brain']['reasoning_effort'];self.owner=None
        async def open(self,spec):
            nonlocal active,peak
            active+=1;peak=max(peak,active);self.owner=spec['working_directory'];opened.append((self.owner,self.effort))
            return SessionRef('fake',self.owner)
        async def review(self,session,packet):
            await asyncio.sleep(.1 if self.effort=='xhigh' else .001)
            yield BrainEvent('task_result',{'result':valid_result()})
        async def close(self,session):
            nonlocal active
            active-=1;closed.append(self.owner)
    monkeypatch.setattr(ctl,'_make_brain',Brain)
    await competition.triage(rnd['id'],ctl)
    assert peak==3 and active==0 and len(opened)==len(closed)==12
    assert config.load_settings()['brain']['reasoning_effort']=='xhigh'
    for row in competition.get_round(rnd['id'])['items']:
        assert [{key:a[key] for key in ('status','helper_effort')} for a in row['triage_attempts']]==[{'status':'timeout','helper_effort':'xhigh'},{'status':'done','helper_effort':'high'}]
        assert row['triage']['difficulty']=='easy'
    assert not db.query('SELECT * FROM model_session_leases')


@pytest.mark.asyncio
async def test_close_unknown_holds_lease_and_blocks_timeout_retry_until_reconciled(monkeypatch):
    rnd,_=seed(1,'connected');monkeypatch.setattr(helpers,'TIMEOUT',.01)
    ctl=RunController();calls=[];fail=True
    class Brain:
        async def open(self,spec):calls.append('open');return SessionRef('fake','fixture')
        async def review(self,session,packet):
            await asyncio.sleep(.1)
            yield BrainEvent('task_result',{'result':valid_result()})
        async def close(self,session):
            if fail:raise RuntimeError('native close unknown')
    monkeypatch.setattr(ctl,'_make_brain',lambda settings:Brain())
    await competition.triage(rnd['id'],ctl,True)
    assert calls==['open'] and len(db.query('SELECT * FROM model_session_leases'))==1
    assert resource_coordinator.close_unknowns()
    assert competition.get_round(rnd['id'])['items'][0]['triage_attempts'][-1]['status']=='close_unknown'
    fail=False;await helpers.retry_closes(timeout=1)
    assert not db.query('SELECT * FROM model_session_leases') and not resource_coordinator.close_unknowns()


@pytest.mark.asyncio
async def test_explicit_request_id_joins_native_task_after_caller_cancel(monkeypatch):
    rnd,_=seed(1);ctl=RunController();entered=asyncio.Event();release=asyncio.Event();calls=[]
    class Brain:
        async def open(self,spec):calls.append('open');entered.set();return SessionRef('fake','fixture')
        async def review(self,session,packet):
            await release.wait();yield BrainEvent('task_result',{'result':valid_result()})
        async def close(self,session):calls.append('close')
    monkeypatch.setattr(ctl,'_make_brain',lambda settings:Brain())
    first=asyncio.create_task(competition.triage(rnd['id'],ctl,operation_id='same'));await entered.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):await first
    second=asyncio.create_task(competition.triage(rnd['id'],ctl,operation_id='same'));release.set();await second
    assert calls==['open','close']
    features.switch('system_triage',False)
    with pytest.raises(competition.CompetitionError,match='关闭'):await competition.triage(rnd['id'],ctl)
    assert calls==['open','close']


@pytest.mark.asyncio
async def test_429_does_not_downgrade_or_replay_helper(monkeypatch):
    rnd,_=seed(1);ctl=RunController();efforts=[]
    class Brain:
        async def open(self,spec):return SessionRef('fake','fixture')
        async def review(self,session,packet):
            raise RuntimeError('HTTP 429 Retry-After: 1')
            yield
        async def close(self,session):pass
    def make(settings):efforts.append(settings['brain']['reasoning_effort']);return Brain()
    monkeypatch.setattr(ctl,'_make_brain',make)
    await competition.triage(rnd['id'],ctl)
    assert efforts==['xhigh']
    assert competition.get_round(rnd['id'])['items'][0]['triage_attempts'][0]['status']=='unknown'


@pytest.mark.asyncio
async def test_shutdown_cancellation_persists_started_and_interrupted_history(monkeypatch):
    rnd,_=seed(1);ctl=RunController();entered=asyncio.Event();closed=[]
    item=rnd['items'][0];old=json.dumps(valid_result())
    db.execute('UPDATE eval_results SET triage_json=? WHERE id=?',(old,item['id']))
    class Brain:
        async def open(self,spec):return SessionRef('fake','fixture')
        async def review(self,session,packet):
            entered.set();await asyncio.Event().wait();yield
        async def close(self,session):closed.append(True)
    monkeypatch.setattr(ctl,'_make_brain',lambda settings:Brain())
    caller=asyncio.create_task(competition.triage(rnd['id'],ctl,operation_id='shutdown'));await entered.wait()
    assert db.query_one('SELECT status FROM competition_triage_attempts')[0]=='started'
    await helpers.drain()
    with pytest.raises(asyncio.CancelledError):await caller
    assert closed==[True]
    record=dict(db.query_one('SELECT * FROM competition_triage_attempts'))
    assert record['status']=='interrupted' and record['ended_at'] and record['previous_result_json']==old
    db.init_db();db.init_db()
    current=competition.get_round(rnd['id'])['items'][0]
    assert current['triage']['difficulty']=='unknown' and current['triage_attempts'][0]['status']=='interrupted'
