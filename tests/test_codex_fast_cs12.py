"""Per-session negotiation and native role wiring; no real model calls."""
import json
import pytest
from httpx import ASGITransport,AsyncClient
from cyberscientist import api,challenge_models,codex_fast,competition,competition_triage,config,db,evaluations,preflight
from cyberscientist.brains.codex import CodexBrain
from cyberscientist.brains.base import BrainEvent,SessionRef
from cyberscientist.controller import RunController
from cyberscientist.prime.codex_exec import CodexExecutor
from test_codex_runtime import FakeRpc
from test_competition import challenges,template,FakeController
from test_triage_import_cs10 import seed,valid_result


class TierRpc(FakeRpc):
    supported=True
    async def request(self,method,params=None,**kwargs):
        if method=='model/list':
            self.calls.append((method,params))
            return {'data':[{'model':'gpt-6.1-sol','serviceTiers':[{'id':'priority','name':'Fast'}] if self.supported else []}]}
        if method=='account/rateLimits/read':
            return {'rateLimits':{'primary':{'usedPercent':12,'resetsAt':999},'accountId':'fixture-account'},'accountId':'fixture-account'}
        result=await super().request(method,params,**kwargs)
        if method in ('thread/start','thread/resume'): result['serviceTier']=params.get('serviceTier') if params.get('serviceTier')!='default' else None
        return result


@pytest.mark.parametrize('role',['brain','executor'])
@pytest.mark.parametrize('fast',[False,True])
async def test_native_roles_send_actual_fast_tier_and_record_platform_ack(monkeypatch,role,fast):
    module='cyberscientist.brains.codex' if role=='brain' else 'cyberscientist.prime.codex_exec'
    monkeypatch.setattr(module+'.JsonRpcStdio',TierRpc)
    runtime=(CodexBrain if role=='brain' else CodexExecutor)(executable='/bin/true',model='gpt-6.1-sol',effort='high',fast_mode=fast)
    session=await (runtime.open({'pi_files_readonly':True}) if role=='brain' else runtime.start({}))
    rpc=runtime.rpc if role=='brain' else runtime._sessions[session].rpc
    params=next(p for m,p in rpc.calls if m=='thread/start')
    assert params['serviceTier']==('priority' if fast else 'default') and params['config']['features.fast_mode']==fast
    facts=json.loads(db.query_one('SELECT payload_json FROM runtime_observations WHERE kind=?',('codex_fast:gpt-6.1-sol',))[0])
    assert facts['enabled']==fast and facts['observed_tier']==('priority' if fast else None)
    rate=db.query_one("SELECT payload_json FROM runtime_observations WHERE kind='codex_rate_limits'")[0]
    assert 'usedPercent' in rate and 'fixture-account' not in rate
    await runtime.close(session)


async def test_unsupported_catalog_omits_fast_without_blocking_native(monkeypatch):
    class Unsupported(TierRpc):supported=False
    monkeypatch.setattr('cyberscientist.brains.codex.JsonRpcStdio',Unsupported)
    brain=CodexBrain(executable='/bin/true',model='gpt-6.1-sol',effort='high',fast_mode=True)
    session=await brain.open({});params=next(p for m,p in brain.rpc.calls if m=='thread/start')
    assert 'serviceTier' not in params and params['config']['features.fast_mode'] is False
    assert session.raw['fast_mode']['status']=='unsupported' and not session.raw['fast_mode']['enabled']
    await brain.close(session)


async def test_deepseek_is_not_given_native_fast_parameters():
    params={};facts=await codex_fast.prepare(TierRpc(),params,'deepseek-flash','deepseek',True)
    assert params=={} and facts['status']=='provider_not_supported'


@pytest.mark.parametrize('message,fallback',[('unsupported service tier priority',True),('HTTP 429 rate limit',False),('request timeout',False),('HTTP 429 priority fast tier not supported while rate limit exceeded',False)])
async def test_only_explicit_native_fast_refusal_can_retry_default(monkeypatch,message,fallback):
    from cyberscientist.jsonrpc_stdio import ProtocolError
    class Refused(TierRpc):
        starts=0
        async def request(self,method,params=None,**kwargs):
            if method=='thread/start':
                self.starts+=1
                if self.starts==1:raise ProtocolError(json.dumps({'code':-32602 if fallback else 429,'message':message}))
            return await super().request(method,params,**kwargs)
    monkeypatch.setattr('cyberscientist.brains.codex.JsonRpcStdio',Refused)
    brain=CodexBrain(executable='/bin/true',model='gpt-6.1-sol',effort='high',fast_mode=True)
    if fallback:
        session=await brain.open({});assert brain.rpc.starts==2
        assert session.raw['fast_mode']['status']=='unsupported_native' and not session.raw['fast_mode']['enabled']
        await brain.close(session)
    else:
        with pytest.raises(ProtocolError,match=message):await brain.open({})
        assert brain.rpc is None


