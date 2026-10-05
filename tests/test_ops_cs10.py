import asyncio
import io
import json
import sys
import threading
import pytest
from cyberscientist import cli,config,db,ops,power,resource_coordinator
from cyberscientist.controller import RunController


@pytest.mark.parametrize('arguments,path,method,result',[
    (['status','--json'],'/ops/status','GET',{'status':'ok'}),
    (['events','run-fixture','--tail','3'],'/ops/events/run-fixture?tail=3','GET',{'items':[]}),
    (['alerts'],'/ops/alerts','GET',{'alerts':[]}),
    (['switch','auto_harvest','off'],'/features/auto_harvest','PUT',{'enabled':False}),
    (['shutdown'],'/system/safe-shutdown','POST',{'can_shutdown':True}),
    (['resume'],'/ops/resume','POST',{'status':'ready'}),
])
def test_each_cli_command_path_and_secret_output(monkeypatch,capsys,arguments,path,method,result):
    calls=[];config.update_secret('fixture','secret-for-cli-output')
    def fetch(request,timeout):
        calls.append(request);return io.BytesIO(json.dumps({**result,'error':'secret-for-cli-output'}).encode())
    monkeypatch.setattr(cli.urllib.request,'urlopen',fetch);monkeypatch.setattr(sys,'argv',['cyberscientist','ops',*arguments])
    cli.main();output=capsys.readouterr().out
    assert 'secret-for-cli-output' not in output and calls[0].full_url.endswith(path) and calls[0].method==method


@pytest.mark.parametrize('command,result,exit_code', [('shutdown',{'can_shutdown':False},1),('resume',{'status':'unknown'},1)])
def test_unknown_operation_nonzero_exit(monkeypatch,command,result,exit_code):
    monkeypatch.setattr(cli.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(json.dumps(result).encode()))
    monkeypatch.setattr(sys,'argv',['cyberscientist','ops',command])
    with pytest.raises(SystemExit) as exc:cli.main()
    assert exc.value.code==exit_code


def runs():
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo) VALUES('ops-ch','fixture','x','x','h',?,1)",(db.utcnow(),))
    ctl=RunController();ids=[]
    for clock,intent in [(1,1),(1,0),(0,1)]:
        rid=ctl.create_run('ops-ch')['id'];ids.append(rid)
        db.execute("UPDATE runs SET phase='paused',clock_version=?,resume_on_startup=? WHERE id=?",(clock,intent,rid))
    return ctl,ids


@pytest.mark.asyncio
async def test_real_read_routes_tail_alerts_version_and_secret_scrubbing():
    from httpx import ASGITransport,AsyncClient
    from cyberscientist.api import create_app
    ctl,ids=runs();config.update_secret('fixture','secret-for-ops-query')
    for i in range(4):db.append_event(ids[0],'controller','run.runtime_error',{'error':'secret-for-ops-query','i':i})
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://t') as client:
        status=await client.get('/api/v1/ops/status');assert status.status_code==200
        result=status.json();assert len(result['runs'])==3 and result['code']['loaded'] and 'resources' in result
        assert 'secret-for-ops-query' not in status.text and result['pending']['alerts']
        got=(await client.get('/api/v1/ops/events/'+ids[0]+'?tail=2')).json()['items']
        assert [r['payload']['i'] for r in got]==[2,3]
        assert (await client.get('/api/v1/ops/events/'+ids[0]+'?tail=0')).status_code==422
        assert (await client.get('/api/v1/ops/alerts')).json()['alerts']
        assert all(not r['stuck']['suspected'] for r in result['runs'])


@pytest.mark.asyncio
async def test_resume_reconciles_first_does_not_delete_or_resume_manual_legacy(monkeypatch):
    from cyberscientist import compute,mailboxes,sandboxes
    ctl,ids=runs();order=[]
    db.execute("INSERT OR REPLACE INTO system_state VALUES('shutdown_requested','1')")
    monkeypatch.setattr(compute,'reconciliation_runs',lambda **k:[ids[0]])
    monkeypatch.setattr(compute,'reconcile',lambda rid,allow_retry:order.append(('jobs',allow_retry)) or {'status':'ok'})
    monkeypatch.setattr(mailboxes,'poll_pending_by_challenge',lambda:order.append(('scores',None)) or {})
    async def control(rid,action,text,operation_id):
        assert order==[('jobs',False),('scores',None)] and rid==ids[0]
        order.append(('resume',rid));db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,));return {'status':'confirmed'}
    monkeypatch.setattr(ctl,'control',control)
    result=await ops.resume(ctl)
    assert result['status']=='ready' and len(result['resumed'])==1
    assert [r['phase'] for r in db.query('SELECT phase FROM runs ORDER BY rowid')]==['running','paused','paused']
    assert (await ops.resume(ctl))['resumed']==[]


