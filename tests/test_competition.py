"""Synthetic rounds exercise the real persistent queue and atomic admission."""
from __future__ import annotations
import asyncio
import json
from datetime import datetime, timedelta, timezone
import pytest
from cyberscientist import competition, config, db, evaluations, resource_coordinator
from cyberscientist.controller import RunController


def challenges(n=10):
    for i in range(n):
        db.execute('INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo) VALUES(?,?,?,?,?,?,1)',
                   (f'c{i}', 'fixture', f'题目{i}', '合成测试题', f'h{i}', db.utcnow()))
    return [f'c{i}' for i in range(n)]


def template():
    return {'authorization': {'allow_model_calls': True, 'max_run_minutes': 60,
                              'max_jobs': 2, 'max_submissions': 0, 'max_sandboxes': 2, 'max_sandbox_minutes': 60}}


class FakeController(RunController):
    def __init__(self):
        super().__init__()
        self.throttled = False
        self.started = []
    async def start_async(self, rid):
        if not self.throttled:
            self.throttled = True
            raise RuntimeError('HTTP 429 Too Many Requests Retry-After: 1')
        settings = self._runtime_settings(rid)
        with db.transaction() as conn:
            resource_coordinator.reserve_sessions_tx(conn, rid, {role: settings[role] for role in ('brain', 'executor')})
            conn.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
        self.started.append(rid)
        return self.run_snapshot(rid)
    async def control(self, rid, action, text, operation_id):
        db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
        return {'status': 'confirmed'}


def test_ten_challenge_round_respects_limits_retries_and_survives_restart():
    ids = challenges()
    rnd = competition.import_round(ids, mode='demo')
    bounded = template(); bounded['authorization']['unlimited_resources'] = False
    competition.confirm(rnd['id'], bounded)
    ctl = FakeController()
    asyncio.run(evaluations.advance(ctl))
    limited = db.query_one('SELECT retry_at,status FROM eval_results WHERE retry_at IS NOT NULL')
    assert limited['status'] != 'failed'
    assert not ctl.started
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    db.execute('UPDATE model_provider_backoff SET retry_at=?', (past,))
    db.execute('UPDATE eval_results SET retry_at=? WHERE retry_at IS NOT NULL', (past,))
    asyncio.run(evaluations.advance(ctl))
    assert len(ctl.started) == 5  # 2 Codex sessions per Run, provider cap 10.
    assert db.query_one('SELECT COUNT(*) FROM model_session_leases')[0] == 10
    assert db.query_one("SELECT COUNT(*) FROM runs WHERE phase NOT IN ('finished','failed','cancelled')")[0] <= 6
    first = ctl.started[0]
    db.execute("UPDATE runs SET phase='finished',ended_at=? WHERE id=?", (db.utcnow(), first))
    resource_coordinator.release_sessions(first)
    # New scheduler instance continues the persistent queue.
    restarted = FakeController(); restarted.throttled = True
    asyncio.run(evaluations.advance(restarted))
    assert restarted.started
    for _ in range(15):
        for row in db.query("SELECT id FROM runs WHERE phase='running'"):
            db.execute("UPDATE runs SET phase='finished',ended_at=? WHERE id=?", (db.utcnow(), row['id']))
            resource_coordinator.release_sessions(row['id'])
        asyncio.run(evaluations.advance(restarted))
    assert competition.get_round(rnd['id'])['status'] == 'complete'
    assert len(db.query('SELECT * FROM runs')) == 10
    assert not db.query('SELECT * FROM submissions')
    extended = competition.append_run(rnd['id'], 'c0')
    assert len(extended['items']) == 11
    assert extended['items'][-1]['challenge_id'] == 'c0'
    asyncio.run(evaluations.advance(restarted))
    assert db.query_one('SELECT COUNT(*) FROM runs WHERE challenge_id=?', ('c0',))[0] == 2


