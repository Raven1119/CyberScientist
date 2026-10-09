import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from cyberscientist import config, db, mailboxes, topic_workspace, sandboxes, sandbox_background, power, compute
from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform, PlatformError
from test_cli_submission_cs14 import bundle, prepare
from test_sandbox_first_cs17 import choose
from test_sandboxes import run


@pytest.mark.parametrize('value', [None, '', '  ', 'unknown', ' UNKNOWN ', 12])
def test_missing_real_model_rejects_before_http_or_cli(tmp_path, monkeypatch, value):
    from cyberscientist import cli_submission
    platform = prepare(tmp_path, monkeypatch)
    content, _ = bundle()
    rebuilt = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(rebuilt, 'w') as target:
        for name in source.namelist():
            data = source.read(name)
            if name == 'provenance/native_session.json':
                proof = json.loads(data); proof['model'] = value; data = json.dumps(proof).encode()
            target.writestr(name, data)
    monkeypatch.setattr(platform, '_http', lambda *a, **kw: pytest.fail('no HTTP before valid model'))
    monkeypatch.setattr(cli_submission.subprocess, 'run', lambda *a, **kw: pytest.fail('no CLI before valid model'))
    with pytest.raises(PlatformError, match='模型标识') as failure:
        cli_submission.submit(platform, 'agent', 'fixture-token', 'unused', 'topic', {'package_bytes': rebuilt.getvalue(), 'model_id': value})
    assert failure.value.no_side_effect


def test_agent_import_checks_owner_and_updates_existing_without_duplicate(monkeypatch):
    platform = BohriumPlaygroundPlatform('https://play.bohrium.com/api', operator_token='fixture-owner')
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    def identity(method, path, token):
        return {'id':'owner','userType':'human'} if token == 'fixture-owner' else {
            'id':'agent-one','email':'agent-one@example.invalid','userType':'agent',
            'operatorId':'owner','operatorConfirmed':True}
    monkeypatch.setattr(platform, '_http', identity)
    first = mailboxes.import_agent_token('fixture-agent-token')
    second = mailboxes.import_agent_token('replacement-agent-token')
    assert first['id'] == second['id'] and second['secret_configured']
    assert second['claim_status'] == 'confirmed' and 'secret_ref' not in second
    assert db.query_one('SELECT COUNT(*) FROM mailboxes')[0] == 1
    row = db.query_one('SELECT * FROM mailboxes WHERE id=?', (first['id'],))
    assert config.resolve_secret(row['secret_ref']) == 'replacement-agent-token'
    before = config.load_secrets()
    monkeypatch.setattr(platform, '_http', lambda *a, **kw: {'id':'foreign','userType':'agent','operatorId':'elsewhere','operatorConfirmed':True})
    with pytest.raises(mailboxes.MailboxError, match='当前操作者'):
        mailboxes.import_agent_token('foreign-token')
    assert config.load_secrets() == before and db.query_one('SELECT COUNT(*) FROM mailboxes')[0] == 1
    monkeypatch.setattr(platform, '_http', lambda *a, **kw: (_ for _ in ()).throw(PlatformError('Rejected fixture-agent-token')))
    with pytest.raises(mailboxes.MailboxError) as failure:
        mailboxes.import_agent_token('fixture-agent-token')
    assert failure.value.code == 'AUTH_CHECK_FAILED' and 'fixture-agent-token' not in str(failure.value)
    assert config.load_secrets() == before


