"""Failure classes observed in the old Job archive must fail before reservation."""
import json

import pytest
from cyberscientist import compute,db,job_checks
from test_sandboxes import run


def spec(command='bash task.sh'):
    return {'command':command,'image_address':'fixture-image','max_run_time':5,'machine_type':'c2_m2_cpu','backward_files':['result.txt','STDOUTERR']}


@pytest.mark.parametrize('files,command,code',[
    ({'task.sh':b'if true; then\necho unfinished\n'},'bash task.sh','INVALID_BASH'),
    ({'task.py':b'for x in\n'},'python task.py','INVALID_PYTHON'),
    ({'task.txt':b'for x in\n'},'python task.txt','INVALID_PYTHON'),
    ({'task.txt':b'for x in\n'},'python -O task.txt','INVALID_PYTHON'),
    ({'task.txt':b'if true; then\n'},'bash task.txt','INVALID_BASH'),
    ({'task.txt':b'if true; then\n'},'bash -e task.txt','INVALID_BASH'),
    ({'task.txt':b'import requests\nrequests.get("https://example.test")\n'},'python task.txt','NETWORK_REQUIRED'),
    ({'task.sh':b'bash payload.txt\n','payload.txt':b'pip install ase\n'},'bash task.sh','NETWORK_REQUIRED'),
    ({},'env python -c \'import requests; requests.get("https://example.test")\'','NETWORK_REQUIRED'),
    ({'task.sh':b'pip install ase\n'},'bash task.sh','NETWORK_REQUIRED'),
    ({'task.sh':b'git clone https://example.test/source\n'},'bash task.sh','NETWORK_REQUIRED'),
    ({'task.sh':b'curl https://example.test/data\n'},'bash task.sh','NETWORK_REQUIRED'),
    ({'task.py':b'import requests\nrequests.get("https://example.test")\n'},'python task.py','NETWORK_REQUIRED'),
    ({'task.py':b'import subprocess,sys\nsubprocess.run([sys.executable,"-m","pip","install","spglib"])\n'},'python task.py','NETWORK_REQUIRED'),
    ({'task.sh':b"cp 'runs/${phase}/STRU' result.txt\n"},'bash task.sh','LITERAL_VARIABLE_PATH'),
    ({},'bash missing.sh','MISSING_ENTRY'),
    ({},'python extract_terminal_state.py','MISSING_ENTRY'),
    ({'task.sh':b'echo result > lost.txt\n'},'bash task.sh','OUTPUTS_NOT_REGISTERED'),
])
def test_archived_preventable_failure_types(files,command,code):
    with pytest.raises(job_checks.Error) as exc:
        job_checks.static(files,spec(command),{})
    assert exc.value.code==code


def test_smoke_time_and_missing_smoke_warning():
    files={'task.sh':b'echo done > result.txt\n'}
    report=job_checks.static(files,spec(),{})
    assert report['warnings'] and report['syntax_checked']
    with pytest.raises(job_checks.Error) as exc:
        job_checks.static(files,spec(),{'smoke_seconds':101})
    assert exc.value.code=='INSUFFICIENT_TIME'


def test_oversized_source_is_blocked_before_remote_probe_and_job_reservation(run,monkeypatch):
    _,rid,work,calls,_=run
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0])
    snapshot['sandbox_first_version']=1
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(snapshot),rid))
    db.execute('UPDATE authorizations SET max_jobs=1 WHERE id=(SELECT authorization_id FROM runs WHERE id=?)',(rid,))
    (work/'task.sh').write_text('#'+('x'*2_000_000)+'\npip install ase\n')
    monkeypatch.setattr(job_checks,'image',lambda *args:pytest.fail('不能跳过大脚本检查'))
    with pytest.raises(compute.ComputeError) as exc:compute.submit(rid,'oversized-job',spec(),str(work))
    assert exc.value.code=='SOURCE_TOO_LARGE'
    assert not calls
    assert db.query_one('SELECT count(*) FROM compute_jobs WHERE run_id=?',(rid,))[0]==0


@pytest.mark.parametrize('flags,valid',[('0 0 0',False),('1 1 1',True)])
def test_abacus_relaxation_flags_and_required_parameters(flags,valid):
    files={'INPUT':b'INPUT_PARAMETERS\ncalculation cell-relax\nbasis_type pw\necutwfc 30\nscf_thr 1e-7\nscf_nmax 50\npseudo_dir /missing/pp\n',
           'STRU':('ATOMIC_POSITIONS\nDirect\nSi\n0.0\n1\n0 0 0 '+flags+'\n').encode()}
    if valid:
        result=job_checks.static(files,spec('abacus'),{})
        assert '/missing/pp' in result['paths']
        files['INPUT']=b'INPUT_PARAMETERS\ncalculation scf\n'
        with pytest.raises(job_checks.Error,match='关键参数'):
            job_checks.static(files,spec('abacus'),{})
    else:
        with pytest.raises(job_checks.Error) as exc:job_checks.static(files,spec('abacus'),{})
        assert exc.value.code=='ABACUS_FIXED_ATOMS'


