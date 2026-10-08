import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import pytest
from cyberscientist import config, db, mailboxes, auto_harvest, alerts
from test_mailboxes import _seed_challenge, _make_run, _make_package, _set_scored


def seed(score=100, limit=5):
    settings=config.load_settings();settings['features']['auto_harvest']=True;config.save_settings(settings)
    _seed_challenge(); rid=_make_run(max_submissions=limit); _make_package(rid)
    mailboxes.register_experiment(1); mailboxes.add_harvest('owned@example.com','fixture-harvest')
    source=mailboxes.submit_experiment(rid,'trial_mb1',None,'experiment')
    _set_scored(source['id'],score)
    db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,))
    return rid, source


def test_threshold_same_hash_total_budget_and_no_duplicate():
    rid,src=seed(limit=2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:auto_harvest.advance_sync(),range(2)))
    automatic=db.query_one('SELECT * FROM automatic_harvests')
    assert automatic['status']=='done' and automatic['reason']=='score_threshold'
    harvest=db.query_one('SELECT * FROM submissions WHERE is_harvest=1')
    assert harvest['source_submission_id']==src['id'] and harvest['package_sha256']==src['package_sha256']
    assert mailboxes.harvest_submit(src['id'],automatic['operation_id'],True)['deduplicated']
    auto_harvest.advance_sync()
    assert len(db.query('SELECT * FROM submissions'))==2
    with pytest.raises(mailboxes.MailboxError,match='授权已用尽'):
        mailboxes.submit_experiment(rid,'trial_mb1',None,'over-total')


def test_completed_experiment_at_leader_unknown_distribution_and_lower_own(monkeypatch):
    rid,src=seed(80)
    db.execute("UPDATE runs SET phase='finished' WHERE id=?",(rid,))
    monkeypatch.setattr(auto_harvest.platform_scores,'get',lambda _, **kwargs: {'status':'unknown'})
    auto_harvest.advance_sync(); assert not db.query('SELECT * FROM automatic_harvests')
    monkeypatch.setattr(auto_harvest.platform_scores,'get',lambda _, **kwargs: {'status':'ok','top_10_scores':[80,60]})
    auto_harvest.advance_sync()
    assert db.query_one('SELECT reason FROM automatic_harvests')[0]=='experiments_done_at_leader'
    harvest=db.query_one('SELECT * FROM submissions WHERE is_harvest=1'); _set_scored(harvest['id'],90)
    _make_package(rid,'trial_mb2','{"value":2}');db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,))
    src2=mailboxes.submit_experiment(rid,'trial_mb2',None,'lower-exp');_set_scored(src2['id'],85)
    s=config.load_settings();s['harvest']['score_threshold']=0;config.save_settings(s)
    auto_harvest.advance_sync()
    assert not db.query_one('SELECT * FROM automatic_harvests WHERE source_submission_id=?',(src2['id'],))
    assert len(db.query('SELECT * FROM submissions WHERE is_harvest=1'))==1


def test_failure_unknown_not_replayed_and_alert_persists(monkeypatch):
    rid,src=seed()
    calls=[]
    def uncertain(*args,**kw): calls.append(args);raise TimeoutError('unknown upload')
    monkeypatch.setattr(mailboxes,'harvest_submit',uncertain)
    auto_harvest.advance_sync();auto_harvest.advance_sync()
    assert len(calls)==1 and db.query_one('SELECT status FROM automatic_harvests')[0]=='unknown'
    db.init_db();auto_harvest.reconcile_interrupted();auto_harvest.advance_sync()
    assert len(calls)==1
    items=alerts.pending(); assert items[0]['kind']=='harvest.unknown'
    event_count=len(items);db.init_db(); assert len(alerts.pending())==event_count
    alerts.acknowledge(items[0]['id']);assert not alerts.pending()


def test_provisional_anomaly_changed_package_and_no_retroactive_old_runs():
    rid,src=seed()
    db.execute("UPDATE submissions SET score_confidence='provisional' WHERE id=?",(src['id'],))
    auto_harvest.advance_sync();assert not db.query('SELECT * FROM automatic_harvests')
    _set_scored(src['id'],100)
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0]);snapshot.pop('automatic_harvest_version')
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(snapshot),rid))
    auto_harvest.advance_sync();assert not db.query('SELECT * FROM automatic_harvests')
    snapshot['automatic_harvest_version']=1;db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(snapshot),rid))
    (config.WORKSPACE_DIR/src['package_path']).write_text('changed')
    auto_harvest.advance_sync();assert db.query_one('SELECT status FROM automatic_harvests')[0]=='failed'
    assert len(db.query('SELECT * FROM submissions'))==1
    auto_harvest.advance_sync();assert len(db.query('SELECT * FROM submissions'))==1