def test_relaxation_checks_final_metrics_and_rejects_incomplete_or_false_success():
    import importlib.util
    import sys
    root=config.WORKSPACE_ROOT/'skills/cyberscientist-job-spec/attachments/abacus/cell-relax'
    sys.path.insert(0,str(root))
    try:
        spec=importlib.util.spec_from_file_location('cell_relax_check',root/'check_relaxation.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        log='#SCF IS CONVERGED#\nLargest force is 0.000000 eV/Angstrom while threshold is 0.010000 eV/Angstrom\nLargest stress is 0.303826 kbar while threshold is 0.500000 kbar\nRelaxation is converged!\n!FINAL_ETOT_IS -212.0305897858216326 eV\nFinish Time : now\n'
        params={'calculation':'cell-relax','force_thr_ev':'0.01','stress_thr':'0.5'}
        assert module.final_relaxation(log,params)['max_stress_kbar']==0.303826
        for invalid in (log.replace('Finish Time','lost'),log+'#SCF IS NOT CONVERGED#\n',log.replace('0.303826','0.600000'),log.replace('0.303826','nan'),log.replace('0.500000','0.900000'),log.replace('Relaxation is converged!','Relaxation is not converged yet!'),log.replace('!FINAL_ETOT_IS -212.0305897858216326 eV\n','')+'!FINAL_ETOT_IS -1 eV\n',log.replace('Largest stress is 0.303826 kbar while threshold is 0.500000 kbar\n','')+'Largest stress is 0.303826 kbar while threshold is 0.500000 kbar\n'):
            with pytest.raises(ValueError):module.final_relaxation(invalid,params)
    finally:sys.path.remove(str(root))


def test_expiry_replacement_restores_identical_files_once(run, monkeypatch, tmp_path):
    _, rid, _, calls, _ = run
    choose(monkeypatch)
    db.execute("INSERT INTO runtime_observations VALUES('sandbox-lifetime-ceiling',?,?)", (json.dumps({'effective_ceiling_seconds':600}), db.utcnow()))
    fact = topic_workspace.ensure(rid)
    assert fact['lifetime_seconds'] == 600
    remote = tmp_path / 'remote'; remote.mkdir(); (remote / 'state.json').write_text('{"checkpoint":3}')
    import shutil
    transfers = []
    def transfer(run_id, action, sid, remote_path, *, local_path):
        transfers.append(action)
        if action == 'read': shutil.copytree(remote, local_path)
        else: shutil.copytree(local_path, remote, dirs_exist_ok=True)
        return {'status':'completed'}
    monkeypatch.setattr(sandboxes, 'transfer', transfer)
    monkeypatch.setattr(topic_workspace, '_remote_fingerprint', lambda *a: topic_workspace._fingerprint(remote))
    snap = topic_workspace.checkpoint(rid, fact['sandbox_id'])
    assert snap['checkpoint']['sha256'] == topic_workspace._fingerprint(remote)
    db.execute('UPDATE compute_sandboxes SET expires_at=? WHERE sandbox_id=?', ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(), fact['sandbox_id']))
    creates = []
    def create(run_id, op, request, **kwargs):
        creates.append((op,request)); return {'status':'active','sandbox_id':'replacement-box'}
    monkeypatch.setattr(sandboxes, 'create', create)
    monkeypatch.setattr(sandboxes, '_owned', lambda run_id, sid: {'status':'deleted','expires_at':'2000-01-01T00:00:00+00:00'} if sid==fact['sandbox_id'] else {'status':'active','expires_at':(datetime.now(timezone.utc)+timedelta(seconds=600)).isoformat()})
    monkeypatch.setattr(sandboxes, 'execute', lambda *a, **kw: {'status':'completed','exit_code':0})
    result = topic_workspace.ensure(rid)
    assert result['mode'] == 'sandbox' and result['generation'] == 1
    assert result['image'] == fact['image'] and transfers == ['read','write']
    assert len(creates) == 1 and topic_workspace.ensure(rid) == result
    assert (remote / 'state.json').read_text() == '{"checkpoint":3}'


def test_replacement_failure_is_durable_same_image_job_fallback(run, monkeypatch, tmp_path):
    _, rid, work, _, _ = run
    db.execute('UPDATE authorizations SET max_sandbox_minutes=80 WHERE id=(SELECT authorization_id FROM runs WHERE id=?)', (rid,))
    choose(monkeypatch); fact = topic_workspace.ensure(rid)
    source = tmp_path / 'snapshot'; source.mkdir()
    topic_workspace._record(rid, fact | {'mode':'renewing','checkpoint':{'path':str(source),'sha256':topic_workspace._fingerprint(source)}})
    monkeypatch.setattr(sandboxes, '_owned', lambda *a: {'status':'deleted'})
    creates=[]
    monkeypatch.setattr(sandboxes, 'create', lambda *a, **kw: creates.append(a) or {'status':'unknown','sandbox_id':None})
    submitted=[]
    monkeypatch.setattr(topic_workspace.compute, 'submit', lambda *a: submitted.append(a) or {'status':'accepted'})
    body={'operation_id':'replacement-work','command':'echo bounded','timeout':30,'input_directory':str(work),'spec':{'image_address':fact['image'],'command':'echo bounded'}}
    assert topic_workspace.work(rid, body)['fallback'] == 'job'
    assert len(creates) == len(submitted) == 1
    assert topic_workspace.ensure(rid)['create_status'] == 'unknown' and len(creates) == 1


