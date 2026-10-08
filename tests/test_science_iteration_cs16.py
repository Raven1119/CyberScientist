"""Application E2E with fake executor/platform; no remote scientific work."""
import json
from cyberscientist import config,db,mailboxes,method_approval,local_scoring
from cyberscientist.controller import RunController
from cyberscientist.prime import ActionReceipt
from test_mailboxes import _seed_challenge,_make_run,_make_package
from test_method_approval_cs16 import PROPOSAL,body
from test_decision import valid_decision

class Executor:
    prompts=[]
    async def prompt(self,sid,text):
        self.prompts.append((sid,text))
        return ActionReceipt(status='accepted',detail='synthetic compute accepted',operation_id='fixture')

async def test_propose_approve_compute_submit_early_science_iterate_rotate(monkeypatch):
    _seed_challenge();rid=_make_run(max_submissions=4)
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0])
    snapshot['settings']['initial_method_approval']=True
    db.execute("UPDATE runs SET phase='running',gate='open',config_snapshot=? WHERE id=?",(json.dumps(snapshot),rid))
    mailboxes.register_experiment(2)
    ctrl=RunController();executor=Executor();executor.prompts=[]
    ctrl._prime_instances[rid]=executor;ctrl._prime_sessions[rid]='fixture-native'
    decision=valid_decision(run_id=rid,actions=[{'op':'start_trial','goal':'完整计算第一版','success_check':'科学约束与产物契约'}],research_brief={'method_proposal':PROPOSAL,'environment_choice':{'mode':'from_zero','reason_md':'隔离fake'}})
    await ctrl._apply_decision(rid,decision,{},None,None)
    assert not executor.prompts
    await ctrl.decide_method(rid,body())
    state=db.query_one('SELECT * FROM runs WHERE id=?',(rid,))
    decision['observed_state_version']=state['state_version']
    await ctrl._apply_decision(rid,decision,{},None,None)
    trial=db.query_one('SELECT * FROM trials WHERE run_id=?',(rid,))
    assert trial and len(executor.prompts)==1
    # Represents completed remote compute; fixture output is explicitly synthetic.
    _make_package(rid,trial['id'],'{"version":1,"synthetic":true}')
    db.execute("UPDATE trials SET status='done' WHERE id=?",(trial['id'],))
    monkeypatch.setattr(local_scoring,'score_candidate',lambda *a,**k:(_ for _ in ()).throw(AssertionError('local score must not gate submission')))
    first=mailboxes.submit_experiment(rid,trial['id'],None,'science-first')
    assert first['status']=='submitted'
    assert db.query_one('SELECT phase FROM runs WHERE id=?',(rid,))[0]=='running'
    # PI can continue before the receipt is final; no automatic score_wait.
    ctrl._executor_busy[rid]=False
    decision=valid_decision(run_id=rid,observed_state_version=state['state_version'],actions=[{'op':'start_trial','goal':'按科学检查改进完整方法','success_check':'完整重算'}])
    await ctrl._apply_decision(rid,decision,{},None,None)
    second_trial=db.query_one('SELECT current_trial_id FROM runs WHERE id=?',(rid,))[0]
    assert second_trial!=trial['id'] and len(executor.prompts)==2
    with db.transaction() as conn:
        mailboxes._record_feedback(conn,conn.execute('SELECT * FROM submissions WHERE id=?',(first['id'],)).fetchone(),'attempt',{'scoringState':{'scoreIsFinal':False},'scorecard':{'harbor_score':75}})
    assert db.query_one("SELECT 1 FROM review_requests WHERE run_id=? AND trigger='submission_feedback' AND status='pending'",(rid,))
    assert db.query_one('SELECT trace_score FROM submissions WHERE id=?',(first['id'],))[0] is None
    _make_package(rid,second_trial,'{"version":2,"synthetic":true}')
    second=mailboxes.submit_experiment(rid,second_trial,None,'science-improved')
    assert second['status']=='submitted' and second['mailbox_id']!=first['mailbox_id']
    assert method_approval.state(rid)['version']==1
