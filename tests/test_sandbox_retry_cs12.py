"""Native pre-mutation refusals retry one operation; uncertain effects do not."""
import json
import asyncio
from threading import Event
from pathlib import Path
import pytest
from httpx import AsyncClient,ASGITransport
from cyberscientist import compute,db,sandboxes,skills,power,api,resource_coordinator,collab
from test_sandboxes import run


def refusal(message,code='COMMAND_FAILED'):
    return {'ok':False,'exit_code':1,'stdout':json.dumps({'ok':False,'error':{
        'code':code,'http':400,'message':message,'retryable':False}}),'stderr':''}


def test_native_image_preparation_recovers_with_one_reservation(run,monkeypatch):
    _,rid,_,calls,_=run;native=compute._native;waits=[]
    def flaky(args,**kwargs):
        if args[:2]==['sandbox','create'] and len([a for a in calls if a[:2]==['sandbox','create']])<2:
            calls.append(args)
            return refusal('IMAGE_PREPARATION_IN_PROGRESS: wait and retry same create','INVALID_REQUEST')
        return native(args,**kwargs)
    monkeypatch.setattr(compute,'_native',flaky);monkeypatch.setattr(sandboxes.time,'sleep',waits.append)
    result=sandboxes.create(rid,'image-ready',{'timeout':600,'image':'registry.example/science:fixed'})
    assert result['status']=='active' and waits==[2,4]
    attempts=[a for a in calls if a[:2]==['sandbox','create']]
    assert len(attempts)==3 and all(a==attempts[0] for a in attempts)
    assert all(a[a.index('--request-id')+1]=='image-ready' for a in attempts)
    assert len(db.query('SELECT * FROM compute_sandboxes WHERE run_id=?',(rid,)))==1
    fact=json.loads(db.query_one("SELECT payload FROM events WHERE run_id=? AND type='sandbox.environment_observed'",(rid,))['payload'])
    assert fact['wait_seconds']==6 and fact['native_ok'] is True
    assert sandboxes.create(rid,'image-ready',{'timeout':600,'image':'registry.example/science:fixed'})['deduplicated']


def test_first_exec_tls_recovers_without_duplicate_command(run,monkeypatch):
    _,rid,_,calls,_=run;sid=sandboxes.create(rid,'ready',{'timeout':600})['sandbox_id']
    native=compute._native;waits=[]
    def flaky(args,**kwargs):
        if args[:2]==['sandbox','exec'] and not any(a[:2]==['sandbox','exec'] for a in calls):
            calls.append(args);return refusal('net/http: TLS handshake timeout: sandbox initial handshake')
        return native(args,**kwargs)
    monkeypatch.setattr(compute,'_native',flaky);monkeypatch.setattr(sandboxes.time,'sleep',waits.append)
    result=sandboxes.execute(rid,sid,'echo once',30,'stable-exec')
    assert result['status']=='completed' and waits==[2]
    attempts=[a for a in calls if a[:2]==['sandbox','exec']]
    assert len(attempts)==2 and attempts[0]==attempts[1]
    assert attempts[0][attempts[0].index('--request-id')+1]=='stable-exec'
    assert len(db.query('SELECT * FROM compute_sandbox_operations WHERE run_id=?',(rid,)))==1
    with pytest.raises(compute.ComputeError,match='已使用'):
        sandboxes.execute(rid,sid,'echo once',30,'stable-exec')
    assert len(calls)==3


@pytest.mark.parametrize('receipt',[
    {'ok':False,'unknown':True,'stdout':'','exit_code':None,'stderr':'timeout'},
    refusal('command accepted but reply timeout'),
    refusal('HTTP status 500'),
    refusal('net/http: TLS handshake timeout') | {'unknown':True},
    refusal('net/http: TLS handshake timeout') | {'truncated':True},
    {'ok':False,'exit_code':1,'stdout':json.dumps({'ok':False,'data':{'exit_code':0},
        'error':{'code':'COMMAND_FAILED','message':'net/http: TLS handshake timeout'}})},
    {'ok':False,'exit_code':1,'stdout':json.dumps({'ok':False,'data':{'exit_code':1,'stderr':'net/http: TLS handshake timeout'}})},
])
def test_uncertain_or_remote_command_failure_never_replayed(run,monkeypatch,receipt):
    _,rid,_,calls,_=run;sid=sandboxes.create(rid,'ready',{'timeout':600})['sandbox_id'];attempts=[]
    monkeypatch.setattr(compute,'_native',lambda args,**kwargs:attempts.append(args) or receipt)
    monkeypatch.setattr(sandboxes.time,'sleep',lambda _:pytest.fail('unexpected retry'))
    result=sandboxes.execute(rid,sid,'echo once',30,'no-replay')
    assert result['status'] in ('unknown','failed') and len(attempts)==1


