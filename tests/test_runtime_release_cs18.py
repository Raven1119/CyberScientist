import json
import hashlib
from pathlib import Path

import pytest

from cyberscientist import backend_identity,config,codex_protocol,runtime_layout,runtime_release,skills


def deployed(tmp_path,monkeypatch):
    root=tmp_path/'CyberScientist-comp';(root/'.runtime/codex').mkdir(parents=True)
    (root/'.runtime/version.json').write_text(json.dumps({'commit':'a'*40}))
    (root/'.runtime/codex/config.toml').write_text('project_doc_max_bytes = 0\n')
    (root/'.runtime/codex/auth.json').write_text('{}')
    monkeypatch.setattr(config,'WORKSPACE_ROOT',root)
    return root


def test_runtime_identity_uses_version_file_without_git(tmp_path,monkeypatch):
    root=deployed(tmp_path,monkeypatch)
    assert not (root/'.git').exists()
    assert backend_identity.capture()['commit']=='a'*40
    (root/'.runtime/version.json').write_text('{"commit":"invalid"}')
    with pytest.raises(ValueError,match='SHA'):backend_identity.capture()


def test_native_home_and_skill_scan_are_competition_only(tmp_path,monkeypatch):
    root=deployed(tmp_path,monkeypatch)
    for name in ('bohrium-job','cyberscientist-sandbox'):
        directory=root/'skills'/name;directory.mkdir(parents=True);(directory/'SKILL.md').write_text('---\nname: '+name+'\ndescription: Competition\n---\n')
    foreign=tmp_path/'global-skills';(foreign/'unrelated').mkdir(parents=True);(foreign/'unrelated/SKILL.md').write_text('---\nname: unrelated\ndescription: Foreign\n---\n')
    monkeypatch.setattr(skills,'SKILL_DIRS',(foreign,))
    assert {item['id'] for item in skills.scan_catalog()}=={'bohrium-job','cyberscientist-sandbox'}
    assert {item['id'] for item in skills.file_catalog()}=={'bohrium-job','cyberscientist-sandbox'}
    env=codex_protocol.native_brain_environment({'HOME':'/original/home','CODEX_HOME':'/global/codex','PATH':'/bin','BOHRIUM_ACCESS_KEY':'excluded'})
    assert env['HOME']==str(root/'.runtime/home') and env['CODEX_HOME']==str(root/'.runtime/codex')
    assert 'BOHRIUM_ACCESS_KEY' not in env
    assert codex_protocol.thread_params({},'gpt-6-astra','xhigh',writable=False)['config']['project_doc_max_bytes']==0
    assert codex_protocol.process_environment({'env':{'HOME':'/original/home'}})['HOME']==env['HOME']
    (root/'.runtime/codex/auth.json').unlink()
    with pytest.raises(ValueError,match='凭据'):codex_protocol.native_brain_environment({})


def test_scanner_reports_locations_and_keeps_comp_sibling_distinct(tmp_path):
    dev=tmp_path/'CyberScientist';comp=tmp_path/'CyberScientist-comp'
    violations=runtime_release.content_violations('safe '+str(comp)+'/skills\nbad '+str(dev)+'/docs\nCS-UP-18 D-79 docs/BUILD.md .package-checks/check', 'prompt', [dev])
    assert len(violations)==5
    assert {item['line'] for item in violations}=={2,3}
    assert runtime_release.content_violations('https://bohrium-doc.dp.tech/docs/official', 'skill', [dev])==[]
    assert not runtime_release.content_violations(str(comp)+'/skills','skill',[dev])


@pytest.mark.parametrize('name', ['AGENTS.md','STATUS.md','.git/config','docs/BUILD.md','experience/global/example.md','skills/demo/AGENTS.md','src/cyberscientist/__pycache__/a.pyc','../secret','/etc/passwd'])
def test_release_allowlist_excludes_development_and_runtime_data(name):
    assert not runtime_release.allowed(name)


def test_scanner_checks_skill_attachments_experience_and_capability_locations(tmp_path):
    (tmp_path/'skills/demo/attachments').mkdir(parents=True)
    (tmp_path/'skills/demo/attachments/check.py').write_text('# CS-UP-18\n')
    exp=tmp_path/'experience';exp.mkdir(exist_ok=True);(exp/'lesson.md').write_text('docs/DEV.md')
    hits=runtime_release.scan_content(tmp_path,[],experience_root=exp,capability_content='D-79')
    assert {item['reason'] for item in hits}=={'development_number','development_docs'}
    assert any(item['location']=='capability_index' for item in hits)


