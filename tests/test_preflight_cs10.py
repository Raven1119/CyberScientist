import io
import json
import urllib.error
from httpx import ASGITransport, AsyncClient
from cyberscientist import api, config, db, preflight


def seed_mailboxes():
    settings = config.load_settings(); settings['mailbox']['platform'] = 'bohrium_playground'
    settings['playground']['token_secret_ref'] = 'local:operator'; settings['bohrium']['access_key_secret_ref'] = 'local:bohr'
    config.save_settings(settings)
    for role in ('harvest', 'experiment'):
        config.update_secret(role, 'fake_' + role)
        db.execute('INSERT INTO mailboxes(id,role,email,platform,secret_ref,created_at) VALUES(?,?,?,?,?,?)', (role,role,role+'@example.invalid','bohrium_playground','local:'+role,db.utcnow()))
    return settings


def fake_checks(monkeypatch):
    monkeypatch.setattr(preflight, '_json_get', lambda url, key: (200, {'data': [{'id': 'deepseek-flash'}]}) if 'deepseek.com' in url else (200, {'id': key, 'email': key.removeprefix('fake_')+'@example.invalid'}))
    async def codex(_): return preflight._item('codex', 'pass', 'native directory', model_turns=0)
    monkeypatch.setattr(preflight, 'codex_check', codex)
    monkeypatch.setattr(preflight.protocol_drift, 'check', lambda: {'status':'unchanged','complete':True})
    for name in ('web_search', 'web_read', 'lkm_search'):
        monkeypatch.setattr(preflight.public_research, name, lambda value: {'status':'received','sha256':'a'*64,'body':'private remote body'})
    monkeypatch.setattr(config, 'deepseek_key', lambda: 'fake_deepseek')
    config.update_secret('operator', 'fake_operator'); config.update_secret('bohr', 'fake_bohr')
    from datetime import datetime,timezone,timedelta
    from cyberscientist import track_transport
    now=datetime.now(timezone.utc)
    snapshot={'track_clock':{'start':now.isoformat(),'end':(now+timedelta(hours=5)).isoformat()},
              'submission_transport':track_transport.defaults() | {'verified':True,'evidence':{'source':'synthetic_fixture'}},
              'template':{'authorization':{'unlimited_resources':True}}}
    db.execute("INSERT OR IGNORE INTO eval_runs(id,suite,repeats,label,status,config_json,created_at,updated_at) VALUES('ready-track','competition',1,'fixture','draft',?,?,?)",(json.dumps(snapshot),db.utcnow(),db.utcnow()))
    db.execute("INSERT OR IGNORE INTO competition_prompt_versions VALUES('ready-track',1,'fixture user prompt',?,?)",('a'*64,db.utcnow()))
    from cyberscientist import codex_fast
    settings=config.load_settings()
    for role in ('brain','executor','reviewer','post_review'):
        choice=settings[role]
        if choice.get('provider',choice['runtime'])=='codex':
            codex_fast.record({'model':choice['model_id'],'requested':True,'enabled':True,'tier':'priority','status':'enabled','source':'synthetic_fixture'})


async def execute():
    async def conn(name): assert name == 'bohrium'; return {'health':{'authenticated':True,'version':'2.7.8'},'detail':'authenticated'}
    async def health(): return {'ok':True,'mode':'connected','backend':{'commit':'example'}}
    return await preflight.run(conn, health)


async def test_readiness_pass_then_disabled_harvest_detected_persists_after_restart(monkeypatch):
    seed_mailboxes(); fake_checks(monkeypatch)
    before = {table: len(db.query('SELECT * FROM '+table)) for table in ('runs','authorizations','submissions','compute_jobs')}
    result = await execute()
    assert all(item['status'] == 'pass' for item in result['items'] if item['name'] != 'code')
    assert result['model_turns'] == 0 and 'private-profile' not in json.dumps(result) and 'private remote body' not in json.dumps(result)
    db.execute("UPDATE mailboxes SET status='disabled' WHERE role='harvest'")
    failed = await execute()
    assert failed['status'] == 'fail' and next(item for item in failed['items'] if item['name']=='harvest_mailbox')['status'] == 'fail'
    db.init_db(); assert preflight.cached() == failed
    assert before == {table: len(db.query('SELECT * FROM '+table)) for table in before}


