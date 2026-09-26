"""协作与静默监督验收测试（docs/collaboration/ACCEPTANCE.md T1-T11）。

实际控制器 + 临时 SQLite；大脑/执行器为可控假协议实现。
T12（浏览器路径）在交付时单独用 webbridge 验证。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from cyberscientist import collab, config, db, experiences, observation, skills
from cyberscientist.brains.base import BrainEvent, RuntimeHealth, SessionRef
from cyberscientist.controller import ControllerError, RunController
from cyberscientist.prime import ActionReceipt, PrimeHealth


def _seed_challenge(cid="COLLAB_CH"):
    db.execute(
        "INSERT INTO challenges(id, platform_challenge_id, origin, title, content,"
        " content_hash, contract_status, imported_at, is_demo)"
        " VALUES(?,?,?,?,?,?,'unknown',?,1)",
        (cid, "COLLAB_000", "demo://local", "协作测试题",
         "目标：验证协作协议。", "hash", db.utcnow()))


def _decision(actions, sv=0, rid="run_test"):
    actions = [({**action, "objective_assessment": {
        "status": "partial", "evidence_refs": [], "remaining_md": "测试未评估科学目标"}}
        if action.get("op") == "finish" and "objective_assessment" not in action
        else action) for action in actions]
    return {"schema_version": 2, "decision_id": f"d-{id(actions)}",
            "run_id": rid, "observed_state_version": sv,
            "summary": "测试决策", "evidence_refs": [],
            "actions": actions, "experience_proposals": []}


def _review_result(frame_id, disposition="silent", guidance=None,
                   note="观察笔记", watchlist=None):
    return {"schema_version": 1, "message_type": "review_result",
            "frame_id": frame_id, "disposition": disposition,
            "private_note_md": note, "watchlist": watchlist or [],
            "guidance": guidance}


def _guidance(kind="steer", intent="observe", text="整理已有结果"):
    return {"kind": kind, "intent": intent, "text_md": text,
            "reason_md": "依据", "evidence_refs": [],
            "expected_change_md": "预期", "revisit_when_md": "条件"}


class FakeExecutor:
    """可控执行器：记录控制面调用，事件由测试注入。"""

    kind = "fake"

    def __init__(self):
        self.queues: dict[str, asyncio.Queue] = {}
        self.prompts: list[tuple[str, str]] = []
        self.steers: list[str] = []
        self.aborts: list[str] = []
        self.busy: dict[str, bool] = {}

    async def inspect(self) -> PrimeHealth:
        return PrimeHealth(installed=True, version="fake-executor")

    async def start(self, spec):
        sid = "sess-1"
        self.queues[sid] = asyncio.Queue()
        self.busy[sid] = False
        self.spec = spec
        return sid

    async def prompt(self, session_id, text):
        self.prompts.append((session_id, text))
        self.busy[session_id] = True
        return ActionReceipt(status="accepted", detail="ok",
                             operation_id=f"op_{len(self.prompts)}")

    async def steer(self, session_id, text):
        self.steers.append(text)
        return ActionReceipt(status="accepted", detail="queued")

    async def abort(self, session_id):
        self.aborts.append(session_id)
        self.busy[session_id] = False
        return ActionReceipt(status="confirmed", detail="aborted")

    async def state(self, session_id):
        return {"status": "busy" if self.busy.get(session_id) else "idle",
                "session_id": session_id}

    async def close(self, session_id):
        pass

    async def emit(self, ev, sid="sess-1"):
        await self.queues[sid].put(ev)

    async def turn_done(self, sid="sess-1"):
        self.busy[sid] = False
        await self.emit({"type": "executor.turn_completed",
                         "stop_reason": "end_turn", "detail": "回合结束"}, sid)

    def events(self, session_id):
        async def gen():
            while True:
                yield await self.queues[session_id].get()
        return gen()


class ScriptableBrain:
    """可控大脑：记录每次调用，结果由测试排队；可用 barrier 卡住。"""

    kind = "fake-brain"

    def __init__(self):
        self.calls: list[dict] = []
        self.results: asyncio.Queue = asyncio.Queue()
        self.barrier: asyncio.Event | None = None
        self.open_spec: dict | None = None

    async def inspect(self) -> RuntimeHealth:
        return RuntimeHealth(installed=True, version="fake-brain")

    async def open(self, spec):
        self.open_spec = spec
        return SessionRef(runtime="fake", session_id="bsess")

    def review(self, session, packet):
        async def gen():
            self.calls.append(packet)
            if self.barrier is not None:
                await self.barrier.wait()
            r = await self.results.get()
            if "error" in r:
                yield BrainEvent("error", {"message": r["error"]})
            elif "question_answer" in r:
                yield BrainEvent("question_answer", r["question_answer"])
            elif "decision" in r:
                yield BrainEvent("decision", {"decision": r["decision"]})
            else:
                yield BrainEvent("review_result", {"result": r["review_result"]})
        return gen()

    async def cancel(self, session):
        return {"status": "accepted"}

    async def close(self, session):
        pass


def _rig(shadow=True, min_interval=0.05, max_reviews=8, max_interval=3600):
    settings = config.load_settings()
    settings["app"]["mode"] = "demo"
    settings["shadow"] = {"enabled": shadow,
                          "min_interval_seconds": min_interval,
                          "max_interval_seconds": max_interval,
                          "max_reviews": max_reviews}
    config.save_settings(settings)
    brain = ScriptableBrain()
    ex = FakeExecutor()
    c = RunController()
    c._make_brain = lambda s: brain  # type: ignore[method-assign]
    c._make_prime = lambda s: ex  # type: ignore[method-assign]
    return c, brain, ex


async def _wait(pred, timeout=10.0):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.05)
    return False


async def _start(c, brain, rid, first_actions=None):
    """启动 Run 并让大脑完成 run_start 生命周期审阅。"""
    c.authorize(rid, "demo", True, 10, 30, 0, None)
    await c.start_async(rid)
    actions = first_actions if first_actions is not None else [
        {"op": "start_trial", "goal": "基线", "success_check": "产物落盘"}]
    await brain.results.put({"decision": _decision(actions)})
    ok = await _wait(lambda: bool(
        db.query_one("SELECT id FROM trials WHERE run_id=?", (rid,))))
    assert ok, "首个 Trial 未创建"
    return db.query_one("SELECT id FROM trials WHERE run_id=?", (rid,))["id"]


def _shadow_reviews(rid):
    return db.query("SELECT * FROM review_requests WHERE run_id=?"
                    " AND source='shadow'", (rid,))


def _guidance_status(rid):
    row = db.query_one("SELECT status FROM guidance WHERE run_id=?", (rid,))
    return row["status"] if row else None


async def _drain_lifecycle(brain, actions=None):
    """若有待处理的生命周期请求，喂一个 wait 决策消化掉。"""
    await brain.results.put({"decision": _decision(
        actions if actions is not None else [{"op": "wait", "reason": "观察"}])})


# ---------- T1 并行与静默 ----------

async def test_t1_brain_review_does_not_block_executor_events():
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    brain.barrier = asyncio.Event()  # 大脑卡在审阅中
    c.authorize(rid, "demo", True, 10, 30, 0, None)
    await c.start_async(rid)
    ok = await _wait(lambda: len(brain.calls) == 1)
    assert ok, "run_start 审阅未开始"

    # 审阅期间执行器事件继续落库
    before = db.query_one("SELECT COUNT(*) AS n FROM events WHERE run_id=?",
                          (rid,))["n"]
    for i in range(3):
        await ex.emit({"type": "execution.progress", "detail": f"工具 {i}"})
    ok = await _wait(lambda: db.query_one(
        "SELECT COUNT(*) AS n FROM events WHERE run_id=?", (rid,))["n"]
        >= before + 3)
    assert ok, "大脑审阅期间执行器事件被阻塞"
    # 控制门禁不等待大脑：暂停可立即进入 pausing
    r = await c.control(rid, "pause", None, "op-pause-t1")
    assert r["status"] == "accepted"
    assert c.run_snapshot(rid)["phase"] in ("pausing", "paused")
    # 同会话只有一个事件消费者
    assert len([t for t in (c._pumps.get(rid),) if t and not t.done()]) == 1
    brain.barrier.set()
    await brain.results.put({"decision": _decision(
        [{"op": "wait", "reason": "x"}])})
    await c.control(rid, "terminate", None, "op-term-t1")


async def test_t2_silent_review_has_zero_executor_effect():
    _seed_challenge()
    c, brain, ex = _rig(shadow=True)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    await _start(c, brain, rid)
    prompts0, steers0, aborts0 = len(ex.prompts), len(ex.steers), len(ex.aborts)

    # 研究级变化触发被动观察；普通检查点仅持久化。
    collab.submit_checkpoint(rid, {
        "schema_version": 1, "message_type": "checkpoint",
        "checkpoint_key": "k1", "review": "none", "stage": "progress",
        "report_md": "进展", "evidence_refs": []},
        source="executor", notify=c.notify_run_change)
    db.append_event(rid, "controller", "submission.scored",
                    {"submission_id": "s1", "score": 0.4})
    c.notify_run_change(rid)
    ok = await _wait(lambda: len(brain.calls) >= 2)
    assert ok, "shadow 审阅未触发"
    frame = brain.calls[-1]
    assert frame.get("protocol") == "review_result"
    await brain.results.put({"review_result": _review_result(
        frame["frame_id"], note="证据不足，继续观察")})
    ok = await _wait(lambda: db.query_one(
        "SELECT private_note_md FROM supervision WHERE run_id=?",
        (rid,))["private_note_md"] == "证据不足，继续观察")
    assert ok
    # SILENT：执行器零调用增量、无指导、无经验发布
    assert (len(ex.prompts), len(ex.steers), len(ex.aborts)) == \
        (prompts0, steers0, aborts0)
    assert db.query("SELECT id FROM guidance WHERE run_id=?", (rid,)) == []
    assert experiences.list_experiences()["items"] == []
    await c.control(rid, "terminate", None, "op-term-t2")


async def test_t3_burst_merges_and_no_self_loop():
    _seed_challenge()
    c, brain, ex = _rig(shadow=True)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    await _start(c, brain, rid)
    calls0 = len(brain.calls)

    # 事件突发：多个研究级变化合并为一个 shadow 请求
    for i in range(3):
        collab.submit_checkpoint(rid, {
            "schema_version": 1, "message_type": "checkpoint",
            "checkpoint_key": f"burst-{i}", "review": "none",
            "stage": "progress", "report_md": f"r{i}", "evidence_refs": []},
            source="executor", notify=c.notify_run_change)
        db.append_event(rid, "controller", "submission.scored",
                        {"submission_id": f"s{i}", "score": i})
        c.notify_run_change(rid)
    await asyncio.sleep(0.3)
    assert len(_shadow_reviews(rid)) == 1, "突发事件未合并为单次审阅"

    # 纯心跳/进度/大脑自身输出不触发新审阅
    for i in range(3):
        await ex.emit({"type": "execution.progress", "detail": f"心跳 {i}"})
    db.append_event(rid, "brain", "brain.raw_output", {"text": "x"})
    await asyncio.sleep(0.4)
    pending = [r for r in _shadow_reviews(rid) if r["status"] == "pending"]
    assert len(pending) <= 1
    # 完成这个审阅（SILENT）；之后无新变化 → 不再调用模型
    ok = await _wait(lambda: len(brain.calls) > calls0)
    assert ok
    await brain.results.put({"review_result": _review_result(
        brain.calls[-1]["frame_id"])})
    ok = await _wait(lambda: _shadow_reviews(rid)[-1]["status"] == "done")
    assert ok
    n = len(brain.calls)
    await asyncio.sleep(0.5)
    assert len(brain.calls) == n, "无新有效变化时发生了自激审阅"
    await c.control(rid, "terminate", None, "op-term-t3")


async def test_t3b_shadow_failure_degrades_not_pauses():
    _seed_challenge()
    c, brain, ex = _rig(shadow=True)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    await _start(c, brain, rid)
    collab.submit_checkpoint(rid, {
        "schema_version": 1, "message_type": "checkpoint",
        "checkpoint_key": "fail-1", "review": "none", "stage": "progress",
        "report_md": "r", "evidence_refs": []},
        source="executor", notify=c.notify_run_change)
    db.append_event(rid, "controller", "submission.scored",
                    {"submission_id": "s1", "score": 0.4})
    c.notify_run_change(rid)
    ok = await _wait(lambda: len(brain.calls) >= 2)
    assert ok
    await brain.results.put({"error": "模型调用超时"})
    ok = await _wait(lambda: db.query_one(
        "SELECT degraded FROM supervision WHERE run_id=?", (rid,))["degraded"] == 1)
    assert ok
    assert c.run_snapshot(rid)["phase"] == "running", "shadow 失败不应暂停 Run"
    # 降级后不再自动发起 shadow 审阅
    n = len(brain.calls)
    collab.submit_checkpoint(rid, {
        "schema_version": 1, "message_type": "checkpoint",
        "checkpoint_key": "fail-2", "review": "none", "stage": "progress",
        "report_md": "r2", "evidence_refs": []},
        source="executor", notify=c.notify_run_change)
    await asyncio.sleep(0.4)
    assert len(brain.calls) == n
    await c.control(rid, "terminate", None, "op-term-t3b")


# ---------- T4-T8 请求与投递 ----------

def _cp_msg(key, review="none", stage="progress", report="报告"):
    return {"schema_version": 1, "message_type": "checkpoint",
            "checkpoint_key": key, "review": review, "stage": stage,
            "report_md": report, "evidence_refs": ["artifact:x"]}


async def test_t4_checkpoint_dedup_conflict_blocking_gate():
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)

    r1 = collab.submit_checkpoint(rid, _cp_msg("k1"), source="executor",
                                  notify=c.notify_run_change)
    assert r1["next_action"] == "continue" and not r1["deduplicated"]
    r2 = collab.submit_checkpoint(rid, _cp_msg("k1"), source="executor")
    assert r2["deduplicated"] and r2["checkpoint_id"] == r1["checkpoint_id"]
    with pytest.raises(collab.CollabError) as exc:
        collab.submit_checkpoint(rid, _cp_msg("k1", report="不同内容"),
                                 source="executor")
    assert exc.value.code == "CONFLICT"

    # blocking：门禁先 yielding，回合终态后 waiting_brain
    r3 = collab.submit_checkpoint(rid, _cp_msg("k2", review="blocking"),
                                  source="executor",
                                  notify=c.notify_run_change)
    assert r3["next_action"] == "yield" and r3["review_id"]
    assert c.run_snapshot(rid)["gate"] == "yielding"
    await ex.turn_done()
    ok = await _wait(lambda: c.run_snapshot(rid)["gate"] == "waiting_brain")
    assert ok
    # 无有效答复（SILENT）不解除等待
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    frame = [p for p in brain.calls if p.get("protocol") == "review_result"][-1]
    await brain.results.put({"review_result": _review_result(frame["frame_id"])})
    await asyncio.sleep(0.3)
    assert c.run_snapshot(rid)["gate"] == "waiting_brain"
    await c.control(rid, "terminate", None, "op-term-t4")


async def test_t5_guidance_queued_while_busy_then_boundary_delivery():
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    prompts0 = len(ex.prompts)

    # 执行器忙（busy=True 由 start_trial 的 prompt 设置）时用户请求审阅
    c.request_review(rid)
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    frame = brain.calls[-1]
    await brain.results.put({"review_result": _review_result(
        frame["frame_id"], disposition="intervene",
        guidance=_guidance(text="先做尺度分组") )})
    ok = await _wait(lambda: db.query_one(
        "SELECT status FROM guidance WHERE run_id=?", (rid,)) is not None)
    assert ok
    g = db.query_one("SELECT * FROM guidance WHERE run_id=?", (rid,))
    assert g["status"] == "queued", "执行器忙时指导必须排队，不得实时打断"
    assert len(ex.prompts) == prompts0 and not ex.steers

    # 到达空闲回合边界：恰好投递一次（prompt 渠道）
    await ex.turn_done()
    ok = await _wait(lambda: db.query_one(
        "SELECT status FROM guidance WHERE run_id=?", (rid,))["status"] == "sent")
    assert ok
    g = db.query_one("SELECT * FROM guidance WHERE run_id=?", (rid,))
    assert g["delivery_channel"] == "idle_prompt"
    assert len(ex.prompts) == prompts0 + 1
    assert g["id"] in ex.prompts[-1][1]

    # ACK 与行动证据分开；重复 ACK 幂等
    ack = collab.ack_guidance(rid, {
        "schema_version": 1, "message_type": "guidance_ack",
        "guidance_id": g["id"], "disposition": "accepted",
        "reason_md": "同意"})
    assert ack["status"] == "acknowledged"
    ack2 = collab.ack_guidance(rid, {
        "schema_version": 1, "message_type": "guidance_ack",
        "guidance_id": g["id"], "disposition": "accepted",
        "reason_md": "重复"})
    assert ack2["deduplicated"]
    collab.mark_applied(rid, g["id"], ["artifact:grouped"])
    g = db.query_one("SELECT * FROM guidance WHERE id=?", (g["id"],))
    assert json.loads(g["applied_evidence"]) == ["artifact:grouped"]
    await c.control(rid, "terminate", None, "op-term-t5")


async def test_t6_observe_continues_same_trial_and_challenge_recorded():
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    tid = await _start(c, brain, rid)

    c.request_review(rid)
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    await brain.results.put({"review_result": _review_result(
        brain.calls[-1]["frame_id"], disposition="intervene",
        guidance=_guidance(intent="observe"))})
    ok = await _wait(lambda: db.query_one(
        "SELECT id FROM guidance WHERE run_id=?", (rid,)) is not None)
    assert ok
    await ex.turn_done()
    ok = await _wait(lambda: db.query_one(
        "SELECT status FROM guidance WHERE run_id=?", (rid,))["status"] == "sent")
    assert ok
    g = db.query_one("SELECT * FROM guidance WHERE run_id=?", (rid,))
    # observe：沿同一 Trial/会话继续
    run = c.run_snapshot(rid)
    assert run["current_trial_id"] == tid
    trial = db.query_one("SELECT status FROM trials WHERE id=?", (tid,))
    assert trial["status"] == "active"
    # 执行器异议留证
    collab.ack_guidance(rid, {
        "schema_version": 1, "message_type": "guidance_ack",
        "guidance_id": g["id"], "disposition": "challenged",
        "reason_md": "分组结果已存在，见证据"})
    g = db.query_one("SELECT * FROM guidance WHERE id=?", (g["id"],))
    assert g["ack_disposition"] == "challenged"
    await c.control(rid, "terminate", None, "op-term-t6")


async def test_t7_turn_end_is_not_delivery_and_unknown_not_success():
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    tid = await _start(c, brain, rid)

    # 原生回合结束但没有 trial_complete 声明：Trial 保持 active
    await ex.turn_done()
    await asyncio.sleep(0.3)
    trial = db.query_one("SELECT status FROM trials WHERE id=?", (tid,))
    assert trial["status"] == "active"
    assert not db.query("SELECT id FROM review_requests WHERE run_id=?"
                        " AND trigger='trial_complete'", (rid,))
    # 未知终态：如实记录，不当成功
    await ex.emit({"type": "executor.turn_completed", "stop_reason": "unknown",
                   "detail": "stopReason=weird"})
    await asyncio.sleep(0.2)
    trial = db.query_one("SELECT status FROM trials WHERE id=?", (tid,))
    assert trial["status"] == "active"
    # 显式交付才进入生命周期审阅
    collab.submit_checkpoint(rid, _cp_msg("final", review="blocking",
                                          stage="trial_complete"),
                             source="executor", notify=c.notify_run_change)
    trial = db.query_one("SELECT status FROM trials WHERE id=?", (tid,))
    assert trial["status"] == "reported_complete"
    ok = await _wait(lambda: db.query_one(
        "SELECT id FROM review_requests WHERE run_id=?"
        " AND trigger='trial_complete'", (rid,)) is not None)
    assert ok
    await c.control(rid, "terminate", None, "op-term-t7")


async def test_t8_pause_invalidates_shadow_guidance_and_stop_gate():
    _seed_challenge()
    c, brain, ex = _rig(shadow=True)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    await _start(c, brain, rid)

    # shadow 审阅产生指导，执行器忙 → queued
    collab.submit_checkpoint(rid, _cp_msg("s1"), source="executor",
                             notify=c.notify_run_change)
    db.append_event(rid, "controller", "submission.scored",
                    {"submission_id": "s1", "score": 0.4})
    c.notify_run_change(rid)
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    await brain.results.put({"review_result": _review_result(
        brain.calls[-1]["frame_id"], disposition="intervene",
        guidance=_guidance())})
    ok = await _wait(lambda: _guidance_status(rid) == "queued")
    assert ok
    # 审阅期间暂停：迟到指导失效，不投递
    await c.control(rid, "pause", None, "op-pause-t8")
    g = db.query_one("SELECT * FROM guidance WHERE run_id=?", (rid,))
    assert g["status"] == "invalidated"
    await ex.turn_done()  # 暂停期间迟到终态不驱动投递
    await asyncio.sleep(0.3)
    assert db.query_one("SELECT status FROM guidance WHERE id=?",
                        (g["id"],))["status"] == "invalidated"
    await c.control(rid, "terminate", None, "op-term-t8")


async def test_t8b_stop_closes_gate_then_confirms_on_terminal():
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    tid = await _start(c, brain, rid)

    c.request_review(rid)
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    await brain.results.put({"review_result": _review_result(
        brain.calls[-1]["frame_id"], disposition="intervene",
        guidance=_guidance(kind="stop", intent="reframe",
                           text="停止扩展当前路线"))})
    ok = await _wait(lambda: c.run_snapshot(rid)["gate"] == "stopped")
    assert ok
    ok = await _wait(lambda: len(ex.aborts) == 1)
    assert ok, "stop 未请求原生取消"
    # 收到原生终态才确认已停
    await ex.emit({"type": "run.aborted", "detail": "cancelled"})
    ok = await _wait(lambda: db.query_one(
        "SELECT status FROM trials WHERE id=?", (tid,))["status"]
        == "interrupted")
    assert ok
    assert db.query_one(
        "SELECT 1 AS x FROM events WHERE run_id=? AND type='run.stop_confirmed'",
        (rid,))
    await c.control(rid, "terminate", None, "op-term-t8b")


# ---------- T9-T11 恢复与产品 ----------

def test_t9_restart_reconciliation_and_migration_idempotent():
    _seed_challenge()
    c = RunController()
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    now = db.utcnow()
    db.execute(
        "INSERT INTO review_requests(id, run_id, source, blocking, status,"
        " created_at, updated_at) VALUES(?,?,?,0,'running',?,?)",
        ("rev_hang", rid, "shadow", now, now))
    db.execute(
        "INSERT INTO guidance(id, run_id, source, kind, intent, text_md,"
        " status, created_at, updated_at) VALUES(?,?,?,?,?,?,'sending',?,?)",
        ("g_hang", rid, "shadow", "steer", "observe", "x", now, now))
    c._recover_review_requests(rid)
    assert db.query_one("SELECT status FROM review_requests WHERE id='rev_hang'"
                        )["status"] == "error"
    assert db.query_one("SELECT status FROM guidance WHERE id='g_hang'"
                        )["status"] == "unknown"
    # 迁移幂等：重复 init_db 不破坏既有数据
    db.init_db()
    db.init_db()
    assert db.query_one("SELECT status FROM review_requests WHERE id='rev_hang'"
                        )["status"] == "error"


def test_t10_frame_hygiene_and_token_scope():
    _seed_challenge()
    c = RunController()
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    collab.submit_checkpoint(rid, {
        "schema_version": 1, "message_type": "checkpoint",
        "checkpoint_key": "sec", "review": "none", "stage": "progress",
        "report_md": "密钥样本 sk-abc123 不应进帧", "evidence_refs": []},
        source="executor")
    frame = observation.build_frame(
        rid, mode="shadow", frame_id="f1", from_seq=1,
        through_seq=db.query_one("SELECT MAX(seq) AS s FROM events WHERE run_id=?",
                                 (rid,))["s"],
        shadow_cfg={"max_reviews": 8})
    blob = json.dumps(frame, ensure_ascii=False)
    assert "sk-abc123" not in blob and "abc123" not in blob  # 令牌主体不得残留
    assert "official_score" in frame["quality"]["unknown_fields"]
    assert frame["metrics"] == []  # 无登记指标时不编造
    # 能力令牌绑定 Run：其他 Run 的指导不能用本 Run 令牌语境确认
    with db.transaction() as conn:
        token = collab.issue_token(conn, rid, "executor", "sess-1", 1)
    identity = collab.validate_token(token)
    assert identity and identity["run_id"] == rid
    with pytest.raises(collab.CollabError) as exc:
        collab.ack_guidance(rid, {
            "schema_version": 1, "message_type": "guidance_ack",
            "guidance_id": "guidance-of-other-run", "disposition": "accepted",
            "reason_md": "x"})
    assert exc.value.code == "NOT_FOUND"


def test_t10b_executor_digest_reaches_frame():
    """执行器实质进展（非思考流）必须以摘录进大脑帧——修复大脑证据帧盲区。"""
    _seed_challenge()
    c = RunController()
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    db.append_event(rid, "executor", "prime.execution.progress",
                    {"detail": "思考: 该不该换数据集"})
    db.append_event(rid, "executor", "prime.execution.progress",
                    {"detail": "工具完成(Bash): wenyon 数据集 lifecycle_state=ready"})
    db.append_event(rid, "executor", "prime.execution.progress",
                    {"detail": "工具失败(Bash): 密钥 sk-probe999 不得进帧"})
    last = db.query_one("SELECT MAX(seq) AS s FROM events WHERE run_id=?",
                        (rid,))["s"]
    frame = observation.build_frame(
        rid, mode="shadow", frame_id="f1", from_seq=1, through_seq=last,
        shadow_cfg={"max_reviews": 8})
    excerpts = [d["excerpt"] for d in frame["executor_digest"]]
    assert any("lifecycle_state=ready" in x for x in excerpts), \
        "实质进展必须进帧，大脑不能只看计数"
    assert all("该不该换数据集" not in x for x in excerpts), \
        "思考流不进帧"
    blob = json.dumps(frame["executor_digest"], ensure_ascii=False)
    assert "sk-probe999" not in blob and "probe999" not in blob  # 脱敏
    # 生命周期帧的单事件摘要：实质进展与 notable 事件带 excerpt
    evs = db.events_after(rid, 0, limit=50)
    ex = [observation.event_excerpt(e) for e in evs]
    assert any("lifecycle_state=ready" in x.get("excerpt", "") for x in ex)
    thinking = [x for e, x in zip(evs, ex)
                if e["type"].startswith("prime.execution.progress")
                and "思考" in str(e["payload"].get("detail", ""))]
    assert thinking == [{}], "思考流在生命周期帧也不带摘录"
    # 摘要上限：超出取尾部并报告省略数
    many = [{"type": "prime.execution.progress", "seq": i,
             "payload": {"detail": f"工具完成(x): {i}"}} for i in range(20)]
    items, omitted_n = observation.executor_digest(many)
    assert len(items) == observation._MAX_DIGEST_ITEMS and omitted_n == 8
    assert items[-1]["seq"] == 19


def test_t10c_question_parsing_from_real_fixture():
    """AskUserQuestion 线协议帧形状解析。"""
    from cyberscientist.prime.kimi_acp import (
        _is_question_options, _permission_pick, _question_from_elicitation,
        _question_from_permission)
    # elicitation/create 协议帧
    eli = {"sessionId": "s", "toolCallId": "t", "mode": "form",
           "message": "冒烟测试用哪个 GPU？",
           "requestedSchema": {"type": "object", "properties": {
               "q0": {"type": "string", "title": "GPU", "oneOf": [
                   {"const": "A100（推荐）", "title": "A100（推荐）"},
                   {"const": "L20", "title": "L20"}]}}, "required": ["q0"]}}
    q = _question_from_elicitation(eli)
    assert q["message"] == "冒烟测试用哪个 GPU？"
    assert q["questions"][0]["required"] is True
    assert q["questions"][0]["options"][1]["const"] == "L20"
    # request_permission 回退协议帧
    opts = [{"optionId": "q0_opt_0", "name": "A100（推荐）", "kind": "allow_once"},
            {"optionId": "q0_opt_1", "name": "L20", "kind": "allow_once"},
            {"optionId": "q0_skip", "name": "Skip", "kind": "reject_once"}]
    assert _is_question_options(opts)
    assert not _is_question_options(
        [{"optionId": "approve_once", "kind": "allow_once"}])
    perm = {"options": opts, "toolCall": {"title": "AskUserQuestion"}}
    qp = _question_from_permission(perm)
    assert qp["questions"][0]["options"][1]["option_id"] == "q0_opt_1"
    assert _permission_pick(perm, {"q0": "L20"}) == "q0_opt_1"
    assert _permission_pick(perm, {"q0": "不存在的选项"}) is None


def test_t10d_extract_question_answer():
    from cyberscientist.decision_extraction import extract_question_answer
    good = ('```json\n{"schema_version":1,"answers":{"q0":"L20"},'
            '"reason_md":"只有 L20 配额"}\n```')
    ans = extract_question_answer(good)
    assert ans and ans["native_answers"] == {"q0": "L20"}
    assert ans["answer_md"] == "只有 L20 配额"
    free = extract_question_answer('{"schema_version":1,"message_type":"research_answer",'
                                   '"request_id":"r","answer_md":"第三路线",'
                                   '"evidence_refs":[],"native_answers":null}')
    assert free and free["native_answers"] is None
    assert extract_question_answer('{"schema_version":1,"answers":{}}') is None
    assert extract_question_answer("没有任何 JSON") is None


async def test_t10e_executor_question_routed_to_brain():
    """Native questions keep an open judgment and legal form mapping separate."""
    _seed_challenge()
    c, brain, ex = _rig()
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    assert await _wait(lambda: bool(ex.prompts))

    question = {"message": "冒烟测试用哪个 GPU？",
                "questions": [{"id": "q0", "title": "GPU", "required": True,
                               "options": [{"const": "A100（推荐）"},
                                           {"const": "L20"}]}]}

    async def ask():
        return await c._answer_executor_question(rid, question)

    # 合法回答：路由大脑、校验通过、返回答案
    task = asyncio.create_task(ask())
    assert await _wait(lambda: any(
        p.get("protocol") == "executor_question" for p in brain.calls)), \
        "大脑未收到 executor_question 审阅"
    packet = [p for p in brain.calls
              if p.get("protocol") == "executor_question"][0]
    assert packet["question"]["message"] == "冒烟测试用哪个 GPU？"
    await brain.results.put({"question_answer": {
        "answers": {"q0": "L20"}, "reason_md": "配额只有 L20"}})
    answer = await asyncio.wait_for(task, 5)
    assert answer and answer["native_answers"] == {"q0": "L20"}
    assert answer["answer_md"] == "配额只有 L20"
    rows = db.query("SELECT type FROM events WHERE run_id=?"
                    " AND type='brain.question_answered'", (rid,))
    assert len(rows) == 1, "大脑回答必须留痕"
    # 选项外判断保留完整正文，表单只能 decline。
    task2 = asyncio.create_task(ask())
    assert await _wait(lambda: len([p for p in brain.calls if p.get(
        "protocol") == "executor_question"]) >= 2)
    await brain.results.put({"question_answer": {
        "answers": {"q0": "H100"}, "reason_md": "自创选项"}})
    answer2 = await asyncio.wait_for(task2, 5)
    assert answer2 and answer2["answer_md"] == "自创选项"
    assert answer2["native_answers"] is None
    await c.control(rid, "terminate", None, "op-term-t10e")

def test_t11_experience_revision_reaches_frame_body():
    _seed_challenge()
    c = RunController()
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    exp_id = "exp_t11"
    r1 = experiences.save_experience(
        exp_id, {"title": "尺度分组", "scope": "challenge",
                 "challenge_id": "COLLAB_CH", "status": "active",
                 "evidence_status": "observed", "kind": "heuristic",
                 "applicability": "a", "evidence_refs": []},
        "第一版正文：先分组", operator="user", reason="init", base_hash=None)
    frame = observation.build_frame(
        rid, mode="shadow", frame_id="f1", from_seq=1,
        through_seq=db.query_one("SELECT MAX(seq) AS s FROM events WHERE run_id=?",
                                 (rid,))["s"],
        shadow_cfg={"max_reviews": 8})
    assert any("第一版正文" in e["body_md"] for e in frame["experiences"]), \
        "大脑输入必须包含选定经验修订的正文，不只是标题/hash"
    # 编辑产生新修订；帧读到新正文，旧修订保留
    experiences.save_experience(
        exp_id, {"title": "尺度分组", "scope": "challenge",
                 "challenge_id": "COLLAB_CH", "status": "active",
                 "evidence_status": "observed", "kind": "heuristic",
                 "applicability": "a", "evidence_refs": []},
        "第二版正文：先查噪声", operator="user", reason="edit",
        base_hash=r1["revision_hash"])
    frame2 = observation.build_frame(
        rid, mode="shadow", frame_id="f2", from_seq=1,
        through_seq=db.query_one("SELECT MAX(seq) AS s FROM events WHERE run_id=?",
                                 (rid,))["s"],
        shadow_cfg={"max_reviews": 8})
    assert any("第二版正文" in e["body_md"] for e in frame2["experiences"])
    revs = experiences.get_revisions(exp_id)
    assert len(revs) == 2


# ---------- 工具端点（能力令牌 HTTP 路径）----------

async def test_tools_endpoints_token_auth():
    from httpx import ASGITransport, AsyncClient

    from cyberscientist.api import create_app

    _seed_challenge()
    c = RunController()
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    db.execute("INSERT INTO supervision(run_id, enabled, updated_at)"
               " VALUES(?,0,?)", (rid, db.utcnow()))
    with db.transaction() as conn:
        token = collab.issue_token(conn, rid, "executor", "sess-1", 1)
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as cli:
        # 无令牌拒绝
        r = await cli.post("/api/v1/tools/checkpoint", json=_cp_msg("t1"))
        assert r.status_code == 401
        # 有令牌登记检查点
        r = await cli.post("/api/v1/tools/checkpoint", json=_cp_msg("t1"),
                           headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["checkpoint_id"] and body["next_action"] == "continue"
        # 未投递指导不能 ACK
        r = await cli.post("/api/v1/tools/ack", json={
            "guidance_id": "g-none", "disposition": "accepted",
            "reason_md": "x"}, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404


# ---------- 审查修复回归（B1/S1/S2/S3）----------

async def test_b1_inflight_shadow_result_expires_after_disable():
    """在途 shadow 审阅期间关闭监督：迟到结果失效，不覆盖笔记、不生成指导。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=True)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    await _start(c, brain, rid)

    collab.submit_checkpoint(rid, _cp_msg("b1", review="none"),
                             source="executor", notify=c.notify_run_change)
    db.append_event(rid, "controller", "submission.scored",
                    {"submission_id": "s1", "score": 0.4})
    c.notify_run_change(rid)
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok, "shadow 审阅未开始"
    frame = brain.calls[-1]
    c.set_shadow(rid, False)  # 审阅在途时关闭监督
    await brain.results.put({"review_result": _review_result(
        frame["frame_id"], disposition="intervene",
        guidance=_guidance(text="迟到指导"), note="迟到笔记")})
    ok = await _wait(lambda: db.query_one(
        "SELECT status FROM review_requests WHERE run_id=?"
        " AND source='shadow'", (rid,))["status"] == "obsolete")
    assert ok, "迟到 shadow 结果未失效"
    sup = db.query_one("SELECT * FROM supervision WHERE run_id=?", (rid,))
    assert sup["private_note_md"] == "", "旧结果覆盖了大脑笔记"
    assert db.query_one("SELECT id FROM guidance WHERE run_id=?",
                        (rid,)) is None, "旧结果生成了指导"
    await c.control(rid, "terminate", None, "op-term-b1")


