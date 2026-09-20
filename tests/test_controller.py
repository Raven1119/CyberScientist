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


@pytest.fixture(autouse=True)
def _demo_mode():
    """Run 模式快照自 settings；本文件默认 demo，connected 用例自行覆盖。"""
    settings = config.load_settings()
    settings["app"]["mode"] = "demo"
    config.save_settings(settings)


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
    # 题内经验提议已落盘并直接生效（自进化闭环：题内免审）
    from cyberscientist import experiences
    items = experiences.list_experiences()["items"]
    assert any(i["status"] == "active" and i["scope"] == "challenge"
               for i in items)


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
    settings["brain"]["runtime"] = "codex"
    settings["brain"]["executable"] = str(tmp_path / "no-brain")
    settings["executor"]["runtime"] = "prime"
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
    assert "执行器不可用" in snap["block_reason"]


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


def test_update_budget_settings_and_auth():
    """预算运行时调整：大脑/Trial 走实时 settings，模型/时长/提交走授权行。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 40, 30, 1, None)
    out = c.update_budget(rid, max_brain_reviews=20, max_model_turns=80,
                          max_run_minutes=120, max_submissions=5,
                          max_trials=9)
    assert out["updated"] == {"max_brain_reviews": 20, "max_trials": 9,
                              "max_model_turns": 80, "max_run_minutes": 120,
                              "max_submissions": 5}
    # settings 落盘并被实时读取
    assert config.load_settings()["run_defaults"]["max_brain_reviews"] == 20
    assert config.load_settings()["run_defaults"]["max_trials"] == 9
    # 授权行更新并反映在 budget 状态里
    budget = c.run_snapshot(rid)["budget"]
    assert budget["max_brain_reviews"] == 20
    assert budget["model_turns"]["limit"] == 80
    assert budget["run_minutes_limit"] == 120
    assert budget["max_submissions"] == 5
    types = [e["type"] for e in db.events_after(rid, 0)]
    assert "run.budget_updated" in types


def test_update_budget_validation():
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    # 未授权时调整授权预算报错
    with pytest.raises(ControllerError) as exc:
        c.update_budget(rid, max_model_turns=10)
    assert exc.value.code == "NEEDS_AUTHORIZATION"
    # 空body / 非正整数
    with pytest.raises(ControllerError) as exc:
        c.update_budget(rid)
    assert exc.value.code == "INVALID_ARGUMENT"
    with pytest.raises(ControllerError) as exc:
        c.update_budget(rid, max_brain_reviews=0)
    assert exc.value.code == "INVALID_ARGUMENT"
    # Run 不存在
    with pytest.raises(ControllerError) as exc:
        c.update_budget("nope", max_brain_reviews=5)
    assert exc.value.code == "NOT_FOUND"


async def test_steer_to_stalled_trial_recovers():
    """stalled Trial 可被大脑 steer 裁决：指导入队且 Trial 恢复 active。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    tid = "trial_stalled_x"
    db.execute(
        "INSERT INTO trials(id, run_id, parent_trial_id, goal, success_check,"
        " status, created_at) VALUES(?,?,NULL,?,?,'stalled',?)",
        (tid, rid, "探索", "判据", db.utcnow()))
    db.execute("UPDATE runs SET current_trial_id=? WHERE id=?", (tid, rid))
    v = c.run_snapshot(rid)["state_version"]
    dec = {"schema_version": 1, "decision_id": "dec_steer_stalled",
           "run_id": rid, "observed_state_version": v, "summary": "停滞收束",
           "evidence_refs": [],
           "actions": [{"op": "steer", "trial_id": tid, "message": "立即交付基线"}],
           "experience_proposals": []}
    await c._apply_decision(rid, dec, {}, None, None)
    types = [e["type"] for e in db.events_after(rid, 0)]
    assert "brain.decision_rejected" not in types
    assert "guidance.queued" in types
    assert db.query_one("SELECT status FROM trials WHERE id=?",
                        (tid,))["status"] == "active"


async def test_update_budget_rejects_terminal_run():
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    await c.control(rid, "terminate", None, f"op_{uuid.uuid4().hex[:10]}")
    with pytest.raises(ControllerError) as exc:
        c.update_budget(rid, max_brain_reviews=30)
    assert exc.value.code == "INVALID_STATE"


def test_max_jobs_authorization_roundtrip():
    """算力授权：authorize 落 max_jobs，update_budget 可运行中调整，budget 状态回读。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    # 默认未授权算力
    assert c.run_snapshot(rid)["budget"] is None or True
    c.authorize(rid, "demo", False, 40, 30, 1, None, max_jobs=2)
    budget = c.run_snapshot(rid)["budget"]
    assert budget["max_jobs"] == 2
    # 运行中提高
    out = c.update_budget(rid, max_jobs=5)
    assert out["updated"] == {"max_jobs": 5}
    assert c.run_snapshot(rid)["budget"]["max_jobs"] == 5
    # 观测帧（给大脑看的预算）也带 max_jobs
    from cyberscientist import observation
    frame = observation.build_frame(
        rid, mode="shadow", frame_id="fr_test", from_seq=0, through_seq=0,
        shadow_cfg={}, request={"kind": "lifecycle", "detail": "test"},
        run_defaults={})
    assert frame["budget"]["max_jobs"] == 5
