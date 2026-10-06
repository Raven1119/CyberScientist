"""Direct regressions for defects recorded in four frozen private reviews."""
import pytest
import json
from cyberscientist import job_preflight,db,collab,experience_context
from cyberscientist.controller import RunController,_objective_evidence_exists
from test_collaboration import _seed_challenge,_cp_msg,_rig,_start,_wait


def reviewed(proposal):
    from cyberscientist import review_policy
    return {**proposal,'review':{'classification':'operation',
        'decision_sha256':review_policy.decisions()['sha256'],'conflicts':[],
        'counterfactual_md':'保留已确认结果并换已授权路径，可避免失去已有科学分；提升为假设。',
        'score_bands_md':'fixture未提供科学分档，unknown',
        'leaderboard_md':'fixture无真实榜首，unknown','known_results_md':'只以本次冻结事件为已知结果'}}


def test_maintenance_excludes_developer_findings_missing_analysis_and_design_conflicts():
    from cyberscientist import review_policy
    from test_collaboration import _proposal
    safe=reviewed(_proposal('global','保留记录后换新操作'))
    conflict=reviewed(_proposal('global','unknown绝不重发'))
    declared=reviewed(_proposal('global','暂停等人'));declared['review']['conflicts']=['D-28','D-33']
    developer=reviewed(_proposal('global','修复控制器'));developer['review']['classification']='developer_defect'
    missing=_proposal('global','没有比较')
    old=reviewed(_proposal('global','旧决定'));old['review']['decision_sha256']='0'*64
    accepted,excluded=review_policy.split([safe,conflict,declared,developer,missing,old])
    assert len(accepted)==1 and 'review' not in accepted[0] and '反事实得分分析' in accepted[0]['body_md']
    assert len(excluded)==5 and excluded[0]['proposal']==conflict
    assert all(item['reasons'] for item in excluded)
    assert len(review_policy.decisions()['text'].splitlines())==38


@pytest.mark.parametrize('text',['对 unknown 只能按原 operation_id 只读对账，不能重发',
                               'unknown 绝不重发','不确定就停',
                               'unknown绝不重发；10分钟后不得提交新操作'])
@pytest.mark.parametrize('field',['body_md','counterfactual_md','score_bands_md','leaderboard_md','known_results_md'])
def test_real_old_conflict_cannot_enter_via_analysis_fields(text,field):
    from cyberscientist import review_policy
    from test_collaboration import _proposal
    proposal=reviewed(_proposal('global','科研建议'))
    if field=='body_md':proposal[field]=text
    else:proposal['review'][field]=text
    accepted,excluded=review_policy.split([proposal])
    assert not accepted and excluded


async def test_global_curation_uses_same_policy_and_keeps_exclusions(monkeypatch):
    from cyberscientist.brains.base import BrainEvent,SessionRef
    from cyberscientist import review_policy
    from test_collaboration import _proposal
    ctl=RunController()
    safe=reviewed(_proposal('global','保留保底科学分'))
    defect=reviewed(_proposal('global','代码缺陷'));defect['review']['classification']='developer_defect'
    class Brain:
        async def open(self,spec):return SessionRef('fixture','global')
        async def close(self,session):pass
        async def review(self,session,packet):
            assert packet['design_decisions']==review_policy.decisions()
            yield BrainEvent('curation_result',{'result':{'schema_version':1,'message_type':'curation_result',
                'summary':'fixture','experience_proposals':[safe,defect]}})
    monkeypatch.setattr(ctl,'_make_brain',lambda _:Brain())
    await ctl._run_global_curation([])
    state=ctl.global_curation_status()
    assert state['state']=='done' and state['proposals_applied']==1
    assert state['excluded_lessons'][0]['proposal']==defect


def test_same_unknown_operation_guard_with_explicit_d31_new_operation_is_retained():
    from cyberscientist import review_policy
    from test_collaboration import _proposal
    proposal=reviewed(_proposal('global','有界对账后继续',
        'unknown时不得盲目重发原operation_id；超过10分钟可以用新operation_id在原授权继续'))
    accepted,excluded=review_policy.split([proposal])
    assert len(accepted)==1 and not excluded


