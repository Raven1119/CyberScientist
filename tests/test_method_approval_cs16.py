"""Initial approval is a durable compute boundary, independent from model speed."""
import json
import uuid
import pytest
from cyberscientist import config, db, method_approval, alerts, planning
from cyberscientist.controller import RunController
from test_controller import _seed_challenge
from test_decision import valid_decision

PROPOSAL = dict(method_md='完整方法', parameters_md='题面约束', basis_md='文献依据',
                outputs_md='契约产物', capabilities=['bohrium-job'])

def seed(enabled=True):
    _seed_challenge()
    settings=config.load_settings();settings['initial_method_approval']=enabled;config.save_settings(settings)
    ctrl=RunController();rid=ctrl.create_run('DEMO_CHALLENGE')['id']
    db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?",(rid,))
    decision=valid_decision(run_id=rid,actions=[{'op':'start_trial','goal':'完整计算','success_check':'题面契约'}],research_brief={'method_proposal':PROPOSAL,'environment_choice':{'mode':'from_zero','reason_md':'受控测试'}})
    return ctrl,rid,decision

def body(action='approve',actor='user',text='',version=1):
    return dict(action=action,actor=actor,text=text,version=version,operation_id=str(uuid.uuid4()))

async def test_proposal_closes_compute_gate_without_delivering_executor_work():
    ctrl,rid,decision=seed()
    await ctrl._apply_decision(rid,decision,{},None,None)
    assert db.query_one('SELECT gate FROM runs WHERE id=?',(rid,))[0]=='awaiting_method_approval'
    assert not db.query('SELECT * FROM trials WHERE run_id=?',(rid,))
    assert method_approval.state(rid)['proposal']==PROPOSAL

async def test_wait_is_not_stall_and_does_not_schedule_shadow_or_alert():
    ctrl,rid,decision=seed();method_approval.hold(rid,decision,{})
    before=len(db.events_after(rid,0))
    ctrl.check_liveness(rid)
    ctrl._maybe_shadow(rid);alerts.synchronize()
    assert len(db.events_after(rid,0))==before
    assert not db.query('SELECT * FROM alerts WHERE run_id=?',(rid,))
    assert not db.query('SELECT * FROM review_requests WHERE run_id=?',(rid,))

@pytest.mark.parametrize('action,actor,text',[('approve','user',''),('modify','monitor','保留题面全部参数'),('reject','user','请核查方法依据')])
async def test_decision_audited_and_pi_wake_is_durable_and_idempotent(action,actor,text):
    ctrl,rid,decision=seed();method_approval.hold(rid,decision,{})
    request=body(action,actor,text);state=await ctrl.decide_method(rid,request)
    assert state['status']==('awaiting_revision' if action=='reject' else 'approved')
    assert db.query_one('SELECT actor FROM method_approval_actions')[0]==actor
    queued=db.query_one('SELECT * FROM review_requests WHERE run_id=?',(rid,))
    assert queued and queued['source']=='lifecycle'
    assert text in json.loads(queued['frame_json'])['user_guidance']
    assert (await ctrl.decide_method(rid,request))['deduplicated']
    assert len(db.query('SELECT * FROM review_requests WHERE run_id=?',(rid,)))==1
    if action!='reject':
        assert state['approved_at'] and state['approved_by']==actor
        assert not method_approval.hold(rid,decision,{})
    else:
        assert method_approval.hold(rid,decision,{})
        with pytest.raises(ValueError,match='版本'):
            method_approval.decide(rid,body(version=1))

async def test_switch_off_bypasses_only_initial_approval():
    _,rid,decision=seed(False)
    assert not method_approval.hold(rid,decision,{})
    assert db.query_one('SELECT gate FROM runs WHERE id=?',(rid,))[0]=='open'

async def test_incomplete_proposal_cannot_be_approved_and_can_be_rejected():
    _,rid,decision=seed();decision['research_brief']['method_proposal']={}
    assert method_approval.hold(rid,decision,{})
    with pytest.raises(ValueError,match='未完整'):
        method_approval.decide(rid,body())
    method_approval.decide(rid,body('reject',text='请补所需能力'))

async def test_major_change_is_visible_and_nonblocking():
    _,rid,_=seed();planning.record_brief(rid,{'major_change':True,'major_change_reason_md':'更换理论方法','environment_choice':{'mode':'from_zero','reason_md':'受控测试'}},'change')
    alerts.synchronize()
    assert db.query_one("SELECT kind FROM alerts WHERE run_id=?",(rid,))[0]=='method.major_change'
    assert db.query_one('SELECT gate FROM runs WHERE id=?',(rid,))[0]=='open'