def test_current_ended_target_guard_zero_post_and_frozen_slug(monkeypatch):
    _seed_challenge(); s=config.load_settings();s['policy'].update(require_ended_submission=True,allowed_submission_targets=['MB']);config.save_settings(s)
    rid=_make_run();db.execute("UPDATE challenges SET platform_challenge_id='UNFINISHED' WHERE id='MB_CH'")
    assert mailboxes._run_challenge_id(rid)=='MB'
    class Platform:
        is_demo=False;operator_token=None
        def _http(self,*args,**kw):
            assert args==('GET','/challenges/MB')
            return {'roundEndAt':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}
    platform=Platform()
    with pytest.raises(mailboxes.PlatformError,match='未发送'):
        mailboxes._guard_submission_target(rid,platform,'MB')
    with pytest.raises(mailboxes.PlatformError,match='范围'):
        mailboxes._guard_submission_target(rid,platform,'UNFINISHED')
    monkeypatch.setattr(platform,'_http',lambda *a,**k: {'roundEndAt':'2026-01-01T00:00:00Z','status':'open'})
    mailboxes._guard_submission_target(rid,platform,'MB')


def test_deadline_check_does_not_bypass_confirmed_score_conditions(monkeypatch):
    rid,src=seed(20)
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0])
    snapshot['competition']={'challenge_snapshot':{'platform':{'roundEndAt':(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()}}}
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(snapshot),rid))
    db.execute("UPDATE submissions SET score_confidence='provisional' WHERE id=?",(src['id'],))
    auto_harvest.advance_sync();auto_harvest.advance_sync()
    assert len(db.query("SELECT * FROM events WHERE type='harvest.deadline_check'"))==1
    assert not db.query('SELECT * FROM automatic_harvests')