def test_publish_preserves_runtime_data_experience_and_custom_configuration(tmp_path):
    root=tmp_path/'comp';stage=tmp_path/'stage'
    values={'src/cyberscientist/cli.py':'new code','config/workspace.example.yaml':'template','apps/web/dist/index.html':'frontend'}
    for name,body in values.items():
        path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    mutable={'.cyberscientist/secrets.json':'private fixture','experience/global/note.md':'runtime revision','config/workspace.local.yaml':'custom settings'}
    for name,body in mutable.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    manifest={'commit':'a'*40,'files':{name:hashlib.sha256(body.encode()).hexdigest() for name,body in values.items()}}
    version=runtime_release.publish(stage,root,manifest)
    assert version['commit']=='a'*40
    assert all((root/name).read_text()==body for name,body in mutable.items())
    assert all((root/name).read_text()==body for name,body in values.items())
    assert not (root/'.git').exists()


def test_publish_rejects_cache_traversal_and_tampering_before_mutation(tmp_path):
    root=tmp_path/'comp';stage=tmp_path/'stage';stage.mkdir()
    for path in ('apps/web/dist/../../../../secrets.json','../outside.py'):
        with pytest.raises(ValueError,match='白名单'):runtime_release.publish(stage,root,{'commit':'a'*40,'files':{path:'f'*64}})
    path=stage/'src/cyberscientist/cli.py';path.parent.mkdir(parents=True);path.write_text('tampered')
    with pytest.raises(ValueError,match='封存清单'):runtime_release.publish(stage,root,{'commit':'a'*40,'files':{'src/cyberscientist/cli.py':'f'*64}})
    assert not root.exists()


def test_publish_removes_old_owned_evaluation_roots_and_preserves_research(tmp_path):
    root=tmp_path/'comp';stage=tmp_path/'stage'
    files={'src/cyberscientist/cli.py':'new code'}
    old={'evals/suite.json':'old evaluation','challenges/old/reference.json':'old reference'}
    for name,body in files.items():
        path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    for name,body in old.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
    mutable=root/'workspace/challenges/current/description.md'
    mutable.parent.mkdir(parents=True);mutable.write_text('current topic')
    cache=root/'.runtime/releases/old/manifest.json'
    cache.parent.mkdir(parents=True);cache.write_text(json.dumps({'files':old}))
    (root/'.runtime/version.json').write_text(json.dumps({'commit':'old'}))
    runtime_release.publish(stage,root,{'commit':'a'*40,'files':{
        name:hashlib.sha256(body.encode()).hexdigest() for name,body in files.items()}})
    assert not (root/'evals').exists() and not (root/'challenges').exists()
    assert mutable.read_text()=='current topic'
    assert list((root/'.runtime/previous').glob('*/evals/suite.json'))


def test_replacing_same_commit_cache_preserves_prior_manifest_evidence(tmp_path):
    stage=tmp_path/'stage';stage.mkdir()
    (stage/'start-runtime.sh').write_text('current')
    runtime=tmp_path/'runtime';cache=runtime/'releases'/('a'*40)
    cache.mkdir(parents=True)
    previous={'commit':'a'*40,'files':{'evals/old.json':'old'}}
    (cache/'manifest.json').write_text(json.dumps(previous))
    manifest={'commit':'a'*40,'files':{'start-runtime.sh':hashlib.sha256(b'current').hexdigest()}}
    runtime_release.cache_release(stage,runtime,manifest)
    assert json.loads((cache/'manifest.json').read_text())==manifest
    assert (cache/'tree/start-runtime.sh').read_text()=='current'
    assert json.loads(next((runtime/'release-cache-history').glob('*/manifest.json')).read_text())==previous


def test_official_dry_build_never_sends_or_reserves(tmp_path,monkeypatch):
    from test_cli_submission_cs14 import prepare,bundle,fake_build
    from cyberscientist import cli_submission,db
    platform=prepare(tmp_path,monkeypatch);content,_=bundle();calls=[]
    before=db.query_one('SELECT COUNT(*) FROM submissions')[0]
    def process(argv,**kwargs):
        assert '--dry-run' in argv
        calls.append(argv)
        return fake_build(argv)
    monkeypatch.setattr(cli_submission.subprocess,'run',process)
    result=cli_submission.submit(platform,'fixture','private-fixture','unused','ended',
                                 {'package_bytes':content,'dry_run':True})
    assert result['status']=='built' and result['submission_created'] is False
    assert len(calls)==1 and db.query_one('SELECT COUNT(*) FROM submissions')[0]==before


def test_historical_artifacts_are_separate_from_new_run_workspaces(tmp_path,monkeypatch):
    root=deployed(tmp_path,monkeypatch)
    archive=tmp_path/'run-archive'
    (root/'.runtime/run-archive.json').write_text(json.dumps({'root':str(archive),'run_ids':['run_old']}))
    monkeypatch.setattr(config,'WORKSPACE_DIR',root/'workspace')
    assert runtime_layout.run_directory('run_old')==archive/'run_old'
    assert runtime_layout.run_directory('run_new')==root/'workspace/runs/run_new'
    with pytest.raises(ValueError):runtime_layout.run_directory('../secret')


