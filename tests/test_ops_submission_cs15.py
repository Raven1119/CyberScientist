"""Bounded old-task authorization guards, using synthetic platform data."""
from datetime import datetime, timedelta, timezone
import pytest
from cyberscientist import config, db, mailboxes, ops_submission
from test_cli_submission_cs14 import bundle
from test_auto_harvest import seed


def request(monkeypatch):
    rid, old = seed(10)
    db.execute("UPDATE runs SET phase='finished' WHERE id=?",(rid,))
    trial=old['trial_id'];db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at) VALUES(?,?,'old task','verified','completed',?)",(trial,rid,db.utcnow()));content,_=bundle(trial)
    db.append_event(rid,'controller','trial.native_session_bound',{'session_id':'native-final'},trial_id=trial)
    path=config.WORKSPACE_DIR/'ops-validation.zip';path.write_bytes(content)
    challenge=mailboxes._run_challenge_id(rid)
    class Platform:
        name=old_platform= db.query_one('SELECT platform FROM mailboxes WHERE id=?',(old['mailbox_id'],))[0]
        def _http(self,*a,**kw): return {'roundEndAt':'2026-01-01T00:00:00Z'}
    monkeypatch.setattr(mailboxes,'_platform_for_run',lambda *a:Platform())
    monkeypatch.setattr(mailboxes,'_perform_submission',lambda sid,*a:dict(db.query_one('SELECT * FROM submissions WHERE id=?',(sid,))))
    grant={'scope_id':'test-old-task','ended_only':True,'max_submissions':1,'targets':[challenge], 'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    return {'run_id':rid,'trial_id':trial,'operation_id':'ops-one','authorization':grant,'package_path':path.name,'mailbox_id':old['mailbox_id']}


def test_finished_task_does_not_reopen_run_and_quota_is_immutable(monkeypatch):
    req=request(monkeypatch)
    before=dict(db.query_one('SELECT * FROM runs WHERE id=?',(req['run_id'],)))
    result=ops_submission.submit(req)
    assert result['validation_scope']=='test-old-task'
    assert dict(db.query_one('SELECT * FROM runs WHERE id=?',(req['run_id'],)))==before
    assert ops_submission.submit(req)['deduplicated']
    with pytest.raises(ValueError,match='额度'):ops_submission.submit(req|{'operation_id':'ops-two'})
    with pytest.raises(ValueError,match='授权文件变化'):
        ops_submission.submit(req|{'operation_id':'ops-two','authorization':req['authorization']|{'max_submissions':2}})


def test_unfinished_task_never_reserves(monkeypatch):
    req=request(monkeypatch)
    p=mailboxes._platform_for_run(req['run_id'])
    monkeypatch.setattr(p,'_http',lambda *a,**k:{'roundEndAt':'2099-01-01T00:00:00Z'})
    monkeypatch.setattr(mailboxes,'_platform_for_run',lambda *a:p)
    with pytest.raises(ValueError,match='已经结束'):ops_submission.submit(req)
    assert not db.query_one('SELECT 1 FROM submissions WHERE operation_id=?',(req['operation_id'],))


def test_foreign_trial_and_cross_account_hash_never_reserve(monkeypatch):
    req=request(monkeypatch)
    foreign= req|{'trial_id':'foreign-trial'}
    with pytest.raises(ValueError,match='不属于此Run'):ops_submission.submit(foreign)
    ops_submission.submit(req)
    new=mailboxes.register_experiment(1)['items'][0]
    larger=req|{'operation_id':'new-scope-intent','mailbox_id':new['id'],'authorization':req['authorization']|{'scope_id':'same-task-another-scope'}}
    with pytest.raises(ValueError,match='同哈希'):ops_submission.submit(larger)
    assert not db.query_one("SELECT 1 FROM submissions WHERE operation_id='new-scope-intent'")


def test_outputs_only_candidate_uses_normal_seal_without_reopening_run(monkeypatch):
    import io,zipfile,hashlib
    req=request(monkeypatch)
    sealed=(config.WORKSPACE_DIR/req['package_path']).read_bytes()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:archive.writestr('outputs/result.json','{"result":1}')
    candidate=stream.getvalue();path=config.WORKSPACE_DIR/'approved-candidate.zip';path.write_bytes(candidate)
    before=dict(db.query_one('SELECT * FROM runs WHERE id=?',(req['run_id'],)))
    seen=[]
    def preflight(run_id,trial_id,package_path):
        seen.append((run_id,trial_id,package_path))
        assert path.read_bytes()==candidate
        return {'error_code':None,'sealed_bytes':sealed}
    monkeypatch.setattr(mailboxes,'preflight_submission',preflight)
    result=ops_submission.submit(req|{'package_path':path.name})
    assert seen==[(req['run_id'],req['trial_id'],str(path))]
    assert result['package_sha256']==hashlib.sha256(sealed).hexdigest()
    assert path.read_bytes()==candidate
    assert dict(db.query_one('SELECT * FROM runs WHERE id=?',(req['run_id'],)))==before