@pytest.mark.parametrize('message',['HTTP 429 Too Many Requests Retry-After:60','provider authentication refused','catalog read timeout'])
async def test_catalog_business_failure_never_downgrades_and_starts_turn(monkeypatch,message):
    from cyberscientist.jsonrpc_stdio import ProtocolError
    created=[]
    class Broken(TierRpc):
        def __init__(self,*a,**k):super().__init__(*a,**k);created.append(self)
        async def request(self,method,params=None,**kwargs):
            if method=='model/list':raise ProtocolError(message)
            return await super().request(method,params,**kwargs)
    monkeypatch.setattr('cyberscientist.brains.codex.JsonRpcStdio',Broken)
    brain=CodexBrain(executable='/bin/true',model='gpt-6.1-sol',effort='high',fast_mode=True)
    with pytest.raises(ProtocolError,match=message):await brain.open({})
    assert created[0].stopped and not any(m in ('thread/start','turn/start') for m,_ in created[0].calls)


async def test_persisted_fast_role_roster_and_effort_survive_other_setting_save():
    settings=config.load_settings();settings['codex_fast_mode']=True
    settings['executor'].update(model_id='gpt-6.1-sol',reasoning_effort='high',fast_mode=True)
    settings['solver_roster']=[{'id':'sol-tier','name':'Sol','runtime':'codex','provider':'codex','model_id':'gpt-6.1-sol','reasoning_effort':'max','fast_mode':False}]
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://fixture') as client:
        response=await client.put('/api/v1/settings',json={'settings':settings,'base_revision':settings['revision']});assert response.status_code==200
        value=(await client.get('/api/v1/settings')).json();value['shadow']['enabled']=False
        response=await client.put('/api/v1/settings',json={'settings':value,'base_revision':value['revision']});assert response.status_code==200
    db.get_db().close();del db._local.conn;db.init_db();saved=config.load_settings()
    assert saved['executor']['fast_mode'] and saved['executor']['reasoning_effort']=='high'
    assert saved['solver_roster'][0]['fast_mode'] is False and saved['solver_roster'][0]['reasoning_effort']=='max'
    rnd=competition.import_round(challenges(1),mode='demo');competition.confirm(rnd['id'],template())
    ctl=FakeController();ctl.throttled=True;await evaluations.advance(ctl)
    run=db.query_one('SELECT * FROM runs');runtime=ctl._runtime_settings(run['id'])
    assert runtime['brain']['fast_mode'] and runtime['executor']['fast_mode']
    assert runtime['brain']['model_id']=='gpt-6-astra' and runtime['brain']['reasoning_effort']=='xhigh'
    runtime['app']['mode']='connected'
    assert ctl._make_brain(runtime).fast_mode and ctl._make_prime(runtime).fast_mode


async def test_easy_triage_recommends_deepseek_but_never_applies_it_implicitly(monkeypatch):
    rnd,_=seed(1);ctl=RunController()
    class Helper:
        async def open(self,spec):return SessionRef('fixture','helper')
        async def close(self,session):pass
        async def review(self,session,packet):yield BrainEvent('task_result',{'result':valid_result() | {'difficulty':'easy','recommended_solver_id':None,'recommended_model':'gpt-6.1-sol'}})
    monkeypatch.setattr(ctl,'_make_brain',lambda settings:Helper())
    await competition.triage(rnd['id'],ctl)
    row=db.query_one('SELECT * FROM eval_results');result=json.loads(row['triage_json'])
    assert result['recommended_solver_id']=='fixture-ds' and result['recommended_model']=='deepseek-flash'
    assert row['template_json'] is None and not db.query('SELECT * FROM runs')


def test_fast_selfcheck_reports_unobserved_unsupported_and_confirmed():
    settings=config.load_settings();settings['executor']['model_id']='gpt-6.1-sol'
    assert preflight.fast_check(settings)['status']=='warn'
    for model in ('gpt-6-astra','gpt-6.1-sol'):
        codex_fast.record({'requested':True,'model':model,'status':'enabled','enabled':True,'tier':'priority'})
    assert preflight.fast_check(settings)['status']=='pass'
    codex_fast.record({'requested':True,'model':'gpt-6.1-sol','status':'unsupported','enabled':False})
    assert preflight.fast_check(settings)['status']=='warn'


@pytest.mark.parametrize('value',['yes',1,None])
def test_invalid_fast_flags_rejected(value):
    settings=config.load_settings();choice=dict(settings['executor'],fast_mode=value)
    with pytest.raises(ValueError,match='布尔值'):challenge_models.choose('executor',choice,settings)