async def test_s1_review_completion_does_not_deliver_when_paused():
    """审阅完成时 Run 已暂停：过期审阅标 obsolete，不得唤醒执行器。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    await ex.turn_done()  # 空闲边界，控制器 busy=False
    prompts0 = len(ex.prompts)

    c.request_review(rid)
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    frame = brain.calls[-1]
    await c.control(rid, "pause", None, "op-pause-s1")  # 审阅在途时暂停
    ok = await _wait(lambda: c.run_snapshot(rid)["phase"] == "paused")
    assert ok
    await brain.results.put({"review_result": _review_result(
        frame["frame_id"], disposition="intervene",
        guidance=_guidance(text="暂停期间不得投递"))})
    ok = await _wait(lambda: db.query_one(
        "SELECT 1 FROM review_requests WHERE run_id=? AND status='obsolete'", (rid,)) is not None)
    assert ok
    assert db.query_one("SELECT * FROM guidance WHERE run_id=?",(rid,)) is None
    assert len(ex.prompts) == prompts0, "暂停期间不得唤醒执行器"
    await c.control(rid, "terminate", None, "op-term-s1")


async def test_s2_blocking_review_failure_pauses_not_strands():
    """blocking 审阅失败：暂停并说明原因，gate 不得永久卡死。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)

    collab.submit_checkpoint(rid, _cp_msg("s2", review="blocking"),
                             source="executor", notify=c.notify_run_change)
    assert c.run_snapshot(rid)["gate"] == "yielding"
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    await brain.results.put({"error": "模拟大脑调用失败"})
    ok = await _wait(lambda: c.run_snapshot(rid)["phase"] == "paused")
    assert ok, "blocking 审阅失败后 Run 应暂停而非卡死等待"
    assert c.run_snapshot(rid)["block_reason"], "暂停必须携带原因"
    await c.control(rid, "terminate", None, "op-term-s2")


