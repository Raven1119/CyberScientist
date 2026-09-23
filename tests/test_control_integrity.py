"""Experience kit batch B: controller/checkpoint public behavior, no real runtimes."""
import asyncio
import json

import pytest

from cyberscientist import collab, config, db
from cyberscientist.controller import RunController, ControllerError
from cyberscientist.prime import ActionReceipt
from test_collaboration import _seed_challenge, _rig, _start, _wait, _guidance


def checkpoint(key="cp", review="blocking"):
    return {"schema_version": 1, "message_type": "checkpoint", "checkpoint_key": key, "stage": "progress",
            "review": review, "report_md": "checkpoint evidence", "evidence_refs": []}


def test_retried_blocking_checkpoint_obeys_current_gate_and_retains_receipt():
    _seed_challenge()
    c = RunController()
    rid = c.create_run("COLLAB_CH")["id"]
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    first = collab.submit_checkpoint(rid, checkpoint(), source="executor")
    retry = collab.submit_checkpoint(rid, checkpoint(), source="executor")
    assert retry["checkpoint_id"] == first["checkpoint_id"]
    assert retry["review_id"] == first["review_id"]
    assert retry["next_action"] == "yield"
    db.execute("UPDATE runs SET gate='open' WHERE id=?", (rid,))
    assert collab.submit_checkpoint(rid, checkpoint(), source="executor")["next_action"] == "continue"
    db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
    assert collab.submit_checkpoint(rid, checkpoint(), source="executor")["next_action"] == "yield"


@pytest.mark.parametrize("channel", ["idle", "checkpoint"])
async def test_old_trial_guidance_never_reaches_new_trial(channel):
    _seed_challenge()
    c, brain, executor = _rig(False)
    rid = c.create_run("COLLAB_CH")["id"]
    db.execute("UPDATE runs SET phase='running',current_trial_id='new' WHERE id=?", (rid,))
    sid = await executor.start({})
    c._prime_instances[rid] = executor
    c._prime_sessions[rid] = sid
    with db.transaction() as conn:
        gid = collab.create_guidance(conn,rid,source="requested",g=_guidance(),target_trial_id="old",
             review_request_id=None,frame_id=None,state_version=0,evidence_revision=0,shadow_epoch=0)
    if channel == "idle":
        await c._deliver_queued_guidance(rid)
        assert executor.prompts == []
    else:
        result = collab.submit_checkpoint(rid,checkpoint(review="none"),source="executor")
        assert result["guidance"] == []
    assert db.query_one("SELECT status FROM guidance WHERE id=?",(gid,))["status"] == "superseded"


async def test_run_mode_and_runtime_identity_are_frozen_before_live_settings_change():
    _seed_challenge()
    c, brain, executor = _rig(False)
    seen = []
    c._make_brain = lambda settings: (seen.append(settings["app"]["mode"]) or brain)
    c._make_prime = lambda settings: (seen.append(settings["app"]["mode"]) or executor)
    rid = c.create_run("COLLAB_CH", mode="demo")["id"]
    settings = config.load_settings(); settings["app"]["mode"] = "connected"; config.save_settings(settings)
    c.authorize(rid,"demo",False,0,30,0,None)
    await c.start_async(rid)
    await asyncio.sleep(0.05)
    try:
        assert seen and set(seen) == {"demo"}
    finally:
        await c.control(rid,"terminate",None,"end-mode-test")


async def test_executor_start_failure_closes_brain_and_revokes_partial_session():
    _seed_challenge()
    c, brain, executor = _rig(False)
    closed = []
    async def close(session): closed.append(session)
    async def fail(spec): raise RuntimeError("injected executor startup failure")
    brain.close = close; executor.start = fail
    rid = c.create_run("COLLAB_CH")["id"]
    c.authorize(rid,"demo",True,10,30,0,None)
    await c.start_async(rid)
    task = c._tasks[rid]
    await asyncio.gather(task,return_exceptions=True)
    assert c.run_snapshot(rid)["phase"] == "failed"
    assert closed
    assert rid not in c._prime_instances and rid not in c._brain_sessions


