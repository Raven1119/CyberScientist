"""Application protocol regressions; no native model or scientific task."""
import json

from cyberscientist import db, observation
from cyberscientist.controller import RunController, _runtime_event_payload, _salvage_review_result
from test_collaboration import _seed_challenge


def test_user_guidance_reaches_pi_packet_without_losing_tail():
    _seed_challenge()
    controller = RunController()
    run = controller.create_run('COLLAB_CH', mode='demo')
    text = 'FIRST_DIRECTIVE\n' + '完整用户指导🙂' * 1000 + '\nLAST_DIRECTIVE: do not submit'
    rid = controller._enqueue_lifecycle(run['id'], 'user_steer', user_guidance=text)
    extra = json.loads(db.query_one('SELECT frame_json FROM review_requests WHERE id=?', (rid,))[0])
    packet = controller._lifecycle_packet(controller._require_run(run['id']), 'user_steer',
                                           user_guidance=extra['user_guidance'])
    assert packet['user_guidance'] == text


def test_overlong_scientific_watch_is_not_changed_to_a_different_statement():
    text = 'x' * 1100 + '\nDO NOT INCREASE PRECISION'
    original = {'watchlist': [{'id': 'watch', 'hypothesis_md': text,
        'evidence_needed_md': text, 'intervene_when_md': text, 'evidence_refs': []}]}
    fixed, _ = _salvage_review_result(original)
    assert fixed['watchlist'][0]['hypothesis_md'] == text
    assert fixed['watchlist'][0]['evidence_needed_md'] == text
    assert fixed['watchlist'][0]['intervene_when_md'] == text


def test_pi_tool_digest_marks_excerpt_and_points_to_complete_receipt():
    _seed_challenge()
    run = RunController().create_run('COLLAB_CH', mode='demo')
    output = 'first\n' + '计算回执🙂' * 1000 + '\nFINAL: do not submit'
    db.append_event(run['id'], 'executor', 'prime.execution.progress',
                    {'detail': 'commandExecution 完成: inspect', 'output': output})
    seq = db.query_one('SELECT MAX(seq) AS s FROM events WHERE run_id=?', (run['id'],))['s']
    frame = observation.build_frame(run['id'], mode='shadow', frame_id='long-receipt',
                                    from_seq=1, through_seq=seq, shadow_cfg={'max_reviews': 8})
    item = frame['executor_digest'][-1]
    assert item['output_excerpt'].endswith('…[截断]')
    assert item['body_truncated'] is True
    assert item['source_ref'] == f"event:{run['id']}:{seq}"
    assert frame['quality']['truncated'] is True
    saved = db.events_after(run['id'], seq - 1, limit=1)[0]['payload']
    assert saved['output'] == output


def test_persisted_public_receipt_and_reply_keep_full_scrubbed_body():
    text = 'FIRST\n' + '科学回执🙂' * 4000 + '\nFINAL: do not submit'
    public = _runtime_event_payload({'output': text, 'text': text})
    assert public['output'] == text
    assert public['text'] == text
    structured = [{'result': text} for _ in range(35)]
    assert _runtime_event_payload({'output': structured})['output'] == structured
    assert 'sk-synthetic-secret-12345' not in _runtime_event_payload(
        {'output': text + '\nsk-synthetic-secret-12345'})['output']


def test_dropped_intent_reason_reaches_pi_without_losing_final_condition():
    _seed_challenge()
    controller = RunController()
    run = controller.create_run('COLLAB_CH', mode='demo')
    snapshot = json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (run['id'],))[0])
    snapshot['lifecycle_version'] = 2
    db.execute("UPDATE runs SET config_snapshot=?,phase='running',pending_action_json=? WHERE id=?",
               (json.dumps(snapshot), json.dumps({'action': 'new_trial'}), run['id']))
    reason = 'x' * 800 + '\nFINAL: preserve the original files'
    controller.drop_pending_intent(run['id'], reason)
    extra = json.loads(db.query_one("SELECT frame_json FROM review_requests WHERE run_id=? AND trigger='pending_intent_dropped'", (run['id'],))[0])
    assert reason in extra['user_guidance']