def test_s3_new_session_token_revokes_old():
    """新会话签发令牌前撤销旧令牌：旧身份不能 ACK 新会话的指导。"""
    _seed_challenge()
    c, _, _ = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    with db.transaction() as conn:
        t1 = collab.issue_token(conn, rid, "executor", "sess-1", 1)
    assert collab.validate_token(t1) is not None
    with db.transaction() as conn:  # _prime_spec 签发路径：先撤销再签发
        collab.revoke_run_tokens(conn, rid)
        t2 = collab.issue_token(conn, rid, "executor", "sess-2", 2)
    assert collab.validate_token(t1) is None
    assert collab.validate_token(t2) is not None


async def test_t13_submit_guidance_auto_submits_without_executor(monkeypatch):
    """kind=submit：系统自动用实验邮箱提交，不投递给执行器、不改门禁。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)

    calls: list[tuple] = []

    def fake_submit(run_id, trial_id, package_path, operation_id):
        calls.append((run_id, trial_id, package_path, operation_id))
        return {"id": "sub_fake1", "status": "submitted",
                "platform_ref": "99999", "error": None}

    monkeypatch.setattr(
        "cyberscientist.controller.mailboxes.submit_experiment", fake_submit)

    prompts0 = len(ex.prompts)
    c.request_review(rid)
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    frame = brain.calls[-1]
    await brain.results.put({"review_result": _review_result(
        frame["frame_id"], disposition="intervene",
        guidance=_guidance(kind="submit", intent="continue",
                           text="结果包已就绪，提交"))})

    ok = await _wait(lambda: db.query_one(
        "SELECT status FROM guidance WHERE run_id=?", (rid,)) is not None
        and db.query_one("SELECT status FROM guidance WHERE run_id=?",
                         (rid,))["status"] == "applied")
    assert ok, "submit 指导应被执行并标记 applied"
    g = db.query_one("SELECT * FROM guidance WHERE run_id=?", (rid,))
    assert g["kind"] == "submit"
    assert g["delivery_channel"] == "system_action"
    assert len(calls) == 1, "应恰好自动提交一次"
    assert calls[0][0] == rid and calls[0][2] is None
    assert calls[0][3] == f"auto-{g['id']}", "幂等键必须绑定 guidance"
    # 不投递给执行器（无新增 prompt），门禁不受影响
    await ex.turn_done()
    await asyncio.sleep(0.3)
    assert len(ex.prompts) == prompts0
    assert c.run_snapshot(rid)["gate"] == "open"
    ev = db.query_one(
        "SELECT type FROM events WHERE run_id=? AND type='submission.auto_done'",
        (rid,))
    assert ev is not None
    await c.control(rid, "terminate", None, "op-term-t13")


async def test_t13b_submit_guidance_failure_marks_failed(monkeypatch):
    """submit 失败：guidance 标 failed、记事件，不自动重试配额动作。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)

    from cyberscientist import mailboxes

    def boom(run_id, trial_id, package_path, operation_id):
        raise mailboxes.MailboxError("NO_MAILBOX", "无可用实验邮箱")

    monkeypatch.setattr(
        "cyberscientist.controller.mailboxes.submit_experiment", boom)

    c.request_review(rid)
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    frame = brain.calls[-1]
    await brain.results.put({"review_result": _review_result(
        frame["frame_id"], disposition="intervene",
        guidance=_guidance(kind="submit", intent="continue", text="提交"))})
    def _failed():
        row = db.query_one(
            "SELECT status FROM guidance WHERE run_id=?", (rid,))
        return row is not None and row["status"] == "failed"
    ok = await _wait(_failed)
    assert ok
    ev = db.query_one(
        "SELECT payload FROM events WHERE run_id=?"
        " AND type='submission.auto_failed'", (rid,))
    assert ev is not None and "NO_MAILBOX" in ev["payload"] \
        and "无可用实验邮箱" in ev["payload"]
    await c.control(rid, "terminate", None, "op-term-t13b")


