"""Exercise the production SSE iterator with real local database records."""
import asyncio
import json

import pytest

from cyberscientist import api, db
from test_collaboration import _seed_challenge


async def event_stream(phase):
    _seed_challenge()
    rid = api.controller.create_run('COLLAB_CH')['id']
    db.execute('UPDATE runs SET phase=? WHERE id=?', (phase, rid))
    route = next(r for r in api.create_app().routes if r.path == '/api/v1/runs/{run_id}/events')
    return rid, (await route.endpoint(rid, 0)).body_iterator


@pytest.mark.parametrize('phase', ['finished', 'failed', 'cancelled'])
async def test_terminal_sse_drains_every_page_then_closes(phase):
    rid, stream = await event_stream(phase)
    for i in range(205):
        db.append_event(rid, 'controller', 'fixture.event', {'index': i})
    async def consume():
        frames = []
        async for frame in stream:
            for line in frame.splitlines():
                if line.startswith('data: '): frames.append(json.loads(line[6:]))
        return frames
    events = await asyncio.wait_for(consume(), timeout=2.5)
    assert [e['payload']['index'] for e in events] == list(range(205))


async def test_paused_sse_stays_live_for_resume_and_final_events():
    rid, stream = await event_stream('paused')
    assert await anext(stream) == ': heartbeat\n\n'
    db.append_event(rid, 'controller', 'run.resumed', {})
    assert 'run.resumed' in await anext(stream)
    db.execute("UPDATE runs SET phase='finished' WHERE id=?", (rid,))
    db.append_event(rid, 'controller', 'run.finished', {})
    assert 'run.finished' in await anext(stream)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=1.5)
