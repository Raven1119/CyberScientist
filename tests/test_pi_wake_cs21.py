import json
from datetime import datetime, timedelta, timezone
from cyberscientist import config, db, pi_wake, alerts
from cyberscientist.controller import RunController
from test_mailboxes import _seed_challenge, _make_run


def setup_run():
    _seed_challenge(); rid = _make_run()
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at) VALUES('trial_mb1',?,'test','test','active',?)",(rid,db.utcnow()))
    db.execute("UPDATE runs SET current_trial_id='trial_mb1' WHERE id=?",(rid,))
    db.execute('UPDATE challenges SET platform_snapshot_json=? WHERE id=?',
               (json.dumps({'output_contract': {'paths': ['/app/a.json', '/app/b.json']}}), 'MB_CH'))
    db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?", (rid,))
    root = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / 'trial_mb1'
    root.mkdir(parents=True,exist_ok=True)
    return rid,root,RunController()


def test_compute_wakeup_does_not_require_checkpoint():
    rid,_,controller = setup_run()
    db.append_event(rid,'controller','job.observed',{'operation_id':'job-done','status':'Finished','remote':{'exitCode':0,'spendTime':65},'files':['a.json']})
    req = pi_wake.collect(controller,rid)
    assert req
    event = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='compute.finished'",(rid,))
    facts = json.loads(event['payload']);assert facts['exit_code']==0 and facts['duration_seconds']==65 and facts['files']==['a.json']
    db.append_event(rid,'controller','job.observed',{'operation_id':'job-done','status':'Finished'})
    assert pi_wake.collect(controller,rid) is None


def test_deliverables_update_and_compute_coalesce():
    rid,root,controller = setup_run()
    pi_wake.collect(controller,rid)
    (root/'a.json').write_text('{}');(root/'b.json').write_text('{}')
    db.append_event(rid,'controller','sandbox.background_polled',{'operation_id':'box-command','status':'completed','exit_code':0,'elapsed_seconds':5})
    req = pi_wake.collect(controller,rid)
    frame=json.loads(db.query_one('SELECT frame_json FROM review_requests WHERE id=?',(req,))['frame_json'])
    assert set(frame['wake_reasons'])=={'compute.finished','deliverables.ready'}
    assert db.query_one("SELECT COUNT(*) FROM review_requests WHERE run_id=? AND status='pending'",(rid,))[0]==1
    (root/'a.json').write_text('{"changed":true}')
    assert pi_wake.collect(controller,rid)==req
    assert pi_wake.collect(controller,rid) is None


def test_periodic_review_uses_interval_and_recent_actions():
    rid,_,controller = setup_run();now=datetime.now(timezone.utc)
    db.execute('UPDATE runs SET started_at=?,created_at=? WHERE id=?',((now-timedelta(minutes=31)).isoformat(),(now-timedelta(minutes=31)).isoformat(),rid))
    db.append_event(rid,'prime','prime.execution.progress',{'detail':'working'})
    req=pi_wake.collect(controller,rid,now=now)
    extra=json.loads(db.query_one('SELECT frame_json FROM review_requests WHERE id=?',(req,))['frame_json'])
    assert extra['wake_reasons']==['pi.periodic_review']
    assert 'prime.execution.progress' in extra['wake_messages'][0]
    assert pi_wake.collect(controller,rid,now=now+timedelta(minutes=1)) is None


def test_cadence_first_submission_alert_and_frame():
    rid,root,controller=setup_run();now=datetime.now(timezone.utc)
    (root/'a.json').write_text('{}');(root/'b.json').write_text('{}')
    approved=(now-timedelta(minutes=91)).isoformat()
    db.execute("INSERT INTO method_approvals(run_id,status,version,proposal_json,approved_at,updated_at) VALUES(?,'approved',1,'{}',?,?)",(rid,approved,approved))
    bits=pi_wake.cadence(rid,now=now)
    assert bits['submission_count']==0 and bits['elapsed_seconds']==5460
    assert '首次提交待办' in bits['cadence_md'] and '最近回执：尚无' in bits['cadence_md']
    pi_wake.collect(controller,rid,now=now)
    assert any(a['title']=='首次提交待办' for a in alerts.pending())
    packet=controller._lifecycle_packet(controller._require_run(rid),'review')
    assert '节奏：方法批准后已' in packet['cadence_md']


def test_cadence_reads_actual_sent_count_and_receipt():
    from cyberscientist import mailboxes
    rid,_,_=setup_run(); now=datetime.now(timezone.utc)
    box=mailboxes.register_experiment(1)['items'][0]
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0])
    snapshot['roundEndAt']=(now+timedelta(hours=2)).isoformat()
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(snapshot),rid))
    db.execute("INSERT INTO submissions(id,run_id,trial_id,mailbox_id,package_path,package_sha256,status,created_at,submitted_at,harbor_score,platform_status) VALUES('cadence-sub',?,'trial_mb1',?,'fixture','fixture','submitted',?,?,75,'scoring')",(rid,box['id'],now.isoformat(),(now-timedelta(minutes=10)).isoformat()))
    bits=pi_wake.cadence(rid,now=now)
    assert bits['submission_count']==1 and bits['since_last_submission_seconds']==600
    assert bits['remaining_seconds']==7200 and '科学分=75' in bits['receipt_summary']
    assert not bits['first_submission_due']