def test_explicitly_rejected_quote_is_not_promoted_but_direct_quoted_instruction_is_excluded():
    from cyberscientist import review_policy
    from test_collaboration import _proposal
    good=reviewed(_proposal('global','按D31换新操作',
        '相反表述“unknown 绝不重发”按 D-61 只作冲突报告；'
        '被观察到的“unknown 绝不重发/不确定就停”才是冲突版本。'))
    bad=reviewed(_proposal('global','盲目停止','应该原样照做：“unknown绝不重发/不确定就停”。'))
    accepted,excluded=review_policy.split([good,bad])
    assert len(accepted)==1 and len(excluded)==1 and excluded[0]['proposal']==bad


@pytest.mark.parametrize('field',['counterfactual_md','score_bands_md','leaderboard_md','known_results_md'])
def test_valid_same_operation_rule_does_not_hide_later_analysis_conflict(field):
    from cyberscientist import review_policy
    from test_collaboration import _proposal
    proposal=reviewed(_proposal('global','规则核对',
        'unknown时不得重发原operation_id；10分钟可以用新operation_id'))
    proposal['review'][field]='unknown绝不重发'
    accepted,excluded=review_policy.split([proposal])
    assert not accepted and excluded and any('D-31' in reason for reason in excluded[0]['reasons'])


def test_completed_review_cannot_teach_executor_to_rewrite_controller_ledger_or_trace():
    from cyberscientist import review_policy
    from test_collaboration import _proposal
    proposal=reviewed(_proposal('global','修改系统记录',
        '到点换通道，并把原预留标记为不再占新名额。每次对账只保留一条结论。'))
    accepted,excluded=review_policy.split([proposal])
    assert not accepted and any('开发者队列' in reason for reason in excluded[0]['reasons'])


def test_large_trace_keeps_design_and_counterfactual_instructions():
    from cyberscientist import maintenance,review_policy
    _seed_challenge();ctl=RunController();rid=ctl.create_run('COLLAB_CH')['id']
    db.append_event(rid,'controller','job.unknown',{'output':'可核验全文'*200000})
    packet=maintenance.snapshot(ctl,rid);small,chunks=maintenance.native_materials(packet)
    assert chunks and review_policy.INSTRUCTION in small['instruction']
    assert small['design_decisions']==packet['design_decisions']


def test_old_frozen_packet_uses_current_review_contract_without_changing_trace_or_snapshot():
    from cyberscientist import maintenance,review_policy
    _seed_challenge();ctl=RunController();rid=ctl.create_run('COLLAB_CH')['id']
    packet=maintenance.snapshot(ctl,rid);packet.pop('design_decisions')
    packet['instruction']='old frozen instruction'
    packet['output_contract']['properties']['strategy_lessons']['items']['properties'].pop('review')
    packet['output_contract']['properties']['strategy_lessons']['items']['required'].remove('review')
    original=json.dumps(packet,sort_keys=True)
    material,chunks=maintenance.native_materials(packet)
    assert not chunks and material['full_public_trace_jsonl']==packet['full_public_trace_jsonl']
    assert json.dumps(packet,sort_keys=True)==original
    assert 'review' in material['output_contract']['properties']['strategy_lessons']['items']['required']
    assert material['design_decisions']==review_policy.decisions()


@pytest.mark.parametrize('command',[
    'python3 -I -c "print(1)"','python3 -Ic "print(1)"',
    '/opt/csenv/bin/python3 -B -I -c "print(1)"',
    'python3 -W ignore -X utf8 -c "print(1)"','python3 -I -m package.module',
    'bash -lc \'python3 -I -c "print(1)"\'',
])
def test_python_interpreter_options_are_never_entry_files(command):
    assert job_preflight.check_sources({},command)['entry'] is None