def test_background_workspace_and_deduplication_keep_command_identity(run, monkeypatch):
    _, rid, work, calls, _ = run
    choose(monkeypatch)
    monkeypatch.setattr(sandboxes, 'transfer', lambda *a, **kw: {'status':'completed'})
    body = {'operation_id':'cwd-command','command':'pwd','timeout':30,'input_directory':str(work)}
    result = topic_workspace.work(rid, body)
    assert result['status'] == 'unknown'  # Native fixture has no background PID.
    launch = next(c for c in calls if '--background' in c)
    assert 'cd /bohr-workspace && pwd' in launch[launch.index('--command') + 1]
    assert topic_workspace.work(rid, body)['deduplicated']
    assert sum('--background' in c for c in calls) == 1
    with pytest.raises(compute.ComputeError, match='绑定其他请求'):
        topic_workspace.work(rid, body | {'command':'other'})
    assert sandbox_background.command_digest('pwd',30) != sandbox_background.command_digest('pwd',30,topic_workspace.REMOTE)


@pytest.mark.parametrize('blocked', ['paused', 'shutdown'])
def test_expiry_never_replaces_while_gate_or_shutdown_is_closed(run, monkeypatch, blocked):
    _, rid, _, calls, _ = run
    choose(monkeypatch); fact = topic_workspace.ensure(rid)
    db.execute('UPDATE compute_sandboxes SET expires_at=? WHERE sandbox_id=?',
               ('2000-01-01T00:00:00+00:00', fact['sandbox_id']))
    if blocked == 'paused':
        db.execute("UPDATE runs SET gate='paused' WHERE id=?", (rid,))
    else:
        monkeypatch.setattr(power, 'shutdown_requested', lambda: True)
    assert topic_workspace.ensure(rid)['mode'] == 'job'
    assert sum(c[:2] == ['sandbox','create'] for c in calls) == 1


@pytest.mark.parametrize('blocked', ['paused', 'shutdown', 'expired'])
def test_work_checks_authorization_before_input_upload(run, monkeypatch, blocked):
    _, rid, work, _, _ = run
    choose(monkeypatch); topic_workspace.ensure(rid)
    if blocked == 'paused':
        db.execute("UPDATE runs SET gate='paused' WHERE id=?", (rid,))
    elif blocked == 'shutdown':
        monkeypatch.setattr(power, 'shutdown_requested', lambda: True)
    else:
        db.execute('UPDATE authorizations SET max_run_minutes=0 WHERE id=(SELECT authorization_id FROM runs WHERE id=?)', (rid,))
    monkeypatch.setattr(sandboxes, 'transfer', lambda *a, **kw: pytest.fail('no upload behind a closed gate'))
    with pytest.raises(compute.ComputeError):
        topic_workspace.work(rid, {'operation_id':'guarded-work','command':'pwd','timeout':30,'input_directory':str(work)})


def test_unknown_input_upload_is_never_repeated_or_executed(run, monkeypatch):
    _, rid, work, calls, _ = run
    choose(monkeypatch); topic_workspace.ensure(rid)
    uploads=[]
    monkeypatch.setattr(sandboxes, 'transfer', lambda *a, **kw: uploads.append(kw['operation_id']) or {'status':'unknown'})
    body={'operation_id':'unknown-input','command':'pwd','timeout':30,'input_directory':str(work)}
    for _ in range(2):
        with pytest.raises(compute.ComputeError) as failure:
            topic_workspace.work(rid,body)
        assert failure.value.code=='WORKSPACE_SYNC_UNKNOWN'
    assert len(uploads)==1 and not any('--background' in c for c in calls)


def test_direct_write_invalidates_snapshot_and_sync_window_rejects_new_writes(run, monkeypatch):
    _, rid, _, calls, _ = run
    choose(monkeypatch); fact=topic_workspace.ensure(rid)
    topic_workspace._record(rid,fact|{'checkpoint':{'path':'fixture','sha256':'old'}})
    sandboxes.transfer(rid,'write',fact['sandbox_id'],'/bohr-workspace/new.txt',content='new-data')
    assert topic_workspace.current(rid)['checkpoint'] is None
    db.execute('UPDATE compute_sandboxes SET expires_at=? WHERE sandbox_id=?',
               ((datetime.now(timezone.utc)+timedelta(seconds=200)).isoformat(),fact['sandbox_id']))
    before=len(calls)
    with pytest.raises(compute.ComputeError) as failure:
        sandboxes.transfer(rid,'write',fact['sandbox_id'],'/bohr-workspace/too-late.txt',content='late-data')
    assert failure.value.code=='SANDBOX_SYNC_WINDOW' and len(calls)==before


