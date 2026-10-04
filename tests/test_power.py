"""Shutdown/restart keeps native identities, active time and remote ledgers."""
import asyncio
import sqlite3
import pytest
from cyberscientist import competition, db, evaluations, power, run_clock
from cyberscientist.controller import RunController


def run():
    db.execute('INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo) VALUES(?,?,?,?,?,?,1)',
               ('clock-topic','fixture','clock','clock','hash',db.utcnow()))
    ctl=RunController()
    rid=ctl.create_run('clock-topic','demo')['id']
    ctl.authorize(rid,'demo',note='fixture',allow_model_calls=True,max_run_minutes=60,max_model_turns=5,max_submissions=0)
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?",(db.utcnow(),rid))
    return ctl,rid


def test_offline_heartbeat_preserves_remaining_and_remote_costs():
    ctl,rid=run()
    run_clock.start(rid,1000)
    run_clock.heartbeat(1015)
    first=run_clock.remaining(db.query_one('SELECT * FROM runs WHERE id=?',(rid,)),{'max_run_minutes':60},1015)
    run_clock.heartbeat(4000)
    row=db.query_one('SELECT * FROM runs WHERE id=?',(rid,))
    assert run_clock.remaining(row,{'max_run_minutes':60},4000)==first
    assert run_clock.remaining(row,{'max_run_minutes':60},4010)==first-10
    assert db.query_one("SELECT payload FROM events WHERE type='run.offline_gap'")
    run_clock.freeze(rid,4010)
    assert run_clock.remaining(db.query_one('SELECT * FROM runs WHERE id=?',(rid,)),{'max_run_minutes':60},9000)==first-10


@pytest.mark.asyncio
@pytest.mark.parametrize('remote_status', ['unknown', 'Running', 'accepted', 'stop_unknown'])
async def test_safe_shutdown_backup_then_automatic_recovery(monkeypatch, remote_status):
    ctl,rid=run()
    run_clock.start(rid)
    db.execute("UPDATE runs SET brain_thread_id='pi-original',executor_thread_id='solver-original' WHERE id=?",(rid,))
    db.execute("INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,spec_json,input_directory,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
               ('remote-original',rid,'t','hash','{}','fixture',remote_status,db.utcnow(),db.utcnow()))
    async def control(run_id,action,text,operation_id):
        if action=='pause':
            db.execute("UPDATE runs SET phase='paused',resume_on_startup=0 WHERE id=?",(run_id,))
            run_clock.freeze(run_id)
        else:
            assert db.query_one('SELECT brain_thread_id FROM runs WHERE id=?',(run_id,))[0]=='pi-original'
            db.execute("UPDATE runs SET phase='running' WHERE id=?",(run_id,))
            run_clock.start(run_id)
        return {'status':'confirmed'}
    monkeypatch.setattr(ctl,'control',control)
    result=await power.safe_shutdown(ctl)
    assert result['can_shutdown'] and result['remote_costs_continue']
    assert result['remote_jobs'][0]['operation_id']=='remote-original'
    with sqlite3.connect(result['backup']) as saved:
        assert saved.execute('SELECT phase FROM runs WHERE id=?',(rid,)).fetchone()[0]=='paused'
    before=run_clock.elapsed(db.query_one('SELECT * FROM runs WHERE id=?',(rid,)))
    ctl.reconcile_on_startup()
    restored=await power.recover(ctl)
    assert restored[0]['status']=='confirmed'
    assert not power.shutdown_requested()
    assert abs(run_clock.elapsed(db.query_one('SELECT * FROM runs WHERE id=?',(rid,)))-before)<1
    assert db.query_one('SELECT COUNT(*) FROM compute_jobs')[0]==1


@pytest.mark.asyncio
async def test_unconfirmed_pause_never_says_can_shutdown(monkeypatch):
    ctl,rid=run()
    async def reject(*args):raise RuntimeError('no native receipt')
    monkeypatch.setattr(ctl,'control',reject)
    result=await power.safe_shutdown(ctl,timeout=.01)
    assert not result['can_shutdown'] and result['errors'] and result['unsettled_runs']
    class NoStarts:
        def __getattr__(self,name):raise AssertionError('new queue start during shutdown')
    await evaluations.advance(NoStarts())


def test_clock_additive_migration_is_idempotent():
    db.init_db();db.init_db()
    assert 'clock_version' in {r['name'] for r in db.query('PRAGMA table_info(runs)')}