def test_template_confirm_freezes_hash_and_per_challenge_model_override():
    challenges(2)
    rnd = competition.import_round(['c0', 'c1'], mode='demo')
    override = template() | {'model_config': {'executor': {'runtime': 'codex', 'model_id': 'other', 'reasoning_effort': 'medium'}}}
    value = competition.confirm(rnd['id'], template(), {'c1': override})
    assert len(value['experience_snapshot_sha256']) == 64
    assert value['items'][1]['template']['model_config']['executor']['model_id'] == 'other'
    assert db.query_one('SELECT COUNT(*) FROM runs')[0] == 0
    with pytest.raises(competition.CompetitionError): competition.append_run(rnd['id'], 'other')


def test_triage_is_native_task_and_authorization_is_required():
    challenges(1)
    ctl = RunController()
    demo = competition.import_round(['c0'], mode='demo')
    result = asyncio.run(competition.triage(demo['id'], ctl))
    assert result['items'][0]['triage']['difficulty'] == 'unknown'
    assert not db.query('SELECT * FROM model_session_leases')
    connected = competition.import_round(['c0'])
    with pytest.raises(competition.CompetitionError, match='显式授权'):
        asyncio.run(competition.triage(connected['id'], ctl))
    with pytest.raises(competition.CompetitionError, match='有界时长'):
        competition.confirm(connected['id'], {'authorization': {'allow_model_calls': True}})


def test_priority_and_pause_are_persistent():
    challenges(2)
    rnd = competition.import_round(['c0', 'c1'], mode='demo')
    competition.confirm(rnd['id'], template())
    item = rnd['items'][1]
    competition.update_item(rnd['id'], item['id'], priority=10, paused=True)
    ctl = FakeController(); ctl.throttled = True
    asyncio.run(evaluations.advance(ctl))
    assert db.query_one('SELECT COUNT(*) FROM runs WHERE challenge_id=?', ('c1',))[0] == 0
    db.init_db(); db.init_db()  # Additive migration is idempotent.
    assert competition.get_round(rnd['id'])['items'][0]['paused'] == 1


def test_providers_have_independent_session_and_rate_limit_budgets():
    settings = config.load_settings(); settings['resources']['provider_sessions']['codex'] = 1
    config.save_settings(settings)
    with db.transaction() as conn:
        resource_coordinator.reserve_sessions_tx(conn, 'one', {'brain': {'runtime': 'codex'}})
    with pytest.raises(resource_coordinator.ResourceWait):
        with db.transaction() as conn:
            resource_coordinator.reserve_sessions_tx(conn, 'two', {'brain': {'runtime': 'codex'}})
    until = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    resource_coordinator.throttle('codex', until)
    with db.transaction() as conn:
        resource_coordinator.reserve_sessions_tx(conn, 'other', {'executor': {'runtime': 'codex', 'provider': 'deepseek'}})
    assert resource_coordinator.status()['sessions'] == [{'provider': 'codex', 'used': 1}, {'provider': 'deepseek', 'used': 1}]


def test_global_compute_limits_use_real_ledger_under_writer_lock():
    from cyberscientist import compute
    settings = config.load_settings(); settings['resources']['max_concurrent_jobs'] = 1
    settings['bohrium']['project_id'] = 88474
    config.save_settings(settings)
    challenges(1)
    ctl = RunController(); rid = ctl.create_run('c0', 'connected')['id']
    ctl.authorize(rid, 'connected', True, 0, 60, 0, '', max_jobs=2)
    db.execute("UPDATE runs SET phase='running',current_trial_id='fixture',started_at=? WHERE id=?", (db.utcnow(), rid))
    db.execute('INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,spec_json,input_directory,status,created_at,updated_at)'
               " VALUES('synthetic-job',?,'fixture','hash','{}','fixture','unknown',?,?)", (rid, db.utcnow(), db.utcnow()))
    with pytest.raises(compute.ComputeError, match='全局 job 并发'):
        with db.transaction() as conn: resource_coordinator.require_compute_slot_tx(conn, 'job')
    assert db.query_one('SELECT COUNT(*) FROM compute_jobs')[0] == 1


def test_default_run_cap_is_six():
    assert config.load_settings()['run_defaults']['max_active_runs'] == 6


