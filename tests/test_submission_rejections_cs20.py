import json
import subprocess

import pytest

from cyberscientist import alerts, cli_submission, config, db, mailboxes
from cyberscientist.mailbox_platform import PlatformError
from test_cli_submission_cs14 import prepare, bundle, fake_build
from test_mailboxes import _make_package, _make_run, _seed_challenge


@pytest.mark.parametrize('stderr,kind',[
    ('error: HTTP 429 Submission limit reached','submission_limit'),
    ('error: HTTP 429 该题已达到提交上限','submission_limit'),
    ('error: Worker 上传的提交包未通过校验；HTTP 400','bundle_validation'),
    ('error: bundle validation failed','bundle_validation'),
    ('error: HTTP 429 too many requests',None),
    ('error: HTTP 400 创建提交记录未通过校验',None),
    ('error: network timed out',None),
])
def test_only_explicit_remote_rejection_is_classified(stderr,kind):
    assert cli_submission.explicit_rejection(1,{'stderr':stderr})==kind
    assert cli_submission.explicit_rejection(0,{'stderr':stderr}) is None


@pytest.mark.parametrize('stderr,kind,known_attempt',[
    ('HTTP 429 Submission limit reached','submission_limit',False),
    ('Worker 上传的提交包未通过校验；HTTP 400 --attempt-id 42','bundle_validation',True),
])
def test_cli_rejection_never_resends_or_loses_known_attempt(tmp_path,monkeypatch,stderr,kind,known_attempt):
    platform=prepare(tmp_path,monkeypatch);content,_=bundle();calls=[];stages=[]
    def process(argv,**kwargs):
        calls.append(argv);built=fake_build(argv)
        return built if '--dry-run' in argv else subprocess.CompletedProcess(argv,1,'',stderr)
    monkeypatch.setattr(cli_submission.subprocess,'run',process)
    with pytest.raises(PlatformError) as caught:
        cli_submission.submit(platform,'fixture','fake-token','unused','ended',{
            'package_bytes':content,'on_stage':lambda *args:stages.append(args)})
    assert caught.value.rejection_kind==kind and len(calls)==2
    assert caught.value.no_side_effect is not known_attempt
    if known_attempt:assert ('cli_unknown','42') in stages


@pytest.mark.parametrize('kind',['submission_limit','bundle_validation'])
def test_definitive_rejection_records_failure_and_correct_account_usage(monkeypatch,kind):
    _seed_challenge();mailboxes.register_experiment(2);rid=_make_run(max_submissions=5)
    _make_package(rid);calls=[]
    from cyberscientist import mailbox_platform
    def reject(*args,**kwargs):
        calls.append(args[0]);raise PlatformError('synthetic explicit rejection',
            no_side_effect=True,rejection_kind=kind)
    monkeypatch.setattr(mailbox_platform,'submit_once',reject)
    first=mailboxes.submit_experiment(rid,'trial_mb1',None,'fixture-reject')
    assert first['status']=='failed' and first['stage']=='rejected_'+kind
    assert first['reservation_released']==1
    again=mailboxes.submit_experiment(rid,'trial_mb1',None,'fixture-reject')
    assert again['id']==first['id'] and len(calls)==1
    event=db.query_one("SELECT payload FROM events WHERE run_id=? AND type='submission.rejected'",(rid,))
    assert not json.loads(event['payload'])['automatic_resend']
    usage={item['mailbox_id']:item for item in mailboxes.mailbox_usage()['items']}
    assert usage[first['mailbox_id']]['used']==0 and usage[first['mailbox_id']]['submitted']==0
    assert usage[first['mailbox_id']]['exhausted']==(kind=='submission_limit')
    assert any(item['kind']=='submission.rejected' for item in alerts.pending())
    if kind=='submission_limit':
        second=mailboxes.submit_experiment(rid,'trial_mb1',None,'fixture-next-submit')
        assert second['mailbox_id']!=first['mailbox_id'] and len(calls)==2
    else:
        assert len(calls)==1


def test_limit_exhaustion_is_per_account_and_frozen_target(monkeypatch):
    _seed_challenge();mailboxes.register_experiment(1);rid=_make_run();_make_package(rid)
    from cyberscientist import mailbox_platform
    monkeypatch.setattr(mailbox_platform,'submit_once',lambda *a,**kw:(_ for _ in ()).throw(
        PlatformError('limit',no_side_effect=True,rejection_kind='submission_limit')))
    first=mailboxes.submit_experiment(rid,'trial_mb1',None,'limit-topic-one')
    from test_mailboxes import _extra_run
    other=_extra_run(2)
    with db.transaction() as conn:
        account=conn.execute('SELECT * FROM mailboxes WHERE id=?',(first['mailbox_id'],)).fetchone()
        assert mailboxes.select_experiment(conn,other,[account])['id']==account['id']
        assert mailboxes.select_experiment(conn,rid,[account]) is None


def test_rejected_worker_attempt_preserves_quota_and_remote_baseline_counts(monkeypatch):
    _seed_challenge();mailboxes.register_experiment(1);rid=_make_run();_make_package(rid)
    from cyberscientist import mailbox_platform
    def reject(*args,**kwargs):
        meta=kwargs['meta'];meta['on_stage']('cli_receipt','new-attempt')
        db.append_event(rid,'controller','submission.cli_baseline',{
            'submission_id':meta['submission_id'],'attempt_ids':['old-one','old-two']})
        raise PlatformError('bundle validation failed',rejection_kind='bundle_validation')
    monkeypatch.setattr(mailbox_platform,'submit_once',reject)
    item=mailboxes.submit_experiment(rid,'trial_mb1',None,'worker-reject')
    assert item['status']=='failed' and item['platform_ref']=='new-attempt'
    assert item['reservation_released']==0
    usage=mailboxes.mailbox_usage()['items'][0]
    assert usage['used']==1 and usage['submitted']==3 and not usage['exhausted']


def test_previously_queued_account_cannot_send_after_confirmed_exhaustion(monkeypatch):
    _seed_challenge();mailboxes.register_experiment(1);rid=_make_run();_make_package(rid)
    from cyberscientist import competition_panel, mailbox_platform, submission_gate
    competition_panel.change(rid,{'action':'submission_hold','value':True,'operation_id':'hold'})
    item=mailboxes.submit_experiment(rid,'trial_mb1',None,'queued-before-limit')
    assert item['status']=='queued'
    with db.transaction() as conn:
        conn.execute('INSERT INTO mailbox_target_exhaustions VALUES(?,?,?,?,?)',(
            mailboxes._account_identity(conn,item['mailbox_id']),mailboxes._challenge_key(conn,rid),
            'external-observed','limit observed',db.utcnow()))
    monkeypatch.setattr(mailbox_platform,'submit_once',lambda *a,**kw:pytest.fail('must not send'))
    competition_panel.change(rid,{'action':'submission_hold','value':False,'operation_id':'unhold'})
    submission_gate.advance_sync()
    result=db.query_one('SELECT * FROM submissions WHERE id=?',(item['id'],))
    assert result['status']=='failed' and result['stage']=='rejected_submission_limit'
