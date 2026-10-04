"""Job grading uses backend downloads and the same immutable score plan."""
import hashlib,json,zipfile
from pathlib import Path
import pytest
from cyberscientist import compute,config,db,executor_scoring,local_scoring
from test_final_candidate_integrity import _run_with_scorer


@pytest.mark.parametrize('tamper',[None,'command','hash','identity','exit','multiple_json','download'])
def test_job_output_is_formal_only_after_system_download_and_verification(monkeypatch,tamper):
    rid,tid,_,_,manifest=_run_with_scorer()
    prepared=executor_scoring.prepare(rid,tid,'job-grade','job',channel='job')
    stored=json.loads(db.query_one('SELECT plan_json FROM executor_score_plans')[0]);plan=stored['plan']
    result={'schema_version':1,'inputs':dict(plan['inputs']),'environment_identity':dict(plan['identity']),
            'science':{'score':51,'components':{},'confidence':'high','notes':'synthetic Job receipt','scorer_version':plan['scorer_version']}}
    if tamper=='hash':result['inputs']['science_package.zip']='0'*64
    if tamper=='identity':result['environment_identity']={'fake':'version'}
    spec={'command':'echo forged' if tamper=='command' else prepared['command'],'image_address':prepared['image_address']}
    now=db.utcnow()
    db.execute('INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,spec_json,input_directory,platform_job_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,\'Finished\',?,?)',
               ('job-original',rid,tid,'hash',json.dumps(spec),prepared['input_directory'],555,now,now))
    def native(args,**kwargs):
        assert args[:2]==['job','download']
        destination=Path(args[args.index('-o')+1])/'555';destination.mkdir(parents=True,exist_ok=True)
        output=json.dumps(result)+ ('\n{}' if tamper=='multiple_json' else '')
        with zipfile.ZipFile(destination/'out.zip','w') as archive:
            archive.writestr('results/score.json',output)
            archive.writestr('results/execution.json',json.dumps({'exit_code':1 if tamper=='exit' else 0}))
        return {'ok':tamper!='download','exit_code':0,'stdout':'fixture','stderr':''}
    monkeypatch.setattr(compute,'_native',native)
    if tamper:
        with pytest.raises(local_scoring.LocalScoreError):executor_scoring.register_job(rid,tid,'job-grade','job-original')
        assert not db.query('SELECT * FROM local_scores')
    else:
        score=executor_scoring.register_job(rid,tid,'job-grade','job-original')
        assert score['science_score']==51 and score['score_source']=='executor_verified'
        assert db.query_one('SELECT COUNT(*) FROM job_score_receipts')[0]==1
        assert executor_scoring.register_job(rid,tid,'job-grade','job-original')['deduplicated']


@pytest.mark.parametrize('layout,tamper',[('flat',False),('nested',False),('flat',True)])
def test_prepared_job_runner_checks_real_stage_layout_before_synthetic_scorer(monkeypatch,tmp_path,layout,tamper):
    """Execute application glue with a tiny fixture, never scientific scoring."""
    import shutil,subprocess
    rid,tid,_,_,_=_run_with_scorer()
    prepared=executor_scoring.prepare(rid,tid,'layout-grade','job',channel='job')
    stored=json.loads(db.query_one('SELECT plan_json FROM executor_score_plans')[0]);plan=stored['plan']
    job=tmp_path/'remote-job';job.mkdir()
    inputs=job/'input' if layout=='nested' else job;inputs.mkdir(exist_ok=True)
    # Replace only the test fixture scorer before preparing a fresh frozen plan.
    scorer=Path(config.WORKSPACE_DIR)/'challenges/MB_CH/scorer/score.py'
    fixture=b'import json,sys;assert open(sys.argv[1],"rb").read(2)==b"PK";print(json.dumps({"fixture": True}))\n'
    scorer.write_bytes(fixture)
    prepared=executor_scoring.prepare(rid,tid,'layout-grade-fixture','job',channel='job')
    for name in plan['inputs']:shutil.copy2(Path(prepared['input_directory'])/name,inputs/name)
    if tamper:(inputs/'science_package.zip').write_bytes(b'not-the-frozen-input')
    process=subprocess.run(prepared['command'],shell=True,cwd=job,capture_output=True,text=True,timeout=10)
    if tamper:
        assert process.returncode!=0 and not (job/'results/score.json').read_text()
        assert 'hash mismatch' in process.stderr
    else:
        assert process.returncode==0,process.stderr
        output=json.loads((job/'results/score.json').read_text())
        assert output['science']=={'fixture':True}
        assert json.loads((job/'results/execution.json').read_text())=={'exit_code':0}
