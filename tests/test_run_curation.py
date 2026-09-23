import asyncio
import json

import pytest
from cyberscientist import config, db, experiences
from cyberscientist.brains.base import BrainEvent, SessionRef
from cyberscientist.controller import RunController
from test_collaboration import _seed_challenge, _proposal


@pytest.mark.parametrize('invalid', [False, True])
async def test_run_curation_freezes_evidence_deduplicates_and_keeps_hypotheses(monkeypatch, invalid):
    _seed_challenge(); c = RunController(); rid = c.create_run('COLLAB_CH')['id']
    db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
    db.append_event(rid, 'user', 'user.steer.queued', {'text': 'External startup assistance'})
    db.append_event(rid, 'controller', 'job.unknown', {'operation_id': 'fixture'})
    calls = []
    class Brain:
        async def open(self, spec): return SessionRef('fixture', 'curation')
        async def close(self, session): pass
        async def review(self, session, packet):
            calls.append(packet)
            ev = packet['run_evidence']
            assert ev['externally_assisted'] and ev['phase'] == 'paused'
            assert any(e['type'] == 'job.unknown' for e in ev['events'])
            p = _proposal('global', 'Do not repeat an unknown create')
            p['evidence_refs'] = ['invented:missing'] if invalid else ev['evidence_refs']
            yield BrainEvent('curation_result', {'result': dict(schema_version=1, message_type='curation_result', summary='Source-grounded fixture', experience_proposals=[p])})
    monkeypatch.setattr(c, '_make_brain', lambda _: Brain())
    first = await c.curate_run_experience(rid, 'stable-op')
    second = await c.curate_run_experience(rid, 'stable-op')
    assert first['id'] == second['id']
    for _ in range(20):
        await asyncio.sleep(.01)
        result = c.run_curation_status(rid)
        if result['state'] != 'running': break
    assert len(calls) == 1
    assert c.run_snapshot(rid)['phase'] == 'paused'
    assert result['state'] == ('failed' if invalid else 'done')
    assert result['proposals_applied'] == (0 if invalid else 1)
    if not invalid:
        exp = experiences.get_experience(result['experience_ids'][0])
        assert exp['frontmatter']['status'] == 'candidate'
        assert exp['frontmatter']['evidence_status'] == 'hypothesis'
    again = await c.curate_run_experience(rid, 'stable-op')
    assert again['id'] == first['id']
    assert len(calls) == 1


async def test_native_run_curation_api_is_separate_from_global(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cyberscientist import api
    _seed_challenge(); rid = api.controller.create_run('COLLAB_CH')['id']
    db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
    calls = []
    class Brain:
        async def open(self, spec): return SessionRef('fixture', 'api-curation')
        async def close(self, session): pass
        async def review(self, session, packet):
            calls.append(packet)
            yield BrainEvent('curation_result', {'result': dict(schema_version=1, message_type='curation_result', summary='No supported proposals', experience_proposals=[])})
    monkeypatch.setattr(api.controller, '_make_brain', lambda _: Brain())
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://local') as client:
        r = await client.post(f'/api/v1/runs/{rid}/curation', json={'operation_id': 'curate-http'})
        assert r.status_code == 200, r.text
        for _ in range(20):
            await asyncio.sleep(.01)
            state = (await client.get(f'/api/v1/runs/{rid}/curation')).json()
            if state['state'] != 'running': break
        assert state['state'] == 'done' and state['proposals_applied'] == 0
    assert calls[0]['run_evidence']['run_id'] == rid
    assert not (config.DATA_DIR / 'global_curation.json').exists()