def test_explicit_inline_entry_still_checks_packaged_source():
    assert job_preflight.check_sources({'work.py':b'import math\n'},'python3 -I -c "..."',entry='work.py')['entry']=='work.py'
    with pytest.raises(job_preflight.PreflightError,match='未打包'):
        job_preflight.check_sources({},'python3 -I -c "..."',entry='work.py')
    assert job_preflight.check_sources({'pkg/work.py':b'import math\n'},'cd pkg && python3 -I work.py')['entry']=='pkg/work.py'
    assert job_preflight.check_sources({'work.py':b'import math\n'},'python3 --check-hash-based-pycs always work.py')['entry']=='work.py'


def test_remote_requirements_import_name_does_not_depend_on_local_install(monkeypatch):
    monkeypatch.setattr(job_preflight.importlib.util,'find_spec',lambda _:None)
    report=job_preflight.check_sources({'work.py':b'import PIL\nimport sklearn\n',
        'requirements.txt':b'Pillow==11.2.1\nscikit-learn==1.6.1\n'},'python3 -I work.py')
    assert report['third_party']==['PIL','sklearn']


def test_registered_score_and_completed_review_refs_are_run_owned():
    _seed_challenge();ctl=RunController();rid=ctl.create_run('COLLAB_CH')['id']
    other=ctl.create_run('COLLAB_CH')['id'];now=db.utcnow()
    db.execute('INSERT INTO local_scores(id,challenge_id,run_id,trial_id,science_score,package_sha256,'
        'science_artifact_hashes_json,manifest_science_sha256,trace_prediction_json,scorer_version,scorer_file_hashes_json,feature_version,model_version,created_at)'
        ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        ('ls_real','COLLAB_CH',rid,'trial',20,'hash','{}','hash','{}','version','{}','fixture','fixture',now))
    db.execute('INSERT INTO package_reviews VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        ('pi_review',rid,'trial','source','sealed','done','{}','{}',None,now,now))
    for ref in ('local_score:ls_real','package_review:pi_review','pi_review'):
        assert _objective_evidence_exists(rid,ref)
        assert not _objective_evidence_exists(other,ref)
    for ref in ('local_score:missing','package_review:missing'):
        assert not _objective_evidence_exists(rid,ref)
    db.execute("UPDATE package_reviews SET status='unknown'")
    assert not _objective_evidence_exists(rid,'pi_review')


def test_bad_adoption_does_not_discard_research_checkpoint_or_replay_warning():
    _seed_challenge();ctl=RunController();rid=ctl.create_run('COLLAB_CH')['id']
    db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?",(rid,))
    msg=_cp_msg('research-preserved');msg['report_md']='真实研究正文保留'
    msg['experience_uses']=[{'context_id':'missing','experience_id':'missing','revision_id':'missing'}]
    # Use the exact installed schema fields; invalid version remains rejected.
    from cyberscientist import collab
    result=collab.submit_checkpoint(rid,msg,source='executor')
    assert len(result['experience_adoption_rejections'])==1
    assert db.query_one('SELECT report FROM checkpoints WHERE id=?',(result['checkpoint_id'],))[0]=='真实研究正文保留'
    assert not db.query('SELECT * FROM experience_uses')
    assert collab.submit_checkpoint(rid,msg,source='executor')['experience_adoption_rejections']==result['experience_adoption_rejections']
    assert len(db.query("SELECT * FROM events WHERE type='experience.adoption_rejected'"))==1


def test_mixed_adoption_keeps_delivered_version_and_rejects_only_bad_item():
    from test_experience_delivery import entry
    _seed_challenge();entry('recipe','真实配方','操作方法')
    ctl=RunController();rid=ctl.create_run('COLLAB_CH')['id'];tid='active-trial'
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,created_at) VALUES(?,?,?,?,?)',
               (tid,rid,'goal','check',db.utcnow()))
    db.execute("UPDATE runs SET phase='running',gate='open',current_trial_id=? WHERE id=?",(tid,rid))
    context=experience_context.freeze(rid,tid,'delivered',role='executor')
    good={'context_id':context['id'],'experience_id':'recipe','revision_id':context['items'][0]['revision_id']}
    msg=_cp_msg('mixed-adoption');msg['experience_uses']=[good,{**good,'revision_id':'not-delivered'}]
    result=collab.submit_checkpoint(rid,msg,source='executor')
    assert len(result['experience_adoption_rejections'])==1
    uses=db.query('SELECT * FROM experience_uses WHERE run_id=?',(rid,))
    assert len(uses)==1 and uses[0]['revision_id']==good['revision_id']
    assert db.query_one('SELECT report FROM checkpoints WHERE id=?',(result['checkpoint_id'],))[0]==msg['report_md']