@pytest.mark.parametrize('unsafe', ['unknown_write','changed_hash'])
def test_rotation_never_restores_an_unconfirmed_snapshot(run, monkeypatch, unsafe):
    _, rid, _, calls, _ = run
    choose(monkeypatch);fact=topic_workspace.ensure(rid)
    topic_workspace._record(rid,fact|{'checkpoint':{'path':'fixture','sha256':'old'}})
    db.execute('UPDATE compute_sandboxes SET expires_at=? WHERE sandbox_id=?',
               ((datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat(),fact['sandbox_id']))
    if unsafe=='unknown_write':
        db.execute("INSERT INTO compute_sandbox_operations(operation_id,run_id,sandbox_id,action,status,started_at) VALUES('unknown-write',?,?,'files.write','unknown',?)", (rid,fact['sandbox_id'],db.utcnow()))
    else:
        monkeypatch.setattr(topic_workspace,'_remote_fingerprint',lambda *a:'changed')
    result=topic_workspace.ensure(rid)
    assert result['mode']=='job' and result['checkpoint'] is None
    assert sum(c[:2]==['sandbox','create'] for c in calls)==1


def test_unknown_old_delete_has_job_fallback_without_delete_replay(run, monkeypatch):
    _, rid, work, calls, _ = run
    choose(monkeypatch);fact=topic_workspace.ensure(rid)
    topic_workspace._record(rid,fact|{'mode':'renewing'})
    db.execute("UPDATE compute_sandboxes SET status='unknown' WHERE sandbox_id=?", (fact['sandbox_id'],))
    submitted=[]
    monkeypatch.setattr(compute,'submit',lambda *a:submitted.append(a) or {'status':'accepted'})
    result=topic_workspace.work(rid,{'operation_id':'delete-unknown-job','command':'echo bounded','input_directory':str(work),'spec':{'image_address':fact['image'],'command':'echo bounded'}})
    assert result['fallback']=='job' and len(submitted)==1
    assert topic_workspace.current(rid)['old_delete_status']=='unknown'
    assert not any(c[:2]==['sandbox','delete'] for c in calls)


def test_confirmed_upload_without_launch_cannot_reuse_changed_remote_inputs(run, monkeypatch):
    _, rid, work, calls, _ = run
    choose(monkeypatch);topic_workspace.ensure(rid)
    uploads=[]
    monkeypatch.setattr(sandboxes,'transfer',lambda *a,**kw:uploads.append(kw) or {'status':'completed'})
    launches=[]
    def refused(*args,**kwargs):
        launches.append(args)
        raise compute.ComputeError('RUN_NOT_RUNNING','pause before background reservation')
    monkeypatch.setattr(sandbox_background,'start',refused)
    body={'operation_id':'prepared-input','command':'pwd','timeout':30,'input_directory':str(work)}
    with pytest.raises(compute.ComputeError):topic_workspace.work(rid,body)
    assert db.query_one("SELECT status FROM operations WHERE kind='topic.work_input'")[0]=='confirmed'
    # A later request may change remote files; a retry cannot execute cached inputs.
    with pytest.raises(compute.ComputeError) as failure:topic_workspace.work(rid,body)
    assert failure.value.code=='WORKSPACE_OPERATION_INCOMPLETE'
    assert len(uploads)==len(launches)==1 and not any('--background' in c for c in calls)


def test_job_fallback_state_never_bypasses_mutation_authorization(run,monkeypatch):
    _, rid, _, calls, _ = run
    choose(monkeypatch);fact=topic_workspace.ensure(rid)
    topic_workspace._record(rid,fact|{'mode':'job'})
    db.execute("UPDATE runs SET gate='paused' WHERE id=?",(rid,))
    before=len(calls)
    with pytest.raises(compute.ComputeError):
        sandboxes.transfer(rid,'write',fact['sandbox_id'],'/bohr-workspace/blocked.txt',content='blocked')
    with pytest.raises(compute.ComputeError):
        sandboxes.execute(rid,fact['sandbox_id'],'echo blocked',10)
    assert len(calls)==before
