import asyncio
import pytest
from cyberscientist import collab, db
from test_pi_wake_cs21 import setup_run
from test_collaboration import FakeExecutor


@pytest.mark.parametrize('kind,intent', [('steer','reframe'),('steer','change_direction'),('steer','deliver_before_submit'),('stop','continue')])
async def test_urgent_delivery_enters_busy_turn_and_can_ack(kind,intent):
    rid,_,controller=setup_run();executor=FakeExecutor()
    controller._prime_instances[rid]=executor;controller._prime_sessions[rid]='busy-turn'
    controller._executor_busy[rid]=True
    command_finished=asyncio.Event()
    command=asyncio.create_task(command_finished.wait())
    with db.transaction() as conn:
        gid=collab.create_guidance(conn,rid,source='requested',g={
            'kind':kind,'intent':intent,'text_md':'明确的紧急指导','reason_md':'需要及时交付',
            'evidence_refs':[],'expected_change_md':'调整','revisit_when_md':'有异议'},
            target_trial_id='trial_mb1',review_request_id=None,frame_id=None,
            state_version=0,evidence_revision=0,shadow_epoch=0)
    if kind=='stop':db.execute("UPDATE runs SET gate='stopped' WHERE id=?",(rid,))
    try:
        await controller._deliver_queued_guidance(rid)
        assert not command.done() and len(executor.steers)==1 and not executor.prompts
        g=db.query_one('SELECT * FROM guidance WHERE id=?',(gid,))
        assert g['status']=='sent' and g['delivery_channel']=='busy_insert'
        assert gid in executor.steers[0] and 'ack_guidance' in executor.steers[0]
        ack=collab.ack_guidance(rid, {'schema_version':1,'message_type':'guidance_ack',
            'guidance_id':gid,'disposition':'accepted','reason_md':'接受紧急指导'})
        assert ack['status']=='acknowledged'
        await controller._deliver_queued_guidance(rid)
        assert len(executor.steers)==1
    finally:
        command_finished.set();await command


async def test_ordinary_note_stays_queued_while_busy():
    rid,_,controller=setup_run();executor=FakeExecutor()
    controller._prime_instances[rid]=executor;controller._prime_sessions[rid]='busy-turn';controller._executor_busy[rid]=True
    with db.transaction() as conn:
        gid=collab.create_guidance(conn,rid,source='requested',g={
            'kind':'nudge','intent':'observe','text_md':'补充背景','reason_md':'参考',
            'evidence_refs':[],'expected_change_md':'参考','revisit_when_md':'有异议'},
            target_trial_id='trial_mb1',review_request_id=None,frame_id=None,
            state_version=0,evidence_revision=0,shadow_epoch=0)
    await controller._deliver_queued_guidance(rid)
    assert db.query_one('SELECT status FROM guidance WHERE id=?',(gid,))[0]=='queued'
    assert not executor.steers and not executor.prompts
