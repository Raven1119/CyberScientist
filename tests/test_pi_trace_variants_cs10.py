import json
import pytest
from httpx import ASGITransport, AsyncClient
from cyberscientist import api, collab, db, mailboxes, mcp_bridge
from test_trace_narrative import _fixture, _raw
from test_mailboxes import _set_scored


async def test_pi_variant_score_and_comparison_preserves_frozen_science_and_quota(monkeypatch):
    rid, tid, package, files, rows, first, second, extra, trial_dir = _fixture()
    mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, 'check', lambda *_: {'verdict': 'admitted', 'signals': {}})
    source = mailboxes.submit_experiment(rid, tid, None, 'baseline', prediction_md='baseline 20')
    _set_scored(source['id'], 20)
    monkeypatch.setattr(collab, 'validate_token', lambda token: {'run_id': rid, 'role': token})
    monkeypatch.setattr(api.controller, 'notify_run_change', lambda _: None)
    body = {'source_submission_id': source['id'], 'operation_id': 'pi-variant',
            'prediction_md': 'factual narrative improves trace score', 'narrative_jsonl': _raw(rows).decode()}
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        rejected = await client.post('/api/v1/tools/trace_variant', json=body, headers={'authorization': 'Bearer executor'})
        assert rejected.status_code == 403
        accepted = await client.post('/api/v1/tools/trace_variant', json=body, headers={'authorization': 'Bearer brain'})
        assert accepted.status_code == 200, accepted.text
        variant = accepted.json()
        assert not (trial_dir / 'trace_narrative.jsonl').exists()
        _set_scored(variant['id'], 25)
        listed = await client.get(f'/api/v1/runs/{rid}/submissions')
    assert listed.status_code == 200
    items = {row['id']: row for row in listed.json()['items']}
    assert items[source['id']]['score'] == 20 and items[variant['id']]['score'] == 25
    assert items[variant['id']]['prediction_md'] == body['prediction_md']
    assert variant['science_artifact_match'] == 1
    assert variant['variant_of'] == source['id']
    assert len(db.query('SELECT * FROM submissions WHERE run_id=?', (rid,))) == 2
    retry = mailboxes.submit_trace_variant(source['id'], 'pi-variant', body['prediction_md'], narrative_jsonl=body['narrative_jsonl'])
    assert retry['deduplicated']
    with pytest.raises(mailboxes.MailboxError, match='预测'):
        mailboxes.submit_trace_variant(source['id'], 'missing', '', projection_only=True)
    assert len(db.query('SELECT * FROM submissions')) == 2


def test_variant_mcp_only_pi_and_native_tool_is_exposed(monkeypatch):
    from cyberscientist.codex_protocol import BRAIN_TOOLS
    assert 'research_trace_variant' in BRAIN_TOOLS
    for role in ('brain', 'executor'):
        monkeypatch.setenv('CS_TOOL_ROLE', role)
        listed = mcp_bridge._handle({'method': 'tools/list', 'id': 1})
        assert ('research_trace_variant' in [t['name'] for t in listed['result']['tools']]) == (role == 'brain')
    monkeypatch.setattr(mcp_bridge, '_post', lambda *a, **k: pytest.fail('executor cannot submit'))
    result = mcp_bridge._handle({'method': 'tools/call', 'id': 2, 'params': {'name': 'research_trace_variant'}})
    assert '仅 PI' in json.dumps(result, ensure_ascii=False)


def test_inline_annotation_keeps_explicit_earlier_writing_time(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    with monkeypatch.context() as clock:
        clock.setattr(db, 'utcnow', lambda: from_time)
        rid, tid, package, files, rows, first, second, extra, trial_dir = _fixture()
    written_at = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, 'check', lambda *_: {'verdict': 'admitted', 'signals': {}})
    source = mailboxes.submit_experiment(rid, tid, None, 'base-annotation', prediction_md='base')
    _set_scored(source['id'], 20)
    rows.append({'step_type': 'observation', 'title': 'Later interpretation', 'annotation': True,
                 'timestamp': written_at, 'cs_refs': [f"{rid}#{second['seq']}"]})
    result = mailboxes.submit_trace_variant(source['id'], 'delayed-inline', 'annotation improves clarity',
        narrative_jsonl=_raw(rows).decode(), narrative_written_at=written_at)
    assert result['status'] == 'submitted' and result['science_artifact_match'] == 1

    rows[-1]['timestamp'] = '2026-01-02T00:00:00+00:00'
    with pytest.raises(mailboxes.MailboxError, match='早于引用事件'):
        mailboxes.submit_trace_variant(source['id'], 'backdated', 'bad chronology',
            narrative_jsonl=_raw(rows).decode(), narrative_written_at=rows[-1]['timestamp'])
