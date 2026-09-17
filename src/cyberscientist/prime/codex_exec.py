"""Codex 执行器：codex app-server JSON-RPC 作为执行系统。

!! 未实测：当前 Codex 账户无额度，本适配器按 app-server 协议（与
brains/codex.py 同一握手面）保守实现，事件映射未经验证。
inspect() 可用（零模型调用握手）；首次真实运行前需重新核对事件形状。
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from ..brains.codex import CLIENT_INFO, default_executable
from ..jsonrpc_stdio import JsonRpcStdio
from . import ActionReceipt, PrimeHealth, with_stall_watchdog

log = logging.getLogger("cyberscientist.executor.codex")


@dataclass
class _Session:
    rpc: JsonRpcStdio
    thread_id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    pump_task: asyncio.Task | None = None
    turn_task: asyncio.Task | None = None
    busy: bool = False


class CodexExecutor:
    """PrimeRuntime 协议实现：codex app-server thread/turn 即执行单元（未实测）。"""

    kind = "codex"

    def __init__(self, executable: str | None = None, model: str | None = None,
                 effort: str | None = None, stall_timeout: float = 240.0):
        self.executable = executable or default_executable() or ""
        self.model = model
        self.effort = effort
        self.stall_timeout = stall_timeout
        self._sessions: dict[str, _Session] = {}

    async def inspect(self) -> PrimeHealth:
        if not self.executable or not os.path.exists(self.executable):
            return PrimeHealth(
                installed=False,
                detail=f"codex 可执行文件不可用: {self.executable or '未配置'}")
        health = PrimeHealth(installed=True)
        rpc = JsonRpcStdio([self.executable, "app-server"], name="codex-exec")
        try:
            await asyncio.wait_for(rpc.start(), 15)
            result = await rpc.request(
                "initialize", {"clientInfo": CLIENT_INFO, "capabilities": {}},
                timeout=30)
            ua = result.get("userAgent", "") if isinstance(result, dict) else ""
            import re
            m = re.search(r"/(\d+\.\S+?) ", ua)
            health.version = m.group(1) if m else None
            health.detail = "app-server 握手成功；执行路径未实测（无额度），" \
                            "事件映射按协议保守实现"
            health.capabilities = {"tool_execution": True, "verified": False}
        except Exception as exc:  # noqa: BLE001
            health.detail = f"握手失败: {exc.__class__.__name__}: {str(exc)[:200]}"
        finally:
            try:
                await rpc.stop()
            except Exception:  # noqa: BLE001
                pass
        return health

    async def start(self, spec: dict[str, Any]) -> str:
        rpc = JsonRpcStdio([self.executable, "app-server"],
                           cwd=spec.get("working_directory"), name="codex-exec")
        await rpc.start()
        try:
            await rpc.request("initialize",
                              {"clientInfo": CLIENT_INFO, "capabilities": {}},
                              timeout=30)
            params: dict[str, Any] = {
                # 执行器需要写产物；审批 never = 引擎内自动执行（留痕于事件流）
                "approvalPolicy": "never",
                "sandboxPolicy": {"type": "workspaceWrite"},
            }
            if self.model:
                params["model"] = self.model
            if self.effort:
                params["effort"] = self.effort
            try:
                result = await rpc.request("thread/start", params, timeout=30)
            except Exception:
                if "effort" not in params:
                    raise
                params.pop("effort")  # 旧版本不支持 effort：降级重试
                result = await rpc.request("thread/start", params, timeout=30)
            thread = result.get("thread", result)
            tid = thread["id"]
        except Exception:
            await rpc.stop()
            raise
        sess = _Session(rpc=rpc, thread_id=tid)
        sess.pump_task = asyncio.create_task(self._pump(sess))
        self._sessions[tid] = sess
        return tid

    async def prompt(self, session_id: str, text: str) -> ActionReceipt:
        sess = self._sessions.get(session_id)
        if not sess:
            return ActionReceipt(status="rejected", detail="会话不存在")
        if sess.busy:
            return ActionReceipt(status="rejected",
                                 detail="上一回合仍在执行；等待完成或先 abort")
        sess.busy = True
        sess.turn_task = asyncio.create_task(self._run_turn(sess, text))
        return ActionReceipt(status="accepted",
                             detail="turn 已启动；以 trial.completed 事件确认",
                             operation_id=f"op_{uuid.uuid4().hex[:10]}")

    async def _run_turn(self, sess: _Session, text: str) -> None:
        try:
            result = await sess.rpc.request("turn/start", {
                "threadId": sess.thread_id,
                "input": [{"type": "text", "text": text}],
            }, timeout=30)
            sess.queue.put_nowait({"type": "execution.progress",
                                   "detail": f"turn 已开始: "
                                             f"{result.get('turn', {}).get('id', '?')}"})
        except Exception as exc:  # noqa: BLE001
            sess.busy = False
            await sess.queue.put({"type": "run.aborted",
                                  "detail": f"turn/start 失败: {str(exc)[:200]}"})

    async def steer(self, session_id: str, text: str) -> ActionReceipt:
        sess = self._sessions.get(session_id)
        if not sess:
            return ActionReceipt(status="rejected", detail="会话不存在")
        if sess.busy:
            return ActionReceipt(status="rejected",
                                 detail="turn 执行中；可先 abort 或等完成后下发")
        return await self.prompt(session_id, f"【人工指导】{text}")

    async def abort(self, session_id: str) -> ActionReceipt:
        sess = self._sessions.get(session_id)
        if not sess:
            return ActionReceipt(status="rejected", detail="会话不存在")
        try:
            await sess.rpc.request("turn/interrupt",
                                   {"threadId": session_id}, timeout=15)
            return ActionReceipt(status="accepted",
                                 detail="已发送 turn/interrupt；以 turn 终态确认")
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
        if sess.turn_task:
            sess.turn_task.cancel()
        await sess.rpc.stop()

    async def _pump(self, sess: _Session) -> None:
        """item/completed → execution.progress；turn/completed → trial.completed。

        未实测：item 类型清单按 app-server 协议文档保守覆盖，未知类型跳过。
        """
        try:
            async for msg in sess.rpc.notifications():
                method, params = msg.get("method"), msg.get("params", {})
                if method == "item/completed":
                    item = params.get("item", {})
                    itype = item.get("type")
                    if itype == "agent_message":
                        await sess.queue.put({
                            "type": "execution.progress",
                            "detail": f"回复: {item.get('text', '')[:300]}"})
                    elif itype == "reasoning":
                        await sess.queue.put({
                            "type": "execution.progress",
                            "detail": f"思考: {item.get('text', '')[:300]}"})
                    elif itype in ("command_execution", "file_change",
                                   "mcp_tool_call"):
                        await sess.queue.put({
                            "type": "execution.progress",
                            "detail": f"{itype}: "
                                      f"{str(item.get('command') or item.get('changes') or '')[:200]}"})
                elif method == "turn/completed":
                    turn = params.get("turn", {})
                    sess.busy = False
                    if turn.get("status") == "completed":
                        await sess.queue.put({
                            "type": "trial.completed",
                            "detail": "turn 完成（turn/completed）"})
                    else:
                        await sess.queue.put({
                            "type": "run.aborted",
                            "detail": f"turn 终态: {turn.get('status')}"})
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await sess.queue.put({"type": "execution.progress",
                                  "detail": f"事件泵异常: {exc.__class__.__name__}: "
                                            f"{str(exc)[:200]}"})
