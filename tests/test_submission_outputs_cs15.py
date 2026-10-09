"""Synthetic protocol tests; these are not platform receipts."""
import io,json,zipfile
from datetime import datetime,timedelta,timezone
import pytest
from cyberscientist import submission_outputs as outputs,cli_submission,db
from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform


def package(files):
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w') as archive:
        archive.writestr('arm_manifest.json','{}')
        for path,body in files.items(): archive.writestr(path,body)
    return result.getvalue()


def test_task_contract_excludes_undeclared_private_and_normalizes_app_path(tmp_path):
    content=package({'app/outputs/a.json':'{"n":1}','outputs/debug.txt':'debug','secret.env':'private'})
    stage=tmp_path/'stage';stage.mkdir()
    staged=outputs.stage(content,stage,{'expected_outputs':[{'path':'outputs/debug.txt'}]},contract={'paths':['/app/outputs/a.json']})
    assert sorted(p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file())==['a.json']
    assert staged['excluded_declared']==['outputs/debug.txt']
    outputs.verify_built(package({'outputs/a.json':'{"n":1}'}),staged['sha256'])
    with pytest.raises(ValueError,match='不一致'):
        outputs.verify_built(package({'outputs/a.json':'{"n":2}'}),staged['sha256'])


def test_explicit_app_root_output_is_staged_alone_with_cli_prefix(tmp_path):
    content=package({'submission.json':'{"witness":1}','contract_report.json':'diagnostic','private.env':'secret'})
    stage=tmp_path/'stage'
    staged=outputs.stage(content,stage,{},contract={'paths':['/app/submission.json']})
    assert staged['included']==['outputs/submission.json']
    assert [p.name for p in stage.iterdir()]==['submission.json']
    outputs.verify_built(package({'outputs/submission.json':'{"witness":1}'}),staged['sha256'])
    with pytest.raises(ValueError):outputs.stage(content,stage,{},contract={'paths':['/app/../private.env']})


def test_fenced_write_directive_is_available_as_task_contract():
    from cyberscientist import artifact_contracts
    text='Write exactly one machine-readable witness to:\n\n```text\n/app/submission.json\n```\n'
    assert artifact_contracts.inspect('',task_content=text)['task_paths']==['/app/submission.json']


@pytest.mark.parametrize('files,contract',[
    ({'outputs/a.json':'bad json'},{'paths':['outputs/a.json'],'json_schemas':{'outputs/a.json':{'type':'object'}}}),
    ({'outputs/a.json':'{}'},{'paths':['outputs/missing.json']}),
    ({'outputs/a.json':'{}'},{'paths':['outputs/../a.json']}),
    ({'outputs/a.json':'{"API_KEY":"synthetic-credential"}'},{'paths':['outputs/a.json']}),
])
def test_invalid_outputs_rejected_before_network(tmp_path,files,contract):
    with pytest.raises(Exception): outputs.stage(package(files),tmp_path,{},contract=contract)


def test_unknown_ten_minute_complete_absence_releases_once(monkeypatch):
    from test_auto_harvest import seed
    rid,source=seed(10)
    db.execute("UPDATE submissions SET status='unknown',platform_ref=NULL,created_at=? WHERE id=?",((datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat(),source['id']))
    db.append_event(rid,'controller','submission.cli_baseline',{'submission_id':source['id'],'owner_id':'owner','attempt_ids':[]})
    db.append_event(rid,'controller','submission.stage',{'submission_id':source['id'],'stage':'create_sent'})
    db.execute("UPDATE events SET occurred_at=? WHERE run_id=? AND type='submission.stage'",((datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat(),rid))
    p=BohriumPlaygroundPlatform('https://play.bohrium.com/api')
    monkeypatch.setattr(cli_submission,'account_attempts',lambda *a:{'owner_id':'owner','attempts':[],'complete':True})
    got=cli_submission.reconcile_unknown(source['id'],p,'private','ended')
    assert got['status']=='not_stored_inferred' and got['retry_allowed']
    assert db.query_one('SELECT reservation_released FROM submissions WHERE id=?',(source['id'],))[0]==1
    db.execute('UPDATE submissions SET retry_of=? WHERE id=?',(source['id'],source['id']))
    assert not cli_submission.reconcile_unknown(source['id'],p,'private','ended')['retry_allowed']


def test_old_reservation_does_not_release_a_fresh_send(monkeypatch):
    from test_auto_harvest import seed
    rid,source=seed(10)
    db.execute("UPDATE submissions SET status='unknown',platform_ref=NULL,created_at=? WHERE id=?",((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),source['id']))
    db.append_event(rid,'controller','submission.cli_baseline',{'submission_id':source['id'],'owner_id':'owner','attempt_ids':[]})
    db.append_event(rid,'controller','submission.stage',{'submission_id':source['id'],'stage':'create_sent'})
    p=BohriumPlaygroundPlatform('https://play.bohrium.com/api')
    monkeypatch.setattr(cli_submission,'account_attempts',lambda *a:{'owner_id':'owner','attempts':[],'complete':True})
    assert cli_submission.reconcile_unknown(source['id'],p,'private','ended')['status']=='absence_observed'
    assert db.query_one('SELECT reservation_released FROM submissions WHERE id=?',(source['id'],))[0]==0


def test_unknown_with_known_attempt_never_authorizes_resend(monkeypatch):
    from test_auto_harvest import seed
    rid,source=seed(10)
    db.execute("UPDATE submissions SET status='unknown',platform_ref='known-remote' WHERE id=?",(source['id'],))
    db.append_event(rid,'controller','submission.cli_baseline',{'submission_id':source['id'],'owner_id':'owner','attempt_ids':[]})
    db.append_event(rid,'controller','submission.stage',{'submission_id':source['id'],'stage':'create_sent'})
    db.execute("UPDATE events SET occurred_at=? WHERE run_id=? AND type='submission.stage'",((datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat(),rid))
    p=BohriumPlaygroundPlatform('https://play.bohrium.com/api')
    monkeypatch.setattr(cli_submission,'account_attempts',lambda *a:{'owner_id':'owner','attempts':[],'complete':True})
    result=cli_submission.reconcile_unknown(source['id'],p,'private','ended')
    assert not result['retry_allowed'] and result['status']=='absence_observed'
    assert db.query_one('SELECT reservation_released FROM submissions WHERE id=?',(source['id'],))[0]==0