def test_curation_sessions_share_provider_capacity_and_release_it():
    settings = config.load_settings(); settings['app']['mode'] = 'connected'
    settings['resources']['provider_sessions']['codex'] = 1
    config.save_settings(settings)
    resource_coordinator.reserve_auxiliary('curation-one', settings)
    with pytest.raises(resource_coordinator.ResourceWait):
        resource_coordinator.reserve_auxiliary('curation-two', settings)
    resource_coordinator.release_sessions('curation-one')
    resource_coordinator.reserve_auxiliary('curation-two', settings)
    assert resource_coordinator.status()['sessions'] == [{'provider': 'codex', 'used': 1}]


@pytest.mark.asyncio
async def test_overlapping_triage_sessions_have_distinct_leases_and_respect_provider_cap(monkeypatch):
    from cyberscientist.brains.base import BrainEvent
    challenges(1)
    rnd=competition.import_round(['c0'],mode='connected')
    settings=config.load_settings();settings['brain']['runtime']='codex'
    settings['resources']['provider_sessions']['codex']=1;config.save_settings(settings)
    entered=asyncio.Event();release=asyncio.Event()
    class Brain:
        async def open(self,spec):entered.set();return 'native'
        async def review(self,session,packet):
            await release.wait()
            yield BrainEvent('task_result',{'result':{'difficulty':'easy','reason':'fixture'}})
        async def close(self,session):pass
    ctl=RunController();monkeypatch.setattr(ctl,'_make_brain',lambda settings:Brain())
    first=asyncio.create_task(competition.triage(rnd['id'],ctl,True));await entered.wait()
    with pytest.raises(resource_coordinator.ResourceWait):await competition.triage(rnd['id'],ctl,True)
    assert db.query_one('SELECT COUNT(*) FROM model_session_leases')[0]==1
    release.set();await first
    assert not db.query('SELECT * FROM model_session_leases')


def test_reimport_binds_new_public_details_to_round_without_changing_topic_identity(monkeypatch):
    from cyberscientist import mailbox_platform
    challenges(1)
    db.execute("UPDATE challenges SET platform_challenge_id='public-fixture',is_demo=0 WHERE id='c0'")
    monkeypatch.setattr(mailbox_platform,'fetch_platform_challenge',lambda *args:{'content':'第一版本','title':'公共题','resources':[]})
    first=competition.import_round(['public-fixture'])
    monkeypatch.setattr(mailbox_platform,'fetch_platform_challenge',lambda *args:{'content':'已修正的第二版本','title':'公共题','resources':[]})
    second=competition.import_round(['public-fixture'])
    def snapshot(rid):return json.loads(db.query_one('SELECT config_json FROM eval_runs WHERE id=?',(rid,))[0])['entries'][0]
    a,b=snapshot(first['id']),snapshot(second['id'])
    assert a['challenge_id']==b['challenge_id']=='c0'
    assert a['challenge_snapshot']['content']=='第一版本'
    assert b['challenge_snapshot']['content']=='已修正的第二版本'
    assert a['challenge_snapshot']['content_sha256']!=b['challenge_snapshot']['content_sha256']


def test_frozen_solver_note_and_public_resources_reach_pi_executor_and_data_tools(monkeypatch):
    from cyberscientist import datasets,mailbox_platform
    challenges(1)
    db.execute("UPDATE challenges SET platform_challenge_id='public-fixture',is_demo=0 WHERE id='c0'")
    resource={'type':'url','url':'https://example.org/new-data.zip','role':'task-public-data'}
    monkeypatch.setattr(mailbox_platform,'fetch_platform_challenge',lambda *args:{'content':'修正题面','title':'新标题','resources':[resource]})
    rnd=competition.import_round(['public-fixture'],mode='demo')
    competition.confirm(rnd['id'],template() | {'solver_note':'便宜求解者，需要明确公式'})
    ctl=FakeController();ctl.throttled=True
    asyncio.run(evaluations.advance(ctl))
    run=db.query_one('SELECT * FROM runs')
    packet=ctl._lifecycle_packet(run,'run_start',sparse=True)
    assert packet['solver_note']=='便宜求解者，需要明确公式'
    assert packet['feedback']['solver_note']==packet['solver_note']
    assert packet['challenge']['content']=='修正题面'
    assert json.loads(ctl._challenge_for_run(run)['resources_json'])==[resource]
    key=datasets.resource_key(resource)
    assert key and datasets._resource('c0',key,run['id'])==resource
    assert datasets.status('c0')['items']
