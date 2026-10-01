"""Sandbox gateway invariants with a fake bohr CLI; no platform calls."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cyberscientist import compute, config, db, sandboxes, skills, trace_projection
from cyberscientist.controller import RunController
from test_collaboration import _seed_challenge


@pytest.fixture
def run(monkeypatch):
    _seed_challenge()
    settings=config.load_settings();settings['bohrium']['project_id']=88474
    settings['bohrium']['access_key_secret_ref']='local:fake-sandbox-key'
    config.save_settings(settings)
    config.update_secret('fake-sandbox-key','fake-key-value')
    c=RunController()
    rid=c.create_run('COLLAB_CH',mode='connected')['id']
    c.authorize(rid,'compute',False,0,60,0,'',max_sandboxes=2,max_sandbox_minutes=20)
    tid='trial_sandbox'
    db.execute("UPDATE runs SET phase='running',gate='open',current_trial_id=?,started_at=? WHERE id=?",
               (tid,db.utcnow(),rid))
    work=config.WORKSPACE_DIR/'runs'/rid/'trials'/tid
    work.mkdir(parents=True)
    calls=[];remote={}
    def native(args,**kwargs):
        calls.append(args)
        if args[:2]==['sandbox','create']:
            remote['fixture--box-001']={'sandboxID':'fixture--box-001','status_name':'running'}
            return {'ok':True,'exit_code':0,'stdout':json.dumps({'data':remote['fixture--box-001']}),'stderr':''}
        if args[:2]==['sandbox','describe']:
            return {'ok':True,'exit_code':0,'stdout':json.dumps({'data':remote.get('fixture--box-001')}),'stderr':''}
        if args[:2]==['sandbox','delete']:
            remote.pop(args[2],None)
            return {'ok':True,'exit_code':0,'stdout':'{}','stderr':''}
        if args[:2]==['sandbox','list']:
            return {'ok':True,'exit_code':0,'stdout':json.dumps({'data':{'items':list(remote.values())}}),'stderr':''}
        if args[:2]==['sandbox','exec']:
            return {'ok':True,'exit_code':0,'stdout':json.dumps({'exitCode':0,'stdout':'1\n'}),'stderr':''}
        return {'ok':True,'exit_code':0,'stdout':'{}','stderr':''}
    monkeypatch.setattr(compute,'_native',native)
    return c,rid,work,calls,remote


def test_authorization_flag_and_budget_boundaries(run):
    _,rid,work,calls,_=run
    with pytest.raises(compute.ComputeError,match='沙箱时长'):
        sandboxes.create(rid,'too-long',{'timeout':1800})
    with pytest.raises(compute.ComputeError,match='GPU'):
        sandboxes.create(rid,'gpu',{'timeout':60,'gpu':True})
    with pytest.raises(compute.ComputeError,match='未开放'):
        compute.cli(rid,['sandbox','create','--timeout','60','--inherit-auth'],str(work))
    with pytest.raises(compute.ComputeError,match='未开放'):
        compute.cli(rid,['sandbox','create','--timeout','60','--wenyon-dataset-id','x'],str(work))
    assert calls==[]
    first=sandboxes.create(rid,'first',{'timeout':600})
    assert first['status']=='active'
    assert '--yes' in calls[0] and '--request-id' in calls[0]
    assert sandboxes.create(rid,'first',{'timeout':600})['deduplicated'] is True
    with pytest.raises(compute.ComputeError,match='累计|上限|额度'):
        sandboxes.create(rid,'third',{'timeout':601})
    assert sum(a[:2]==['sandbox','create'] for a in calls)==1


def test_ownership_paths_exec_events_and_cleanup(run):
    c,rid,work,calls,_=run
    sid=sandboxes.create(rid,'owned',{'timeout':600})['sandbox_id']
    other=c.create_run('COLLAB_CH',mode='connected')['id']
    with pytest.raises(compute.ComputeError,match='未登记'):
        sandboxes.execute(other,sid,'echo no',10)
    with pytest.raises(compute.ComputeError,match='路径'):
        sandboxes.transfer(rid,'write',sid,'/tmp/x',local_path='/tmp/outside')
    with pytest.raises(compute.ComputeError,match='剩余'):
        sandboxes.execute(rid,sid,'echo no',3600)
    source=work/'source.txt';source.write_text('hello')
    transferred=sandboxes.transfer(rid,'write',sid,'/tmp/source.txt',local_path=str(source))
    assert transferred['files'][0]['sha256']==compute._file_sha256(source)
    result=sandboxes.execute(rid,sid,'python3 -c "print(1)"',30,'exec-1')
    assert result['status']=='completed'
    events=db.query("SELECT type,payload FROM events WHERE run_id=? AND type LIKE 'sandbox.exec_%' ORDER BY seq",(rid,))
    assert [e['type'] for e in events]==['sandbox.exec_started','sandbox.exec_completed']
    assert all(json.loads(e['payload'])['operation_id']=='exec-1' for e in events)
    through=db.query_one('SELECT MAX(seq) n FROM events WHERE run_id=?',(rid,))['n']
    steps=trace_projection.project(rid,None,through,{})
    assert [s['step_type'] for s in steps if s.get('tool_call_id')=='sandbox:exec-1']==['tool_call','tool_result']
    assert sandboxes.cleanup_run(rid)[0]['status']=='deleted'
    assert db.query_one('SELECT status FROM compute_sandboxes WHERE operation_id=?',('owned',))['status']=='deleted'
    assert sum(a[:2]==['sandbox','delete'] for a in calls)==1


def test_uncertain_create_reconciles_without_second_create(run,monkeypatch):
    _,rid,_,calls,remote=run
    original=compute._native
    def uncertain(args,**kwargs):
        if args[:2]==['sandbox','create']:
            calls.append(args)
            remote['fixture--box-001']={'sandboxID':'fixture--box-001','status_name':'running'}
            return {'ok':False,'unknown':True,'exit_code':None,'stdout':'','stderr':'timeout'}
        return original(args,**kwargs)
    monkeypatch.setattr(compute,'_native',uncertain)
    assert sandboxes.create(rid,'uncertain',{'timeout':120})['status']=='unknown'
    assert sandboxes.reconcile_create(rid,'uncertain')['status']=='active'
    assert sum(a[:2]==['sandbox','create'] for a in calls)==1
    assert '--create-request-id' in calls[-1]


def test_scoring_workspace_is_bound_to_run_and_uses_native_large_file_transport(run):
    _, rid, work, calls, _ = run
    source = work / 'science.zip'
    source.write_bytes(b'bounded fixture science bytes')
    sid = sandboxes.create(rid, 'session-score', {'timeout': 600}, _session_id=rid)['sandbox_id']
    assert calls[0][calls[0].index('--session-id') + 1] == rid
    result = sandboxes.transfer(rid, 'write', sid, '/bohr-workspace/score/package.zip',
                               local_path=str(source), operation_id='large-file-write')
    assert result['status'] == 'completed'
    assert '--ti' in calls[-1]
    assert calls[-1][calls[-1].index('--session-id') + 1] == rid
    assert result['files'][0]['sha256'] == compute._file_sha256(source)
    sandboxes.transfer(rid, 'write', sid, '/tmp/package.zip', local_path=str(source),
                       operation_id='local-file-write')
    assert '--ti' not in calls[-1]
    before = len(calls)
    assert sandboxes.create(rid, 'session-score', {'timeout': 600}, _session_id=rid)['deduplicated']
    assert len(calls) == before
    with pytest.raises(compute.ComputeError, match='绑定本 Run'):
        sandboxes.create(rid, 'foreign-session', {'timeout': 60}, _session_id='other-run')
    with pytest.raises(compute.ComputeError, match='不支持'):
        sandboxes.create(rid, 'agent-session', {'timeout': 60, 'session_id': rid})
    assert len(calls) == before


def test_legacy_sandbox_never_claims_persistent_workspace_or_retries_timeout(run, monkeypatch):
    _, rid, work, calls, _ = run
    source = work / 'science.zip'; source.write_bytes(b'original scene')
    sid = sandboxes.create(rid, 'legacy-score', {'timeout': 600})['sandbox_id']
    original = compute._native
    def native(args, **kwargs):
        if args[:3] == ['sandbox', 'files', 'write']:
            calls.append(args)
            return {'ok': False, 'exit_code': 1, 'unknown': True, 'stdout': json.dumps({
                'ok': False, 'error': {'code': 'COMMAND_FAILED', 'http': 400,
                'message': 'write request failed: context deadline exceeded'}})}
        return original(args, **kwargs)
    monkeypatch.setattr(compute, '_native', native)
    result = sandboxes.transfer(rid, 'write', sid, '/bohr-workspace/package.zip',
                               local_path=str(source), operation_id='write-timeout')
    assert result['status'] == 'unknown'
    assert '--ti' not in calls[-1]
    before = len(calls)
    with pytest.raises(compute.ComputeError, match='不自动重复传输'):
        sandboxes.transfer(rid, 'write', sid, '/bohr-workspace/package.zip',
                           local_path=str(source), operation_id='write-timeout')
    assert len(calls) == before


def test_controller_scoring_lifetime_fits_remaining_grant_without_releasing_unknown(run):
    _, rid, _, calls, _ = run
    db.execute('UPDATE runs SET started_at=? WHERE id=?',
               ((datetime.now(timezone.utc) - timedelta(minutes=55)).isoformat(), rid))
    seconds = sandboxes.bounded_lifetime(rid, 600)
    assert 290 <= seconds <= 295
    sandboxes.create(rid, 'short-scorer', {'timeout': seconds})
    assert int(calls[-1][calls[-1].index('--timeout') + 1]) == seconds
    db.execute("UPDATE compute_sandboxes SET status='unknown' WHERE run_id=?", (rid,))
    db.execute('UPDATE authorizations SET max_sandbox_minutes=4 WHERE id='
               '(SELECT authorization_id FROM runs WHERE id=?)', (rid,))
    with pytest.raises(compute.ComputeError, match='耗尽'):
        sandboxes.bounded_lifetime(rid, 600)
    assert len(calls) == 1


def test_local_billing_confirmation_rejection_does_not_reserve_minutes(run,monkeypatch):
    _,rid,_,_,_=run
    monkeypatch.setattr(compute,'_native',lambda *a,**k: {'ok':False,'exit_code':10,
        'stdout':json.dumps({'ok':False,'error':{'code':'CONFIRMATION_REQUIRED'}}),'stderr':''})
    assert sandboxes.create(rid,'locally-rejected',{'timeout':600})['status']=='failed'
    row=db.query_one('SELECT status,deleted_at FROM compute_sandboxes WHERE operation_id=?',
                     ('locally-rejected',))
    assert row['status']=='failed' and row['deleted_at'] is not None


def test_local_dns_socket_denial_never_reserves_remote_sandbox_minutes(run, monkeypatch):
    _, rid, _, calls, _ = run
    receipt = {'ok': False, 'exit_code': 1, 'stdout': json.dumps({
        'ok': False, 'error': {'code': 'NETWORK_ERROR',
        'message': 'Post https://open.bohrium.com/openapi/v4/sandbox_work/sandboxes: '
                   'dial tcp: lookup open.bohrium.com on 10.0.0.1:53: '
                   'dial udp 10.0.0.1:53: socket: operation not permitted'}}),
        'stderr': ''}
    monkeypatch.setattr(compute, '_native', lambda *args, **kwargs: receipt)
    assert sandboxes.create(rid, 'dns-denied', {'timeout': 120})['status'] == 'failed'
    row = db.query_one('SELECT status,created_at,deleted_at FROM compute_sandboxes'
                       ' WHERE operation_id=?', ('dns-denied',))
    assert row['status'] == 'failed' and row['deleted_at'] == row['created_at']
    now = db.utcnow()
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,request_json,status,'
               'created_at,expires_at,receipt_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
               ('old-dns-denied', rid, 'trial_sandbox', '{}', 'unknown', now, now,
                json.dumps(receipt), now))
    assert sandboxes.reconcile_create(rid, 'old-dns-denied')['status'] == 'failed'
    old = db.query_one('SELECT created_at,deleted_at FROM compute_sandboxes'
                       ' WHERE operation_id=?', ('old-dns-denied',))
    assert old['deleted_at'] == old['created_at']
    assert calls == []


def test_invalid_cpu_is_rejected_before_remote_create(run):
    _,rid,_,calls,_=run
    with pytest.raises(compute.ComputeError, match='2c4g'):
        sandboxes.create(rid,'bad-cpu',{'timeout':120,'cpu':'2'})
    assert calls==[]
    assert db.query_one('SELECT 1 FROM compute_sandboxes WHERE operation_id=?',
                        ('bad-cpu',)) is None


def test_template_create_preserves_native_hardware_after_delete(run, monkeypatch):
    _, rid, _, _, _ = run
    original = compute._native
    def native(args, **kwargs):
        if args[:2] == ['sandbox', 'create']:
            return {'ok': True, 'exit_code': 0, 'stdout': json.dumps({'ok': True,
                'data': {'sandboxID': 'fixture--box-001', 'cpuCount': 2,
                         'memoryMB': 4096, 'gpuCount': 0}})}
        return original(args, **kwargs)
    monkeypatch.setattr(compute, '_native', native)
    sid = sandboxes.create(rid, 'observed-machine', {'timeout': 60, 'template': 'fixture'})['sandbox_id']
    sandboxes.delete(rid, sid)
    event = db.query_one("SELECT payload FROM events WHERE run_id=?"
                         " AND type='sandbox.resources_observed'", (rid,))
    assert event
    payload = json.loads(event['payload'])
    assert payload['resources'] == {'cpu': '2c4g', 'gpu_count': 0}
    assert payload['operation_id'] == 'observed-machine'
    assert payload['sandbox_id'] == sid


@pytest.mark.parametrize('data', [
    {'sandboxID': 'other-box', 'cpuCount': 2, 'memoryMB': 4096},
    {'sandboxID': 'fixture--box-001', 'cpuCount': True, 'memoryMB': 4096},
    {'sandboxID': 'fixture--box-001', 'cpuCount': 2, 'memoryMB': 4097},
])
def test_resource_facts_reject_unbound_or_unusable_native_hardware(data):
    receipt = {'ok': True, 'stdout': json.dumps({'ok': True, 'data': data})}
    assert sandboxes.observed_resources(receipt, 'fixture--box-001') == {}


def test_sandbox_receipt_redacts_before_encoding_escaped_secret(monkeypatch):
    secret = 'synthetic-key-with-"quotes"'
    monkeypatch.setattr(config, 'load_secrets', lambda: {'synthetic': secret})
    result = sandboxes._receipt({'ok': True, 'stdout': 'reply "value" ' + secret})
    assert secret not in result['stdout']
    assert 'reply "value"' in result['stdout']


def test_rejected_create_request_id_miss_releases_reservation(run,monkeypatch):
    _,rid,_,calls,_=run
    def native(args,**kwargs):
        calls.append(args)
        if args[:2]==['sandbox','create']:
            error={'code':'INVALID_ARGUMENTS','http':400,'retryable':False,
                   'message':'--cpu must be one of 2c4g'}
        else:
            error={'code':'RESOURCE_NOT_FOUND','http':404,'retryable':False,
                   'message':'Wenyon request not found'}
        return {'ok':False,'exit_code':1,'stdout':json.dumps({'ok':False,'error':error}),
                'stderr':''}
    monkeypatch.setattr(compute,'_native',native)
    # Simulate an older gateway that conservatively saved the 400 as unknown.
    now=db.utcnow()
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,request_json,status,'
               'created_at,expires_at,receipt_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
               ('old-bad-cpu',rid,'trial_sandbox',json.dumps({'timeout':120,'cpu':'2'}),
                'unknown',now,now,json.dumps(native(['sandbox','create']) ),now))
    result=sandboxes.reconcile_create(rid,'old-bad-cpu')
    assert result['status']=='failed' and result['sandbox_id'] is None
    row=db.query_one('SELECT status,created_at,deleted_at FROM compute_sandboxes'
                     ' WHERE operation_id=?',('old-bad-cpu',))
    assert row['status']=='failed' and row['deleted_at']==row['created_at']
    assert sum(args[:2]==['sandbox','describe'] for args in calls)==1
    assert sum(args[:2]==['sandbox','create'] for args in calls)==1


def test_startup_reclaims_known_terminal_run_and_reports_unowned(run):
    _,rid,_,calls,remote=run
    sid=sandboxes.create(rid,'orphan',{'timeout':120})['sandbox_id']
    remote['other--box-001']={'sandboxID':'other--box-001','status_name':'running'}
    db.execute("UPDATE runs SET phase='finished' WHERE id=?",(rid,))
    result=sandboxes.reconcile_startup()
    assert result['unowned_sandbox_ids']==['other--box-001']
    assert result['cleaned'][0]['sandbox_id']==sid
    assert 'other--box-001' in remote and sid not in remote
    assert sum(a[:2]==['sandbox','delete'] for a in calls)==1


def test_terminating_run_deletes_owned_sandbox(run):
    controller,rid,_,calls,remote=run
    sid=sandboxes.create(rid,'terminate-box',{'timeout':120})['sandbox_id']
    assert asyncio.run(controller.control(rid,'terminate',None,'terminate-op'))['status']=='confirmed'
    assert sid not in remote
    assert db.query_one('SELECT status FROM compute_sandboxes WHERE operation_id=?',
                        ('terminate-box',))['status']=='deleted'
    assert sum(a[:2]==['sandbox','delete'] for a in calls)==1


def test_delete_waits_for_remote_reclamation(run,monkeypatch):
    _,rid,_,calls,remote=run
    sid=sandboxes.create(rid,'slow-delete',{'timeout':120})['sandbox_id']
    original=compute._native
    def delayed(args,**kwargs):
        if args[:2]==['sandbox','delete']:
            calls.append(args)
            remote[sid]['status_name']='destroying'
            return {'ok':True,'exit_code':0,'stdout':'{}','stderr':''}
        return original(args,**kwargs)
    monkeypatch.setattr(compute,'_native',delayed)
    assert sandboxes.delete(rid,sid)['status']=='deleting'
    assert sandboxes.reconcile_deletions()['settled']==0
    remote.pop(sid)
    assert sandboxes.reconcile_deletions()['settled']==1
    assert db.query_one('SELECT status FROM compute_sandboxes WHERE operation_id=?',
                        ('slow-delete',))['status']=='deleted'
    assert sum(a[:2]==['sandbox','delete'] for a in calls)==1


def test_receipt_redacts_access_key_and_truncates(run,monkeypatch):
    _,rid,_,_,_=run
    config.update_secret('fixture-secret','private-fixture-key')
    monkeypatch.setattr(compute,'_native',lambda *a,**k: {
        'ok':True,'exit_code':0,'stdout':json.dumps({'data':{'sandboxID':'fixture--box-002'},
        'note':'accessKey=private-fixture-key'})+'x'*20000,'stderr':'private-fixture-key'})
    # Invalid trailing bytes mean a create receipt is uncertain, never invented.
    result=sandboxes.create(rid,'secret',{'timeout':120})
    assert result['status']=='unknown'
    saved=db.query_one('SELECT receipt_json FROM compute_sandboxes WHERE operation_id=?',('secret',))['receipt_json']
    assert 'private-fixture-key' not in saved
    assert len(json.loads(saved)['stdout'])<=12000


def test_remote_command_failure_is_not_hidden_by_cli_exit_zero(run,monkeypatch):
    _,rid,_,_,_=run
    sid=sandboxes.create(rid,'remote-failure',{'timeout':120})['sandbox_id']
    original=compute._native
    def native(args,**kwargs):
        if args[:2]==['sandbox','exec']:
            return {'ok':True,'exit_code':0,'stdout':json.dumps({'data':{
                'exit_code':7,'stdout':'partial','stderr':'failed'}}),'stderr':''}
        return original(args,**kwargs)
    monkeypatch.setattr(compute,'_native',native)
    result=sandboxes.execute(rid,sid,'false',20,'remote-failure-exec')
    assert result['status']=='failed' and result['exit_code']==7
    event=db.query_one("SELECT payload FROM events WHERE run_id=? AND type='sandbox.exec_completed'",(rid,))
    assert json.loads(event['payload'])['exit_code']==7


def test_delete_waits_for_inflight_scoring_exec(run,monkeypatch):
    _,rid,_,calls,_=run
    sid=sandboxes.create(rid,'score-box',{'timeout':120})['sandbox_id']
    original=compute._native
    def during_exec(args,**kwargs):
        if args[:2]==['sandbox','exec']:
            with pytest.raises(compute.ComputeError, match='仍有执行'):
                sandboxes.delete(rid,sid)
            assert db.query_one('SELECT status FROM compute_sandboxes WHERE sandbox_id=?',
                                (sid,))['status']=='active'
        return original(args,**kwargs)
    monkeypatch.setattr(compute,'_native',during_exec)
    assert sandboxes.execute(rid,sid,'true',20,'score-exec')['status']=='completed'
    assert sum(args[:2]==['sandbox','delete'] for args in calls)==0
    assert sandboxes.delete(rid,sid)['status']=='deleted'


def test_sandbox_skills_are_default_for_executor_only(run):
    _,rid,_,_,_=run
    challenge=db.query_one('SELECT challenge_id FROM runs WHERE id=?',(rid,))['challenge_id']
    settings=config.load_settings()
    executor={s['id'] for s in skills.effective_for(db.get_db(),settings,challenge,role='executor')}
    brain={s['id'] for s in skills.effective_for(db.get_db(),settings,challenge,role='brain')}
    assert {'cyberscientist-sandbox','cyberscientist-clean-rerun'} <= executor
    assert not {'cyberscientist-sandbox','cyberscientist-clean-rerun'} & brain


async def test_mcp_and_bohr_proxy_share_owned_gateway(run):
    from httpx import ASGITransport, AsyncClient
    from cyberscientist import collab
    from cyberscientist.api import create_app
    _,rid,work,calls,_=run
    app=create_app()
    with db.transaction() as conn:
        token=collab.issue_token(conn,rid,'executor','sandbox-test',1)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as client:
        created=await client.post('/api/v1/tools/sandbox',json={'action':'create',
            'operation_id':'mcp-box','request':{'timeout':120}},
            headers={'Authorization':'Bearer '+token})
        assert created.status_code==200,created.text
        sid=created.json()['sandbox_id']
        via_shim=await client.post('/api/v1/tools/bohr',json={'args':['sandbox','describe',sid],
            'cwd':str(work)},headers={'Authorization':'Bearer '+token})
        assert via_shim.status_code==200,via_shim.text
        other=await client.post('/api/v1/tools/sandbox',json={'action':'describe','sandbox_id':'foreign--box'},
            headers={'Authorization':'Bearer '+token})
        assert other.status_code==409
        assert other.json()['detail']['code']=='NOT_OWNED'
        assert sum(a[:2]==['sandbox','create'] for a in calls)==1