@pytest.mark.parametrize('abort_status',['accepted','unknown'])
@pytest.mark.parametrize('close_fails',[False,True])
async def test_manual_executor_pause_without_terminal_event_settles_by_native_close(monkeypatch,abort_status,close_fails):
    from cyberscientist.prime import ActionReceipt
    from cyberscientist.controller import ControllerError
    _seed_challenge();ctl,brain,executor=_rig(shadow=False)
    rid=ctl.create_run('COLLAB_CH')['id'];await _start(ctl,brain,rid)
    closed=[]
    async def abort(_):return ActionReceipt(status=abort_status,detail='no terminal event')
    async def close(session):
        closed.append(session)
        if close_fails:raise TimeoutError('close unknown')
    monkeypatch.setattr(executor,'abort',abort);monkeypatch.setattr(executor,'close',close)
    await ctl.control(rid,'pause',None,'manual-pause')
    if close_fails:
        assert await _wait(lambda:db.query_one("SELECT 1 FROM system_state WHERE key=?",('native_close_unknown:executor-pause:'+rid,)))
        assert ctl.run_snapshot(rid)['phase']=='pausing'
        with pytest.raises(ControllerError,match='停止仍在核对'):
            await ctl.control(rid,'resume',None,'unsafe-resume')
    else:
        assert await _wait(lambda:ctl.run_snapshot(rid)['phase']=='paused')
        assert closed and ctl._prime_instances[rid] is None
        assert not db.query_one('SELECT * FROM run_post_reviews WHERE run_id=?',(rid,))


@pytest.mark.parametrize('second_close_fails',[False,True])
async def test_failed_pause_close_then_late_boundary_retries_close_and_resumes_same_native_thread(monkeypatch,second_close_fails):
    import asyncio
    from cyberscientist.prime import ActionReceipt
    from cyberscientist.prime.codex_exec import CodexExecutor
    from test_codex_runtime import FakeRpc
    _seed_challenge();ctl,brain,executor=_rig(shadow=False)
    rid=ctl.create_run('COLLAB_CH')['id'];tid=await _start(ctl,brain,rid)
    original_sid=ctl._prime_sessions[rid];attempts=[];allow_close=False
    async def abort(_):return ActionReceipt(status='confirmed' if attempts else 'accepted',detail='interrupt/idle')
    async def close(session):
        attempts.append(session)
        if not allow_close or (second_close_fails and len(attempts)==2):raise TimeoutError('close still unknown')
    monkeypatch.setattr(executor,'abort',abort);monkeypatch.setattr(executor,'close',close)
    await ctl.control(rid,'pause',None,'pause-then-recover')
    key='native_close_unknown:executor-pause:'+rid
    assert await _wait(lambda:db.query_one('SELECT 1 FROM system_state WHERE key=?',(key,)))
    allow_close=True
    await ctl._signals[rid].put({'type':'prime_event','event':{'type':'executor.turn_completed','trial_id':tid}})
    if second_close_fails:
        assert await _wait(lambda:len(attempts)==2)
        assert ctl.run_snapshot(rid)['phase']=='pausing'
        assert db.query_one('SELECT 1 FROM system_state WHERE key=?',(key,))
        await ctl._signals[rid].put({'type':'native_pause_check'})
    assert await _wait(lambda:ctl.run_snapshot(rid)['phase']=='paused')
    assert len(attempts)==(3 if second_close_fails else 2) and not db.query_one('SELECT 1 FROM system_state WHERE key=?',(key,))
    calls=[]
    class ResumeRpc(FakeRpc):
        async def request(self,method,params=None,**kwargs):
            calls.append((method,params))
            if method=='thread/resume':
                assert params['threadId']==original_sid
                return {'thread':{'id':original_sid},'model':params['model'],
                        'reasoningEffort':params['config']['model_reasoning_effort']}
            if method=='turn/start':return {'turn':{'id':'continued-turn'}}
            return await super().request(method,params,**kwargs)
    monkeypatch.setattr('cyberscientist.prime.codex_exec.JsonRpcStdio',ResumeRpc)
    monkeypatch.setattr(ctl,'_make_prime',lambda _:CodexExecutor('/bin/true','gpt-6.1-sol','xhigh'))
    await ctl.control(rid,'resume',None,'resume-original-thread')
    assert await _wait(lambda:any(method=='turn/start' for method,params in calls))
    assert any(method=='thread/resume' for method,params in calls)
    assert not any(method=='thread/start' for method,params in calls)
    assert ctl._require_run(rid)['executor_thread_id']==original_sid
    assert ctl._require_run(rid)['current_trial_id']==tid
    assert db.query_one('SELECT COUNT(*) FROM trials WHERE run_id=?',(rid,))[0]==1
    await ctl.control(rid,'terminate',None,'stop-regression')