def test_submit_kind_in_contract_schema():
    """契约 schema 必须接受 kind=submit（大脑才可能发出）。"""
    import jsonschema

    from cyberscientist.controller import _REVIEW_RESULT_SCHEMA
    schema = {"$ref": "#/$defs/ReviewResult",
              "$defs": _REVIEW_RESULT_SCHEMA["$defs"]}
    r = _review_result("f1", disposition="intervene",
                       guidance=_guidance(kind="submit", intent="continue",
                                          text="提交"))
    jsonschema.validate(r, schema)  # 不抛即通过


async def test_trial_prompt_includes_enabled_skills(tmp_path, monkeypatch):
    """启用技能（常驻 ∪ 本题绑定）注入执行器任务文本并记录事件。"""
    sdir = tmp_path / "skills_root" / "tdd"
    sdir.mkdir(parents=True)
    (sdir / "SKILL.md").write_text(
        "---\nname: tdd\ndescription: 测试驱动开发\n---\n\n正文",
        encoding="utf-8")
    monkeypatch.setattr(skills, "SKILL_DIRS", (tmp_path / "skills_root",))

    _seed_challenge()
    with db.transaction() as conn:
        db.bind_challenge_skill(conn, "COLLAB_CH", "tdd")
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    tid = await _start(c, brain, rid)

    prompt = ex.prompts[-1][1]
    assert "本 Trial 启用技能" in prompt
    assert "- tdd: 测试驱动开发" in prompt
    ev = db.query_one(
        "SELECT payload, trial_id FROM events WHERE run_id=?"
        " AND type='trial.skills_enabled'", (rid,))
    assert ev is not None
    payload = json.loads(ev["payload"])
    assert payload["skills"] == ["tdd"]
    assert payload["trial_id"] == tid
    assert ev["trial_id"] == tid
    await c.control(rid, "terminate", None, "op-term-skills")


async def test_trial_prompt_without_skills_unchanged(tmp_path, monkeypatch):
    """无生效技能时任务文本不含技能段落，也不记录事件。"""
    monkeypatch.setattr(skills, "SKILL_DIRS", (tmp_path / "empty_root",))
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)

    assert "本 Trial 启用技能" not in ex.prompts[-1][1]
    assert db.query_one(
        "SELECT event_id FROM events WHERE run_id=?"
        " AND type='trial.skills_enabled'", (rid,)) is None
    await c.control(rid, "terminate", None, "op-term-noskills")


# ---------- 容错：格式问题不整单拒收 ----------

async def test_review_salvage_string_watchlist():
    """watchlist 写成字符串数组：就地包装为 Watch 对象接受，笔记与审阅不陪葬。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=True)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    await _start(c, brain, rid)
    collab.submit_checkpoint(rid, {
        "schema_version": 1, "message_type": "checkpoint",
        "checkpoint_key": "salvage-1", "review": "async", "stage": "progress",
        "report_md": "r", "evidence_refs": []},
        source="executor", notify=c.notify_run_change)
    ok = await _wait(lambda: len(brain.calls) >= 2)
    assert ok
    frame = brain.calls[-1]
    await brain.results.put({"review_result": _review_result(
        frame["frame_id"], note="笔记保留",
        watchlist=["r 的二分外层是否收敛（资本需求单调性）"])})
    ok = await _wait(lambda: "hypothesis_md" in (db.query_one(
        "SELECT watchlist FROM supervision WHERE run_id=?",
        (rid,))["watchlist"] or ""))
    assert ok, "字符串 watchlist 未被容错接受"
    sup = db.query_one("SELECT private_note_md, watchlist FROM supervision"
                       " WHERE run_id=?", (rid,))
    assert sup["private_note_md"] == "笔记保留"
    wl = json.loads(sup["watchlist"])
    assert wl[0]["hypothesis_md"] == "r 的二分外层是否收敛（资本需求单调性）"
    types = [e["type"] for e in db.events_after(rid, 0)]
    assert "brain.review_salvaged" in types
    assert "brain.error" not in types
    assert db.query_one("SELECT status FROM review_requests WHERE run_id=?"
                        " AND source='executor'", (rid,))["status"] == "done"
    await c.control(rid, "terminate", None, "op-term-salv1")


async def test_review_salvage_bad_guidance_downgrades():
    """intervene 但 guidance 缺必填字段：丢 guidance 降级 silent，笔记仍保存。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=True)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    await _start(c, brain, rid)
    collab.submit_checkpoint(rid, {
        "schema_version": 1, "message_type": "checkpoint",
        "checkpoint_key": "salvage-2", "review": "async", "stage": "progress",
        "report_md": "r", "evidence_refs": []},
        source="executor", notify=c.notify_run_change)
    ok = await _wait(lambda: len(brain.calls) >= 2)
    assert ok
    frame = brain.calls[-1]
    await brain.results.put({"review_result": _review_result(
        frame["frame_id"], disposition="intervene",
        guidance={"kind": "steer"}, note="坏指导不陪葬")})
    ok = await _wait(lambda: db.query_one(
        "SELECT private_note_md FROM supervision WHERE run_id=?",
        (rid,))["private_note_md"] == "坏指导不陪葬")
    assert ok, "guidance 非法时整张审阅被拒收"
    assert db.query("SELECT id FROM guidance WHERE run_id=?", (rid,)) == []
    salv = [e for e in db.events_after(rid, 0)
            if e["type"] == "brain.review_salvaged"]
    assert salv and any("降级" in f for f in salv[-1]["payload"]["fixes"])
    assert db.query_one("SELECT status FROM review_requests WHERE run_id=?"
                        " AND source='executor'", (rid,))["status"] == "done"
    await c.control(rid, "terminate", None, "op-term-salv2")


async def test_decision_per_action_rejection():
    """单个动作非法只拒该动作并进事件流，其余动作照常执行。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    tid = await _start(c, brain, rid)
    seq0 = db.query_one("SELECT COALESCE(MAX(seq),0) AS s FROM events"
                        " WHERE run_id=?", (rid,))["s"]
    v = c.run_snapshot(rid)["state_version"]
    await c._apply_decision(rid, _decision([
        {"op": "steer", "trial_id": "trial_nope", "message": "错 Trial"},
        {"op": "wait", "reason": "好动作"}], sv=v, rid=rid), {}, None, None)
    events = db.events_after(rid, seq0)
    types = [e["type"] for e in events]
    assert "brain.decision_rejected" not in types, "整单拒收不应再发生"
    rejected = [e for e in events if e["type"] == "brain.action_rejected"]
    assert rejected and any("不符" in r for r in rejected[0]["payload"]["reasons"])
    assert "brain.wait" in types, "合法动作未执行"
    await c.control(rid, "terminate", None, "op-term-peract")


async def test_decision_second_direction_op_rejected_only():
    """同一 Decision 第二个方向动作被拒，第一个与经验提议不受影响。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    seq0 = db.query_one("SELECT COALESCE(MAX(seq),0) AS s FROM events"
                        " WHERE run_id=?", (rid,))["s"]
    v = c.run_snapshot(rid)["state_version"]
    await c._apply_decision(rid, _decision([
        {"op": "wait", "reason": "先观察"},
        {"op": "finish", "reason": "结束"},
        {"op": "finish", "reason": "重复结束"}], sv=v, rid=rid), {}, None, None)
    events = db.events_after(rid, seq0)
    types = [e["type"] for e in events]
    # finish 被收尾整理推迟（见 test_finish_defers_to_curation_then_finalizes）
    assert types.count("run.finished") == 0
    assert "run.finish_deferred" in types
    assert db.query_one("SELECT id FROM review_requests WHERE run_id=?"
                        " AND trigger='curation'", (rid,))
    rejected = [e["payload"] for e in events
                if e["type"] == "brain.action_rejected"]
    assert any("最多一个" in (p.get("reason") or "") for p in rejected)
    # 整理审阅完结后自动收尾
    ok = await _wait(lambda: len(brain.calls) >= 2)
    assert ok
    await brain.results.put({"decision": _decision(
        [{"op": "wait", "reason": "整理完毕"}], sv=v, rid=rid)})
    ok = await _wait(lambda: c.run_snapshot(rid)["phase"] == "finished")
    assert ok