def test_concurrent_release_refuses_before_touching_live_code(tmp_path,monkeypatch):
    import fcntl
    root=tmp_path/'comp';(root/'.runtime').mkdir(parents=True)
    with (root/'.runtime/release.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        monkeypatch.setattr(runtime_release,'_release_locked',lambda *a,**k:pytest.fail('must not enter'))
        result=runtime_release.release('HEAD',root=root,port=8765)
    assert result['phase']=='lock' and result['status']=='failed'


def test_metadata_failure_restores_code_and_prior_version(tmp_path,monkeypatch):
    root=tmp_path/'comp';(root/'.runtime').mkdir(parents=True)
    source=root/'src/cyberscientist/cli.py';source.parent.mkdir(parents=True);source.write_text('old code')
    (root/'.runtime/version.json').write_text(json.dumps({'commit':'b'*40}))
    (root/'.runtime/cyberscientist_launch.py').write_text('old launcher')
    stage=tmp_path/'stage';target=stage/'src/cyberscientist/cli.py';target.parent.mkdir(parents=True);target.write_text('new code')
    original=Path.write_text
    def write(path,*args,**kwargs):
        if path.name=='version.pending':raise OSError('injected disk failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'write_text',write)
    with pytest.raises(OSError,match='injected'):
        runtime_release.publish(stage,root,{'commit':'a'*40,'files':{'src/cyberscientist/cli.py':hashlib.sha256(b'new code').hexdigest()}})
    assert source.read_text()=='old code'
    assert json.loads((root/'.runtime/version.json').read_text())['commit']=='b'*40
    assert (root/'.runtime/cyberscientist_launch.py').read_text()=='old launcher'


def test_pre_competition_commit_is_refused_before_shutdown(tmp_path,monkeypatch):
    root=tmp_path/'comp'
    monkeypatch.setattr(runtime_release,'export',lambda commit,stage,**k:{'commit':'a'*40,'files':{}})
    monkeypatch.setattr(runtime_release,'build_frontend',lambda *a:None)
    monkeypatch.setattr(runtime_release,'stop_runtime',lambda *a:pytest.fail('old backend must remain'))
    result=runtime_release.release('old-tag',root=root,port=8765,source=Path(__file__).resolve().parents[1])
    assert result['status']=='failed' and '发布协议' in result['reason']


async def test_monitor_guidance_reaches_pi_queue_without_executor_delivery():
    import asyncio
    from cyberscientist import db
    from cyberscientist.controller import RunController
    from test_collaboration import _seed_challenge
    _seed_challenge();controller=RunController();rid=controller.create_run('COLLAB_CH')['id']
    db.execute("UPDATE runs SET phase='running' WHERE id=?",(rid,))
    class Executor:
        async def steer(self,*args):pytest.fail('monitor must not steer executor')
        async def prompt(self,*args):pytest.fail('monitor must not prompt executor')
    controller._prime_instances[rid]=Executor();controller._prime_sessions[rid]='native-executor'
    controller._signals[rid]=asyncio.Queue()
    await controller.control(rid,'steer','technical repair facts','monitor-guidance')
    await controller._handle_signal(await controller._signals[rid].get(),rid,controller._signals[rid])
    request=db.query_one("SELECT frame_json FROM review_requests WHERE run_id=? AND trigger='user_steer'",(rid,))
    assert json.loads(request['frame_json'])['user_guidance']=='technical repair facts'


def test_release_updates_native_skill_bytes_without_touching_auth(tmp_path):
    root=tmp_path/'comp';stage=tmp_path/'stage'
    auth=root/'.runtime/codex/auth.json';auth.parent.mkdir(parents=True);auth.write_text('private fixture')
    old=auth.parent/'skills/demo/SKILL.md';old.parent.mkdir(parents=True);old.write_text('old lesson')
    new=stage/'skills/demo/SKILL.md';new.parent.mkdir(parents=True);new.write_text('new lesson')
    manifest={'commit':'a'*40,'files':{'skills/demo/SKILL.md':hashlib.sha256(new.read_bytes()).hexdigest()}}
    runtime_release.publish(stage,root,manifest)
    assert old.read_text()=='new lesson' and auth.read_text()=='private fixture'


def test_archived_run_score_reconciliation_preserves_migrated_notes(tmp_path,monkeypatch):
    from cyberscientist import trial_notes
    root=deployed(tmp_path,monkeypatch)
    monkeypatch.setattr(config,'WORKSPACE_DIR',root/'workspace')
    (root/'.runtime/run-archive.json').write_text(json.dumps({'root':str(tmp_path/'archive'),'run_ids':['run_old']}))
    monkeypatch.setattr(trial_notes.experiences,'save_experience',lambda *a,**k:pytest.fail('archived notes must remain frozen'))
    assert trial_notes.record('run_old','trial_old') is None
    assert not runtime_layout.archived_run('run_new')