@pytest.mark.parametrize('stop',['pause','shutdown'])
def test_retry_wait_obeys_manual_pause_and_global_shutdown(run,monkeypatch,stop):
    _,rid,_,_,_=run;attempts=[]
    monkeypatch.setattr(compute,'_native',lambda args,**kwargs:attempts.append(args) or refusal(
        'IMAGE_PREPARATION_IN_PROGRESS: wait','INVALID_REQUEST'))
    shutdown=[False];monkeypatch.setattr(power,'shutdown_requested',lambda:shutdown[0])
    def wait(_):
        if stop=='pause':db.execute("UPDATE runs SET phase='paused',gate='closed' WHERE id=?",(rid,))
        else:shutdown[0]=True
    monkeypatch.setattr(sandboxes.time,'sleep',wait)
    result=sandboxes.create(rid,'stopped',{'timeout':600})
    assert result['status']=='unknown' and len(attempts)==1


def test_job_spec_builtin_and_key_operating_facts():
    root=Path(__file__).resolve().parents[1]
    text=(root/'skills/cyberscientist-job-spec/SKILL.md').read_text()
    for term in ('/personal','/share','占位符','input_directory','可执行权限','python3 -I -c',
                 'preflight.entry','research_job','v4','GPU','沙箱','本地秒级','环境目录','冒烟','对象存储','分块','SHA','unknown'):
        assert term in text
    assert 'cyberscientist-job-spec' in skills.BUILTIN_EXECUTOR_SKILLS
    assert 'cyberscientist-job-spec' in {s['id'] for s in skills.scan_catalog()}


@pytest.mark.parametrize('endpoint',['sandbox','bohr'])
@pytest.mark.parametrize('lifespan',[False,True])
async def test_cancelled_native_tool_thread_drains_before_safe_exit(run,monkeypatch,endpoint,lifespan):
    _,rid,_,_,_=run
    entered,release,closed=Event(),Event(),Event();exiting=asyncio.Event()
    def dispatch(*args):entered.set();assert release.wait(5);closed.set();return {'status':'unknown'}
    monkeypatch.setattr(sandboxes,'dispatch',dispatch)
    monkeypatch.setattr(compute,'cli',dispatch)
    with db.transaction() as conn:
        token=collab.issue_token(conn,rid,'executor','test-session',1)
    monkeypatch.setattr(api.controller,'reconcile_on_startup',lambda:None)
    monkeypatch.setattr(compute,'recover_pending',lambda:None)
    from cyberscientist import machine_catalog
    monkeypatch.setattr(machine_catalog,'refresh',lambda:None)
    async def recover(*args,**kwargs):return []
    monkeypatch.setattr(power,'recover',recover)
    async def control(*args,**kwargs):
        db.execute("UPDATE runs SET phase='paused',gate='closed' WHERE id=?",(rid,))
        return {'status':'confirmed'}
    monkeypatch.setattr(api.controller,'control',control)
    app=api.create_app()
    async def host():
        async def work():
            async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as client:
                request=asyncio.create_task(client.post('/api/v1/tools/'+endpoint,headers={'Authorization':'Bearer '+token},json={'action':'create','operation_id':'owned-thread','timeout':600,'args':['sandbox','create']}))
                assert await asyncio.to_thread(entered.wait,1)
                request.cancel()
                with pytest.raises(asyncio.CancelledError):await request
            exiting.set()
            if not lifespan:assert (await power.safe_shutdown(api.controller,timeout=.1))['can_shutdown']
        if lifespan:
            async with app.router.lifespan_context(app):await work()
        else:await work()
    task=asyncio.create_task(host())
    try:
        await asyncio.wait_for(exiting.wait(),2);await asyncio.sleep(.02)
        assert not task.done() and resource_coordinator.auxiliary_tasks() and not closed.is_set()
        release.set();await asyncio.wait_for(task,2)
        assert closed.is_set() and not resource_coordinator.auxiliary_tasks()
    finally:release.set();await asyncio.gather(task,return_exceptions=True)
