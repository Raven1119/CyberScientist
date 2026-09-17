"""RunController 状态机（Demo 组件，纯本地，无外部调用）。"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from cyberscientist import config, db
from cyberscientist.controller import ControllerError, RunController


def _seed_challenge(cid="DEMO_CHALLENGE"):
    db.execute(
        "INSERT INTO challenges(id, platform_challenge_id, origin, title, content,"
        " content_hash, contract_status, imported_at, is_demo)"
        " VALUES(?,?,?,?,?,?,'unknown',?,1)",
        (cid, "DEMO_000", "demo://local", "演示题", "内容", "hash", db.utcnow()))


def _controller() -> RunController:
    return RunController()


async def _wait_for(pred, timeout=15.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.2)
    return False


def test_create_run_requires_challenge():
    with pytest.raises(ControllerError) as exc:
        _controller().create_run("nope")
    assert exc.value.code == "NOT_FOUND"


def test_single_active_run_guard():
    _seed_challenge()
    c = _controller()
    c.create_run("DEMO_CHALLENGE")
    with pytest.raises(ControllerError) as exc:
        c.create_run("DEMO_CHALLENGE")
    assert exc.value.code == "RUN_ACTIVE"


async def test_full_demo_loop_to_finished():
    _seed_challenge()
    c = _controller()
    run = c.create_run("DEMO_CHALLENGE")
    rid = run["id"]
    with pytest.raises(ControllerError) as exc:
        await c.start_async(rid)
    assert exc.value.code == "NEEDS_AUTHORIZATION"
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    snap = await c.start_async(rid)
    assert snap["phase"] == "running"
    ok = await _wait_for(
        lambda: c.run_snapshot(rid)["phase"] == "finished", timeout=20)
    assert ok, "demo 闭环未在限时内完成"
    snap = c.run_snapshot(rid)
    assert any(t["status"] == "done" for t in snap["trials"])
    # 经验候选已落盘
    from cyberscientist import experiences
    items = experiences.list_experiences()["items"]
    assert any(i["status"] == "candidate" for i in items)


async def test_pause_resume_terminate():
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    await c.start_async(rid)
    ok = await _wait_for(lambda: c.run_snapshot(rid)["current_trial_id"], 10)
    assert ok
    op = f"op_{uuid.uuid4().hex[:10]}"
    receipt = await c.control(rid, "pause", None, op)
    assert receipt["status"] == "accepted"
    assert c.run_snapshot(rid)["phase"] == "pausing"
    ok = await _wait_for(lambda: c.run_snapshot(rid)["phase"] == "paused", 10)
    assert ok, "demo abort confirmed 后应显示 paused"
    receipt = await c.control(rid, "resume", None, f"op_{uuid.uuid4().hex[:10]}")
    assert receipt["status"] == "confirmed"
    assert c.run_snapshot(rid)["phase"] == "running"
    receipt = await c.control(rid, "terminate", None, f"op_{uuid.uuid4().hex[:10]}")
    assert receipt["status"] == "confirmed"
    assert c.run_snapshot(rid)["phase"] == "cancelled"


async def test_control_operation_id_dedup():
    """同一 operation_id 的并发控制请求只受理一次。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    await c.start_async(rid)
    await _wait_for(lambda: c.run_snapshot(rid)["current_trial_id"], 10)
    op = f"op_{uuid.uuid4().hex[:10]}"
    results = await asyncio.gather(
        c.control(rid, "steer", "dup-test", op),
        c.control(rid, "steer", "dup-test", op))
    dedup_count = sum(1 for r in results if r.get("deduplicated"))
    queued = sum(1 for r in results if r.get("status") == "queued")
    assert dedup_count == 1 and queued == 1
    await c.control(rid, "terminate", None, f"op_{uuid.uuid4().hex[:10]}")


async def test_connected_mode_blocked_without_components(tmp_path):
    _seed_challenge()
    settings = config.load_settings()
    settings["app"]["mode"] = "connected"
    settings["brain"]["executable"] = ""
    settings["prime"]["executable"] = str(tmp_path / "no-prime")
    config.save_settings(settings)
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE", mode="connected")["id"]
    c.authorize(rid, "model_roundtrip", True, 1, 30, 0, None)
    with pytest.raises(ControllerError) as exc:
        await c.start_async(rid)
    assert exc.value.code == "MISSING_CREDENTIAL"
    snap = c.run_snapshot(rid)
    assert snap["phase"] == "blocked"
    assert "Prime" in snap["block_reason"]


async def test_stale_decision_not_executed():
    """state_version 变化后旧判断只保存不执行。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    await c.start_async(rid)
    await _wait_for(lambda: c.run_snapshot(rid)["current_trial_id"], 10)
    v = c.run_snapshot(rid)["state_version"]
    db.bump_state_version(rid)  # 模拟用户暂停/指导造成的版本变化
    dec = {"schema_version": 1, "decision_id": "dec_stale", "run_id": rid,
           "observed_state_version": v, "summary": "旧判断",
           "evidence_refs": [], "actions": [{"op": "finish", "reason": "r"}],
           "experience_proposals": []}
    await c._apply_decision(rid, dec, {}, None, None)
    types = [e["type"] for e in db.events_after(rid, 0)]
    assert "brain.decision_stale" in types
    assert "run.finished" not in types
    await c.control(rid, "terminate", None, f"op_{uuid.uuid4().hex[:10]}")