# ---------- 终止/重启可靠性 ----------

async def test_terminate_aborts_executor_and_cleans_trials():
    """终止：执行器会话收到 abort、stalled Trial 一并 interrupted、悬空审阅作废。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    tid = await _start(c, brain, rid)
    db.execute("UPDATE trials SET status='stalled' WHERE id=?", (tid,))
    db.execute(
        "INSERT INTO review_requests(id, run_id, source, trigger, blocking,"
        " status, created_at, updated_at) VALUES(?,?,?,?,0,'pending',?,?)",
        ("rev_dangle", rid, "shadow", "passive", db.utcnow(), db.utcnow()))
    r = await c.control(rid, "terminate", None, "op-term-clean")
    assert r["status"] == "confirmed"
    assert ex.aborts, "终止未 abort 执行器会话（孤儿进程风险）"
    assert db.query_one("SELECT status FROM trials WHERE id=?",
                        (tid,))["status"] == "interrupted"
    assert db.query_one("SELECT status FROM review_requests WHERE id=?",
                        ("rev_dangle",))["status"] == "obsolete"
    assert c.run_snapshot(rid)["phase"] == "cancelled"


async def test_reconcile_and_resume_after_restart():
    """重启对账：僵尸 Run 标记 recovering；恢复重建会话并让大脑以 recovery 裁决。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    c.authorize(rid, "demo", True, 10, 30, 0, None)
    # 模拟后端崩溃后的僵尸：phase 停在 running，但没有任何会话/事件循环
    db.execute("UPDATE runs SET phase='running', started_at=? WHERE id=?",
               (db.utcnow(), rid))
    db.execute(
        "INSERT INTO review_requests(id, run_id, source, trigger, blocking,"
        " status, created_at, updated_at) VALUES(?,?,?,?,0,'running',?,?)",
        ("rev_zombie", rid, "lifecycle", "run_start", db.utcnow(), db.utcnow()))
    marked = c.reconcile_on_startup()
    assert marked == [rid]
    snap = c.run_snapshot(rid)
    assert snap["phase"] == "recovering" and "后端重启" in snap["block_reason"]
    assert db.query_one("SELECT status FROM review_requests WHERE id=?",
                        ("rev_zombie",))["status"] == "obsolete"
    types = [e["type"] for e in db.events_after(rid, 0)]
    assert "run.needs_recovery" in types
    # 恢复：重建循环，大脑收到 recovery 触发的生命周期审阅
    r = await c.control(rid, "resume", None, "op-resume-rec")
    assert r["status"] == "confirmed"
    ok = await _wait(lambda: any(
        p.get("trigger") == "recovery" for p in brain.calls))
    assert ok, "恢复后大脑未收到 recovery 审阅"
    assert c.run_snapshot(rid)["phase"] == "running"
    await brain.results.put({"decision": _decision(
        [{"op": "wait", "reason": "恢复后观察"}], rid=rid)})
    await asyncio.sleep(0.3)
    await c.control(rid, "terminate", None, "op-term-rec")


async def test_periodic_shadow_wakes_brain_when_executor_silent():
    """Old Run snapshots retain their periodic supervision semantics."""
    _seed_challenge()
    c, brain, ex = _rig(shadow=True, max_interval=0.2)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    old = json.loads(db.query_one("SELECT config_snapshot FROM runs WHERE id=?",
                                  (rid,))["config_snapshot"])
    old.pop("sparse_brain_version")
    db.execute("UPDATE runs SET config_snapshot=? WHERE id=?",
               (json.dumps(old), rid))
    await _start(c, brain, rid)
    n0 = len(brain.calls)
    # 只来心跳（非触发词表），等时间兜底
    await ex.emit({"type": "execution.progress", "detail": "埋头干活"})
    ok = await _wait(lambda: len(brain.calls) > n0)
    assert ok, "时间兜底未唤起大脑"
    reqs = db.query("SELECT * FROM review_requests WHERE run_id=?"
                    " AND source='shadow'", (rid,))
    assert any(r["trigger"] == "periodic" for r in reqs)
    # 答复后 covered_seq 推进；无新事件不再自激
    await brain.results.put({"review_result": _review_result(
        brain.calls[-1]["frame_id"], note="周期性查看")})
    ok = await _wait(lambda: db.query_one(
        "SELECT covered_seq FROM supervision WHERE run_id=?",
        (rid,))["covered_seq"] > 0)
    assert ok
    n = len(brain.calls)
    await asyncio.sleep(0.6)
    assert len(brain.calls) == n, "无新事件时 periodic 自激"
    collab.submit_checkpoint(rid, _cp_msg("old-run-checkpoint", review="none",
                                         report="旧 Run 报告正文"),
                             source="executor", notify=c.notify_run_change)
    assert await _wait(lambda: len(brain.calls) > n)
    assert brain.calls[-1]["checkpoint_summaries"][-1]["report_md"] == "旧 Run 报告正文"
    await brain.results.put({"review_result": _review_result(brain.calls[-1]["frame_id"])})
    await c.control(rid, "terminate", None, "op-term-periodic")


async def test_sparse_brain_normal_progress_does_not_periodically_review():
    _seed_challenge()
    c, brain, ex = _rig(shadow=True, max_interval=0.2)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    trial_id = await _start(c, brain, rid)
    db.execute("INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,"
               "spec_json,input_directory,status,created_at,updated_at)"
               " VALUES(?,?,?,?,?,?,?,?,?)",
               ("op-long", rid, trial_id, "hash", "{}", "/tmp/fake",
                "Running", db.utcnow(), db.utcnow()))
    count = len(brain.calls)
    await ex.emit({"type": "execution.progress", "detail": "正常长任务仍在进行"})
    await ex.emit({"type": "trial.stalled", "detail": "执行器在等待 Job"})
    await asyncio.sleep(0.6)
    assert len(brain.calls) == count
    assert db.query_one("SELECT status FROM trials WHERE id=?",
                        (trial_id,))["status"] == "active"
    assert db.query_one("SELECT 1 FROM review_requests WHERE run_id=?"
                        " AND trigger='periodic'", (rid,)) is None
    collab.submit_checkpoint(rid, _cp_msg("milestone", review="none"),
                             source="executor", notify=c.notify_run_change)
    await asyncio.sleep(0.6)
    assert len(brain.calls) == count
    assert _shadow_reviews(rid) == []
    await c.control(rid, "terminate", None, "op-term-sparse-periodic")


async def test_sparse_checkpoint_summary_and_explicit_review_once():
    from cyberscientist import research_trace

    _seed_challenge()
    c, brain, _ = _rig(shadow=True, max_interval=0.2)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    await _start(c, brain, rid)
    count = len(brain.calls)
    report = ("pip install package\nbash run.sh\n大量工具日志\n"
              "最终科学结论：频率失败，但几何可复用")
    summarized = _cp_msg("with-summary", review="none", report=report)
    summarized["research_summary_md"] = "频率阶段失败；成功几何仍可复用；失败原因尚未确认。"
    first = collab.submit_checkpoint(rid, summarized, source="executor",
                                     notify=c.notify_run_change)
    legacy = _cp_msg("legacy-no-summary", review="async", report=report)
    second = collab.submit_checkpoint(rid, legacy, source="executor",
                                      notify=c.notify_run_change)
    assert first["review_id"] is None and second["review_id"]
    assert await _wait(lambda: len(brain.calls) > count)
    frame = brain.calls[-1]
    checkpoints = {item["checkpoint_id"]: item
                   for item in frame["checkpoint_summaries"]}
    assert checkpoints[first["checkpoint_id"]]["research_summary_md"] == summarized["research_summary_md"]
    assert checkpoints[first["checkpoint_id"]]["research_summary_available"] is True
    assert checkpoints[second["checkpoint_id"]]["research_summary_available"] is False
    assert checkpoints[second["checkpoint_id"]]["stage"] == "progress"
    assert checkpoints[second["checkpoint_id"]]["evidence_refs"] == legacy["evidence_refs"]
    assert "report_md" not in checkpoints[first["checkpoint_id"]]
    assert "report_md" not in checkpoints[second["checkpoint_id"]]
    serialized = json.dumps(frame, ensure_ascii=False)
    assert "pip install" not in serialized and "bash run.sh" not in serialized
    assert "大量工具日志" not in serialized
    read = research_trace.access(rid, {"action": "read",
                                      "ref": f"checkpoint:{second['checkpoint_id']}"})
    assert json.loads(read["content"])["report_md"] == report
    assert db.query_one("SELECT report FROM checkpoints WHERE id=?",
                        (first["checkpoint_id"],))["report"] == report
    await brain.results.put({"review_result": _review_result(frame["frame_id"])})
    assert await _wait(lambda: db.query_one(
        "SELECT status FROM review_requests WHERE id=?",
        (second["review_id"],))["status"] == "done")
    await asyncio.sleep(0.4)
    assert len(brain.calls) == count + 1
    assert _shadow_reviews(rid) == []
    final = collab.submit_checkpoint(
        rid, _cp_msg("research-delivery", review="none", stage="trial_complete"),
        source="executor", notify=c.notify_run_change)
    assert final["review_id"] and final["next_action"] == "yield"
    lifecycle = db.query_one("SELECT source,trigger FROM review_requests WHERE id=?",
                             (final["review_id"],))
    assert (lifecycle["source"], lifecycle["trigger"]) == ("lifecycle", "trial_complete")
    assert c.run_snapshot(rid)["gate"] == "yielding"
    assert await _wait(lambda: len(brain.calls) == count + 2)
    assert _shadow_reviews(rid) == []
    await c.control(rid, "terminate", None, "op-term-summary")


async def test_sparse_job_terminal_transition_wakes_once():
    _seed_challenge()
    c, brain, _ = _rig(shadow=True, max_interval=0.2)
    rid = c.create_run("COLLAB_CH", shadow_enabled=True)["id"]
    await _start(c, brain, rid)
    count = len(brain.calls)

    for status in ("Running", "Running", "Scheduling", "Pending"):
        db.append_event(rid, "controller", "job.observed",
                        {"operation_id": "job-1", "status": status})
        c.notify_run_change(rid)
    await asyncio.sleep(0.35)
    assert len(brain.calls) == count
    assert _shadow_reviews(rid) == []

    db.append_event(rid, "controller", "job.observed",
                    {"operation_id": "job-1", "status": "Failed"})
    c.notify_run_change(rid)
    assert await _wait(lambda: len(brain.calls) == count + 1)
    await brain.results.put({"review_result": _review_result(brain.calls[-1]["frame_id"])})
    assert await _wait(lambda: _shadow_reviews(rid)[-1]["status"] == "done")
    db.append_event(rid, "controller", "job.observed",
                    {"operation_id": "job-1", "status": "Failed"})
    c.notify_run_change(rid)
    await asyncio.sleep(0.35)
    assert len(brain.calls) == count + 1
    assert len(_shadow_reviews(rid)) == 1
    db.append_event(rid, "controller", "submission.scored",
                    {"submission_id": "score-1", "score": 0.6})
    c.notify_run_change(rid)
    assert await _wait(lambda: len(brain.calls) == count + 2)
    await brain.results.put({"review_result": _review_result(brain.calls[-1]["frame_id"])})
    assert await _wait(lambda: _shadow_reviews(rid)[-1]["status"] == "done")
    trial_id = c.run_snapshot(rid)["current_trial_id"]
    db.append_event(rid, "controller", "trial.stalled",
                    {"trial_id": trial_id}, trial_id=trial_id)
    c.notify_run_change(rid)
    assert await _wait(lambda: len(brain.calls) == count + 3)
    await brain.results.put({"review_result": _review_result(brain.calls[-1]["frame_id"])})
    assert await _wait(lambda: _shadow_reviews(rid)[-1]["status"] == "done")
    db.append_event(rid, "controller", "trial.stalled",
                    {"trial_id": trial_id}, trial_id=trial_id)
    c.notify_run_change(rid)
    await asyncio.sleep(0.35)
    assert len(brain.calls) == count + 3
    await c.control(rid, "terminate", None, "op-term-job-transition")


