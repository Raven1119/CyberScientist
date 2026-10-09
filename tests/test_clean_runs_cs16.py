import hashlib,io,json,zipfile
import pytest
from cyberscientist import config,db,clean_runs,package_seal
from cyberscientist.controller import RunController
from cyberscientist.prime import ActionReceipt
from test_mailboxes import _seed_challenge,_make_run
from test_decision import valid_decision
from test_trace_narrative import _zip

HANDOFF={'method_md':'按题面完整方法重算','parameters_md':'固定题面参数','validation_md':'独立核查方法与字段','pitfalls_md':'核查单位与边界'}

async def test_fresh_thread_waits_idle_preserves_old_log_and_seals_only_new(tmp_path,monkeypatch):
    _seed_challenge();rid=_make_run();db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?",(rid,))
    old=tmp_path/'old.jsonl';old.write_text(json.dumps({'type':'session_meta','payload':{'id':'old-thread'}})+'\n')
    original=old.read_bytes();new=tmp_path/'new.jsonl'
    specs=[];prompts=[]
    class Native:
        async def close(self,sid):assert sid=='old-thread'
        async def start(self,spec):
            specs.append(spec);assert 'resume_thread_id' not in spec
            from pathlib import Path
            assert Path(spec['working_directory']).parent.name == 'trials'
            assert list(Path(spec['working_directory']).iterdir()) == []
            new.write_text(json.dumps({'type':'session_meta','payload':{'id':'new-thread'}})+'\n')
            db.append_event(rid,'controller','session.configuration',{'role':'executor','session_id':'new-thread','native_log_path':str(new),'model':'fixture-model'})
            return 'new-thread'
        async def prompt(self,sid,text):
            from pathlib import Path
            assert list(Path(specs[-1]['working_directory']).iterdir()) == []
            prompts.append((sid,text));return ActionReceipt(status='accepted',detail='fixture')
    ctrl=RunController();ctrl._prime_instances[rid]=Native();ctrl._prime_sessions[rid]='old-thread'
    monkeypatch.setattr(ctrl,'_make_prime',lambda settings:Native())
    action={'op':'start_trial','goal':'must not leak exploration-result=987654','success_check':'complete','fresh_executor_session':True,'clean_handoff':HANDOFF}
    decision=valid_decision(run_id=rid,actions=[action])
    ctrl._executor_busy[rid]=True
    await ctrl._apply_decision(rid,decision,{},None,None)
    assert not specs and not db.query('SELECT * FROM trials WHERE run_id=?',(rid,))
    ctrl._executor_busy[rid]=False
    await ctrl._apply_decision(rid,decision,{},None,None)
    trial=db.query_one('SELECT * FROM trials WHERE run_id=?',(rid,))
    binding=json.loads(db.query_one("SELECT payload FROM events WHERE trial_id=? AND type='trial.native_session_bound'",(trial['id'],))[0])
    assert binding['session_id']=='new-thread' and old.read_bytes()==original
    assert prompts[0][0]=='new-thread' and '方法来自本方此前的探索' in prompts[0][1]
    text = prompts[0][1]
    assert all(item in text for item in (rid, trial['id'], specs[0]['working_directory'], 'result_package.zip', '真实原生轨迹由系统绑定，禁止编造', 'stage=trial_complete', '环境索引'))
    assert text.index('流程（method_md）') < text.index('参数（parameters_md）') < text.index('验证（validation_md）') < text.index('故障（pitfalls_md）')
    assert clean_runs.PARAMETER_POLICY in text
    assert ctrl._prime_spec(rid, config.load_settings())['working_directory'] == specs[0]['working_directory']
    db.execute("DELETE FROM events WHERE run_id=? AND type='trial.clean_run'", (rid,))
    db.execute('UPDATE runs SET current_trial_id=NULL WHERE id=?', (rid,))
    assert ctrl._prime_spec(rid, config.load_settings())['working_directory'] == specs[0]['working_directory']
    assert '987654' not in prompts[0][1] and '本地科学Python' not in prompts[0][1]
    source=_zip({'arm_manifest.json':b'{"trace_path":"trace.jsonl"}', 'trace.jsonl':b'{"step_type":"observation","title":"synthetic"}\n'})
    sealed,_=package_seal.seal(source,rid,trial['id'],0)
    with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
        assert archive.read('raw_messages.jsonl')==new.read_bytes()
        assert json.loads(archive.read('provenance/native_session.json'))['session_id']=='new-thread'
    assert old.read_bytes()==original

@pytest.mark.parametrize('handoff',[{},HANDOFF|{'code':'x'},HANDOFF|{'method_md':'```python\nprint(1)\n```'}, {k:v for k,v in HANDOFF.items() if k != 'validation_md'}, HANDOFF|{'validation_md':' '}, HANDOFF|{'validation_md':'x'*12001}])
def test_invalid_handoff_is_not_delivered(handoff):
    with pytest.raises(ValueError):clean_runs.validate(handoff)

def test_policy_default_and_no_score_no_automatic_clean_run():
    _seed_challenge();rid=_make_run()
    assert config.DEFAULT_SETTINGS['clean_run_policy']=='when_not_accepted'
    assert not clean_runs.should_offer(rid)

async def test_unknown_old_close_retains_handle_and_prevents_new_trial(monkeypatch):
    _seed_challenge();rid=_make_run();db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?",(rid,))
    class Old:
        async def close(self,sid):raise RuntimeError('synthetic close unknown')
    old=Old();ctrl=RunController();ctrl._prime_instances[rid]=old;ctrl._prime_sessions[rid]='old'
    monkeypatch.setattr(ctrl,'_make_prime',lambda settings:(_ for _ in ()).throw(AssertionError('must not start')))
    action={'op':'start_trial','goal':'fresh','success_check':'complete','fresh_executor_session':True,'clean_handoff':HANDOFF}
    await ctrl._apply_decision(rid,valid_decision(run_id=rid,actions=[action]),{},None,None)
    assert ctrl._prime_instances[rid] is old and ctrl._prime_sessions[rid]=='old'
    assert not db.query('SELECT * FROM trials WHERE run_id=?',(rid,))
    assert db.query_one('SELECT 1 FROM system_state WHERE key=?',('native_close_unknown:'+rid,))


async def test_confirmed_close_and_failed_fresh_start_cannot_leave_running_stale_handle(monkeypatch):
    _seed_challenge(); rid = _make_run()
    db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?", (rid,))
    class Old:
        async def close(self, sid):
            return None
    class Failed:
        async def start(self, spec):
            raise RuntimeError('fixture native start unavailable')
    controller = RunController()
    controller._prime_instances[rid] = Old(); controller._prime_sessions[rid] = 'old'
    monkeypatch.setattr(controller, '_make_prime', lambda settings: Failed())
    action = {'op': 'start_trial', 'goal': 'fresh', 'success_check': 'complete',
              'fresh_executor_session': True, 'clean_handoff': HANDOFF}
    await controller._apply_decision(rid, valid_decision(run_id=rid, actions=[action]), {}, None, None)
    assert rid not in controller._prime_instances and rid not in controller._prime_sessions
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] != 'running'
    assert not db.query('SELECT * FROM trials WHERE run_id=?', (rid,))
