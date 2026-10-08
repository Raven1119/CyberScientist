"""A synthetic research fixture executes only a seconds-long local calculation."""
import asyncio
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

from cyberscientist import arm_admission, config, db, package_seal
from cyberscientist.controller import RunController
from test_compute_gateway import run
from test_collaboration import FakeExecutor, _decision
from test_ev_upgrade import _protocol


def test_native_local_result_has_real_command_output_and_passes_seal_and_admission(run):
    rid, source = run
    code = '''from pathlib import Path
import numpy as np
from scipy.linalg import det
import sympy as sp
answer = int(np.sum([20,22]))
assert det(np.eye(2)) == 1 and sp.simplify(sp.Symbol('x')-sp.Symbol('x')+answer) == 42
text = 'CS_LOCAL_SECONDS answer=42 det=1 symbolic=42'
Path('answer.txt').write_text(text+'\\n')
print(text)
'''
    (source / 'work.py').write_text(code)
    command = [sys.executable, 'work.py']; controller = RunController()
    asyncio.run(controller._handle_signal({'type':'prime_event','event':{'type':'execution.progress','item_id':'local-seconds','status':'started','detail':str(command)}}, rid, asyncio.Queue()))
    started=time.monotonic()
    result=subprocess.run(command,cwd=source,capture_output=True,text=True,timeout=10)
    elapsed=time.monotonic()-started
    assert result.returncode == 0 and elapsed < 10
    asyncio.run(controller._handle_signal({'type':'prime_event','event':{'type':'execution.progress','item_id':'local-seconds','status':'completed','detail':str(command),'output':result.stdout,'exit_code':result.returncode,'elapsed_seconds':elapsed}}, rid, asyncio.Queue()))
    files = {'arm_manifest.json':json.dumps({'arm_version':'1.1','entrypoint':'work.py','trace':'trace.jsonl','execution':{'log_path':'run.log','artifacts':[{'id':'answer','path':'answer.txt','type':'text'}]}}).encode(),
             'work.py':code.encode(),'answer.txt':(source/'answer.txt').read_bytes(),'run.log':result.stdout.encode(),'characterization.json':b'{}','trace.jsonl':b''}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        for name,raw in files.items():z.writestr(name,raw)
    seq=db.query_one('SELECT MAX(seq) FROM events WHERE run_id=?',(rid,))[0]
    sealed,steps=package_seal.seal(buf.getvalue(),rid,'trial_fixture',seq)
    report=arm_admission.check(sealed,_protocol())
    assert report['verdict']=='admitted',report
    assert any('work.py' in step.get('body','') for step in steps if step['step_type']=='tool_call')
    assert any('answer=42' in step.get('tool_output','') for step in steps if step['step_type']=='tool_result')
    assert not db.query('SELECT * FROM compute_jobs WHERE run_id=?',(rid,))
    with zipfile.ZipFile(io.BytesIO(sealed)) as z:assert z.read('answer.txt') == files['answer.txt']


def test_old_policy_migrates_and_executor_receives_local_science_environment(run):
    rid,_=run
    settings=config.load_settings();settings['policy']['science_compute']='bohrium_only';config.save_settings(settings)
    assert config.load_settings()['policy']['science_compute']=='sandbox_first'
    # Explicit legacy settings remain compatible; migrating the new default
    # itself no longer authorizes seconds-long local scientific work.
    settings=config.load_settings();settings['policy']['science_compute']='local_seconds_remote_heavy';config.save_settings(settings)
    assert config.load_settings()['policy']['science_compute']=='local_seconds_remote_heavy'
    executor=FakeExecutor();controller=RunController();controller._prime_instances[rid]=executor;controller._prime_sessions[rid]='fake'
    asyncio.run(controller._apply_decision(rid,_decision([{'op':'start_trial','goal':'synthetic local check','success_check':'real output'}],rid=rid),{},None,None))
    assert '秒级小计算允许本地执行' in executor.prompts[0][1]
    assert '.venv/bin/python' in executor.prompts[0][1]
    assert '重计算使用已授权' in executor.prompts[0][1]


def test_all_pi_and_executor_prompt_branches_have_consistent_seconds_boundary():
    from cyberscientist.brains.codex import CodexBrain
    from cyberscientist.brains.kimi import _brain_instruction
    from cyberscientist.controller import executor_instruction_suffix
    for packet in ({'protocol':'executor_question'}, {'protocol':'executor_question','sparse_brain_version':1},
                   {'protocol':'review_result','sparse_brain_version':1}, {'trigger':'run_start'}):
        prompt=CodexBrain._render_prompt(packet)
        assert '秒级小计算' in prompt and '重计算' in prompt
    for text in (_brain_instruction(), executor_instruction_suffix()):
        assert '秒级小计算' in text and '重计算' in text
        assert '科学计算、依赖验证、统计分析、科学作图在已授权' not in text
    from cyberscientist import runtime_facts
    assert runtime_facts.facts('nonexistent')['status'] == 'unknown'