@pytest.mark.asyncio
async def test_resume_fault_retains_shutdown_and_new_shutdown_wins(monkeypatch):
    from cyberscientist import mailboxes
    ctl,ids=runs();db.execute("INSERT OR REPLACE INTO system_state VALUES('shutdown_requested','1')")
    def fail():raise OSError('fixture network failure')
    monkeypatch.setattr(mailboxes,'poll_pending_by_challenge',fail)
    result=await ops.resume(ctl);assert result['status']=='unknown' and power.shutdown_requested()
    def again():
        db.execute("INSERT OR REPLACE INTO system_state VALUES('shutdown_epoch','new-shutdown')");return {}
    monkeypatch.setattr(mailboxes,'poll_pending_by_challenge',again)
    result=await ops.resume(ctl);assert result['status']=='unknown' and power.shutdown_requested()
    assert all(r['phase']=='paused' for r in db.query('SELECT phase FROM runs'))


@pytest.mark.asyncio
async def test_resume_cancel_keeps_actual_http_tracked_and_single_worker(monkeypatch):
    from cyberscientist import mailboxes
    ctl,ids=runs();db.execute("INSERT OR REPLACE INTO system_state VALUES('shutdown_requested','1')")
    entered=threading.Event();released=threading.Event();calls=[]
    def slow():entered.set();released.wait(5);calls.append('http');return {}
    monkeypatch.setattr(mailboxes,'poll_pending_by_challenge',slow)
    async def control(*args):raise AssertionError('cancelled resume must not start native work')
    monkeypatch.setattr(ctl,'control',control)
    waiter=asyncio.create_task(ops.resume(ctl));assert await asyncio.to_thread(entered.wait,1)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):await waiter
    worker=ops.RESUME_TASK;worker.cancel();await asyncio.sleep(.02)
    assert not worker.done() and worker in resource_coordinator.auxiliary_tasks()
    released.set();await asyncio.gather(worker,return_exceptions=True)
    assert calls==['http'] and power.shutdown_requested() and not resource_coordinator.auxiliary_tasks()


def test_status_run_score_not_other_run_score_and_current_origin_does_not_erase_history():
    ctl,ids=runs()
    db.execute("INSERT INTO mailboxes(id,role,email,platform,status,created_at) VALUES('ops-mb','experiment','fixture@example.test','demo','active',?)",(db.utcnow(),))
    db.execute("INSERT INTO submissions(id,run_id,mailbox_id,package_path,package_sha256,status,score,score_status,score_confidence,created_at) VALUES('ops-score',?,'ops-mb','fixture','h','submitted',70,'scored','confirmed',?)",(ids[0],db.utcnow()))
    data={r['id']:r for r in ops.status()['runs']}
    assert data[ids[0]]['platform_best']==70 and data[ids[1]]['platform_best'] is None
    settings=config.load_settings();settings['playground']['base_url']='https://changed.example/api';config.save_settings(settings)
    after={r['id']:r for r in ops.status()['runs']}
    assert after[ids[0]]['platform_best']==70 and after[ids[1]]['platform_best'] is None


@pytest.mark.asyncio
async def test_persistent_recovery_intent_retries_after_resource_wait_without_barrier(monkeypatch):
    from cyberscientist import mailboxes
    ctl,ids=runs();power.begin_shutdown();calls=[]
    monkeypatch.setattr(mailboxes,'poll_pending_by_challenge',lambda:{})
    async def control(rid,*args):
        calls.append(rid)
        if len(calls)==1: raise resource_coordinator.ResourceWait('synthetic rate backoff')
        db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,));return {'status':'confirmed'}
    monkeypatch.setattr(ctl,'control',control)
    first=await ops.resume(ctl)
    assert first['status']=='unknown' and not power.shutdown_requested()
    second=await ops.resume(ctl)
    assert second['status']=='ready' and calls==[ids[0],ids[0]]
    assert all(r['phase']=='paused' for r in db.query('SELECT phase FROM runs WHERE id!=?',(ids[0],)))


@pytest.mark.asyncio
async def test_production_exit_epoch_prevents_old_resume_clearing_barrier(monkeypatch):
    from cyberscientist import mailboxes
    from cyberscientist.api import create_app
    ctl,ids=runs();app=create_app();lifespan=app.router.lifespan_context(app)
    await lifespan.__aenter__();power.begin_shutdown()
    # Startup conservatively marked legacy/manual rows recovering; restore the
    # explicit shutdown fixture to exercise only its persisted intent.
    db.execute("UPDATE runs SET phase='paused' WHERE id=?",(ids[0],))
    entered=threading.Event();released=threading.Event();calls=[]
    def slow():entered.set();released.wait(5);return {}
    monkeypatch.setattr(mailboxes,'poll_pending_by_challenge',slow)
    async def control(*args):calls.append(args);return {'status':'confirmed'}
    monkeypatch.setattr(ctl,'control',control)
    waiter=asyncio.create_task(ops.resume(ctl));assert await asyncio.to_thread(entered.wait,1)
    closing=asyncio.create_task(lifespan.__aexit__(None,None,None));await asyncio.sleep(.02)
    assert not closing.done()
    released.set();await asyncio.wait_for(closing,2);await asyncio.gather(waiter,return_exceptions=True)
    assert not calls and power.shutdown_requested() and not resource_coordinator.auxiliary_tasks()
