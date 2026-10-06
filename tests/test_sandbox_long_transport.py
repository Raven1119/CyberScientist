"""Long transport chooses exactly one POST before execution, never after timeout."""
import json
import subprocess
import pytest
from cyberscientist import bohr_proxy, sandbox_transport
from cyberscientist import compute, config, db, power, run_clock, sandboxes
from test_sandboxes import run

REAL_NATIVE = compute._native

ARGS=['sandbox','create','--image','registry.example/lean:fixed','--cpu','8c32g',
      '--timeout','600','--project-id','88474','--request-id','stable-id']


def setup(monkeypatch, raw, status=201, *, path=sandbox_transport.PATH, exception=None):
    payload={'timeout':600,'projectId':88474,'templateID':'d-image-replace-c8-m32',
             'metadata':{'e2b.agents.kruise.io/image':'registry.example/lean:fixed'}}
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a,0,
        json.dumps({'ok':True,'data':{'operations':[{'method':'POST','path':path,'body':payload}]}}),''))
    calls=[]
    class Client:
        def __init__(self,**kw):assert 0<kw['timeout']<=240 and kw['follow_redirects'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kw):
            calls.append((url,kw));assert kw['json']==payload
            assert kw['headers']=={'Authorization':'Bearer fake-account-key','X-Request-ID':'stable-id'}
            if exception:raise exception
            class Response:
                status_code=status
                def json(self):return raw
            return Response()
    monkeypatch.setattr(sandbox_transport.httpx,'Client',Client)
    return calls


def invoke():return sandbox_transport.create(ARGS,'bohr-2.7.8',{},'fake-account-key','https://open.bohrium.com',240)


def test_long_create_uses_cli_payload_once_and_redacts_vendor_token(monkeypatch):
    calls=setup(monkeypatch,{'sandboxID':'fixture--long-001','envdAccessToken':'fake-ephemeral-token'})
    value=invoke();assert value['ok'] and not value['unknown'] and len(calls)==1
    assert 'fake-ephemeral-token' not in value['stdout'] and 'fake-account-key' not in value['stdout']
    assert json.loads(value['stdout'])['data']['envdAccessToken']=='[REDACTED]'


@pytest.mark.parametrize('exception',[TimeoutError('fake'),None])
def test_unknown_is_not_replayed_or_fallen_back(monkeypatch,exception):
    calls=setup(monkeypatch,{'message':'upstream unavailable'},status=503,exception=exception)
    value=invoke();assert not value['ok'] and value['unknown'] and len(calls)==1


def test_explicit_preparation_refusal_is_still_recognized(monkeypatch):
    from cyberscientist import sandboxes
    calls=setup(monkeypatch,{'message':'IMAGE_PREPARATION_IN_PROGRESS: waiting'},status=400)
    value=invoke();assert not value['unknown'] and len(calls)==1
    assert sandboxes._retry_reason(value,'create')=='image_preparation'


def test_unverified_local_protocol_does_not_post(monkeypatch):
    calls=setup(monkeypatch,{},path='/unexpected')
    value=invoke();assert value['not_started'] and not calls


def test_stopped_during_local_validation_does_not_post(monkeypatch):
    calls=setup(monkeypatch,{'sandboxID':'fixture--long-001'})
    stopped=[False];native=subprocess.run
    def paused(*a,**kw):
        value=native(*a,**kw);stopped[0]=True;return value
    monkeypatch.setattr(subprocess,'run',paused)
    value=sandbox_transport.create(ARGS,'bohr-2.7.8',{},'fake-account-key','https://open.bohrium.com',240,
                                   before_send=lambda:not stopped[0])
    assert value['not_started'] and not calls


@pytest.mark.parametrize('stop',['pause','shutdown','expired'])
def test_gateway_checks_bound_run_after_dry_run_before_post(run,monkeypatch,stop):
    _,rid,_,_,_=run
    settings=config.load_settings();settings['bohrium']['wenyon_executable']='/fixture/bohr-2.7.8';config.save_settings(settings)
    calls=setup(monkeypatch,{'sandboxID':'fixture--long-001'})
    dry_run=subprocess.run
    def stop_now(*a,**kw):
        value=dry_run(*a,**kw)
        if stop=='pause':db.execute("UPDATE runs SET phase='paused',gate='closed' WHERE id=?",(rid,))
        elif stop=='shutdown':monkeypatch.setattr(power,'shutdown_requested',lambda:True)
        else:monkeypatch.setattr(run_clock,'remaining',lambda *a,**kw:0)
        return value
    monkeypatch.setattr(subprocess,'run',stop_now)
    monkeypatch.setattr(compute,'_native',REAL_NATIVE)
    result=sandboxes.create(rid,'stable-id',{'image':'registry.example/lean:fixed','timeout':600})
    assert result['status']=='failed' and result['receipt']['not_started'] and not calls
    assert len(db.query('SELECT * FROM compute_sandboxes WHERE operation_id=?',('stable-id',)))==1


