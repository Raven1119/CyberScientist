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
