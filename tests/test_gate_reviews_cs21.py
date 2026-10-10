import hashlib
import json
import pytest
from cyberscientist import db, gate_reviews, mailboxes, native_logs
from test_pi_wake_cs21 import setup_run


def install_submission(monkeypatch, rid, root, *, hard=False):
    path = root / 'result_package.zip'; path.write_bytes(b'unchanged candidate')
    monkeypatch.setattr(mailboxes, '_resolve_package', lambda *args: path)
    monkeypatch.setattr('cyberscientist.config.sensitive_values', lambda: ['fixture-secret-long-enough'] if hard else [])
    text = json.dumps({'text': 'fixture-secret-long-enough' if hard else 'public fixture Bearer ' + 'q'*25})
    calls = []
    def submit_experiment(run_id, trial_id, package_path, operation_id):
        native_logs.assert_safe(text, run_id=run_id, trial_id=trial_id, source='native.jsonl')
        calls.append(operation_id)
        return {'status': 'submitted'}
    submit_experiment.__module__ = 'cyberscientist.mailboxes'
    monkeypatch.setattr(mailboxes, 'submit_experiment', submit_experiment)
    return submit_experiment, path, calls


@pytest.mark.asyncio
async def test_shape_release_continues_original_intent_once_and_notifies_pi(monkeypatch):
    rid,root,controller=setup_run()
    fn,path,calls=install_submission(monkeypatch,rid,root)
    before=path.read_bytes()
    with pytest.raises(ValueError):
        await mailboxes.submit_async(fn,rid,'trial_mb1',str(path),'original-op')
    item=gate_reviews.pending()['items'][0]
    assert item['source']=='native.jsonl' and item['line']==1 and item['risk']=='high'
    gate_reviews.resolve(item['id'],false_positive=True,reason='公开合成示例')
    result=await gate_reviews.continue_resolved(item['id'],controller)
    assert result[0]['status']=='submitted' and calls==['original-op'] and path.read_bytes()==before
    assert await gate_reviews.continue_resolved(item['id'],controller)==[]
    from cyberscientist import pi_wake
    pi_wake.collect(controller,rid)
    row=db.query_one("SELECT frame_json FROM review_requests WHERE run_id=? AND status='pending' ORDER BY rowid DESC LIMIT 1",(rid,))
    assert 'gate.resolved' in json.loads(row['frame_json'])['wake_reasons']


@pytest.mark.asyncio
async def test_changed_candidate_is_not_automatically_sent(monkeypatch):
    rid,root,controller=setup_run();fn,path,calls=install_submission(monkeypatch,rid,root)
    with pytest.raises(ValueError):await mailboxes.submit_async(fn,rid,'trial_mb1',str(path),'original-op')
    item=gate_reviews.pending()['items'][0];gate_reviews.resolve(item['id'],false_positive=True,reason='example')
    path.write_bytes(b'changed candidate')
    result=await gate_reviews.continue_resolved(item['id'],controller)
    assert result[0]['status']=='blocked' and '变化' in result[0]['reason'] and not calls


@pytest.mark.asyncio
async def test_hard_credential_stays_blocked(monkeypatch):
    rid,root,_=setup_run();fn,path,calls=install_submission(monkeypatch,rid,root,hard=True)
    with pytest.raises(ValueError):await mailboxes.submit_async(fn,rid,'trial_mb1',str(path),'original-op')
    item=gate_reviews.pending()['items'][0]
    with pytest.raises(ValueError,match='禁止人工放行'):gate_reviews.resolve(item['id'],false_positive=True,reason='no')
    assert await gate_reviews.continue_resolved(item['id'])==[] and not calls


@pytest.mark.parametrize('kind,payload', [
    ('submission.preflight_failed',{'code':'PLATFORM_SCHEMA_INVALID','source_package_sha256':'sha'}),
    ('submission.rejected',{'rejection_kind':'invalid_bundle','reason':'明确拒收'}),
    ('job.preflight',{'status':'blocked','code':'MPI_SLOTS','message':'oversubscription'}),
    ('admission.blocked',{'code':'ENTRYPOINT'})])
def test_all_automatic_blocks_enter_same_queue(kind,payload):
    rid,_,_=setup_run();event=db.append_event(rid,'controller',kind,payload,trial_id='trial_mb1')
    item=gate_reviews.pending()['items'][0]
    assert item['source']==f"event:{rid}:{event['seq']}" and item['rule'].startswith(kind) and item['context']


def test_neighbor_unknown_shapes_are_redacted(monkeypatch):
    monkeypatch.setattr('cyberscientist.config.sensitive_values',lambda:[])
    prefix='asp_'+'z'*25
    item=gate_reviews.record('token_prefix','hash',source='native',context='neighbor '+prefix+' end')
    assert prefix not in item['context']


@pytest.mark.asyncio
@pytest.mark.parametrize('known_status, released, expected_send', [('failed',1,True),('unknown',0,False)])
async def test_known_rejection_can_continue_but_unknown_is_never_replayed(monkeypatch,known_status,released,expected_send):
    rid,root,controller=setup_run();fn,path,calls=install_submission(monkeypatch,rid,root)
    bid=mailboxes.register_experiment(1)['items'][0]['id']
    db.execute('INSERT INTO submissions(id,run_id,trial_id,mailbox_id,package_path,package_sha256,status,operation_id,created_at,reservation_released) VALUES(?,?,?,?,?,?,?,?,?,?)',
               ('old-sub',rid,'trial_mb1',bid,str(path),'hash',known_status,'original-op',db.utcnow(),released))
    with pytest.raises(ValueError): await mailboxes.submit_async(fn,rid,'trial_mb1',str(path),'original-op')
    item=gate_reviews.pending()['items'][0];gate_reviews.resolve(item['id'],false_positive=True,reason='单项误报')
    result=await gate_reviews.continue_resolved(item['id'],controller)
    if expected_send:
        assert len(calls)==1 and calls[0].startswith('original-op-review-') and result[0]['status']=='submitted'
    else:
        assert not calls and result[0]['status']=='blocked' and '未知' in result[0]['reason']
