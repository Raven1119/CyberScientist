import asyncio
import time
import pytest
from cyberscientist import compute, db, mcp_bridge, sandbox_background, server_wait
from cyberscientist.codex_protocol import thread_params
from test_pi_wake_cs21 import setup_run


def seed(kind):
    rid,_,_=setup_run()
    if kind=='job':
        db.execute("INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,spec_json,input_directory,status,created_at,updated_at) VALUES('wait-op',?,'trial_mb1','hash','{}','input','Running',?,?)",(rid,db.utcnow(),db.utcnow()))
    else:
        db.execute("INSERT INTO compute_sandbox_operations(operation_id,run_id,sandbox_id,action,status,started_at) VALUES('wait-op',?,'box','background','running',?)",(rid,db.utcnow()))
    return rid


@pytest.mark.asyncio
async def test_one_job_wait_returns_terminal_without_retry_submission(monkeypatch):
    rid=seed('job');calls=[]
    def observe(run_id,**kwargs):
        calls.append(kwargs)
        db.execute("UPDATE compute_jobs SET status='Finished' WHERE operation_id='wait-op'")
    monkeypatch.setattr(compute,'reconcile',observe)
    result=await server_wait.wait(rid,'wait-op',5,kind='job')
    assert result['status']=='Finished' and result['terminal'] and not result['timed_out']
    assert calls==[{'allow_retry':False}]


@pytest.mark.asyncio
async def test_one_background_wait_keeps_waiting_and_returns_exit_code(monkeypatch):
    rid=seed('sandbox');calls=[]
    def poll(*args):
        calls.append(args)
        return {'status':'running'} if len(calls)==1 else {'status':'completed','exit_code':0}
    monkeypatch.setattr(sandbox_background,'poll',poll)
    result=await server_wait.wait(rid,'wait-op',5,kind='sandbox')
    assert result['terminal'] and result['exit_code']==0 and len(calls)==2
    assert db.query_one("SELECT COUNT(*) FROM events WHERE type='server.wait_started'")[0]==1


@pytest.mark.asyncio
async def test_hung_observation_cannot_extend_deadline(monkeypatch):
    rid=seed('job')
    async def hung(*args,**kwargs):await asyncio.sleep(2)
    monkeypatch.setattr(server_wait.resource_coordinator,'tracked_thread',hung)
    start=time.monotonic()
    result=await server_wait.wait(rid,'wait-op',1,kind='job')
    assert result['timed_out'] and not result['terminal']
    assert time.monotonic()-start<1.8
    with pytest.raises(compute.ComputeError):await server_wait.wait(rid,'wait-op',1201,kind='job')
    with pytest.raises(compute.ComputeError):await server_wait.wait(rid,'foreign-op',1,kind='job')


def test_mcp_and_native_timeouts_cover_twenty_minutes(monkeypatch):
    calls=[]
    monkeypatch.setattr(mcp_bridge,'_post',lambda path,payload,**kwargs:calls.append((path,kwargs)) or {'terminal':True})
    for name in ('research_job','research_sandbox'):
        mcp_bridge._handle({'id':1,'method':'tools/call','params':{'name':name,'arguments':{'action':'wait','operation_id':'wait-op','timeout':1200}}})
    assert all(kw['timeout']==1260 and kw['retry_transient'] is False for _,kw in calls)
    spec={'working_directory':'/tmp','mcp_servers':[{'name':'cyberscientist','command':'python','args':[]}]}
    params=thread_params(spec,None,None,writable=True)
    assert params['config']['mcp_servers']['cyberscientist']['tool_timeout_sec']==1500
