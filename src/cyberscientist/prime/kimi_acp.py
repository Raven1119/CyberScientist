"""Kimi Code 执行器：`kimi acp`（Agent Client Protocol）作为执行系统。

实测协议面（checks/fixtures/real/kimi-acp-executor-probe.jsonl 等）：
- session/set_config_option：configId "model" / "thinking"（low|high|max）/ "mode"
- mode=yolo：引擎内自动批准全部工具，不再发 session/request_permission；
  工具调用仍以 tool_call / tool_call_update 事件全程留痕（用户确认的策略：
  自动同意 + 全程可视）。
- session/prompt 的 stopReason=end_turn 只表示原生回合结束
  → executor.turn_completed；实验交付必须由执行器经
  research_checkpoint(stage=trial_complete) 显式声明（A4）。
- 协作工具经 session/new 的 mcpServers 注入（spec["mcp_servers"]）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from ..brains.kimi import ACP_PROTOCOL_VERSION, default_executable
from ..jsonrpc_stdio import JsonRpcStdio, ProtocolError
from . import ActionReceipt, PrimeHealth, with_stall_watchdog

log = logging.getLogger("cyberscientist.executor.kimi")

# ACP thinking 只有 low/high/max 三档；UI 通用档位的映射关系
_EFFORT_MAP = {"low": "low", "medium": "high", "high": "high",
               "xhigh": "max", "max": "max"}

_QUESTION_OPT_RE = re.compile(r"^q\d+_opt_\d+$")


def _is_question_options(options: list[dict[str, Any]]) -> bool:
    """request_permission 的提问回退形态：optionId 为 q{N}_opt_{M}。"""
    return any(_QUESTION_OPT_RE.match(str(o.get("optionId", "")))
               for o in options)


def _question_from_elicitation(params: dict[str, Any]) -> dict[str, Any]:
    """elicitation/create（form 模式）→ 统一问题载荷。"""
    schema = params.get("requestedSchema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    questions: list[dict[str, Any]] = []
    for qid, spec in props.items():
        if not isinstance(spec, dict):
            continue
        opts = [{"const": o.get("const"), "title": o.get("title", ""),
                 "description": o.get("description", "")}
                for o in (spec.get("oneOf") or []) if isinstance(o, dict)]
        questions.append({"id": qid, "title": spec.get("title", qid),
                          "options": opts, "required": qid in required,
                          "default": spec.get("default")})
    return {"message": params.get("message", ""), "questions": questions}


def _question_from_permission(params: dict[str, Any]) -> dict[str, Any]:
    """request_permission 回退形态 → 统一问题载荷（选项带 optionId 供回映射）。"""
    questions: dict[str, dict[str, Any]] = {}
    for o in params.get("options", []):
        oid = str(o.get("optionId", ""))
        m = re.match(r"^(q\d+)_opt_\d+$", oid)
        if not m:
            continue
        q = questions.setdefault(m.group(1), {
            "id": m.group(1), "title": m.group(1), "options": [],
            "required": True})
        q["options"].append({"const": o.get("name", ""),
                             "title": o.get("name", ""), "description": "",
                             "option_id": oid})
    return {"message": (params.get("toolCall") or {}).get("title", ""),
            "questions": list(questions.values())}


def _permission_pick(params: dict[str, Any],
                     answers: dict[str, Any]) -> str | None:
    """大脑答案（const 值）→ 回退形态的 optionId。"""
    question = _question_from_permission(params)
    wanted = {q["id"]: str(answers.get(q["id"], ""))
              for q in question["questions"]}
    for q in question["questions"]:
        for o in q["options"]:
            if str(o["const"]) == wanted.get(q["id"]):
                return o["option_id"]
    return None


def map_update(u: dict[str, Any]) -> dict[str, Any] | None:
    """单帧 session/update → 控制器事件（不含文本 chunk 的合并缓冲）。

    实测帧形状见 checks/fixtures/real/kimi-acp-executor-probe.jsonl。
    """
    kind = u.get("sessionUpdate")
    if kind == "tool_call":
        return {"type": "execution.progress",
                "detail": f"工具调用: {u.get('title', '?')}"
                          f"（{u.get('kind', '?')}）"}
    if kind == "tool_call_update" and u.get("status") in ("completed", "failed"):
        content = u.get("content") or []
        text = ""
        if content and isinstance(content[0], dict):
            inner = content[0].get("content", {})
            if isinstance(inner, dict):
                text = inner.get("text", "")
        label = "工具完成" if u.get("status") == "completed" else "工具失败"
        return {"type": "execution.progress",
                "detail": f"{label}({u.get('title') or ''}): {text[:200]}"}
    return None


@dataclass
class _Session:
    rpc: JsonRpcStdio
    session_id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    pump_task: asyncio.Task | None = None
    prompt_task: asyncio.Task | None = None
    busy: bool = False


class KimiExecutor:
    """PrimeRuntime 协议实现：Kimi Code ACP 会话即执行单元。"""

    kind = "kimi"

    def __init__(self, executable: str | None = None, model: str | None = None,
                 effort: str | None = None, stall_timeout: float = 240.0):
        self.executable = executable or default_executable() or ""
        self.model = model
        self.effort = effort
        self.stall_timeout = stall_timeout
        # 执行器 AskUserQuestion → 大脑回答（控制器注入；None 则如实 decline）
        self.ask_handler: Any = None
        self._sessions: dict[str, _Session] = {}

    # ---------- 进程与握手 ----------
    def _argv(self) -> list[str]:
        exe = self.executable
        if not exe:
            raise RuntimeError("kimi 可执行文件不可用")
        if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", exe, "acp"]
        return [exe, "acp"]

    async def _spawn(self, cwd: str | None) -> JsonRpcStdio:
        rpc = JsonRpcStdio(self._argv(), cwd=cwd, name="kimi-exec-acp")
        await asyncio.wait_for(rpc.start(), timeout=30)
        await rpc.request(
            "initialize",
            {"protocolVersion": ACP_PROTOCOL_VERSION,
             "clientCapabilities": {"fs": {"readTextFile": False,
                                           "writeTextFile": False},
                                    "terminal": False,
                                    # 声明 form 能力：AskUserQuestion 走
                                    # elicitation/create（回退路径实测无效）
                                    "elicitation": {"form": {}}}},
            timeout=30)
        return rpc

    async def _set_option(self, rpc: JsonRpcStdio, sid: str,
                          config_id: str, value: str) -> bool:
        try:
            await rpc.request("session/set_config_option",
                              {"sessionId": sid, "configId": config_id,
                               "value": value}, timeout=15)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("set_config_option %s=%s 失败: %s", config_id, value, exc)
            return False

    # ---------- 探针 ----------
    async def inspect(self) -> PrimeHealth:
        if not self.executable or not os.path.exists(self.executable):
            return PrimeHealth(
                installed=False,
                detail=f"kimi 可执行文件不可用: {self.executable or '未安装'}")
        health = PrimeHealth(installed=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                *(self._argv()[:-1] + ["--version"]),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            health.version = out.decode("utf-8", errors="replace").strip()[:120]
        except Exception as exc:  # noqa: BLE001
            health.detail = f"版本探针失败: {exc}"
            return health
        rpc: JsonRpcStdio | None = None
        try:
            rpc = await self._spawn(None)
            health.detail = "ACP initialize 成功；执行模式 mode=yolo（工具自动批准，" \
                            "事件全程留痕）；未发起模型调用"
            health.capabilities = {"tool_execution": True, "stall_watchdog": True,
                                   "thinking_config": True}
        except Exception as exc:  # noqa: BLE001
            health.detail = f"ACP 握手失败: {exc.__class__.__name__}: {str(exc)[:200]}"
        finally:
            if rpc:
                try:
                    await rpc.stop()
                except Exception:  # noqa: BLE001
                    pass
        return health

    # ---------- PrimeRuntime ----------
    async def start(self, spec: dict[str, Any]) -> str:
        cwd = spec.get("working_directory") or os.getcwd()
        rpc = await self._spawn(cwd)
        try:
            result = await rpc.request(
                "session/new",
                {"cwd": cwd,
                 "mcpServers": spec.get("mcp_servers") or []},
                timeout=30)
            sid = result.get("sessionId")
            if not sid:
                raise RuntimeError(f"session/new 未返回 sessionId: {result}")
            # 执行策略：yolo（引擎内自动批准工具，事件留痕）
            await self._set_option(rpc, sid, "mode", "yolo")
            if self.effort:
                await self._set_option(rpc, sid, "thinking",
                                       _EFFORT_MAP.get(self.effort, self.effort))
            if self.model:
                await self._set_option(rpc, sid, "model", self.model)
        except Exception:
            await rpc.stop()
            raise
        sess = _Session(rpc=rpc, session_id=sid)
        sess.pump_task = asyncio.create_task(self._pump(sess))
        self._sessions[sid] = sess
        return sid

    async def prompt(self, session_id: str, text: str) -> ActionReceipt:
        sess = self._sessions.get(session_id)
        if not sess:
            return ActionReceipt(status="rejected", detail="会话不存在")
        if sess.busy:
            return ActionReceipt(status="rejected",
                                 detail="上一回合仍在执行；等待完成或先 abort")
        sess.busy = True
        sess.prompt_task = asyncio.create_task(self._run_turn(sess, text))
        return ActionReceipt(status="accepted",
                             detail="回合已启动；以 executor.turn_completed "
                                    "事件确认回合结束",
                             operation_id=f"op_{uuid.uuid4().hex[:10]}")

    async def _run_turn(self, sess: _Session, text: str) -> None:
        """回合终态只发 executor.turn_completed；实验交付走 MCP 检查点。"""
        try:
            result = await sess.rpc.request(
                "session/prompt",
                {"sessionId": sess.session_id,
                 "prompt": [{"type": "text", "text": text}]},
                timeout=3600)
            stop = result.get("stopReason") if isinstance(result, dict) else None
            if stop == "end_turn":
                await sess.queue.put({"type": "executor.turn_completed",
                                      "stop_reason": "end_turn",
                                      "detail": "回合完成（stopReason=end_turn）；"
                                                "不代表实验交付"})
            elif stop == "cancelled":
                await sess.queue.put({"type": "run.aborted",
                                      "detail": "回合被取消（stopReason=cancelled）"})
            else:
                # 未知终态如实记 unknown，不当成功
                await sess.queue.put({
                    "type": "executor.turn_completed",
                    "stop_reason": "unknown",
                    "detail": f"回合结束，stopReason={stop!r}（未知终态，如实记录）"})
        except Exception as exc:  # noqa: BLE001
            await sess.queue.put({"type": "execution.progress",
                                  "detail": f"回合异常: {exc.__class__.__name__}: "
                                            f"{str(exc)[:200]}"})
            await sess.queue.put({"type": "run.aborted",
                                  "detail": "回合通信失败"})
        finally:
            sess.busy = False

    async def steer(self, session_id: str, text: str) -> ActionReceipt:
        sess = self._sessions.get(session_id)
        if not sess:
            return ActionReceipt(status="rejected", detail="会话不存在")
        if sess.busy:
            # ACP 无 turn 内 steer；如实拒绝，不假装已送达
            return ActionReceipt(status="rejected",
                                 detail="回合执行中，ACP 不支持插入指导；"
                                        "可先终止或等回合完成后下发")
        return await self.prompt(session_id, f"【人工指导】{text}")

    async def abort(self, session_id: str) -> ActionReceipt:
        sess = self._sessions.get(session_id)
        if not sess:
            return ActionReceipt(status="rejected", detail="会话不存在")
        try:
            await sess.rpc.request("session/cancel",
                                   {"sessionId": session_id}, timeout=15)
            return ActionReceipt(status="accepted",
                                 detail="已发送 session/cancel；以 run.aborted 确认")
        except Exception as exc:  # noqa: BLE001
            return ActionReceipt(status="unknown", detail=str(exc)[:200])

    async def state(self, session_id: str) -> dict[str, Any]:
        sess = self._sessions.get(session_id)
        if not sess:
            return {"status": "unknown", "error": "会话不存在"}
        return {"status": "streaming" if sess.busy else "idle",
                "session_id": session_id}

    async def events(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        sess = self._sessions[session_id]

        async def gen() -> AsyncIterator[dict[str, Any]]:
            while True:
                yield await sess.queue.get()

        async for ev in with_stall_watchdog(gen(), self.stall_timeout):
            yield ev

    async def close(self, session_id: str) -> None:
        sess = self._sessions.pop(session_id, None)
        if not sess:
            return
        if sess.pump_task:
            sess.pump_task.cancel()
        if sess.prompt_task:
            sess.prompt_task.cancel()
        try:
            await sess.rpc.request("session/close",
                                   {"sessionId": session_id}, timeout=10)
        except Exception:  # noqa: BLE001
            pass
        await sess.rpc.stop()

    # ---------- 事件泵：ACP update → 控制器词汇 ----------
    async def _pump(self, sess: _Session) -> None:
        rpc = sess.rpc
        thought_buf: list[str] = []

        async def flush_thought() -> None:
            if thought_buf:
                text = "".join(thought_buf).strip()
                thought_buf.clear()
                if text:
                    await sess.queue.put({"type": "execution.progress",
                                          "detail": f"思考: {text[:300]}"})

        async def handle_updates() -> None:
            async for msg in rpc.notifications():
                if msg.get("method") != "session/update":
                    continue
                if msg.get("params", {}).get("sessionId") != sess.session_id:
                    continue
                u = msg["params"].get("update", {})
                kind = u.get("sessionUpdate")
                if kind in ("agent_message_chunk", "agent_thought_chunk"):
                    content = u.get("content", {})
                    if isinstance(content, dict):
                        thought_buf.append(content.get("text", ""))
                        if sum(len(t) for t in thought_buf) > 400:
                            await flush_thought()
                elif kind in ("tool_call", "tool_call_update"):
                    mapped = map_update(u)
                    if mapped:
                        await flush_thought()
                        await sess.queue.put(mapped)
                # config_option_update / session_info_update /
                # available_commands_update：元信息不映射

        async def answer_question_request(req: dict[str, Any]) -> None:
            """AskUserQuestion → 大脑回答（全自动：不向人类提问）。

            elicitation/create 是正道；request_permission 的 q*_opt_* 形状是
            同一提问的回退形态（该路径当前版本对提问无效，仍按大脑答案应答）。
            无大脑可用/超时：如实 decline/cancel，不伪造答案。
            """
            params = req.get("params", {})
            if req.get("method") == "elicitation/create":
                question = _question_from_elicitation(params)
            else:
                question = _question_from_permission(params)
            await sess.queue.put({
                "type": "execution.progress",
                "detail": f"提问(路由大脑): {question['message'][:120]}"})
            answer = None
            if self.ask_handler:
                try:
                    answer = await asyncio.wait_for(
                        self.ask_handler(sess.session_id, question),
                        timeout=150)
                except Exception:  # noqa: BLE001
                    answer = None
            try:
                if answer and answer.get("answers"):
                    if req.get("method") == "elicitation/create":
                        await rpc.respond(req["id"], result={
                            "action": "accept", "content": answer["answers"]})
                    else:
                        picked = _permission_pick(params, answer["answers"])
                        if picked:
                            await rpc.respond(req["id"], result={
                                "outcome": {"outcome": "selected",
                                            "optionId": picked}})
                        else:
                            await rpc.respond(req["id"], result={
                                "outcome": {"outcome": "cancelled"}})
                    await sess.queue.put({
                        "type": "execution.progress",
                        "detail": "大脑回答: " + json.dumps(
                            answer["answers"], ensure_ascii=False)[:150]})
                else:
                    if req.get("method") == "elicitation/create":
                        await rpc.respond(req["id"], result={"action": "decline"})
                    else:
                        await rpc.respond(req["id"], result={
                            "outcome": {"outcome": "cancelled"}})
                    await sess.queue.put({
                        "type": "execution.progress",
                        "detail": "提问未获大脑回答（超时/额度/错误），已如实拒绝"})
            except ProtocolError:
                pass

        async def handle_requests() -> None:
            # yolo 模式下工具审批不应到达；兜底：自动同意第一个 allow 项并留痕。
            # AskUserQuestion 的提问（elicitation/create 或 q*_opt_* 权限形状）
            # 路由给大脑回答。
            async for req in rpc.server_requests():
                if req.get("method") == "elicitation/create":
                    await answer_question_request(req)
                    continue
                if req.get("method") == "session/request_permission":
                    options = req.get("params", {}).get("options", [])
                    if _is_question_options(options):
                        await answer_question_request(req)
                        continue
                    allow = next((o for o in options
                                  if "allow" in str(o.get("kind", ""))), None)
                    tool = req.get("params", {}).get("toolCall", {})
                    try:
                        if allow:
                            await rpc.respond(req["id"], result={
                                "outcome": {"outcome": "selected",
                                            "optionId": allow["optionId"]}})
                            await sess.queue.put({
                                "type": "approval.granted",
                                "detail": f"自动批准 {tool.get('title', '?')}"
                                          f"（{allow.get('optionId')}）"})
                        else:
                            await rpc.respond(req["id"], result={
                                "outcome": {"outcome": "cancelled"}})
                            await sess.queue.put({
                                "type": "approval.rejected",
                                "detail": f"无可同意选项，已取消 "
                                          f"{tool.get('title', '?')}"})
                    except ProtocolError:
                        pass
                else:
                    try:
                        await rpc.respond(req["id"], error={
                            "code": -32601, "message": "unsupported by executor"})
                    except ProtocolError:
                        pass

        try:
            await asyncio.gather(handle_updates(), handle_requests())
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await sess.queue.put({"type": "execution.progress",
                                  "detail": f"事件泵异常: {exc.__class__.__name__}: "
                                            f"{str(exc)[:200]}"})