async def test_deadline_without_events_requests_abort_and_waits_for_terminal():
    from datetime import datetime, timezone, timedelta
    _seed_challenge()
    c, brain, executor = _rig(False)
    async def accepted(sid):
        executor.aborts.append(sid)
        return ActionReceipt(status="accepted",detail="await native terminal")
    executor.abort = accepted
    rid = c.create_run("COLLAB_CH")["id"]
    c.authorize(rid,"demo",True,10,1,0,None)
    await c.start_async(rid)
    db.execute("UPDATE runs SET started_at=? WHERE id=?",
               ((datetime.now(timezone.utc)-timedelta(seconds=59.85)).isoformat(),rid))
    try:
        assert await _wait(lambda: bool(executor.aborts), timeout=2)
        assert c.run_snapshot(rid)["phase"] == "pausing"
        await executor.emit({"type":"run.aborted","detail":"native cancelled"})
        assert await _wait(lambda:c.run_snapshot(rid)["phase"] == "paused",timeout=2)
    finally:
        await c.control(rid,"terminate",None,"end-deadline-test")


@pytest.mark.parametrize("trigger", ["run_start", "recovery"])
async def test_initial_brain_error_pauses_idle_run_and_is_visible_via_api(trigger, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cyberscientist import api

    _seed_challenge()
    c, brain, executor = _rig(False)
    monkeypatch.setattr(api, "controller", c)
    rid = c.create_run("COLLAB_CH")["id"]
    c.authorize(rid, "demo", True, 10, 30, 0, None)
    message = "HTTP 400: this model requires a newer Codex CLI"
    await brain.results.put({"error": message})
    if trigger == "recovery":
        db.execute("UPDATE runs SET phase='recovering' WHERE id=?", (rid,))
        await c.control(rid, "resume", None, "recover-initial-error")
    else:
        await c.start_async(rid)
    try:
        assert await _wait(lambda: c.run_snapshot(rid)["phase"] == "paused")
        async with AsyncClient(transport=ASGITransport(app=api.create_app()),
                               base_url="http://local") as client:
            response = await client.get(f"/api/v1/runs/{rid}")
        assert response.status_code == 200
        snapshot = response.json()
        assert snapshot["phase"] == "paused"
        assert message in snapshot["block_reason"]
        assert snapshot["current_trial_id"] is None
        request = db.query_one("SELECT * FROM review_requests WHERE run_id=?", (rid,))
        assert request["status"] == "error" and request["error"] == message
        assert request["trigger"] == trigger
        events = db.events_after(rid, 0)
        assert any(event["type"] == "brain.error" for event in events)
        paused = [event for event in events if event["type"] == "run.paused"]
        assert len(paused) == 1 and paused[0]["payload"]["review_id"] == request["id"]
        await asyncio.sleep(0.1)
        assert len(brain.calls) == 1  # 错误不自动触发重试或降级模型。
        assert executor.prompts == [] and executor.aborts == []
        # 用户按恢复后才发起第二次判断；重放恢复信号不重复发起模型请求。
        await c.control(rid, "resume", None, f"resume-{trigger}-error")
        assert await _wait(lambda: len(brain.calls) == 2)
        assert brain.calls[-1]["trigger"] == trigger
        await c._signals[rid].put({"type": "resume"})
        await asyncio.sleep(0.1)
        requests = db.query("SELECT status FROM review_requests WHERE run_id=?", (rid,))
        assert len(requests) == 2
        assert sorted(item["status"] for item in requests) == ["error", "running"]
        assert c.run_snapshot(rid)["block_reason"] is None
        from test_collaboration import _decision
        await brain.results.put({"decision": _decision([
            {"op": "start_trial", "goal": "retry after explicit resume", "success_check": "evidence"}])})
        assert await _wait(lambda: len(executor.prompts) == 1)
        assert len(brain.calls) == 2
    finally:
        await c.control(rid, "terminate", None, f"end-{trigger}-error")


@pytest.mark.parametrize("trigger,busy,active_trial", [
    ("recovery", True, False), ("recovery", False, True), ("user_steer", False, False),
])
def test_lifecycle_failure_does_not_pause_other_or_active_work(trigger, busy, active_trial):
    _seed_challenge()
    c, _, _ = _rig(False)
    rid = c.create_run("COLLAB_CH")["id"]
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    if active_trial:
        db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at)"
                   " VALUES(?,?,?,?,'active',?)",
                   ("active-trial", rid, "ongoing research", "evidence", db.utcnow()))
        db.execute("UPDATE runs SET current_trial_id=? WHERE id=?", ("active-trial", rid))
    c._executor_busy[rid] = busy
    review_id = c._enqueue_lifecycle(rid, trigger=trigger)
    request = db.query_one("SELECT * FROM review_requests WHERE id=?", (review_id,))

    c._review_failed(rid, request, "lifecycle", "injected failure")

    assert c.run_snapshot(rid)["phase"] == "running"
    assert not any(event["type"] == "run.paused" for event in db.events_after(rid, 0))