async def test_wrong_platform_missing_key_and_network_unknown_are_distinct(monkeypatch):
    seed_mailboxes(); fake_checks(monkeypatch)
    db.execute("UPDATE mailboxes SET platform='demo' WHERE role='experiment'")
    config.update_secret('operator', None)
    monkeypatch.setattr(preflight, '_json_get', lambda url, key: (None,None))
    result = await execute(); items={item['name']:item for item in result['items']}
    assert items['experiment_mailbox']['status']=='fail' and items['playground']['status']=='fail'
    assert items['harvest_mailbox']['status']=='warn' and items['deepseek']['status']=='warn'


async def test_real_frontend_routes_use_bohrium_callback_and_persist_report(tmp_path, monkeypatch):
    import subprocess
    seed_mailboxes(); fake_checks(monkeypatch)
    executable=tmp_path/'bohr'; executable.write_text('fake executable')
    settings=config.load_settings(); settings['bohrium'].update(executable=str(executable),project_id=88474);config.save_settings(settings)
    calls=[]
    def process(argv,**kwargs):
        calls.append(argv)
        output='2.7.8' if argv[1:]==['version'] else '[{"projectId":88474}]' if argv[1:]==['project','list','--json'] else ''
        return subprocess.CompletedProcess(argv,0,output,'')
    monkeypatch.setattr(subprocess,'run',process)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://fixture') as client:
        assert (await client.get('/api/v1/preflight')).json() is None
        response=await client.post('/api/v1/preflight');assert response.status_code==200
        result=response.json();assert result['status']=='pass' and result['model_turns']==0
        assert (await client.get('/api/v1/preflight')).json()==result
    assert [str(executable),'project','list','--json'] in calls
    assert not db.query('SELECT * FROM runs') and not db.query('SELECT * FROM submissions')


async def test_codex_directory_paginated_native_account_no_login_no_turn(monkeypatch):
    calls=[]
    class RPC:
        def __init__(self,*args,**kwargs): pass
        async def start(self): calls.append('start')
        async def stop(self): calls.append('stop')
        async def request(self,method,params,timeout):
            calls.append((method,params))
            if method=='account/rateLimits/read': return {'rateLimits':{'primary':{'usedPercent':7,'resetsAt':1791601547}}}
            if method=='account/read': return {'account':{'type':'chatgpt','email':'private@example.invalid','planType':'pro'},'requiresOpenaiAuth':True}
            if params['cursor'] is None: return {'data':[{'model':'gpt-6-astra','supportedReasoningEfforts':[{'reasoningEffort':'xhigh'}]}],'nextCursor':'page2'}
            return {'data':[{'model':'gpt-6.1-sol','supportedReasoningEfforts':[{'reasoningEffort':'high'}]}]}
    from cyberscientist import jsonrpc_stdio, codex_protocol
    monkeypatch.setattr(jsonrpc_stdio,'JsonRpcStdio',RPC)
    async def initialize(_): pass
    monkeypatch.setattr(codex_protocol,'initialize',initialize)
    settings=config.load_settings();settings['brain']['executable']='/fake/codex'
    result=await preflight.codex_check(settings)
    assert result['status']=='pass' and result['facts']['model_turns']==0 and 'private@' not in json.dumps(result)
    assert calls[1]==('account/read',{'refreshToken':False}) and [x[0] for x in calls if isinstance(x,tuple)]==['account/read','account/rateLimits/read','model/list','model/list']
    assert calls[-1]=='stop'