async def test_sparse_brain_open_answer_optional_read_and_delivery():
    """Actual controller + MCP HTTP + fake native sessions + outbox."""
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app

    class SelectiveBrain(ScriptableBrain):
        def __init__(self):
            super().__init__()
            self.question_count = 0
            self.reads = []
            self.target_ref = ""

        def review(self, session, packet):
            if packet.get("protocol") != "executor_question":
                return super().review(session, packet)

            async def gen():
                self.calls.append(packet)
                self.question_count += 1
                refs = []
                if self.question_count == 2:
                    token = self.open_spec["env"]["CS_TOOL_TOKEN"]
                    headers = {"Authorization": f"Bearer {token}"}
                    async with AsyncClient(transport=ASGITransport(app=create_app()),
                                           base_url="http://test") as cli:
                        listing = await cli.post("/api/v1/tools/trace",
                                                 json={"action": "list", "keyword": "失败回执"},
                                                 headers=headers)
                        assert listing.status_code == 200, listing.text
                        assert any(x["ref"] == self.target_ref
                                   for x in listing.json()["items"])
                        reading = await cli.post("/api/v1/tools/trace",
                                                 json={"action": "read", "ref": self.target_ref},
                                                 headers=headers)
                        assert reading.status_code == 200, reading.text
                        self.reads.append(reading.json())
                    refs = [self.target_ref]
                body = (("需要先保留成功几何，再核实频率失败阶段；独立产物可以继续。" * 20)
                        if self.question_count == 1 else
                        "回执显示失败；先确认实际失败阶段，再决定资源变化。")
                yield BrainEvent("question_answer", {
                    "schema_version": 1, "message_type": "research_answer",
                    "request_id": packet["request_id"], "answer_md": body,
                    "evidence_refs": refs, "native_answers": None})
            return gen()

    _seed_challenge()
    c, _, ex = _rig(shadow=False)
    brain = SelectiveBrain()
    c._make_brain = lambda settings: brain
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    token = brain.open_spec["env"]["CS_TOOL_TOKEN"]
    assert collab.validate_token(token)["role"] == "brain"
    assert brain.open_spec["instructions"].find("research_trace") >= 0
    assert "enabled_skills" not in brain.open_spec["instructions"]

    question = {"message": "频率失败，是否直接把内存加倍？",
                "questions": [{"id": "q0", "required": True,
                               "options": [{"const": "是"}, {"const": "否"}]}]}
    first = _cp_msg("research-one", review="async", report="执行器建议加倍")
    first["research_question"] = question
    receipt = collab.submit_checkpoint(rid, first, source="executor",
                                       notify=c.notify_run_change)
    assert receipt["review_id"] and receipt["next_action"] == "continue"
    assert await _wait(lambda: db.query_one(
        "SELECT status FROM review_requests WHERE id=?",
        (receipt["review_id"],))["status"] == "done")
    assert db.query_one("SELECT COUNT(*) AS n FROM events WHERE run_id=?"
                        " AND type='brain.trace_read'", (rid,))["n"] == 0
    first_answer = json.loads(db.query_one(
        "SELECT result_json FROM review_requests WHERE id=?",
        (receipt["review_id"],))["result_json"])
    assert len(first_answer["answer_md"]) > 500
    assert first_answer["native_answers"] is None
    assert collab.submit_checkpoint(rid, first, source="executor",
                                    notify=c.notify_run_change)["deduplicated"]
    await ex.turn_done()
    assert await _wait(lambda: any(first_answer["answer_md"] in p[1]
                                   for p in ex.prompts))
    guides = db.query("SELECT id FROM guidance WHERE review_request_id=?",
                      (receipt["review_id"],))
    assert len(guides) == 1
    assert collab.ack_guidance(rid, {"schema_version": 1,
                                     "message_type": "guidance_ack",
                                     "guidance_id": guides[0]["id"],
                                     "disposition": "accepted",
                                     "reason_md": "将核查失败阶段"})["status"] == "acknowledged"
    assert collab.validate_token(token), "执行器会话签发不可撤销大脑令牌"

    other = db.append_event(rid, "executor", "prime.execution.progress",
                            {"detail": "失败回执", "status": "failed",
                             "output": "失败回执：频率阶段退出"})
    brain.target_ref = f"event:{rid}:{other['seq']}"
    second = _cp_msg("research-two", review="async", report="再次建议加倍")
    second["research_question"] = question
    next_receipt = collab.submit_checkpoint(rid, second, source="executor",
                                            notify=c.notify_run_change)
    assert await _wait(lambda: db.query_one(
        "SELECT status FROM review_requests WHERE id=?",
        (next_receipt["review_id"],))["status"] == "done")
    assert brain.reads and brain.reads[0]["source_seq"] == other["seq"]
    assert "failed" in brain.reads[0]["content"]
    await ex.turn_done()
    second_answer = json.loads(db.query_one(
        "SELECT result_json FROM review_requests WHERE id=?",
        (next_receipt["review_id"],))["result_json"])
    assert await _wait(lambda: any(second_answer["answer_md"] in p[1]
                                   for p in ex.prompts))
    status = c.supervision_status(rid)
    assert {a["id"]: a["delivery_status"]
            for a in status["research_answers"]}[receipt["review_id"]] == "acknowledged"
    assert {read["action"] for read in status["trace_reads"]} == {"list", "read"}
    assert len([p for p in brain.calls if p.get("protocol") == "executor_question"]) == 2
    await c.control(rid, "terminate", None, "op-term-sparse-e2e")


async def test_sparse_trace_scope_and_role_restrictions():
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app

    _seed_challenge()
    c = RunController()
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    db.execute("INSERT INTO supervision(run_id,enabled,updated_at) VALUES(?,0,?)",
               (rid, db.utcnow()))
    before = db.append_event(rid, "executor", "job.unknown",
                             {"operation_id": "op-a", "detail": "sk-secretvalue"})
    with db.transaction() as conn:
        brain_token = collab.issue_token(conn, rid, "brain", "b", 1)
        executor_token = collab.issue_token(conn, rid, "executor", "e", 1)
        rev = collab._enqueue_request_tx(conn, rid, source="executor",
                                        blocking=False, trigger="research_question")
        conn.execute("UPDATE review_requests SET status='running',through_seq=?"
                     " WHERE id=?", (before["seq"], rev))
        collab.revoke_role_tokens(conn, rid, "executor")
    assert collab.validate_token(brain_token)
    future = db.append_event(rid, "executor", "job.observed", {"operation_id": "op-a"})
    headers = {"Authorization": f"Bearer {brain_token}"}
    async with AsyncClient(transport=ASGITransport(app=create_app()),
                           base_url="http://test") as cli:
        denied_write = await cli.post("/api/v1/tools/checkpoint", json=_cp_msg("x"),
                                      headers=headers)
        assert denied_write.status_code == 403
        denied_job = await cli.post("/api/v1/tools/job", json={"action": "list"},
                                    headers=headers)
        assert denied_job.status_code == 403
        assert (await cli.post("/api/v1/tools/trace", json={"action": "list"},
                               headers={"Authorization": f"Bearer {executor_token}"})).status_code == 401
        good = await cli.post("/api/v1/tools/trace", json={
            "action": "read", "ref": f"event:{rid}:{before['seq']}"}, headers=headers)
        assert good.status_code == 200
        assert "sk-secretvalue" not in good.json()["content"]
        for ref in (f"event:{rid}:{future['seq']}", f"event:other-run:{before['seq']}"):
            assert (await cli.post("/api/v1/tools/trace", json={
                "action": "read", "ref": ref}, headers=headers)).status_code == 409
        db.execute("UPDATE review_requests SET status='done' WHERE id=?", (rev,))
        assert (await cli.post("/api/v1/tools/trace", json={
            "action": "list"}, headers=headers)).status_code == 409


def test_sparse_trace_frozen_manifest_requires_matching_saved_version():
    from cyberscientist import research_trace

    _seed_challenge()
    c = RunController()
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    event = db.append_event(rid, "controller", "job.accepted",
                            {"operation_id": "op-frozen"})
    db.execute("INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,"
               "spec_json,input_directory,status,created_at,updated_at)"
               " VALUES(?,?,?,?,?,?,?,?,?)",
               ("op-frozen", rid, "trial-frozen", "hash-v1", "{}", "/tmp/fake", "reserved",
                db.utcnow(), db.utcnow()))
    path = config.DATA_DIR / "job-inputs" / "op-frozen" / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"request_hash": "hash-v1", "files": []}),
                    encoding="utf-8")
    rev = collab._enqueue_request_tx(db.get_db(), rid, source="executor",
                                    blocking=False, trigger="research_question")
    db.execute("UPDATE review_requests SET status='running',through_seq=?"
               " WHERE id=?", (event["seq"], rev))
    result = research_trace.access(rid, {"action": "read", "ref": "manifest:op-frozen"})
    assert result["source_seq"] == event["seq"]
    assert result["version"].startswith("saved-manifest-sha256:")
    path.write_text(json.dumps({"request_hash": "different", "files": []}),
                    encoding="utf-8")
    with pytest.raises(research_trace.TraceError):
        research_trace.access(rid, {"action": "read", "ref": "manifest:op-frozen"})


def test_sparse_native_form_decline_and_valid_accept():
    from cyberscientist.prime.kimi_acp import (
        _is_research_elicitation, _native_question_response)
    params = {"requestedSchema": {"type": "object", "properties": {
        "q0": {"type": "string", "enum": ["是", "否"]}}, "required": ["q0"]}}
    free = {"answer_md": "先查失败阶段", "native_answers": None}
    assert _native_question_response("elicitation/create", params, free) == (
        {"action": "decline"}, "declined")
    assert _native_question_response("elicitation/create", params, {
        "native_answers": {"q0": "是"}}) == (
        {"action": "accept", "content": {"q0": "是"}}, "mapped")
    assert _native_question_response("elicitation/create", params, {
        "native_answers": {"q0": "第三路线"}}) == (
        {"action": "decline"}, "declined")
    form = {"mode": "form", "toolCallId": "tool-1", "requestedSchema": {
        "properties": {"q0": {"oneOf": [{"const": "是"}, {"const": "否"}]}}}}
    assert _is_research_elicitation(form, {"tool-1": "AskUserQuestion"})
    assert not _is_research_elicitation(form, {"tool-1": "LocalPermission"})
    assert not _is_research_elicitation(form, {})
    assert not _is_research_elicitation({"mode": "form", "toolCallId": "tool-1",
        "requestedSchema": {"properties": {
            "local_permission": {"oneOf": [{"const": "允许"}]}}}},
        {"tool-1": "AskUserQuestion"})


# ---------- 经验闭环（自进化：直接生效/审批/整理/回联）----------

def _proposal(scope, title, body="正文", target_id=None, kind=None):
    p = {"scope": scope,
         "challenge_id": None if scope == "global" else "COLLAB_CH",
         "title": title, "body_md": body, "applicability": "条件",
         "evidence_refs": ["artifact:x"]}
    if target_id:
        p["target_id"] = target_id
    if kind:
        p["kind"] = kind
    return p


async def _steer_decision(c, brain, rid, dec, calls_before):
    """经 user_steer 生命周期审阅让大脑下发一个 Decision。"""
    await c.control(rid, "steer", "请判断", f"op-steer-{calls_before}")
    ok = await _wait(lambda: len(brain.calls) > calls_before)
    assert ok, "steer 未触发生命周期审阅"
    await brain.results.put({"decision": dec})


