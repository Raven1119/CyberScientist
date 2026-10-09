"""Output-only sealing and the pinned CLI build, with explicit native fixtures."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from cyberscientist import (cli_submission, config, db, mcp_bridge, native_logs,
    ops_digest, package_seal, progressive_context, submission_outputs,
    platform_contracts, trace_selection, clean_runs, mailboxes)
from cyberscientist.codex_protocol import thread_params
from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform
from test_mailboxes import _seed_challenge, _make_run


def zip_bytes(files):
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w') as archive:
        for name,body in files.items():archive.writestr(name,body)
    return result.getvalue()


def seed_native(tmp_path):
    _seed_challenge();rid=_make_run();tid='trial_outputs'
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at) VALUES(?,?,'fixture','fixture','active',?)",(tid,rid,db.utcnow()))
    rows=[{'type':'session_meta','payload':{'id':'fixture-output-session'}},
          {'type':'response_item','payload':{'type':'message','role':'assistant',
              'content':[{'type':'output_text','text':'Synthetic application fixture; no science or remote operation was run.'}]}}]
    raw=('\n'.join(json.dumps(row) for row in rows)+'\n').encode()
    path=tmp_path/'native.jsonl';path.write_bytes(raw)
    ops_digest.record_session(rid,'executor','fixture-output-session',{
        'native_log_path':str(path),'model':'gpt-5.6-terra'})
    native_logs.bind_trial(rid,tid,'fixture-output-session')
    return rid,tid,raw


@pytest.mark.parametrize('wrapper',['','bundle/'])
def test_output_only_sealing_generates_schema_valid_manifest_and_preserves_source(tmp_path,wrapper):
    rid,tid,raw=seed_native(tmp_path)
    science=b'{"answer":42}\n'
    source=zip_bytes({wrapper+'outputs/answer.json':science})
    sealed,_=package_seal.seal(source,rid,tid,0)
    with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
        manifest=json.loads(archive.read(wrapper+'arm_manifest.json'))
        assert archive.read(wrapper+'outputs/answer.json')==science
        assert archive.read(wrapper+'raw_messages.jsonl')==raw
        assert manifest['expected_outputs']==[{'name':'outputs/answer.json','path':'outputs/answer.json','type':'data'}]
        assert manifest['entrypoint']=='' # No invented execution script.
        assert archive.read(wrapper+package_seal.TRACE)
    assert platform_contracts.validate_bundle(sealed)['valid']
    assert list(zipfile.ZipFile(io.BytesIO(source)).namelist())==[wrapper+'outputs/answer.json']
    assert trace_selection.bundle_root({'outputs/answer.json':science})==''
    manifest,actual,_=cli_submission._files(sealed)
    staged=submission_outputs.stage(sealed,tmp_path/'stage',manifest)
    assert staged['sha256']=={'outputs/answer.json':hashlib.sha256(science).hexdigest()}
    assert actual==raw


def test_existing_executor_manifest_keeps_its_original_scientific_fields(tmp_path):
    rid,tid,_=seed_native(tmp_path)
    original={'arm_version':'1.1','paper':{'title':'Executor declaration'},'entrypoint':'work.py',
              'expected_outputs':[{'name':'chosen','path':'outputs/answer.json','type':'data'}]}
    source=zip_bytes({'arm_manifest.json':json.dumps(original),'work.py':'print(42)',
                      'outputs/answer.json':'{"answer":42}'})
    sealed,_=package_seal.seal(source,rid,tid,0)
    with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
        actual=json.loads(archive.read('arm_manifest.json'))
    assert {key:actual[key] for key in original}==original


def test_submission_preflight_accepts_output_only_source_with_native_binding(tmp_path):
    rid,tid,raw=seed_native(tmp_path)
    path=config.WORKSPACE_DIR/'runs'/rid/'trials'/tid/'result_package.zip'
    path.parent.mkdir(parents=True)
    source=zip_bytes({'outputs/answer.json':'{"answer":42}'})
    path.write_bytes(source)
    report=mailboxes.preflight_submission(rid,tid,str(path))
    assert report['error_code'] is None
    assert report['source_package_sha256']==hashlib.sha256(source).hexdigest()
    assert cli_submission._files(report['sealed_bytes'])[1]==raw
    assert path.read_bytes()==source


def test_real_pinned_cli_build_contains_only_outputs_and_native_fixture(tmp_path,monkeypatch):
    rid,tid,raw=seed_native(tmp_path)
    science=b'{"answer":42}\n'
    sealed,_=package_seal.seal(zip_bytes({'outputs/answer.json':science}),rid,tid,0)
    platform=BohriumPlaygroundPlatform('https://play.bohrium.com/api')
    monkeypatch.setattr(platform,'_http',lambda method,path,**kw:
        {'id':'fixture-owner'} if path=='/auth/me' else {'attempts':[],'total':0})
    calls=[];packages=[];real_run=subprocess.run
    def dry_run_only(argv,**kwargs):
        assert '--dry-run' in argv
        calls.append(argv)
        return real_run(argv,**kwargs)
    monkeypatch.setattr(cli_submission.subprocess,'run',dry_run_only)
    result=cli_submission.submit(platform,'fixture','synthetic-fixture-token','unused','ended-fixture',{
        'package_bytes':sealed,'dry_run':True,'on_package':lambda content,meta:packages.append(content)})
    assert result['dry_run'] and not result['submission_created'] and len(calls)==1
    assert result['native_sha256']==hashlib.sha256(raw).hexdigest()
    assert result['outputs']=={'outputs/answer.json':hashlib.sha256(science).hexdigest()}
    with zipfile.ZipFile(io.BytesIO(packages[0])) as archive:
        assert archive.read('outputs/answer.json')==science
        assert not any(package_seal.TRACE in name or 'trace_narrative.jsonl' in name for name in archive.namelist())


def test_competition_executor_hides_narrative_tool_on_both_mcp_layers(monkeypatch):
    monkeypatch.setenv('CS_TOOL_ROLE','executor');monkeypatch.setenv('CS_EVIDENCE_MODE','competition')
    monkeypatch.delenv('CS_PUBLIC_RESEARCH_PROBE',raising=False)
    tools=mcp_bridge._handle({'jsonrpc':'2.0','id':1,'method':'tools/list'})['result']['tools']
    assert 'research_trace_narrative_check' not in {tool['name'] for tool in tools}
    server={'name':'cyberscientist','command':'python','args':[]}
    params=thread_params({'mcp_servers':[server],'evidence_mode':'competition'},'fixture','xhigh',writable=True)
    assert 'research_trace_narrative_check' not in params['config']['mcp_servers']['cyberscientist']['enabled_tools']
    monkeypatch.setenv('CS_EVIDENCE_MODE','development')
    tools=mcp_bridge._handle({'jsonrpc':'2.0','id':1,'method':'tools/list'})['result']['tools']
    assert 'research_trace_narrative_check' in {tool['name'] for tool in tools}


def test_exploration_and_clean_prompts_share_output_contract_instruction():
    _seed_challenge();rid=_make_run()
    exploration=progressive_context.executor_prompt(rid,'trial_prompt',{},'method','check',{},[],{})
    clean=clean_runs.prompt({},dict.fromkeys(clean_runs.FIELDS,'method'),[],'index',
        run_id=rid,trial_id='trial_prompt',delivery_directory='delivery',environment_index=[])
    assert package_seal.OUTPUT_PACKAGE_INSTRUCTION in exploration
    assert package_seal.OUTPUT_PACKAGE_INSTRUCTION in clean
