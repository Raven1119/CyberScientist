import json,uuid
import pytest
from cyberscientist import competition_panel as panel,config,db,mailboxes,submission_gate
from cyberscientist.controller import RunController
from test_mailboxes import _seed_challenge,_make_run,_make_package

def change(rid,action,value):return panel.change(rid,dict(action=action,value=value,operation_id=str(uuid.uuid4())))

def test_hold_survives_restart_and_only_blocks_submission():
    _seed_challenge();rid=_make_run();_make_package(rid);mailboxes.register_experiment(1)
    change(rid,'submission_hold',True)
    sub=mailboxes.submit_experiment(rid,'trial_mb1',None,'held')
    assert sub['status']=='queued' and submission_gate.items()[0]['reason']=='本题暂缓提交'
    db.init_db();submission_gate.advance_sync()
    assert db.query_one('SELECT status FROM submissions WHERE id=?',(sub['id'],))[0]=='queued'
    assert db.query_one('SELECT phase FROM runs WHERE id=?',(rid,))[0] in ('created','running')
    change(rid,'submission_hold',False);submission_gate.advance_sync()
    assert db.query_one('SELECT status FROM submissions WHERE id=?',(sub['id'],))[0]=='submitted'

def test_model_override_does_not_rewrite_frozen_snapshot():
    _seed_challenge();rid=_make_run();before=db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0]
    choice={'runtime':'codex','model_id':'gpt-5.6-terra','reasoning_effort':'xhigh','provider':'codex','fast_mode':True}
    change(rid,'executor',choice)
    assert RunController()._runtime_settings(rid)['executor']['model_id']=='gpt-5.6-terra'
    assert db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0]==before
    assert db.query_one("SELECT COUNT(*) FROM events WHERE run_id=? AND type='panel.executor'",(rid,))[0]==1

def test_account_preference_keeps_same_hash_and_rotation_constraints():
    _seed_challenge();rid=_make_run();_make_package(rid);accounts=mailboxes.register_experiment(2)['items']
    change(rid,'mailbox',accounts[1]['id']);first=mailboxes.submit_experiment(rid,'trial_mb1',None,'first')
    assert first['mailbox_id']==accounts[1]['id']
    _make_package(rid,'second','{"complete":2}');second=mailboxes.submit_experiment(rid,'second',None,'second')
    assert second['mailbox_id']!=first['mailbox_id']
    same=mailboxes.submit_experiment(rid,'trial_mb1',None,'same')
    assert same['mailbox_id']==first['mailbox_id']

def test_panel_preserves_unknown_and_repair_idempotence():
    _seed_challenge();rid=_make_run()
    row=panel.view()['items'][0];assert row['receipt'] is None and row['scoring_seconds'] is None
    request={'operation_id':'repair','run_id':rid,'text':'已核对运行边界，没有重放未知提交。'}
    panel.record_repair(request);panel.record_repair(request)
    assert len(panel.view()['repairs'])==1
    with pytest.raises(ValueError):panel.record_repair(request|{'text':'changed'})
    request={'operation_id':'same','action':'submission_hold','value':True}
    panel.change(rid,request);assert panel.change(rid,request)['deduplicated']
    with pytest.raises(ValueError):panel.change(rid,request|{'value':False})


def test_panel_method_tracks_latest_brief_and_policy_uses_best_science():
    from cyberscientist import planning,clean_runs
    _seed_challenge();rid=_make_run();_make_package(rid);mailboxes.register_experiment(1)
    planning.record_brief(rid,{'science_md':'自主改进后的当前方法','environment_choice':{'mode':'from_zero','reason_md':'fixture'}},'new-method')
    sub=mailboxes.submit_experiment(rid,'trial_mb1',None,'accepted')
    db.execute("UPDATE submissions SET harbor_score=100,trace_decision='accept' WHERE id=?",(sub['id'],))
    assert panel.view()['items'][0]['method_summary']=='自主改进后的当前方法'
    assert not clean_runs.offer(rid)['recommended']
    settings=config.load_settings();settings['clean_run_policy']='always_after_science';config.save_settings(settings)
    row=panel.view()['items'][0]
    assert row['clean_run']['recommended'] and row['clean_run']['best_science']['id']==sub['id']
    assert row['clean_run']['automatic_execution'] is False


def test_submission_model_uses_bound_trial_not_next_model_or_original_snapshot():
    _seed_challenge();rid=_make_run()
    db.append_event(rid,'controller','trial.native_session_bound',{'role':'executor','session_id':'actual','model':'gpt-6-astra','provider':'codex'},trial_id='submitted-trial')
    change(rid,'executor',{'runtime':'codex','provider':'codex','model_id':'gpt-5.6-terra','reasoning_effort':'xhigh','fast_mode':True})
    assert mailboxes._submission_metadata(rid,'submitted-trial')['model']=='gpt-6-astra'