def test_deleted_sandbox_can_register_prior_verified_execution_without_recreating(monkeypatch):
    from test_executor_scoring import _setup,_execute
    from cyberscientist import executor_scoring,local_scoring
    rid,tid,sid,prepared,output=_setup(monkeypatch)
    _execute(monkeypatch,rid,sid,prepared['command'],output)
    db.execute("UPDATE compute_sandboxes SET status='deleted' WHERE sandbox_id=?",(sid,))
    monkeypatch.setattr('cyberscientist.compute._native',lambda *a,**k:pytest.fail('no new remote call'))
    result=executor_scoring.register(rid,tid,'executor-candidate','executor-grading-execution')
    assert result['science_score']==64.79 and result['score_source']=='executor_verified'
    assert executor_scoring.register(rid,tid,'executor-candidate','executor-grading-execution')['deduplicated']


def test_archive_copy_of_answer_is_visible_duplicate_and_never_auto_deleted():
    from test_trace_narrative import _fixture,_zip
    from test_local_scoring import _scorer
    from cyberscientist import local_scoring,artifact_contracts
    rid,tid,_,files,*rest=_fixture();scorer=_scorer();path=scorer/'scorer.json'
    descriptor=json.loads(path.read_text());descriptor['input_contract']={'artifact_paths':['answer.txt'],
        'required':True,'verification':'synthetic declared path'};path.write_text(json.dumps(descriptor))
    files.update({'answer.txt':b'current','archive/answer.txt':b'historical'})
    sealed=_zip(files);report=artifact_contracts.inspect('MB_CH',sealed)
    assert report['duplicate']==['answer.txt'] and report['status']=='mismatch'
    assert 'archive/answer.txt' in report['package_paths']
    with pytest.raises(local_scoring.LocalScoreError,match='重复'):
        artifact_contracts.require_supported('MB_CH',sealed)
    assert _zip(files)==sealed


def test_checkpoint_unknown_fields_do_not_relax_strict_tool_contract():
    from cyberscientist.collab import CollabError
    _seed_challenge();ctl=RunController();rid=ctl.create_run('COLLAB_CH')['id']
    message=_cp_msg('extra-fields');message.update({key:'extra' for key in
        ('quality_score','trace_score','next_action','sandbox_id','platform_status')})
    with pytest.raises(CollabError,match='契约校验'):collab.submit_checkpoint(rid,message,source='executor')
    assert not db.query('SELECT * FROM checkpoints')
