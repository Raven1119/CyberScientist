"""TBMA regressions: synthetic runtimes only, no model or cloud requests."""
import json
import pytest

from cyberscientist import config, db, observation
from cyberscientist.brains.base import BrainEvent, SessionRef
from cyberscientist.brains.codex import CodexBrain
from cyberscientist.controller import RunController
from test_collaboration import _seed_challenge


async def test_runless_curation_has_its_own_output_contract(monkeypatch):
    class Brain:
        async def open(self, spec):
            return SessionRef('fixture', 'curation')

        async def close(self, session):
            pass

        async def review(self, session, packet):
            prompt = CodexBrain._render_prompt(packet)
            if packet.get('protocol') == 'experience_curation':
                assert 'curation_result' in prompt
                yield BrainEvent('curation_result', {'result': {
                    'schema_version': 1, 'message_type': 'curation_result',
                    'summary': 'No supported new lesson.', 'experience_proposals': []}})
            else:
                # Same public response shape as the real failed TBMA curation.
                yield BrainEvent('decision', {'decision': {
                    'schema_version': 1, 'decision_id': 'fixture', 'run_id': None,
                    'observed_state_version': None, 'summary': 'No new lesson.',
                    'evidence_refs': [], 'actions': [{'op': 'wait', 'reason': 'No Run'}],
                    'experience_proposals': []}})
    controller = RunController()
    monkeypatch.setattr(controller, '_make_brain', lambda _: Brain())
    await controller._run_global_curation([])
    assert controller.global_curation_status()['state'] == 'done'
    assert controller.global_curation_status()['proposals_applied'] == 0


def test_executor_never_receives_bohrium_account_key(monkeypatch):
    _seed_challenge()
    controller = RunController()
    rid = controller.create_run('COLLAB_CH')['id']
    settings = config.load_settings()
    settings['executor']['runtime'] = 'codex'
    settings['bohrium'].update(executable='/fixture/bohr', access_key_secret_ref='fixture')
    monkeypatch.setattr(config, 'resolve_secret', lambda _: 'synthetic-private-key')
    spec = controller._prime_spec(rid, settings)
    assert 'synthetic-private-key' not in json.dumps(spec)
    assert not {'BOHR_ACCESS_KEY', 'ACCESS_KEY', 'CS_BOHR_EXECUTABLE'} & set(spec['env'])


def test_observer_receives_completed_tool_result_not_just_command_label():
    digest, omitted = observation.executor_digest([{
        'seq': 17, 'type': 'prime.execution.progress', 'payload': {
            'item_id': 'download-1', 'detail': 'commandExecution 完成: bohr job download',
            'status': 'completed', 'exit_code': 0,
            'output': 'Successfully downloaded result.zip; sha256=fixture'}}])
    assert omitted == 0
    assert digest[0]['operation_id'] == 'download-1'
    assert 'Successfully downloaded' in digest[0]['output_excerpt']
    assert digest[0]['status'] == 'completed'


@pytest.mark.parametrize('delivered', [False, True])
def test_job_transition_supersedes_pending_guidance(delivered):
    from cyberscientist import collab
    from test_collaboration import _guidance
    _seed_challenge(); c = RunController(); rid = c.create_run('COLLAB_CH')['id']
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    with db.transaction() as conn:
        conn.execute("INSERT INTO review_requests(id,run_id,source,status,frame_id,frame_json,created_at,updated_at) VALUES(?,?,'user','done','frame',?,?,?)",
                     ('review', rid, json.dumps({'through_seq': 0}), db.utcnow(), db.utcnow()))
        gid = collab.create_guidance(conn, rid, source='requested', g=_guidance(), target_trial_id=None,
            review_request_id='review', frame_id='frame', state_version=0, evidence_revision=0, shadow_epoch=0)
    if delivered:
        db.execute("UPDATE guidance SET status='sent' WHERE id=?", (gid,))
    db.append_event(rid, 'controller', 'job.observed', {'operation_id': 'job', 'status': 'Finished'})
    with db.transaction() as conn:
        assert collab.deliver_via_checkpoint_return(conn, rid, None) == []
        if delivered:
            g = conn.execute('SELECT * FROM guidance WHERE id=?', (gid,)).fetchone()
            assert collab.guidance_eligible(conn, rid, g), 'Late ACK still records delivered guidance'
    assert db.query_one('SELECT status FROM guidance WHERE id=?', (gid,))['status'] == ('sent' if delivered else 'superseded')


def test_usage_heartbeat_does_not_spend_periodic_review():
    from test_collaboration import _rig
    _seed_challenge(); c, _, _ = _rig(shadow=True, max_interval=.1)
    rid = c.create_run('COLLAB_CH', shadow_enabled=True)['id']
    db.execute("UPDATE runs SET phase='running', started_at='2020-01-01T00:00:00+00:00' WHERE id=?", (rid,))
    c.set_shadow(rid, True)
    db.append_event(rid, 'prime', 'prime.usage.updated', {'tokens': 10})
    c._maybe_periodic_shadow(rid)
    assert not db.query('SELECT * FROM review_requests WHERE run_id=?', (rid,))


def test_kimi_receipt_retains_tool_identity_and_output():
    from cyberscientist.prime.kimi_acp import map_update
    mapped = map_update({'sessionUpdate': 'tool_call_update', 'toolCallId': 'download-1',
        'status': 'failed', 'content': [{'content': {'type': 'text', 'text': 'Error: malformed archive'}}]})
    assert mapped['item_id'] == 'download-1' and mapped['status'] == 'failed'
    assert mapped['output'] == 'Error: malformed archive'


def test_job_mcp_uses_controlled_route_and_preserves_unknown(monkeypatch):
    from cyberscientist import mcp_bridge
    calls = []
    monkeypatch.setattr(mcp_bridge, '_post', lambda path, args: calls.append((path, args)) or {'status': 'unknown', 'operation_id': args['operation_id']})
    msg = {'id': 1, 'method': 'tools/call', 'params': {'name': 'research_job', 'arguments': {'action': 'submit'}}}
    assert mcp_bridge._handle(msg)['result']['isError'] and not calls
    msg['params']['arguments']['operation_id'] = 'stable-create'
    result = mcp_bridge._handle(msg)['result']
    assert result['isError']
    assert calls[0][0] == '/api/v1/tools/job'
    assert json.loads(result['content'][0]['text'])['operation_id'] == 'stable-create'
