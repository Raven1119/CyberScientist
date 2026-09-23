"""Real-runtime regression boundaries: liveness, public evidence and privacy."""
import asyncio
import json

import pytest

from cyberscientist import config, db
from cyberscientist.brains.base import BrainEvent, SessionRef
from cyberscientist.controller import RunController
from test_collaboration import _seed_challenge, _decision


def running_run(*, trial_status=None, busy=False, phase="running"):
    _seed_challenge()
    controller = RunController()
    run_id = controller.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    controller.authorize(run_id, "demo", True, 10, 30, 0, None)
    db.execute("UPDATE runs SET phase=? WHERE id=?", (phase, run_id))
    if trial_status:
        db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at)"
                   " VALUES('trial-runtime',?,?,?,?,?)",
                   (run_id, "research", "evidence", trial_status, db.utcnow()))
        db.execute("UPDATE runs SET current_trial_id='trial-runtime' WHERE id=?", (run_id,))
    controller._executor_busy[run_id] = busy
    return controller, run_id


@pytest.mark.parametrize("trial_status,busy,phase", [
    (None, False, "running"), (None, True, "running"),
    ("active", False, "running"), ("reported_complete", True, "running"),
    ("active", True, "paused"),
])
async def test_idle_stall_is_discarded_without_events_or_brain_reviews(trial_status, busy, phase):
    controller, run_id = running_run(trial_status=trial_status, busy=busy, phase=phase)
    before = db.events_after(run_id, 0)
    await controller._handle_signal(
        {"type": "prime_event", "event": {"type": "trial.stalled", "detail": "240 seconds"}},
        run_id, asyncio.Queue())
    assert db.events_after(run_id, 0) == before
    assert not db.query("SELECT * FROM review_requests WHERE run_id=?", (run_id,))
    assert controller._executor_busy[run_id] == busy


async def test_busy_active_trial_stall_still_requests_lifecycle_review():
    controller, run_id = running_run(trial_status="active", busy=True)
    await controller._handle_signal(
        {"type": "prime_event", "event": {"type": "trial.stalled", "detail": "240 seconds"}},
        run_id, asyncio.Queue())
    assert db.query_one("SELECT status FROM trials WHERE id='trial-runtime'")["status"] == "stalled"
    events = db.events_after(run_id, 0)
    assert any(event["type"] == "trial.stalled" and event["trial_id"] == "trial-runtime" for event in events)
    reviews = db.query("SELECT * FROM review_requests WHERE run_id=? AND source='lifecycle'", (run_id,))
    assert len(reviews) == 1 and reviews[0]["trigger"] == "trial_stalled"


async def test_executor_public_fields_and_raw_usage_survive_without_secrets():
    controller, run_id = running_run(trial_status="active", busy=True)
    config.update_secret("test-key", "saved-private-key")
    events = [
        {"type": "execution.progress", "detail": "command completed saved-private-key",
         "status": "failed", "exit_code": 9, "item_id": "tool-1",
         "output": "saved-private-key https://host/?accessKey=unknown-private-key&x=1 " + "x" * 15000},
        {"type": "usage.updated", "usage": {
            "total": {"inputTokens": 123, "outputTokens": 17}, "cost": None,
            "provider_note": "https://host/?api_key=other-private-key"}},
        {"type": "usage.updated", "usage": None},
        {"type": "reasoning", "detail": "private reasoning must disappear"},
        {"type": "execution.progress", "detail": "思考: private thoughts must disappear"},
    ]
    for event in events:
        await controller._handle_signal({"type": "prime_event", "event": event}, run_id, asyncio.Queue())
    recorded = [event for event in db.events_after(run_id, 0) if event["source"] == "prime"]
    assert len(recorded) == 3
    progress = recorded[0]["payload"]
    assert progress["status"] == "failed" and progress["exit_code"] == 9
    assert progress["item_id"] == "tool-1"
    assert progress["output"].startswith("[REDACTED] https://host/?accessKey=[REDACTED]&x=1")
    assert len(progress["output"]) <= 12000
    assert recorded[1]["payload"]["usage"]["total"] == {"inputTokens": 123, "outputTokens": 17}
    assert recorded[1]["payload"]["usage"]["cost"] is None
    assert recorded[2]["payload"]["usage"] is None
    serialized = json.dumps(recorded)
    for forbidden in ("saved-private-key", "unknown-private-key", "other-private-key", "private reasoning", "private thoughts"):
        assert forbidden not in serialized


async def test_brain_public_progress_is_persisted_before_review_finishes():
    controller, run_id = running_run()
    config.update_secret("test-key", "saved-private-key")
    review_id = controller._enqueue_lifecycle(run_id, trigger="run_start")
    request = db.query_one("SELECT * FROM review_requests WHERE id=?", (review_id,))
    waiting = asyncio.Event()
    release = asyncio.Event()

    class Brain:
        async def review(self, session, packet):
            yield BrainEvent("token", {"text": "private reasoning must disappear"})
            yield BrainEvent("progress", {"detail": "command completed", "status": "completed",
                                           "item_id": "brain-tool-1", "exit_code": 0,
                                           "output": "saved-private-key ?token=unknown-private-key"})
            yield BrainEvent("usage", {"usage": {"total": {"inputTokens": 123}, "cost": None}})
            waiting.set()
            await release.wait()
            yield BrainEvent("decision", {"decision": _decision([{"op": "wait", "reason": "research"}])})

    task = asyncio.create_task(controller._run_one_review(
        run_id, request, Brain(), SessionRef("fake", "brain-session")))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=2)
        assert not task.done()
        recorded = db.events_after(run_id, 0)
        progress = next(event["payload"] for event in recorded if event["type"] == "brain.progress")
        assert progress["item_id"] == "brain-tool-1" and progress["exit_code"] == 0
        assert progress["output"] == "[REDACTED] ?token=[REDACTED]"
        usage = next(event["payload"]["usage"] for event in recorded if event["type"] == "brain.usage.updated")
        assert usage == {"total": {"inputTokens": 123}, "cost": None}
        assert "private reasoning" not in json.dumps(recorded)
    finally:
        release.set()
        await task
    assert not any(event["type"] == "brain.raw_output" for event in db.events_after(run_id, 0))