def test_image_commands_paths_and_packages_are_remote_facts(run):
    _,rid,_,_,_=run
    report={'commands':['unzip','/usr/bin/time'],'paths':['/pp'],'third_party':['spglib']}
    with pytest.raises(job_checks.Error) as exc:job_checks.image(rid,'fixture-image',report)
    assert exc.value.code=='IMAGE_FACTS_MISSING'
    facts={'commands':{'unzip':'/usr/bin/unzip','/usr/bin/time':'/usr/bin/time'},'paths':{'/pp':True},'packages':{'spglib':{'version':'fixture'}}}
    db.execute('INSERT INTO image_facts VALUES(?,?,?,?,?)',('fixture-image','f'*64,json.dumps(facts),'fixture-probe',db.utcnow()))
    assert job_checks.image(rid,'fixture-image',report)['image_checked']


def test_mandatory_failure_does_not_create_or_reserve_job_even_with_probe_option(run):
    _,rid,work,calls,_=run
    db.execute('UPDATE authorizations SET max_jobs=2 WHERE id=(SELECT authorization_id FROM runs WHERE id=?)',(rid,))
    row=db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,));snapshot=json.loads(row[0]);snapshot['sandbox_first_version']=1
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(snapshot),rid))
    (work/'task.sh').write_text('pip install spglib\n')
    with pytest.raises(compute.ComputeError) as exc:
        compute.submit(rid,'blocked-job',spec(),str(work),{'purpose':'probe','allow_network_install':True})
    assert exc.value.code=='NETWORK_REQUIRED'
    assert db.query_one('SELECT count(*) FROM compute_jobs WHERE run_id=?',(rid,))[0]==0
    assert not calls
    event=db.query_one("SELECT payload FROM events WHERE type='job.preflight' AND run_id=? ORDER BY seq DESC LIMIT 1",(rid,))
    assert json.loads(event[0])['reservation_created'] is False


def test_shell_heredoc_cwd_and_wrappers_do_not_lose_semantics():
    report=job_checks.static({'task.sh':b"python3 - <<'PYCODE'\nprint('ready')\nPYCODE\n"},spec(),{})
    assert set(report['commands'])=={'bash','python3'}
    report=job_checks.static({'task.sh':b'cd phase; python3 task.py\n','phase/task.py':b'print("ready")\n'},spec(),{})
    assert 'python3' in report['commands']
    with pytest.raises(job_checks.Error) as exc:job_checks.static({},spec('mpirun -np 2 abacus'),{})
    assert exc.value.code=='ABACUS_INPUT_MISSING'
    with pytest.raises(job_checks.Error) as exc:job_checks.static({},spec("bash -c 'python missing.py'"),{})
    assert exc.value.code=='MISSING_ENTRY'


@pytest.mark.parametrize('command',["python3 -c 'import requests; requests.get(\"https://example.test\")'",'pip install --no-index local.whl && curl https://example.test -o result.txt'])
def test_inline_network_and_offline_flag_cannot_bypass(command):
    with pytest.raises(job_checks.Error) as exc:job_checks.static({},spec(command),{})
    assert exc.value.code=='NETWORK_REQUIRED'


def test_closed_gate_job_cannot_probe_remote_image(run,monkeypatch):
    _,rid,work,calls,_=run
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0]);snapshot['sandbox_first_version']=1
    db.execute("UPDATE runs SET config_snapshot=?,gate='awaiting_method_approval' WHERE id=?",(json.dumps(snapshot),rid))
    monkeypatch.setattr(job_checks,'image',lambda *args:pytest.fail('关门时禁止远端预检'))
    with pytest.raises(compute.ComputeError):compute.submit(rid,'closed-job',spec('echo ready'),str(work))
    assert not calls


def test_printed_download_instructions_are_not_network_execution():
    report=job_checks.static({'task.sh':b"echo 'pip install ase'\nprintf '%s\\n' 'curl https://example.test'\n"},spec(),{})
    assert report['commands']==['bash']


def test_packaged_executable_is_checked_as_input_not_image_command():
    files={'task.sh':b'#!/bin/bash\necho ready > result.txt\n'}
    report=job_checks.static(files,spec('./task.sh'),{'_file_modes':{'task.sh':0o755}})
    assert './task.sh' not in report['commands']
    with pytest.raises(job_checks.Error) as exc:
        job_checks.static(files,spec('./task.sh'),{'_file_modes':{'task.sh':0o644}})
    assert exc.value.code=='SCRIPT_NOT_EXECUTABLE'


def test_existing_job_request_is_readable_after_gate_closes(run,monkeypatch):
    _,rid,work,calls,_=run
    db.execute('UPDATE authorizations SET max_jobs=1 WHERE id=(SELECT authorization_id FROM runs WHERE id=?)',(rid,))
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0]);snapshot['sandbox_first_version']=1
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(snapshot),rid))
    monkeypatch.setattr(job_checks,'image',lambda *args:{'image_checked':True})
    first=compute.submit(rid,'deduplicated-job',spec('echo ready'),str(work))
    count=len(calls)
    db.execute("UPDATE runs SET gate='awaiting_method_approval' WHERE id=?",(rid,))
    monkeypatch.setattr(job_checks,'image',lambda *args:pytest.fail('旧请求不能重跑远端预检'))
    again=compute.submit(rid,'deduplicated-job',spec('echo ready'),str(work))
    assert again['deduplicated'] and again['status']==first['status']
    assert len(calls)==count