async def test_experience_challenge_proposal_lands_active():
    """题内提议直接落 active（无审查门槛）；执行器任务文本带冻结经验正文。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    c.authorize(rid, "demo", True, 10, 30, 0, None)
    await c.start_async(rid)
    dec = _decision([{"op": "start_trial", "goal": "基线",
                      "success_check": "产物落盘"}])
    dec["experience_proposals"] = [_proposal("challenge", "题内经验A",
                                             kind="failure")]
    await brain.results.put({"decision": dec})
    ok = await _wait(lambda: bool(db.query_one(
        "SELECT id FROM trials WHERE run_id=?", (rid,))))
    assert ok
    listing = experiences.list_experiences(scope="challenge",
                                           challenge_id="COLLAB_CH")
    assert len(listing["items"]) == 1
    item = listing["items"][0]
    assert item["status"] == "active" and item["kind"] == "failure"
    assert item["evidence_status"] == "hypothesis"
    assert any("冻结经验" in text and item["revision_id"] in text for _, text in ex.prompts)
    await c.control(rid, "terminate", None, "op-term-exp1")


async def test_experience_global_proposal_waits_user_approval():
    """全局提议落 candidate（待用户审批）；approve/reject 是唯一起落通道。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    dec = _decision([{"op": "wait", "reason": "观察"}], sv=999)
    dec["experience_proposals"] = [_proposal("global", "全局经验G")]
    await _steer_decision(c, brain, rid, dec, len(brain.calls))
    ok = await _wait(lambda: bool(experiences.list_experiences(
        scope="global")["items"]))
    assert ok
    item = experiences.list_experiences(scope="global")["items"][0]
    assert item["status"] == "candidate"
    # 驳回 → 保持 candidate + 批注；批准 → active
    experiences.reject_experience(item["id"], "证据不足，补独立复现", expected_revision=item["revision_id"])
    item = experiences.list_experiences(scope="global")["items"][0]
    assert item["status"] == "candidate"
    assert item["review_note"] == "证据不足，补独立复现"
    experiences.approve_experience(item["id"], expected_revision=item["revision_id"])
    item = experiences.list_experiences(scope="global")["items"][0]
    assert item["status"] == "active" and item["review_note"] is None
    await c.control(rid, "terminate", None, "op-term-exp2")


async def test_experience_target_id_updates_in_place():
    """target_id=更新已有条目（追加修订）；未知 target_id 只拒该提议。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    dec = _decision([{"op": "wait", "reason": "x"}], sv=999)
    dec["experience_proposals"] = [_proposal("challenge", "条目甲")]
    await _steer_decision(c, brain, rid, dec, len(brain.calls))
    ok = await _wait(lambda: bool(experiences.list_experiences(
        scope="challenge", challenge_id="COLLAB_CH")["items"]))
    assert ok
    exp_id = experiences.list_experiences(
        scope="challenge", challenge_id="COLLAB_CH")["items"][0]["id"]

    dec2 = _decision([{"op": "wait", "reason": "y"}], sv=999)
    dec2["experience_proposals"] = [
        _proposal("challenge", "条目甲 v2", body="修订正文",
                  target_id=exp_id),
        _proposal("challenge", "不存在的目标", target_id="exp_nope")]
    await _steer_decision(c, brain, rid, dec2, len(brain.calls))
    ok = await _wait(lambda: any(
        e["type"] == "experience.updated" for e in db.query(
            "SELECT type FROM events WHERE run_id=?", (rid,))))
    assert ok
    exp = experiences.get_experience(exp_id)
    assert exp["body_md"].startswith("修订正文")
    assert len(exp["revisions"]) == 2  # 冲突=追加新修订，不拒绝
    listing = experiences.list_experiences(scope="challenge",
                                           challenge_id="COLLAB_CH")
    assert len(listing["items"]) == 1  # 没有重复造条目
    assert db.query_one(
        "SELECT event_id FROM events WHERE run_id=?"
        " AND type='brain.action_rejected'"
        " AND payload LIKE '%exp_nope%'", (rid,))
    await c.control(rid, "terminate", None, "op-term-exp3")


async def test_finish_defers_to_curation_then_finalizes():
    """finish 先自动整理（curation 审阅带素材），审阅完结后自动收尾。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    dec = _decision([{"op": "finish", "reason": "收工"}], sv=999)
    await _steer_decision(c, brain, rid, dec, len(brain.calls))
    ok = await _wait(lambda: bool(db.query_one(
        "SELECT id FROM review_requests WHERE run_id=?"
        " AND trigger='curation'", (rid,))))
    assert ok, "finish 未推迟为 curation 审阅"
    assert c.run_snapshot(rid)["phase"] == "running"
    ok = await _wait(lambda: len(brain.calls) >= 3)
    assert ok
    packet = brain.calls[-1]
    assert packet["trigger"] == "curation"
    assert packet["curation"]["scope"] == "challenge"
    assert "usage" in packet["curation"]
    # 大脑整理答复（带一条题内提议）→ 自动收尾
    dec2 = _decision([{"op": "wait", "reason": "整理完毕"}], sv=999)
    dec2["experience_proposals"] = [_proposal("challenge", "收尾总结")]
    await brain.results.put({"decision": dec2})
    ok = await _wait(lambda: c.run_snapshot(rid)["phase"] == "finished")
    assert ok, "curation 完结后未自动收尾"
    # 效果回联原料：起止快照齐全
    row = db.query_one("SELECT experience_snapshot FROM runs WHERE id=?",
                       (rid,))
    snap = json.loads(row["experience_snapshot"])
    assert "at_start" in snap and "at_end" in snap
    exp_id = experiences.list_experiences(
        scope="challenge", challenge_id="COLLAB_CH")["items"][0]["id"]
    assert exp_id in {it["id"] for it in snap["at_end"]["items"]}


async def test_curate_global_experience_runless_session():
    """手动全局整理：无 Run 的一次性大脑会话，素材含题内经验与回联，
    全局产出落 candidate 待审批。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    status = await c.curate_global_experience(["COLLAB_CH"])
    assert status["state"] == "running"
    ok = await _wait(lambda: len(brain.calls) == 1)
    assert ok
    packet = brain.calls[0]
    assert packet["trigger"] == "global_curation"
    assert packet["challenges"][0]["challenge_id"] == "COLLAB_CH"
    assert "usage" in packet["challenges"][0]
    dec = _decision([{"op": "wait", "reason": "仅整理"}], sv=0)
    dec["experience_proposals"] = [_proposal("global", "全局整理产出")]
    await brain.results.put({"decision": dec})
    ok = await _wait(lambda: c.global_curation_status().get("state") == "done")
    assert ok
    assert c.global_curation_status()["proposals_applied"] == 1
    items = experiences.list_experiences(scope="global")["items"]
    assert len(items) == 1 and items[0]["status"] == "candidate"
    # 并发护栏：进行中重复触发被拒
    brain.barrier = asyncio.Event()
    await c.curate_global_experience([])
    ok = await _wait(lambda: len(brain.calls) == 2)
    assert ok
    with pytest.raises(ControllerError):
        await c.curate_global_experience([])
    brain.barrier.set()
    await brain.results.put(
        {"decision": _decision([{"op": "wait", "reason": "x"}], sv=0)})
    ok = await _wait(lambda: c.global_curation_status().get("state") == "done")
    assert ok


async def test_global_curation_failure_terminal_and_persisted():
    """全局整理任何一步失败（含大脑装配/会话建立之前）都必须终态化 failed
    并落盘：不永卡 running，重启（新控制器）后读到持久化状态，可重试。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)

    def _boom(settings):  # 模拟 load_settings 之后的装配失败
        raise RuntimeError("配置损坏无法装配大脑")
    c._make_brain = _boom  # type: ignore[method-assign]
    status = await c.curate_global_experience(["COLLAB_CH"])
    assert status["state"] == "running"
    ok = await _wait(
        lambda: c.global_curation_status().get("state") == "failed")
    assert ok, "大脑装配失败后整理状态未终态化（前端会永远显示整理中）"
    assert "配置损坏" in c.global_curation_status()["error"]

    # 持久化：新控制器（模拟重启）读到 failed 而不是空/假 running
    c2, brain2, _ = _rig(shadow=False)
    st2 = c2.global_curation_status()
    assert st2["state"] == "failed" and "配置损坏" in st2["error"]
    # 失败后可重新触发（不被假 running 卡住）
    await c2.curate_global_experience([])
    ok = await _wait(lambda: len(brain2.calls) == 1)
    assert ok
    await brain2.results.put(
        {"decision": _decision([{"op": "wait", "reason": "x"}], sv=0)})
    ok = await _wait(
        lambda: c2.global_curation_status().get("state") == "done")
    assert ok

    # 重启悬挂对账：状态文件停在 running，新进程如实转为 failed/interrupted
    (config.DATA_DIR / "global_curation.json").write_text(json.dumps(
        {"state": "running", "started_at": db.utcnow(),
         "challenge_ids": []}, ensure_ascii=False), encoding="utf-8")
    c3, _, _ = _rig(shadow=False)
    st3 = c3.global_curation_status()
    assert st3["state"] == "failed" and st3["interrupted"] is True
    assert "重启" in st3["error"]


async def test_finish_deferred_curation_completes_while_paused():
    """finish 已推迟到 curation，用户在整理在途时暂停：curation 完结仍执行
    被推迟的 finish，Run 不停在 paused 软锁。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    dec = _decision([{"op": "finish", "reason": "收工"}], sv=999)
    await _steer_decision(c, brain, rid, dec, len(brain.calls))
    ok = await _wait(lambda: len(brain.calls) >= 3)
    assert ok and brain.calls[-1]["trigger"] == "curation"
    # 整理在途时用户暂停
    r = await c.control(rid, "pause", None, "op-pause-curation")
    assert r["status"] == "accepted"
    ok = await _wait(lambda: c.run_snapshot(rid)["phase"] == "paused")
    assert ok
    # 大脑整理答复在暂停期间到达 → 仍执行被推迟的 finish
    await brain.results.put({"decision": _decision(
        [{"op": "wait", "reason": "整理完毕"}], sv=999, rid=rid)})
    ok = await _wait(lambda: c.run_snapshot(rid)["phase"] == "finished")
    assert ok, "暂停期间 curation 完结后 Run 未收尾（软锁）"


async def test_finish_finalizes_when_curation_obsoleted():
    """curation 审阅被作废（obsolete）也执行被推迟的 finish。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    assert c._defer_finish_for_curation(rid, "收工") is True
    req = db.query_one("SELECT id FROM review_requests WHERE run_id=?"
                       " AND trigger='curation'", (rid,))
    assert req, "finish 未推迟为 curation 审阅"
    c._obsolete_request(req["id"], "测试：整理被作废")
    assert c.run_snapshot(rid)["phase"] == "finished"


async def test_finish_finalizes_when_curation_interrupted_by_restart():
    """重启对账作废在途 curation（finish_after）→ Run 直接收尾，不软锁。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    c.authorize(rid, "demo", True, 10, 30, 0, None)
    # 模拟重启现场：Run 停在 running，curation 审阅在途且承载着 finish
    db.execute("UPDATE runs SET phase='running', started_at=? WHERE id=?",
               (db.utcnow(), rid))
    frame = json.dumps({"finish_after": True, "finish_reason": "收工"},
                       ensure_ascii=False)
    db.execute(
        "INSERT INTO review_requests(id, run_id, source, trigger, blocking,"
        " status, frame_json, created_at, updated_at)"
        " VALUES(?,?,'lifecycle','curation',0,'running',?,?,?)",
        ("rev_cur_zombie", rid, frame, db.utcnow(), db.utcnow()))
    marked = c.reconcile_on_startup()
    assert rid in marked
    assert db.query_one("SELECT status FROM review_requests"
                        " WHERE id='rev_cur_zombie'")["status"] == "obsolete"
    assert c.run_snapshot(rid)["phase"] == "finished"


async def test_finish_finalizes_when_curation_marked_error_on_recovery():
    """恢复路径把 running 的 curation 标 error 时，承载的 finish 同样执行。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    c.authorize(rid, "demo", True, 10, 30, 0, None)
    db.execute("UPDATE runs SET phase='running', started_at=? WHERE id=?",
               (db.utcnow(), rid))
    frame = json.dumps({"finish_after": True, "finish_reason": "收工"},
                       ensure_ascii=False)
    db.execute(
        "INSERT INTO review_requests(id, run_id, source, trigger, blocking,"
        " status, frame_json, created_at, updated_at)"
        " VALUES(?,?,'lifecycle','curation',0,'running',?,?,?)",
        ("rev_cur_err", rid, frame, db.utcnow(), db.utcnow()))
    c._recover_review_requests(rid)
    assert db.query_one("SELECT status FROM review_requests"
                        " WHERE id='rev_cur_err'")["status"] == "error"
    assert c.run_snapshot(rid)["phase"] == "finished"


