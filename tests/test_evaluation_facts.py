"""Baseline failures reproduced with synthetic sessions and no cloud calls."""
import asyncio
import io
import json
import sys
import urllib.request

import pytest

from cyberscientist import bohr_proxy, collab, db, evaluations
from cyberscientist.brains.base import BrainEvent
from test_evaluations import FakeController, _catalog, _fake_score


def _evaluation_run(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(evaluations, '_score_run', _fake_score)
    evaluations.create_evaluation('fast', 1, 'facts')
    controller = FakeController()
    asyncio.run(evaluations.advance(controller))
    rid = controller.starts[0]
    return controller.real, rid


def test_evaluation_scientific_objective_is_separate_from_authorization(monkeypatch, tmp_path):
    controller, rid = _evaluation_run(monkeypatch, tmp_path)
    run = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    auth = db.query_one('SELECT note FROM authorizations WHERE id=?', (run['authorization_id'],))
    packet = controller._lifecycle_packet(run, 'run_start', sparse=True)
    assert packet['run_objective'] != auth['note']
    assert 'fixture task' in packet['run_objective']
    assert 'evaluation_handoff' not in packet
    assert packet['authorization']['max_submissions'] == 0
    assert db.eval_mode(rid) is None


@pytest.mark.parametrize('source', ['shadow', 'executor'])
def test_every_review_surface_has_same_resource_and_evaluation_facts(monkeypatch, tmp_path, source):
    controller, rid = _evaluation_run(monkeypatch, tmp_path)
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    controller.set_shadow(rid, True)
    with db.transaction() as conn:
        request_id = collab._enqueue_request_tx(conn, rid, source=source,
                                               blocking=False, trigger='passive')
    request = db.query_one('SELECT * FROM review_requests WHERE id=?', (request_id,))
    captured = []

    class CaptureBrain:
        async def review(self, session, packet):
            captured.append(packet)
            yield BrainEvent('error', {'message': 'fixture ends after frame capture'})

    asyncio.run(controller._run_one_review_impl(rid, request, CaptureBrain(), None))
    assert len(captured) == 1
    run = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    lifecycle = controller._lifecycle_packet(run, 'run_start', sparse=True)
    for key in ('max_sandboxes', 'max_sandbox_minutes', 'allow_sandbox_gpu',
                'allow_data_download', 'max_jobs', 'max_submissions', 'max_run_minutes'):
        assert captured[0]['authorization'][key] == lifecycle['authorization'][key]
    assert 'evaluation_handoff' not in captured[0] and 'evaluation_handoff' not in lifecycle
    assert captured[0]['authorization']['max_submissions'] == 0
    stored = json.loads(db.query_one('SELECT frame_json FROM review_requests WHERE id=?',
                                    (request_id,))['frame_json'])
    assert stored['authorization'] == captured[0]['authorization']


def test_proxy_nested_network_error_remains_parseable_after_redaction(monkeypatch, capsys):
    monkeypatch.setenv('CS_TOOL_TOKEN', 'fixture-capability')
    monkeypatch.setattr(sys, 'argv', ['bohr', 'job', 'list'])
    original = {'items': [{'receipt': {'stderr':
        'Get "https://platform/job?accessKey=account-secret": timeout\n'
        'Bearer fixture-capability'}}], 'observation': 'unknown'}
    monkeypatch.setattr(urllib.request, 'urlopen',
                        lambda *args, **kwargs: io.BytesIO(json.dumps(original).encode()))
    bohr_proxy.main()
    raw = capsys.readouterr().out
    parsed = json.loads(raw)
    assert parsed['observation'] == 'unknown'
    assert 'account-secret' not in raw and 'fixture-capability' not in raw
    assert parsed['items'][0]['receipt']['stderr'].endswith('Bearer [REDACTED]')


def test_evaluation_freezes_topic_model_choices_without_global_changes(monkeypatch, tmp_path):
    from cyberscientist import config
    _catalog(monkeypatch, tmp_path)
    before = config.load_settings()
    choices = {role: {'runtime': 'codex', 'model_id': 'fixture-selected-model',
                      'reasoning_effort': 'xhigh'} for role in ('brain', 'executor')}
    for cid in ('eval_a', 'eval_b'):
        db.execute('UPDATE challenges SET brain_config_json=?,executor_config_json=? WHERE id=?',
                   (json.dumps(choices['brain']), json.dumps(choices['executor']), cid))
    created = evaluations.create_evaluation('fast', 1, 'selected')
    snapshot = json.loads(db.query_one('SELECT config_json FROM eval_runs WHERE id=?',
                                      (created['id'],))['config_json'])
    template = json.loads(db.query_one('SELECT template_json FROM eval_results WHERE id=?', (created['results'][0]['id'],))[0])
    assert snapshot['ordinary_round']
    assert template['model_config'] == {role: choice | {'provider': 'codex'} for role, choice in choices.items()}
    assert config.load_settings() == before
