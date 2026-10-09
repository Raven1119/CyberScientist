import json
from copy import deepcopy

from cyberscientist import alerts, challenge_context, config, db, progressive_context, submission_receipts
from cyberscientist.controller import RunController
from test_mailboxes import _seed_challenge, _make_run


def test_model_frames_strip_current_and_frozen_platform_metadata_without_changing_database():
    _seed_challenge();rid=_make_run()
    raw={'scoring':{'method':'incorrect-platform-metadata'},'challenge':{
         'scoring':{'method':'nested-incorrect-metadata'}},
         'output_contract':{'json_schemas':{'answer.json':{'properties':{'scoring':{'type':'number'}}}}}}
    encoded=json.dumps(raw)
    db.execute('UPDATE challenges SET platform_snapshot_json=? WHERE id=?',(encoded,'MB_CH'))
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0])
    snapshot['competition']={'challenge_snapshot':{'title':'Frozen title','content':'Frozen scientific body',
        'resources':[],'platform':raw}}
    frozen=json.dumps(snapshot)
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(frozen,rid))
    run=db.query_one('SELECT * FROM runs WHERE id=?',(rid,))
    controller=RunController();task=controller._challenge_for_run(run)
    assert 'incorrect-platform-metadata' not in json.dumps(task)
    assert task['science_scoring_fact']==challenge_context.SCORING_FACT
    projected=json.loads(task['platform_snapshot_json'])
    assert projected['output_contract']==raw['output_contract']
    packet=controller._lifecycle_packet(run,'run_start')
    assert 'incorrect-metadata' not in json.dumps(packet)
    assert 'incorrect-platform-metadata' not in json.dumps(packet)
    assert packet['challenge']['content']=='Frozen scientific body'
    compact=progressive_context.compact(rid,packet)
    reference=compact['progressive_disclosure']['source']
    stored=(config.WORKSPACE_DIR/'runs'/rid/'facts'/reference['path']).read_text()
    assert 'incorrect-platform-metadata' not in stored and 'nested-incorrect-metadata' not in stored
    assert db.query_one('SELECT platform_snapshot_json FROM challenges WHERE id=?',('MB_CH',))[0]==encoded
    assert db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0]==frozen


def test_projection_does_not_mutate_source_or_remove_scientific_contract_fields():
    source={'challenge':{'platform_snapshot':{'scoring':{'bad':True},
        'output_contract':{'fields':['scoring']}}},'scorecard':{'scoring':{'real_receipt':True}}}
    old=deepcopy(source);projected=challenge_context.project(source)
    assert source==old
    assert 'scoring' not in projected['challenge']['platform_snapshot']
    assert projected['challenge']['platform_snapshot']['output_contract']==old['challenge']['platform_snapshot']['output_contract']
    assert projected['scorecard']==source['scorecard']


def test_missing_harbor_receipt_alert_is_once_and_does_not_turn_queued_into_failure():
    from test_auto_harvest import seed
    rid,sub=seed(10)
    db.execute("UPDATE submissions SET harbor_score=NULL,receipt_details_json='{}' WHERE id=?",(sub['id'],))
    def observe(body):
        with db.transaction() as conn:
            submission_receipts.observe_tx(conn,conn.execute('SELECT * FROM submissions WHERE id=?',(sub['id'],)).fetchone(),body)
    observe({'scoringState':{'scoreIsFinal':False}})
    assert not db.query_one("SELECT 1 FROM events WHERE type='submission.harbor_missing'")
    receipt={'scoringState':{'scoreIsFinal':True,'displayScore':70},
             'scorecard':{'trace_score':70,'trace_decision':'accept'}}
    observe(receipt);observe(receipt)
    events=db.query("SELECT payload FROM events WHERE type='submission.harbor_missing'")
    assert len(events)==1 and '赛后补交' in json.loads(events[0]['payload'])['reason']
    assert any(item['kind']=='submission.harbor_missing' for item in alerts.pending())
    row=db.query_one('SELECT * FROM submissions WHERE id=?',(sub['id'],))
    assert row['harbor_score'] is None and row['status']=='submitted'
    observe({'scorecard':{'harbor_score':91}})
    assert db.query_one('SELECT harbor_score FROM submissions WHERE id=?',(sub['id'],))[0]==91