async def test_challenge_proposal_challenge_id_bound_to_run():
    """题内提议自报的 challenge_id 不被信任：强制绑定当前 Run 的题目并记事件。"""
    _seed_challenge()
    db.execute(  # 另一道题目：绑错时会静默写到这里，必须可观测
        "INSERT INTO challenges(id, platform_challenge_id, origin, title,"
        " content, content_hash, contract_status, imported_at, is_demo)"
        " VALUES('OTHER_CH','OTH_000','demo://local','别的题','内容','h2',"
        "'unknown',?,1)", (db.utcnow(),))
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    dec = _decision([{"op": "wait", "reason": "x"}], sv=999)
    bad = _proposal("challenge", "自报错题的经验")
    bad["challenge_id"] = "OTHER_CH"  # 模型自报了错误的题目
    dec["experience_proposals"] = [bad]
    await _steer_decision(c, brain, rid, dec, len(brain.calls))
    ok = await _wait(lambda: bool(experiences.list_experiences(
        scope="challenge", challenge_id="COLLAB_CH")["items"]))
    assert ok
    assert not experiences.list_experiences(
        scope="challenge", challenge_id="OTHER_CH")["items"], \
        "题内提议被写到了模型自报的错误题目"
    assert db.query_one(
        "SELECT event_id FROM events WHERE run_id=?"
        " AND type='experience.proposal_rebound'", (rid,))
    await c.control(rid, "terminate", None, "op-term-rebind")


async def test_orphaned_waiting_brain_gate_released_at_turn_boundary():
    """blocking 审阅被作废（如重启对账）后，waiting_brain 不得永久卡死。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)

    collab.submit_checkpoint(rid, _cp_msg("orphan", review="blocking"),
                             source="executor", notify=c.notify_run_change)
    await ex.turn_done()
    ok = await _wait(lambda: c.run_snapshot(rid)["gate"] == "waiting_brain")
    assert ok
    ok = await _wait(lambda: any(
        p.get("protocol") == "review_result" for p in brain.calls))
    assert ok
    # 模拟重启对账：在途 blocking 审阅被作废，不再有任何东西会开门
    db.execute("UPDATE review_requests SET status='obsolete', updated_at=?"
               " WHERE run_id=? AND blocking=1"
               " AND status IN ('pending','running')", (db.utcnow(), rid))
    await ex.turn_done()
    ok = await _wait(lambda: c.run_snapshot(rid)["gate"] == "open")
    assert ok, "blocking 审阅作废后门禁必须兜底放行"
    ev = db.query_one(
        "SELECT payload FROM events WHERE run_id=?"
        " AND type='run.gate_opened'", (rid,))
    assert ev is not None and "no_blocking_inflight" in ev["payload"]
    await c.control(rid, "terminate", None, "op-term-orphan")


async def test_recovery_resume_heals_orphaned_gate_and_allows_start_trial():
    """事故复现：waiting_brain + blocking 审阅被重启作废 → 恢复后
    start_trial 不得再被门禁拒绝。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    c.authorize(rid, "demo", True, 10, 30, 0, None)
    # 模拟崩溃现场：门禁卡在 waiting_brain，blocking 审阅仍在途
    db.execute("UPDATE runs SET phase='running', gate='waiting_brain',"
               " started_at=? WHERE id=?", (db.utcnow(), rid))
    db.execute(
        "INSERT INTO review_requests(id, run_id, source, trigger, blocking,"
        " status, created_at, updated_at) VALUES(?,?,?,?,1,'pending',?,?)",
        ("rev_orphan", rid, "lifecycle", "trial_complete",
         db.utcnow(), db.utcnow()))
    marked = c.reconcile_on_startup()
    assert marked == [rid]
    assert db.query_one("SELECT status FROM review_requests WHERE id=?",
                        ("rev_orphan",))["status"] == "obsolete"
    r = await c.control(rid, "resume", None, "op-resume-heal")
    assert r["status"] == "confirmed"
    ok = await _wait(lambda: any(
        p.get("trigger") == "recovery" for p in brain.calls))
    assert ok
    assert c.run_snapshot(rid)["gate"] == "open", "恢复后孤儿门禁必须被放行"
    await brain.results.put({"decision": _decision(
        [{"op": "start_trial", "goal": "修复 executability",
          "success_check": "评分器可执行"}], rid=rid)})
    ok = await _wait(lambda: bool(
        db.query_one("SELECT id FROM trials WHERE run_id=?", (rid,))))
    assert ok, "门禁放行后 start_trial 必须被接受"
    assert not db.query_one(
        "SELECT event_id FROM events WHERE run_id=?"
        " AND type='brain.action_rejected'", (rid,))
    await c.control(rid, "terminate", None, "op-term-heal")


async def test_steer_to_reported_complete_trial_accepted():
    """事故复现：Trial reported_complete 等待验收时，大脑 steer 追问
    不得被拒；且 steer 不把 Trial 状态改回 active。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    tid = await _start(c, brain, rid)

    # 执行器声明交付：Trial → reported_complete，门禁 yielding + blocking 审阅
    collab.submit_checkpoint(rid, _cp_msg("done1", stage="trial_complete"),
                             source="executor", notify=c.notify_run_change)
    ok = await _wait(lambda: db.query_one(
        "SELECT status FROM trials WHERE id=?", (tid,))["status"]
        == "reported_complete")
    assert ok
    ok = await _wait(lambda: any(
        p.get("trigger") == "trial_complete" for p in brain.calls))
    assert ok
    await brain.results.put({"decision": _decision(
        [{"op": "steer", "trial_id": tid,
          "message": "补充训练曲线与失败样例的侦察报告"}], rid=rid)})
    ok = await _wait(lambda: db.query_one(
        "SELECT id FROM guidance WHERE run_id=?", (rid,)) is not None)
    assert ok, "对 reported_complete Trial 的 steer 应生成指导"
    assert db.query_one(
        "SELECT status FROM trials WHERE id=?", (tid,))["status"] \
        == "reported_complete", "验收语义归大脑，steer 不得改 Trial 状态"
    assert not db.query_one(
        "SELECT event_id FROM events WHERE run_id=?"
        " AND type='brain.action_rejected'", (rid,))
    await c.control(rid, "terminate", None, "op-term-steer-rc")


async def test_decision_salvage_drops_only_invalid_proposals():
    """非法经验提议（如自创 kind）只剔除该提议并留痕，finish/wait 等
    主决定与合法提议不再陪葬（复现：非法经验提议不应导致主决定被整单拒收）。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    seq0 = db.query_one("SELECT COALESCE(MAX(seq),0) AS s FROM events"
                        " WHERE run_id=?", (rid,))["s"]
    v = c.run_snapshot(rid)["state_version"]
    bad = _proposal("challenge", "自创 kind 的提议")
    bad["kind"] = "finding"
    good = _proposal("challenge", "合法 kind 的提议")
    good["kind"] = "heuristic"
    dec = _decision([{"op": "wait", "reason": "继续观察"}], sv=v, rid=rid)
    dec["experience_proposals"] = [bad, good]
    await c._apply_decision(rid, dec, {}, None, None)
    events = db.events_after(rid, seq0)
    types = [e["type"] for e in events]
    assert "brain.decision_rejected" not in types, "非法提议不得陪葬整个 Decision"
    assert "brain.wait" in types, "主决定动作必须执行"
    salvaged = [e for e in events if e["type"] == "brain.decision_salvaged"]
    assert salvaged, "剔除必须留痕"
    dropped = salvaged[0]["payload"]["dropped_proposals"]
    assert len(dropped) == 1 and dropped[0]["kind"] == "finding", \
        "被剔除提议全文必须保留在事件中供大脑重提"
    titles = [i["title"] for i in experiences.list_experiences(
        scope="challenge", challenge_id="COLLAB_CH")["items"]]
    assert "合法 kind 的提议" in titles, "合法提议必须照常落库"
    assert "自创 kind 的提议" not in titles
    await c.control(rid, "terminate", None, "op-term-salvage")


async def test_time_limit_pauses_once_without_hot_loop():
    """时长上限触发：置 paused + 记一条事件后循环必须停泊等待信号；
    不得重复置 paused + continue 空转，避免事件循环被同步写入堵塞。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    await _start(c, brain, rid)
    # 把授权时长改为已在过去耗尽（started_at 前移，上限 1 分钟）
    db.execute("UPDATE authorizations SET max_run_minutes=1 WHERE run_id=?",
               (rid,))
    db.execute("UPDATE runs SET started_at=? WHERE id=?",
               ("2000-01-01T00:00:00+00:00", rid))
    # 用不改变 phase 的信号唤醒主循环，使其在 running 状态下走到时长检查
    await ex.turn_done()
    ok = await _wait(lambda: c.run_snapshot(rid)["phase"] == "paused")
    assert ok, "时长超限应置 paused"
    assert c.run_snapshot(rid)["block_reason"]
    await asyncio.sleep(0.6)  # 若空转，0.6s 足以产生数千条垃圾事件
    n = db.query_one("SELECT COUNT(*) AS n FROM events WHERE run_id=?"
                     " AND type='run.time_limit'", (rid,))["n"]
    assert n == 1, f"time_limit 事件应恰好一条，实际 {n}"
    await c.control(rid, "terminate", None, "op-term-tl")


async def test_blocking_review_answered_by_decision_opens_gate():
    """blocking 审阅收到 Decision 答复 = 有效答复：先开门再应用，
    答复里的 start_trial 不得被自己正在解除的门禁拒绝
    （事故复现：已结束的会话重复处理出站结果导致循环死锁）。"""
    _seed_challenge()
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    tid = await _start(c, brain, rid)

    # 执行器声明交付：gate → yielding，blocking 生命周期审阅入队
    collab.submit_checkpoint(rid, _cp_msg("tc1", stage="trial_complete"),
                             source="executor", notify=c.notify_run_change)
    await ex.turn_done()
    ok = await _wait(lambda: c.run_snapshot(rid)["gate"] == "waiting_brain")
    assert ok
    ok = await _wait(lambda: any(
        p.get("trigger") == "trial_complete" for p in brain.calls))
    assert ok
    # 大脑用 Decision 答复 blocking 审阅：开新 Trial
    await brain.results.put({"decision": _decision(
        [{"op": "start_trial", "goal": "v3 单变量实验",
          "success_check": "假设被证实或证伪"}], rid=rid)})
    ok = await _wait(lambda: db.query_one(
        "SELECT id FROM trials WHERE run_id=? AND id<>?", (rid, tid))
        is not None)
    assert ok, "blocking 审阅的 Decision 答复中的 start_trial 必须生效"
    assert c.run_snapshot(rid)["gate"] == "open"
    ev = db.query_one("SELECT payload FROM events WHERE run_id=?"
                      " AND type='run.gate_opened'"
                      " AND payload LIKE '%blocking_decision%'", (rid,))
    assert ev is not None, "开门必须留痕"
    assert not db.query_one(
        "SELECT event_id FROM events WHERE run_id=?"
        " AND type='brain.action_rejected'"
        " AND payload LIKE '%门禁%'", (rid,))
    await c.control(rid, "terminate", None, "op-term-blkdec")


def test_lifecycle_packet_carries_challenge_at_run_start():
    """开局帧必须带题目要素（标题/平台链接/资源清单/完整题面），
    大脑亲自核实后再规划；非开局帧不带完整题面（省 token）。"""
    _seed_challenge()
    db.execute("UPDATE challenges SET platform_challenge_id=?,"
               " resources_json=? WHERE id=?",
               ("some-slug-123",
                json.dumps([{"kind": "data", "name": "d1"}],
                           ensure_ascii=False), "COLLAB_CH"))
    c, brain, ex = _rig(shadow=False)
    rid = c.create_run("COLLAB_CH", shadow_enabled=False)["id"]
    c.authorize(rid, "demo", True, 10, 30, 0, None)
    run = c._require_run(rid)
    pkt = c._lifecycle_packet(run, "run_start")
    ch = pkt["challenge"]
    assert ch["title"] == "协作测试题"
    assert ch["platform_url"] == "https://play.bohrium.com/challenge/some-slug-123"
    assert ch["resources"][0]["name"] == "d1"
    assert ch["content"], "run_start 帧必须带完整题面"
    pkt2 = c._lifecycle_packet(run, "trial_done")
    assert "content" not in pkt2["challenge"], "非开局帧不带完整题面"
    assert pkt2["challenge"]["resources"], "资源清单各帧都带"
