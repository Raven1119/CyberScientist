"""Persistent workspace and background recovery, using explicit native fixtures."""
import json

import pytest
from cyberscientist import capabilities, compute, config, db, features, sandbox_background, sandboxes, topic_workspace
from test_sandboxes import run


def choose(monkeypatch):
    monkeypatch.setattr(topic_workspace.environment_catalog, 'current', lambda rid: {'mode':'catalog','entry_id':'fixture'})
    monkeypatch.setattr(topic_workspace.environment_catalog, 'get', lambda ident: {'id':ident,'image':'registry.example/science:fixed'})


def test_persistent_workspace_is_single_and_uses_pi_image(run, monkeypatch):
    _, rid, _, calls, _ = run
    choose(monkeypatch)
    fact=topic_workspace.ensure(rid)
    assert fact['mode']=='sandbox'
    assert fact['image']=='registry.example/science:fixed'
    assert topic_workspace.ensure(rid)==fact
    assert sum(c[:2]==['sandbox','create'] for c in calls)==1
    assert fact['lifetime_seconds'] <= 1200
    assert fact['renewal']=='unavailable_in_native_cli'
    assert any(x['id']=='topic-sandbox' for x in capabilities.index(rid))
    sandboxes.cleanup_run(rid)
    assert topic_workspace.ensure(rid)['mode']=='job'
    assert sum(c[:2]==['sandbox','create'] for c in calls)==1


def test_creation_unknown_falls_back_without_replay_or_release(run,monkeypatch):
    _,rid,work,calls,_=run
    choose(monkeypatch)
    original=compute._native
    def native(args,**kwargs):
        if args[:2]==['sandbox','create']:
            calls.append(args)
            return {'ok':False,'unknown':True,'stderr':'TLS reply unknown','stdout':''}
        return original(args,**kwargs)
    monkeypatch.setattr(compute,'_native',native)
    submissions=[]
    monkeypatch.setattr(compute,'submit',lambda *args: submissions.append(args) or {'status':'created'})
    request={'operation_id':'work-one','command':'echo bounded','spec':{'image_address':'registry.example/science:fixed','command':'echo bounded'},'input_directory':str(work)}
    result=topic_workspace.work(rid,request)
    assert result['fallback']=='job' and len(submissions)==1
    assert submissions[0][2]['image_address']==topic_workspace.current(rid)['image']
    row=db.query_one('SELECT * FROM compute_sandboxes WHERE operation_id=?',('topic_'+rid,))
    assert row['status']=='unknown' and sandboxes.reserved_seconds(row)>0
    topic_workspace.ensure(rid)
    assert sum(c[:2]==['sandbox','create'] for c in calls)==1
    with pytest.raises(compute.ComputeError,match='同镜像'):
        topic_workspace.work(rid,request|{'spec':request['spec']|{'image_address':'different'}})
    assert len(submissions)==1


def test_missing_pi_choice_does_not_create(run):
    _,rid,_,calls,_=run
    assert topic_workspace.ensure(rid)['mode']=='not_selected'
    assert calls==[]


def test_background_poll_has_live_log_and_actual_exit(run,monkeypatch):
    _,rid,_,calls,_=run
    sid=sandboxes.create(rid,'box',{'timeout':300})['sandbox_id']
    original=compute._native
    pending=[True]
    def native(args,**kwargs):
        if '--background' in args:
            calls.append(args)
            return {'ok':True,'exit_code':0,'stdout':json.dumps({'data':{'pid':42,'background':True}})}
        if args[:2]==['sandbox','exec']:
            calls.append(args)
            out='CS_BACKGROUND_PENDING\nfirst log\n' if pending[0] else 'CS_BACKGROUND_EXIT=3\nfirst log\nfailed honestly\n'
            return {'ok':True,'exit_code':0,'stdout':json.dumps({'data':{'exit_code':0,'stdout':out}})}
        return original(args,**kwargs)
    monkeypatch.setattr(compute,'_native',native)
    result=sandbox_background.start(rid,sid,'sleep 2; exit 3',60,'bg-one')
    assert result['status']=='running' and result['pid']==42
    assert '--background' in calls[-1] and calls[-1][calls[-1].index('--timeout')+1]=='0'
    assert 'timeout --signal=TERM --kill-after=5 60' in calls[-1][calls[-1].index('--command')+1]
    assert sandbox_background.poll(rid,'bg-one')['log']=='first log\n'
    pending[0]=False
    result=sandbox_background.poll(rid,'bg-one')
    assert result['status']=='failed' and result['exit_code']==3
    assert db.query_one('SELECT status FROM compute_sandbox_operations WHERE operation_id=?',('bg-one',))[0]=='failed'
    sandbox_background.start(rid,sid,'sleep 2; exit 3',60,'bg-one')
    assert sum('--background' in c for c in calls)==1


def test_lost_background_reply_never_relaunches_and_checks_identity(run,monkeypatch):
    _,rid,_,calls,_=run
    sid=sandboxes.create(rid,'box',{'timeout':300})['sandbox_id']
    def native(args,**kwargs):
        calls.append(args)
        return {'ok':False,'unknown':True,'stderr':'reply lost'}
    monkeypatch.setattr(compute,'_native',native)
    assert sandbox_background.start(rid,sid,'echo once',60,'unknown-bg')['status']=='unknown'
    assert sandbox_background.start(rid,sid,'echo once',60,'unknown-bg')['deduplicated']
    with pytest.raises(compute.ComputeError,match='其他请求'):
        sandbox_background.start(rid,sid,'echo twice',60,'unknown-bg')
    assert sum('--background' in c for c in calls)==1
    with pytest.raises(compute.ComputeError,match='不属于'):
        sandbox_background.poll('other-run','unknown-bg')


def test_background_launch_rejects_closed_gate_and_excess_lifetime(run):
    _,rid,_,calls,_=run
    sid=sandboxes.create(rid,'box',{'timeout':60})['sandbox_id']
    with pytest.raises(compute.ComputeError,match='寿命'):
        sandbox_background.start(rid,sid,'sleep 90',90,'too-long')
    db.execute("UPDATE runs SET gate='awaiting_method_approval' WHERE id=?",(rid,))
    with pytest.raises(compute.ComputeError,match='门禁'):
        sandbox_background.start(rid,sid,'echo no',10,'closed')
    assert sum('--background' in c for c in calls)==0


def test_sandbox_first_disables_local_science_structurally():
    settings=config.load_settings();settings['policy']['science_compute']='sandbox_first';settings['features']['local_calculation']=True
    config.save_settings(settings)
    assert not features.enabled('local_calculation')
    assert '常驻沙箱' in features.science_instruction()
