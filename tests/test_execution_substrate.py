"""Regression fixtures reproduce CS-UP-07 defects without scientific compute."""
import asyncio
import json
from datetime import datetime,timedelta,timezone
import pytest
from cyberscientist import compute,config,db,observation,resource_coordinator,scoring_runner
from test_compute_gateway import run,spec,receipt
from test_collaboration import _seed_challenge,_rig,_start,_wait,_decision


def test_unknown_after_ten_minutes_frees_slots_but_not_total_or_fee(run,monkeypatch):
    rid,source=run
    from test_compute_budget import _prices
    from cyberscientist import compute_budget
    db.execute('UPDATE authorizations SET max_compute_cost_cny=\'10\' WHERE run_id=?',(rid,))
    _prices(rid)
    monkeypatch.setattr(compute,'_native',lambda *a,**k:receipt('',False))
    compute.submit(rid,'unknown-1',spec(),str(source));compute.submit(rid,'unknown-2',spec(),str(source))
    with pytest.raises(compute.ComputeError,match='并发'):compute.submit(rid,'too-early',spec(),str(source))
    old=(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat()
    db.execute('UPDATE compute_jobs SET unknown_since=?',(old,))
    reserved_before=compute_budget.summary(rid)['committed_estimate_cny']
    assert len(compute.release_unknown_slots())==2
    assert compute_budget.summary(rid)['committed_estimate_cny']==reserved_before
    assert compute.list_jobs(rid)['concurrent_slots_used']==0
    assert not compute.release_unknown_slots()
    compute.submit(rid,'new-operation',spec(),str(source))
    assert db.query_one('SELECT COUNT(*) FROM compute_jobs')[0]==3
    with pytest.raises(compute.ComputeError,match='总数'):compute.submit(rid,'over-total',spec(),str(source))
    settings=config.load_settings();settings['resources']['max_concurrent_jobs']=2;config.save_settings(settings)
    with db.transaction() as conn:resource_coordinator.require_compute_slot_tx(conn,'job')
    assert all(j['status']=='unknown' for j in db.query('SELECT status FROM compute_jobs'))


def test_frozen_copy_and_remote_bootstrap_keep_executable_bits(run,monkeypatch):
    rid,source=run
    binary=source/'public-tool';binary.write_bytes(b'#!/bin/sh\nexit 0\n');binary.chmod(0o755)
    def native(args,**kwargs):
        frozen=config.DATA_DIR/'job-inputs'/'exec-bit'/'input'/'public-tool'
        assert frozen.stat().st_mode & 0o111
        submitted=json.loads((config.DATA_DIR/'job-inputs'/'exec-bit'/'job.json').read_text())
        assert "chmod 0755 -- input/public-tool" in submitted['command']
        return receipt('JobId: 456')
    monkeypatch.setattr(compute,'_native',native)
    assert compute.submit(rid,'exec-bit',spec(),str(source))['status']=='accepted'


def test_preflight_never_becomes_remote_job_state(run):
    rid,_=run
    db.append_event(rid,'controller','job.preflight',{'operation_id':'no-reservation','status':'passed'})
    assert observation.job_states(rid,999)==[]
    db.append_event(rid,'controller','job.reserved',{'operation_id':'real'})
    db.append_event(rid,'controller','job.preflight',{'operation_id':'real','status':'passed'})
    assert observation.job_states(rid,999)[0]['status']=='submitting'
    facts=observation.authority_facts(rid)
    assert facts['authorization']['job_limits']==compute.DEFAULT_LIMITS
    assert facts['operating_facts']['effective_job_limits']==compute.DEFAULT_LIMITS


def test_python310_hash_implementation_does_not_need_file_digest(tmp_path,monkeypatch):
    import hashlib
    path=tmp_path/'public-software';path.write_bytes(b'public fixture')
    monkeypatch.delattr(hashlib,'file_digest')
    assert scoring_runner.digest(path)==hashlib.sha256(b'public fixture').hexdigest()


@pytest.mark.asyncio
async def test_new_trial_waits_for_native_boundary_and_old_events_keep_old_trial():
    _seed_challenge();c,brain,executor=_rig(False)
    rid=c.create_run('COLLAB_CH')['id'];old=await _start(c,brain,rid)
    db.execute("UPDATE trials SET status='reported_complete' WHERE id=?",(old,))
    c._executor_busy[rid]=True
    dec=_decision([{'op':'start_trial','goal':'second route','success_check':'verified output'}],rid=rid)
    dec['observed_state_version']=db.query_one('SELECT state_version FROM runs WHERE id=?',(rid,))[0]
    await c._apply_decision(rid,dec,{'authorization':{}},brain,c._brain_sessions[rid])
    assert db.query_one('SELECT current_trial_id FROM runs WHERE id=?',(rid,))[0]==old
    assert db.query_one('SELECT pending_trial_json FROM runs WHERE id=?',(rid,))[0]
    await c._handle_signal({'type':'prime_event','event':{'type':'execution.progress','detail':'old output','turn_id':'old-turn'}},rid,c._signals[rid])
    c._executor_busy[rid]=False
    await c._on_turn_boundary(rid,{})
    new=db.query_one('SELECT current_trial_id FROM runs WHERE id=?',(rid,))[0]
    assert new!=old
    assert len(executor.prompts)==2
    await c._handle_signal({'type':'prime_event','event':{'type':'executor.turn_completed','turn_id':'old-turn'}},rid,c._signals[rid])
    event=db.events_after(rid,0)[-1]
    assert event['trial_id']==old and c._executor_busy[rid]
    await c.control(rid,'terminate',None,'finish-substrate-fixture')

@pytest.mark.asyncio
async def test_pre_reservation_rejection_reports_no_remote_effect_and_original_operation(run,monkeypatch):
    from httpx import AsyncClient,ASGITransport
    from cyberscientist import api,collab
    rid,source=run
    now=db.utcnow()
    for i in range(2):
        db.execute('INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,spec_json,input_directory,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                   (f'occupied-{i}',rid,'trial_fixture','hash','{}',str(source),'unknown',now,now))
    with db.transaction() as conn:token=collab.issue_token(conn,rid,'executor','fixture-session',1)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://test') as client:
        response=await client.post('/api/v1/tools/job',headers={'Authorization':'Bearer '+token},json={
            'action':'submit','operation_id':'local-rejected','spec':spec(),'input_directory':str(source)})
    assert response.status_code==409
    facts=response.json()['failure_feedback']
    assert facts['possible_remote_effect']=='none' and facts['operation_id']=='local-rejected'
    assert db.query_one('SELECT COUNT(*) FROM compute_jobs')[0]==2
