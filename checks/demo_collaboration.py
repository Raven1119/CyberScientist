"""确定性协作演示（docs/collaboration/ACCEPTANCE.md §2）。

无付费调用：真实 FastAPI/uvicorn + SQLite + SSE + 真实 MCP 桥子进程；
大脑与执行器为脚本化假协议实现（fixture 脚本化大脑不代表模型判断能力）。
所有合成指标标记 synthetic，不与比赛成绩混用。

确定性策略：大脑默认自动驾驶（任何审阅立即回 SILENT/wait）；
需要注入特定结果时先关自动驾驶、等目标来源的请求进入 running 再喂结果，
避免并发审阅与结果队列错位。

运行：uv run python checks/demo_collaboration.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
OUT_DIR = ROOT / "checks" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

from test_collaboration import FakeExecutor, ScriptableBrain, _decision, \
    _guidance, _review_result  # noqa: E402
from cyberscientist.brains.base import BrainEvent  # noqa: E402

from cyberscientist import collab, config, db  # noqa: E402

# 隔离数据目录（绝不触碰真实工作区）
TMP = Path(tempfile.mkdtemp(prefix="cs-collab-demo-"))
for d in (TMP / ".cyberscientist", TMP / "workspace",
          TMP / "experience" / "global"):
    d.mkdir(parents=True, exist_ok=True)
config.DATA_DIR = TMP / ".cyberscientist"
config.DB_PATH = TMP / ".cyberscientist" / "demo.db"
config.SECRETS_PATH = TMP / ".cyberscientist" / "secrets.json"
config.SETTINGS_PATH = TMP / ".cyberscientist" / "settings.json"
config.LOCK_PATH = TMP / ".cyberscientist" / "controller.lock"
config.WORKSPACE_DIR = TMP / "workspace"
config.EXPERIENCE_DIR = TMP / "experience"

settings = config.load_settings()
settings["app"]["mode"] = "demo"
settings["shadow"] = {"enabled": True, "min_interval_seconds": 0.05,
                      "max_interval_seconds": 0.2, "max_reviews": 8}
config.save_settings(settings)
db.init_db()

from cyberscientist import api  # noqa: E402


class AutoBrain(ScriptableBrain):
    """自动驾驶大脑：results 队列有覆盖结果时优先消费，否则立即默认应答。"""

    def __init__(self):
        super().__init__()
        self.auto = True

    def review(self, session, packet):
        async def gen():
            self.calls.append(packet)
            if self.barrier is not None:
                await self.barrier.wait()
            r = None
            while r is None:
                try:
                    r = self.results.get_nowait()
                except asyncio.QueueEmpty:
                    if self.auto:
                        break  # 自动驾驶可在等待途中接管，避免挂死
                    await asyncio.sleep(0.05)
            if r is None:
                if packet.get("protocol") == "review_result":
                    r = {"review_result": _review_result(
                        packet.get("frame_id", "f?"))}
                else:
                    r = {"decision": _decision(
                        [{"op": "wait", "reason": "自动驾驶"}])}
            if "error" in r:
                yield BrainEvent("error", {"message": r["error"]})
            elif "decision" in r:
                yield BrainEvent("decision", {"decision": r["decision"]})
            else:
                yield BrainEvent("review_result", {"result": r["review_result"]})
        return gen()


BRAIN = AutoBrain()
EXEC = FakeExecutor()
api.controller._make_brain = lambda s: BRAIN  # type: ignore[method-assign]
api.controller._make_prime = lambda s: EXEC  # type: ignore[method-assign]

PORT = 18799
BASE = f"http://127.0.0.1:{PORT}"

CHECKS: list[tuple[str, bool, str]] = []
TIMELINE: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def mark(label: str) -> None:
    TIMELINE.append(f"{time.strftime('%H:%M:%S')} {label}")


def _post(path: str, payload: dict) -> tuple[int, dict]:
    import urllib.request
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def _get(path: str) -> dict:
    import urllib.request
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode())


class McpClient:
    """真实 MCP 桥子进程（python -m cyberscientist.mcp_bridge）。"""

    def __init__(self, token: str):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "cyberscientist.mcp_bridge"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            cwd=ROOT, text=True, encoding="utf-8",
            env={"PATH": os.environ.get("PATH", ""),
                 "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                 "CS_TOOL_TOKEN": token, "CS_API_URL": BASE,
                 "PYTHONUTF8": "1"})
        self._id = 0

    def call(self, method: str, params: dict) -> dict:
        self._id += 1
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": self._id, "method": method,
             "params": params}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        deadline = time.time() + 30
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("id") == self._id:
                return msg
        raise TimeoutError(f"MCP {method} 无响应")

    def tool(self, name: str, args: dict) -> dict:
        resp = self.call("tools/call", {"name": name, "arguments": args})
        result = resp.get("result", {})
        text = (result.get("content") or [{}])[0].get("text", "{}")
        return json.loads(text)

    def close(self) -> None:
        self.proc.terminate()


async def wait_for(pred, timeout=15.0, label="") -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            if pred():
                return True
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(0.1)
    print(f"  [timeout] {label}")
    return False


RID = ""  # main 中赋值


def _running_request(source: str):
    return db.query_one(
        "SELECT * FROM review_requests WHERE run_id=? AND source=?"
        " AND status='running'", (RID, source))


async def scripted_call(source: str, label: str, since: int = 0) -> dict | None:
    """等待指定来源的审阅进入 running 且大脑已被调用，返回对应调用帧。

    since：触发动作之前 BRAIN.calls 的基线长度（由调用方在触发前捕获），
    避免"调用发生在捕获之前"的竞态；非生命周期帧另按 frame_id 精确匹配。
    """
    ok = await wait_for(lambda: _running_request(source) is not None,
                        label=label)
    if not ok:
        return None
    req = _running_request(source)
    fid = req["frame_id"] if req else None
    ok = await wait_for(
        lambda: (bool(fid) and any(c.get("frame_id") == fid
                                   for c in BRAIN.calls))
        or len(BRAIN.calls) > since, label=label + ":调用")
    if not ok:
        return None
    if fid:
        for c in reversed(BRAIN.calls):
            if c.get("frame_id") == fid:
                return c
    return BRAIN.calls[-1]


async def settle() -> None:
    """自动驾驶排空所有待处理审阅，恢复确定性基线。"""
    BRAIN.auto = True
    await wait_for(lambda: not db.query(
        "SELECT id FROM review_requests WHERE run_id=?"
        " AND status IN ('pending','running')", (RID,)), label="settle")
    await asyncio.sleep(0.3)


async def main() -> None:
    global RID
    db.execute(
        "INSERT INTO challenges(id, platform_challenge_id, origin, title,"
        " content, content_hash, contract_status, imported_at, is_demo)"
        " VALUES('DEMO_CH','D','demo://local','协作演示题','内容（合成）','h',"
        "'unknown',?,1)", (db.utcnow(),))

    import uvicorn
    app = api.create_app()
    server_cfg = uvicorn.Config(app, host="127.0.0.1", port=PORT,
                                log_level="error")
    server = uvicorn.Server(server_cfg)
    # 与演示脚本同一事件循环：大脑/执行器桩的 asyncio.Queue 跨线程会丢唤醒
    serve_task = asyncio.create_task(server.serve())
    for _ in range(100):
        try:
            await asyncio.to_thread(_get, "/api/v1/health")
            break
        except OSError:
            await asyncio.sleep(0.1)
    mark("后端启动（真实 uvicorn + SQLite）")

    # 1. 创建 + 授权 + 启动（开启静默监督）
    _, run = await asyncio.to_thread(
        _post, "/api/v1/runs", {"challenge_id": "DEMO_CH",
                                "shadow_enabled": True})
    RID = run["id"]
    rid = RID
    await asyncio.to_thread(
        _post, f"/api/v1/runs/{rid}/authorize",
        {"scope": "demo", "allow_model_calls": True, "max_model_turns": 10,
         "max_run_minutes": 30, "max_submissions": 0})
    BRAIN.auto = False
    calls0 = len(BRAIN.calls)
    await asyncio.to_thread(_post, f"/api/v1/runs/{rid}/start", {})
    mark(f"Run {rid} 启动（shadow=on）")

    # 2. run_start 生命周期审阅 → start_trial
    call = await scripted_call("lifecycle", "run_start 审阅", since=calls0)
    check("run_start 生命周期审阅发生", call is not None)
    await BRAIN.results.put({"decision": _decision(
        [{"op": "start_trial", "goal": "合成基线", "success_check": "产物落盘"}])})
    ok = await wait_for(lambda: bool(db.query_one(
        "SELECT id FROM trials WHERE run_id=?", (rid,))), label="trial 创建")
    check("Trial 创建并由执行器受理", ok and len(EXEC.prompts) == 1)
    mark("Trial 1 启动（执行器工作中）")
    await settle()

    # 3. 执行器产生活动事件 + SSE 可读
    sse_seen: list[str] = []

    async def sse_reader():
        import httpx
        async with httpx.AsyncClient(base_url=BASE, timeout=None) as cli:
            async with cli.stream("GET", f"/api/v1/runs/{rid}/events") as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        sse_seen.append(line)
                        if len(sse_seen) > 400:
                            return
    sse_task = asyncio.create_task(sse_reader())
    await EXEC.emit({"type": "execution.progress", "detail": "工具调用: 合成分析"})
    ok = await wait_for(lambda: any("execution.progress" in s
                                    for s in sse_seen), label="SSE 事件")
    check("SSE 实时推送执行器事件", ok)

    # 4. 新检查点（真实 MCP 桥子进程，async）→ 大脑 SILENT → 执行器零打扰
    with db.transaction() as conn:
        token = collab.issue_token(conn, rid, "executor", "sess-1", 1)
    mcp = McpClient(token)
    init = await asyncio.to_thread(
        mcp.call, "initialize", {"protocolVersion": "2024-11-05",
                                 "capabilities": {},
                                 "clientInfo": {"name": "demo", "version": "0"}})
    check("MCP 桥 initialize", "result" in init)
    tools = await asyncio.to_thread(mcp.call, "tools/list", {})
    check("MCP tools/list 含两个协作工具",
          {t["name"] for t in tools["result"]["tools"]}
          == {"research_checkpoint", "ack_guidance"})
    prompts0 = len(EXEC.prompts)
    BRAIN.auto = False
    calls0 = len(BRAIN.calls)
    r = await asyncio.to_thread(mcp.tool, "research_checkpoint", {
        "checkpoint_key": "demo-1", "review": "async", "stage": "progress",
        "report_md": "合成进展：两组对照已登记（synthetic，非比赛指标）。",
        "evidence_refs": ["artifact:synthetic-v1"]})
    check("MCP research_checkpoint(async) 快速返回",
          r.get("next_action") == "continue" and bool(r.get("review_id")))
    mark("检查点 demo-1 登记（async 审阅）")
    call = await scripted_call("executor", "requested 审阅", since=calls0)
    check("大脑收到 requested 审阅（ObservationFrame）",
          call is not None and call.get("protocol") == "review_result")
    frame = call or {}
    check("帧含检查点正文且带来源",
          any("synthetic" in (c.get("report_md") or "")
              for c in frame.get("checkpoint_summaries", [])))
    await BRAIN.results.put({"review_result": _review_result(
        frame.get("frame_id", ""), disposition="silent", note="先观察，不干预")})
    ok = await wait_for(lambda: db.query_one(
        "SELECT private_note_md FROM supervision WHERE run_id=?",
        (rid,))["private_note_md"] == "先观察，不干预", label="silent 落库")
    check("SILENT 只更新大脑笔记", ok)
    check("SILENT 对执行器零调用增量", len(EXEC.prompts) == prompts0
          and not EXEC.steers and not EXEC.aborts)
    mark("大脑 SILENT（执行器未被打扰）")
    await settle()

    # 5. 用户显式审阅 → STEER；执行器忙 → 指导排队；边界投递 → ACK
    BRAIN.auto = False
    calls0 = len(BRAIN.calls)
    await asyncio.to_thread(
        _post, f"/api/v1/runs/{rid}/review_requests", {"blocking": False})
    call = await scripted_call("user", "用户显式审阅", since=calls0)
    check("用户显式请求审阅", call is not None)
    await BRAIN.results.put({"review_result": _review_result(
        (call or {}).get("frame_id", ""), disposition="intervene",
        guidance=_guidance(text="用已有结果按尺度分组比较，先不启动新训练"))})
    ok = await wait_for(lambda: db.query_one(
        "SELECT * FROM guidance WHERE run_id=? AND status='queued'",
        (rid,)) is not None, label="指导排队")
    grow = db.query_one("SELECT * FROM guidance WHERE run_id=?", (rid,))
    check("执行器忙时指导持久排队（无 busy 拒绝丢失）",
          ok and grow is not None and grow["status"] == "queued")
    mark(f"指导 {grow['id']} queued（执行器忙）")

    await EXEC.turn_done()
    ok = await wait_for(lambda: db.query_one(
        "SELECT status FROM guidance WHERE id=?", (grow["id"],))["status"]
        == "sent", label="边界投递")
    check("空闲回合边界恰好投递一次（idle_prompt 渠道）",
          ok and grow["id"] in EXEC.prompts[-1][1])
    mark("指导经空闲边界投递")

    ack = await asyncio.to_thread(mcp.tool, "ack_guidance", {
        "guidance_id": grow["id"], "disposition": "accepted",
        "reason_md": "先整理已有结果（synthetic 演示）"})
    check("MCP ack_guidance 确认", ack.get("status") == "acknowledged")
    mark("执行器 ACK accepted")
    await settle()

    # 6. 执行器按指导补报证据（沿同一 Trial）
    r = await asyncio.to_thread(mcp.tool, "research_checkpoint", {
        "checkpoint_key": "demo-2", "review": "none", "stage": "progress",
        "report_md": f"按 {grow['id']} 分组比较完成（synthetic）。",
        "evidence_refs": ["artifact:synthetic-v2"]})
    check("补报检查点沿同一 Trial", r.get("next_action") == "continue")
    snap = await asyncio.to_thread(_get, f"/api/v1/runs/{rid}")
    check("同一 Trial 继续（未新建/清空）",
          len(snap["trials"]) == 1 and snap["trials"][0]["status"] == "active")
    mark("补报完成，同一 Trial")
    await settle()

    # 7. shadow 审阅期间用户暂停 → 迟到的 shadow 指导失效
    collab_id = grow["id"]
    BRAIN.auto = False
    calls0 = len(BRAIN.calls)
    await asyncio.to_thread(mcp.tool, "research_checkpoint", {
        "checkpoint_key": "demo-3", "review": "none", "stage": "progress",
        "report_md": "新合成对照完成（synthetic）。",
        "evidence_refs": ["artifact:synthetic-v3"]})
    call = await scripted_call("shadow", "shadow 审阅", since=calls0)
    check("新证据触发被动观察审阅", call is not None)
    await BRAIN.results.put({"review_result": _review_result(
        (call or {}).get("frame_id", ""), disposition="intervene",
        guidance=_guidance(text="迟到指导：不应在暂停后投递"))})
    ok = await wait_for(lambda: db.query_one(
        "SELECT * FROM guidance WHERE run_id=? AND id<>? AND status='queued'",
        (rid, collab_id)) is not None, label="迟到指导排队")
    late0 = db.query_one("SELECT * FROM guidance WHERE run_id=? AND id<>?",
                         (rid, collab_id))
    check("shadow 指导在执行器忙时排队", ok and late0 is not None
          and late0["source"] == "shadow",
          f"source={late0['source'] if late0 else 'missing'}")
    await asyncio.to_thread(
        _post, f"/api/v1/runs/{rid}/control",
        {"action": "pause", "operation_id": "op-demo-pause"})
    await asyncio.sleep(0.3)
    late = db.query_one("SELECT * FROM guidance WHERE id=?",
                        (late0["id"],))
    check("暂停使未投递 shadow 指导失效", late is not None
          and late["status"] == "invalidated",
          f"实际状态 {late['status'] if late else 'missing'}")
    mark("用户暂停；未投递 shadow 指导失效")

    # 8. 重启服务：状态可见、无重复外部操作；迁移幂等
    server.should_exit = True
    await asyncio.sleep(0.5)
    mcp.close()
    prompts_before = len(EXEC.prompts)
    db._local.conn.close()
    del db._local.conn
    db.init_db()
    db.init_db()
    row = db.query_one("SELECT phase FROM runs WHERE id=?", (rid,))
    reqs = db.query("SELECT id, status FROM review_requests WHERE run_id=?",
                    (rid,))
    acks = db.query("SELECT id, status, ack_disposition FROM guidance"
                    " WHERE run_id=?", (rid,))
    check("重启后审阅/ACK/指导记录仍在", row is not None
          and len(reqs) >= 3 and len(acks) >= 1)
    check("重启不重复外部操作（执行器无新增调用）",
          len(EXEC.prompts) == prompts_before)
    mark("服务重启对账完成")

    sse_task.cancel()
    timeline_path = OUT_DIR / "collaboration_demo_timeline.txt"
    timeline_path.write_text("\n".join(TIMELINE) + "\n", encoding="utf-8")

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n==== {passed}/{len(CHECKS)} PASS ====")
    print(f"时间线: {timeline_path}")
    sys.exit(0 if passed == len(CHECKS) else 1)


if __name__ == "__main__":
    asyncio.run(main())