def test_authenticated_get_does_not_follow_redirect_or_emit_profile(monkeypatch):
    calls=[]
    class Opener:
        def open(self,request,timeout):
            calls.append(request)
            raise urllib.error.HTTPError(request.full_url,302,'redirect',{'Location':'https://elsewhere.invalid'},io.BytesIO(b'private'))
    def opener(handler):
        assert handler.redirect_request(None,None,None,None,None,None) is None
        return Opener()
    monkeypatch.setattr(preflight.urllib.request,'build_opener',opener)
    assert preflight._json_get('https://play.bohrium.com/api/auth/me','test-key')==(302,None)
    assert len(calls)==1


def test_preflight_cli_calls_readonly_route_and_returns_failure_exit(monkeypatch,capsys):
    import sys
    from cyberscientist import cli
    result={'status':'fail','items':[{'name':'harvest_mailbox','status':'fail','detail':'disabled'}],'model_turns':0}
    calls=[]
    def open_request(request,timeout):
        calls.append((request.full_url,request.method,timeout,request.data))
        return io.BytesIO(json.dumps(result).encode())
    monkeypatch.setattr(cli.urllib.request,'urlopen',open_request)
    monkeypatch.setattr(sys,'argv',['cyberscientist','preflight','--json','--port','8899'])
    import pytest
    with pytest.raises(SystemExit) as stopped:cli.main()
    assert stopped.value.code==1 and json.loads(capsys.readouterr().out)==result
    assert calls==[('http://127.0.0.1:8899/api/v1/preflight','POST',600,b'{}')]


def test_wrong_mailbox_owner_and_duplicate_token_are_failures(monkeypatch):
    settings=seed_mailboxes(); fake_checks(monkeypatch)
    monkeypatch.setattr(preflight,'_json_get',lambda url,key:(200,{'id':'same-platform-account','email':'harvest@example.invalid'}))
    results=preflight.mailbox_checks(settings)
    assert [item['status'] for item in results]==['fail','fail']
    assert all(item['facts']['duplicate_identity'] for item in results)
    assert results[1]['facts']['identity_matches']==[False]
    assert 'same-platform-account' not in json.dumps(results) and '@example.invalid' not in json.dumps(results)


async def test_codex_unknown_account_shape_never_passes(monkeypatch):
    from cyberscientist import codex_protocol,jsonrpc_stdio
    unknown={}
    class RPC:
        def __init__(self,*args,**kwargs):pass
        async def start(self):pass
        async def stop(self):pass
        async def request(self,method,params,timeout):
            if method=='account/read':return {'account':unknown,'requiresOpenaiAuth':True}
            return {'data':[{'model':'gpt-6-astra','supportedReasoningEfforts':[{'reasoningEffort':'xhigh'}]},{'model':'gpt-6.1-sol','supportedReasoningEfforts':[{'reasoningEffort':'high'}]}]}
    async def initialize(_):pass
    monkeypatch.setattr(jsonrpc_stdio,'JsonRpcStdio',RPC);monkeypatch.setattr(codex_protocol,'initialize',initialize)
    settings=config.load_settings();settings['brain']['executable']='/fake/codex'
    for value in ({},{'type':'invented'},{'type':'chatgpt'}):
        unknown=value;result=await preflight.codex_check(settings)
        assert result['status']=='warn' and result['facts']['authenticated'] is False