def test_native_explicit_dry_run_stays_read_only(run,monkeypatch):
    settings=config.load_settings();settings['bohrium']['wenyon_executable']='/fixture/bohr-2.7.8';config.save_settings(settings)
    calls=setup(monkeypatch,{'sandboxID':'fixture--long-001'})
    result=REAL_NATIVE(ARGS+['-y','--dry-run'],timeout=240)
    assert result['ok'] and not calls and 'operations' in json.loads(result['stdout'])['data']


def test_dry_run_consumes_the_same_rpc_budget(monkeypatch):
    calls=setup(monkeypatch,{'sandboxID':'fixture--long-001'});clock=[0]
    monkeypatch.setattr(sandbox_transport.time,'monotonic',lambda:clock[0]);dry_run=subprocess.run
    def slow(*a,**kw):
        value=dry_run(*a,**kw);clock[0]=40;return value
    monkeypatch.setattr(subprocess,'run',slow)
    value=sandbox_transport.create(ARGS,'bohr-2.7.8',{},'fake-account-key','https://open.bohrium.com',40)
    assert value['not_started'] and not calls


def test_http_receives_only_budget_remaining_after_dry_run(monkeypatch):
    setup(monkeypatch,{'sandboxID':'fixture--long-001'});clock=[0];http_budgets=[]
    monkeypatch.setattr(sandbox_transport.time,'monotonic',lambda:clock[0]);dry_run=subprocess.run
    def slow(*a,**kw):
        value=dry_run(*a,**kw);clock[0]=30;return value
    client=sandbox_transport.httpx.Client
    def observed(**kw):http_budgets.append(kw['timeout']);return client(**kw)
    monkeypatch.setattr(subprocess,'run',slow);monkeypatch.setattr(sandbox_transport.httpx,'Client',observed)
    assert sandbox_transport.create(ARGS,'bohr-2.7.8',{},'fake-account-key','https://open.bohrium.com',40)['ok']
    assert http_budgets==[10]


def test_mcp_and_run_local_cli_wait_for_preparation_without_http_replay(monkeypatch,capsys):
    import io,sys,urllib.request
    from cyberscientist import mcp_bridge
    posts=[]
    monkeypatch.setattr(mcp_bridge,'_post',lambda path,args,**kw:posts.append((path,kw)) or {'status':'active'})
    result=mcp_bridge._handle({'jsonrpc':'2.0','id':1,'method':'tools/call',
        'params':{'name':'research_sandbox','arguments':{'action':'create','operation_id':'once','timeout':600}}})
    assert result and posts==[('/api/v1/tools/sandbox',{'timeout':3000,'retry_transient':False})]
    monkeypatch.setenv('CS_TOOL_TOKEN','fake-capability');monkeypatch.setattr(sys,'argv',['bohr','sandbox','create','--timeout','600'])
    waits=[]
    def reply(request,**kw):waits.append(kw['timeout']);return io.BytesIO(b'{"status":"active"}')
    monkeypatch.setattr(urllib.request,'urlopen',reply)
    assert bohr_proxy.main()==0 and waits==[3000]
    assert 'fake-capability' not in capsys.readouterr().out


@pytest.mark.parametrize('extra',[{'data':{}},{'data':{'sandboxID':'fixture--created-001'}},
                                 {'sandboxID':'fixture--created-001'},{'sandbox':{'id':'fixture--created-001'}}])
def test_preparation_with_possible_effect_is_unknown_and_not_retryable(monkeypatch,extra):
    from cyberscientist import sandboxes
    calls=setup(monkeypatch,{'message':'IMAGE_PREPARATION_IN_PROGRESS: waiting'}|extra,status=400)
    result=invoke();assert result['unknown'] and len(calls)==1
    assert sandboxes._retry_reason(result,'create') is None
    assert json.loads(result['stdout'])['unconfirmed_response']=={'message':'IMAGE_PREPARATION_IN_PROGRESS: waiting'}|extra


@pytest.mark.parametrize('field',['envdAccessToken','envd_access_token','envd-token','accessToken'])
def test_ephemeral_credentials_removed_before_serialization(field):
    raw={field:'fake-ephemeral-value','scientific_signature':'keep'}
    assert bohr_proxy.redact_value(raw,[])=={field:'[REDACTED]','scientific_signature':'keep'}
    safe=bohr_proxy.redact(json.dumps(raw),[])
    assert 'fake-ephemeral-value' not in safe and json.loads(safe)['scientific_signature']=='keep'