def test_alerts_pause_error_best_long_throttle_and_budget(monkeypatch):
    rid,src=seed(50)
    db.append_event(rid,'controller','run.paused',{'reason':'all authorized routes tried'})
    db.append_event(rid,'prime','prime.error',{'message':'fixture'})
    db.append_event(rid,'controller','submission.scored',{'submission_id':src['id']})
    past=(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat()
    db.execute("INSERT INTO model_rate_limits(run_id,role,first_at,attempts,retry_at,state) VALUES(?,'executor',?,3,?,'waiting')",(rid,past,db.utcnow()))
    db.execute('UPDATE runs SET started_at=?,active_elapsed_seconds=1750,clock_active_since=NULL,clock_version=1 WHERE id=?',(past,rid))
    kinds={row['kind'] for row in alerts.pending()}
    assert {'run.paused','prime.error','submission.scored','model.long_rate_limit','authorization.near_exhaustion'}<=kinds
    before=len(alerts.pending());alerts.synchronize();assert len(alerts.pending())==before


def test_migrations_and_harvest_parameter_validation():
    db.init_db();db.init_db()
    assert db.query_one("SELECT name FROM sqlite_master WHERE name='automatic_harvests'")
    for params in ({'score_threshold':float('nan')},{'deadline_check_hours':-1},{'experiments_done_at_leader':'true'}):
        with pytest.raises(ValueError):auto_harvest.validate(params)
    assert auto_harvest.validate({})['score_threshold']==100


def test_same_topic_other_run_prevents_leader_trigger(monkeypatch):
    rid,src=seed(80)
    from cyberscientist.controller import RunController
    other=RunController().create_run('MB_CH')['id']
    db.execute("UPDATE runs SET phase='finished' WHERE id=?",(rid,))
    monkeypatch.setattr(auto_harvest.platform_scores,'get',lambda _, **kw: {'status':'ok','top_10_scores':[80]})
    auto_harvest.advance_sync();assert not db.query('SELECT * FROM automatic_harvests')
    db.execute("UPDATE runs SET phase='finished' WHERE id=?",(other,))
    auto_harvest.advance_sync();assert db.query_one('SELECT status FROM automatic_harvests')[0]=='done'


def test_score_correction_before_reservation_does_not_use_old_trigger(monkeypatch):
    rid,src=seed(100)
    real_trigger=auto_harvest._trigger
    def corrected(run,source,params):
        result=real_trigger(run,source,params)
        _set_scored(src['id'],90)
        return result
    monkeypatch.setattr(auto_harvest,'_trigger',corrected)
    auto_harvest.advance_sync()
    assert not db.query('SELECT * FROM submissions WHERE is_harvest=1')


def test_unknown_harvest_can_be_reconciled_from_receipt_without_post(monkeypatch):
    rid,src=seed()
    auto_harvest.advance_sync()
    db.execute("UPDATE automatic_harvests SET status='unknown'")
    monkeypatch.setattr(mailboxes,'harvest_submit',lambda *a,**k:pytest.fail('不得重交'))
    auto_harvest.reconcile_interrupted();auto_harvest.advance_sync()
    assert db.query_one('SELECT status FROM automatic_harvests')[0]=='done'


@pytest.mark.asyncio
async def test_actual_http_worker_survives_repeated_cancellation(monkeypatch):
    import asyncio, threading
    from cyberscientist import resource_coordinator
    entered=threading.Event();release=threading.Event()
    def slow():
        entered.set()
        assert release.wait(5)
    monkeypatch.setattr(auto_harvest,'advance_sync',slow)
    await auto_harvest.advance()
    for _ in range(100):
        if entered.is_set():break
        await asyncio.sleep(.005)
    assert entered.is_set()
    task=next(iter(auto_harvest.ACTIVE_TASKS))
    task.cancel();await asyncio.sleep(.01);task.cancel();await asyncio.sleep(.01)
    assert not task.done() and task in resource_coordinator.auxiliary_tasks()
    release.set();await auto_harvest.drain()
    assert task.done() and task not in resource_coordinator.auxiliary_tasks()


def test_actual_runtime_compute_failures_are_alerted():
    rid,src=seed()
    db.append_event(rid,'controller','run.runtime_error',{'reason':'fixture'})
    db.append_event(rid,'controller','sandbox.failed',{'error':'fixture'})
    db.append_event(rid,'controller','job.observed',{'status':'Failed'})
    kinds={row['kind'] for row in alerts.pending()}
    assert {'run.runtime_error','sandbox.failed','job.observed'}<=kinds


def test_leader_distribution_refreshes_frozen_target(monkeypatch):
    from cyberscientist import platform_scores
    rid,src=seed(80)
    db.execute("UPDATE challenges SET platform_challenge_id='wrong-target' WHERE id='MB_CH'")
    platform_scores._cache['MB']=(__import__('time').monotonic(),{'status':'ok','top_10_scores':[10]})
    calls=[]
    monkeypatch.setattr(platform_scores,'_collect',lambda slug: calls.append(slug) or {'status':'ok','top_10_scores':[99]})
    assert platform_scores.get(rid,fresh=True)['top_10_scores']==[99]
    assert calls==['MB']
    platform_scores._cache.clear()


def test_final_score_correction_before_post_is_blocked(monkeypatch):
    rid,src=seed(100)
    original=mailboxes._guard_submission_target
    def correcting(run,platform,target):
        if db.query_one('SELECT 1 FROM submissions WHERE is_harvest=1'):
            _set_scored(src['id'],90)
        return original(run,platform,target)
    monkeypatch.setattr(mailboxes,'_guard_submission_target',correcting)
    auto_harvest.advance_sync()
    harvest=db.query_one('SELECT * FROM submissions WHERE is_harvest=1')
    assert harvest['status']=='failed' and harvest['reservation_released']==1 and harvest['platform_ref'] is None
    assert db.query_one('SELECT status FROM automatic_harvests')[0]=='failed'


def test_unlisted_topic_reports_clear_404_without_attempt_post():
    rid,src=seed()
    class Removed:
        is_demo=False;operator_token=None
        def _http(self,method,path,**kwargs):
            assert method=='GET'
            raise mailboxes.PlatformError('平台接口 GET 返回 HTTP 404')
    with pytest.raises(mailboxes.PlatformError,match='题目已下架或不存在') as caught:
        mailboxes._guard_submission_target(rid,Removed(),'MB')
    assert caught.value.no_side_effect


@pytest.mark.asyncio
async def test_alert_api_acknowledgement_survives_new_app_instance():
    import httpx
    from cyberscientist.api import create_app
    rid,src=seed()
    db.append_event(rid,'controller','run.runtime_error',{'reason':'fixture runtime'})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),base_url='http://test') as client:
        rows=(await client.get('/api/v1/alerts')).json()['items']
        assert len(rows)==1
        assert (await client.post('/api/v1/alerts/'+rows[0]['id']+'/acknowledge',json={})).status_code==200
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),base_url='http://test') as client:
        assert (await client.get('/api/v1/alerts')).json()['items']==[]


def test_other_topic_run_exhaustion_does_not_claim_all_experiments_done(monkeypatch):
    rid,src=seed(80)
    from cyberscientist.controller import RunController
    other=RunController().create_run('MB_CH')['id']
    db.execute("UPDATE runs SET phase='finished' WHERE challenge_id='MB_CH'")
    db.execute("UPDATE runs SET end_reason='brain_review_limit' WHERE id=?",(other,))
    monkeypatch.setattr(auto_harvest.platform_scores,'get',lambda _, **kw: {'status':'ok','top_10_scores':[80]})
    auto_harvest.advance_sync();assert not db.query('SELECT * FROM automatic_harvests')


def test_late_live_receipt_reconciles_unknown_without_touching_running(monkeypatch):
    rid,src=seed()
    auto_harvest.advance_sync()
    db.execute("UPDATE automatic_harvests SET status='unknown'")
    monkeypatch.setattr(mailboxes,'harvest_submit',lambda *a,**k:pytest.fail('不得重发'))
    auto_harvest.advance_sync()
    assert db.query_one('SELECT status FROM automatic_harvests')[0]=='done'
    db.execute("UPDATE automatic_harvests SET status='running'")
    auto_harvest.reconcile_interrupted(include_running=False)
    assert db.query_one('SELECT status FROM automatic_harvests')[0]=='running'