async def test_shutdown_tracks_native_close_and_double_cancel(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from cyberscientist import codex_protocol,jsonrpc_stdio,power,resource_coordinator
    started=asyncio.Event();closing=asyncio.Event();release=asyncio.Event()
    class RPC:
        def __init__(self,*args,**kwargs):pass
        async def start(self):started.set()
        async def request(self,*args,**kwargs):await asyncio.Future()
        async def stop(self):closing.set();await release.wait()
    async def initialize(_):pass
    monkeypatch.setattr(jsonrpc_stdio,'JsonRpcStdio',RPC);monkeypatch.setattr(codex_protocol,'initialize',initialize)
    settings=config.load_settings();settings['brain']['executable']='/fake/codex'
    native=asyncio.create_task(preflight.codex_check(settings));await started.wait()
    shutdown=asyncio.create_task(power.safe_shutdown(SimpleNamespace(_tasks={}),timeout=1))
    await closing.wait();native.cancel();await asyncio.sleep(0)
    assert not native.done() and not shutdown.done() and preflight._NATIVE_HANDLES and resource_coordinator.auxiliary_tasks()
    release.set();result=await shutdown
    assert result['can_shutdown'] is True and not preflight._NATIVE_HANDLES and not resource_coordinator.close_unknowns()
    assert native.cancelled()


async def test_failed_close_retains_handle_unknown_until_shutdown_retry(monkeypatch):
    from types import SimpleNamespace
    from cyberscientist import codex_protocol,jsonrpc_stdio,power,resource_coordinator
    import pytest
    class RPC:
        def __init__(self,*args,**kwargs):self.attempt=0
        async def start(self):pass
        async def request(self,method,params,timeout):return {'account':None} if method=='account/read' else {'data':[]}
        async def stop(self):
            self.attempt+=1
            if self.attempt==1:raise OSError('close failed')
    async def initialize(_):pass
    monkeypatch.setattr(jsonrpc_stdio,'JsonRpcStdio',RPC);monkeypatch.setattr(codex_protocol,'initialize',initialize)
    settings=config.load_settings();settings['brain']['executable']='/fake/codex'
    with pytest.raises(OSError):await preflight.codex_check(settings)
    assert preflight._NATIVE_HANDLES and resource_coordinator.close_unknowns()
    result=await power.safe_shutdown(SimpleNamespace(_tasks={}),timeout=1)
    assert result['can_shutdown'] is True and not preflight._NATIVE_HANDLES and not resource_coordinator.close_unknowns()


async def test_shutdown_barrier_rejects_preflight_before_any_calls():
    from cyberscientist import resource_coordinator
    import pytest
    db.execute("INSERT INTO system_state VALUES('shutdown_requested','1')")
    async def forbidden(*args):raise AssertionError('external check must not start')
    with pytest.raises(resource_coordinator.ResourceWait):await preflight.run(forbidden,forbidden)


async def test_cancelled_http_waiter_keeps_readonly_worker_tracked(monkeypatch):
    import asyncio
    from cyberscientist import resource_coordinator
    started=asyncio.Event();release=asyncio.Event();completed=asyncio.Event()
    async def work(*args):
        started.set();await release.wait();completed.set();return {'status':'pass'}
    monkeypatch.setattr(preflight,'_run',work)
    waiter=asyncio.create_task(preflight.run(None,None));await started.wait()
    waiter.cancel()
    import pytest
    with pytest.raises(asyncio.CancelledError):await waiter
    tracked=resource_coordinator.auxiliary_tasks();assert tracked and not completed.is_set()
    for task in tracked:task.cancel();task.cancel()
    await asyncio.sleep(0);assert not completed.is_set() and resource_coordinator.auxiliary_tasks()
    release.set();await asyncio.gather(*tracked)
    assert completed.is_set() and not resource_coordinator.auxiliary_tasks()


async def test_parallel_close_retries_share_one_task_and_obey_time_budget():
    import asyncio
    from cyberscientist import resource_coordinator
    owner='preflight-close-race';started=asyncio.Event();release=asyncio.Event()
    class RPC:
        def __init__(self):self.calls=0
        async def stop(self):self.calls+=1;started.set();await release.wait()
    rpc=RPC();preflight._NATIVE_HANDLES[owner]=rpc
    resource_coordinator.close_failed(owner,OSError('original failure'))
    await asyncio.gather(preflight.retry_closes(timeout=.01),preflight.retry_closes(timeout=.01))
    assert started.is_set() and rpc.calls==1 and preflight._NATIVE_HANDLES[owner] is rpc and resource_coordinator.close_unknowns()
    closing=preflight._CLOSE_TASKS[owner];assert closing in resource_coordinator.auxiliary_tasks() and not closing.done()
    release.set();await closing
    assert rpc.calls==1 and owner not in preflight._NATIVE_HANDLES and not resource_coordinator.close_unknowns()
