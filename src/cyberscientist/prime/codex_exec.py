"""Codex executor using native app-server threads, turns and session MCP.

Protocol fields verified with Linux CLI 0.148.0-alpha.15. A turn completion is
an execution boundary; experiment delivery still requires a checkpoint.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from ..brains.codex import CodexBrain, default_executable
from ..codex_protocol import (deny_requests, initialize, process_environment,
                              thread_params, verify_thread_config)
from ..jsonrpc_stdio import JsonRpcStdio
from . import ActionReceipt, PrimeHealth, with_stall_watchdog


@dataclass
class _Session:
    rpc: JsonRpcStdio
    thread_id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    pump_task: asyncio.Task | None = None
    turn_task: asyncio.Task | None = None
    requests_task: asyncio.Task | None = None
    turn_id: str | None = None
    busy: bool = False


class CodexExecutor:
    kind = "codex"

    def __init__(self, executable: str | None = None, model: str | None = None,
                 effort: str | None = None, stall_timeout: float = 240.0):
        self.executable = executable or default_executable() or ""
        self.model = model
        self.effort = effort
        self.stall_timeout = stall_timeout
        self._sessions: dict[str, _Session] = {}

    async def inspect(self) -> PrimeHealth:
        health = await CodexBrain(self.executable, self.model, self.effort).inspect()
        return PrimeHealth(installed=health.installed, version=health.version,
                           detail=health.detail,
                           capabilities={"tool_execution": True,
                                         "collaboration_mcp": True,
                                         "verified": False})

    async def start(self, spec: dict[str, Any]) -> str:
        rpc = JsonRpcStdio([self.executable, "app-server"],
                           cwd=spec.get("working_directory"),
                           env=process_environment(spec), name="codex-exec")
        try:
            await rpc.start()
            await initialize(rpc)
            result = await rpc.request("thread/start", thread_params(
                spec, self.model, self.effort, writable=True), timeout=60)
            verify_thread_config(result, self.model, self.effort)
            tid = result["thread"]["id"]
        except BaseException:
            await rpc.stop()
            raise
        sess = _Session(rpc=rpc, thread_id=tid)

        async def report(payload: dict[str, Any]) -> None:
            await sess.queue.put({"type": "approval.request", **payload})

        sess.requests_task = asyncio.create_task(deny_requests(rpc, report))
        sess.pump_task = asyncio.create_task(self._pump(sess))
        self._sessions[tid] = sess
        return tid

    async def prompt(self, session_id: str, text: str) -> ActionReceipt:
        sess = self._sessions.get(session_id)
        if not sess:
            return ActionReceipt(status="rejected", detail="会话不存在")
        if sess.busy:
            return ActionReceipt(status="rejected", detail="上一回合仍在执行")
        sess.busy = True
        sess.turn_task = asyncio.create_task(self._run_turn(sess, text))
        return ActionReceipt(status="accepted", detail="正在请求原生 turn；终态由事件确认",
                             operation_id=f"op_{uuid.uuid4().hex[:10]}")

    async def _run_turn(self, sess: _Session, text: str) -> None:
        try:
            params: dict[str, Any] = {
                "threadId": sess.thread_id,
                "input": [{"type": "text", "text": text}],
            }
            if self.effort:
                params["effort"] = self.effort
            result = await sess.rpc.request("turn/start", params, timeout=30)
            # A fast terminal event can arrive before the response is consumed.
            if sess.busy:
                sess.turn_id = result["turn"]["id"]
            await sess.queue.put({"type": "execution.progress",
                                  "detail": f"turn 已开始: {result['turn']['id']}"})
        except Exception as exc:
            sess.busy = False
            sess.turn_id = None
            await sess.queue.put({"type": "run.aborted",
                                  "detail": f"turn/start 失败: {str(exc)[:500]}"})

    async def steer(self, session_id: str, text: str) -> ActionReceipt:
        sess = self._sessions.get(session_id)
        if not sess:
            return ActionReceipt(status="rejected", detail="会话不存在")
        if not sess.busy:
            return await self.prompt(session_id, f"【人工指导】{text}")
        if not sess.turn_id:
            return ActionReceipt(status="rejected", detail="turn 尚未获得服务端 ID")
        try:
            await sess.rpc.request("turn/steer", {
                "threadId": session_id, "expectedTurnId": sess.turn_id,
                "input": [{"type": "text", "text": text}],
            }, timeout=15)
            return ActionReceipt(status="accepted", detail="turn/steer 已接受；不代表指导已执行")
        except Exception as exc:
            return ActionReceipt(status="unknown", detail=str(exc)[:300])

    async def abort(self, session_id: str) -> ActionReceipt:
        sess = self._sessions.get(session_id)
        if not sess:
            return ActionReceipt(status="rejected", detail="会话不存在")
        if not sess.busy:
            return ActionReceipt(status="confirmed", detail="当前无活动 turn")
        if not sess.turn_id and sess.turn_task:
            try:
                await asyncio.wait_for(asyncio.shield(sess.turn_task), timeout=5)
            except asyncio.TimeoutError:
                return ActionReceipt(status="unknown", detail="turn/start 尚未确认，不能猜测 turn ID")
        if not sess.turn_id:
            return ActionReceipt(status="unknown", detail="缺少活动 turn ID")
        try:
            await sess.rpc.request("turn/interrupt", {
                "threadId": session_id, "turnId": sess.turn_id}, timeout=15)
            return ActionReceipt(status="accepted", detail="已请求中断；以 turn 终态确认")
        except Exception as exc:
            return ActionReceipt(status="unknown", detail=str(exc)[:300])

    async def state(self, session_id: str) -> dict[str, Any]:
        sess = self._sessions.get(session_id)
        if not sess:
            return {"status": "unknown", "error": "会话不存在"}
        return {"status": "streaming" if sess.busy else "idle",
                "session_id": session_id, "turn_id": sess.turn_id}

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
        tasks = [t for t in (sess.pump_task, sess.turn_task, sess.requests_task) if t]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await sess.rpc.stop()

    async def _pump(self, sess: _Session) -> None:
        try:
            async for msg in sess.rpc.notifications():
                method, params = msg.get("method"), msg.get("params", {})
                if params.get("threadId", sess.thread_id) != sess.thread_id:
                    continue
                if method == "turn/started":
                    sess.turn_id = params["turn"]["id"]
                elif method in ("item/started", "item/completed"):
                    item = params.get("item", {})
                    itype = item.get("type")
                    completed = method == "item/completed"
                    if itype in ("agentMessage", "agent_message") and completed:
                        await sess.queue.put({"type": "execution.progress",
                                              "detail": item.get("text", ""),
                                              "item_id": item.get("id")})
                    elif itype == "reasoning" and completed:
                        await sess.queue.put({"type": "reasoning",
                                              "detail": "\n".join(item.get("summary") or [])})
                    elif itype in ("commandExecution", "fileChange", "mcpToolCall", "webSearch"):
                        label = (item.get("command") or item.get("query") or
                                 item.get("tool") or str(item.get("changes") or ""))
                        output = item.get("aggregatedOutput") or ""
                        if itype == "mcpToolCall":
                            output = json.dumps(item.get("result") or item.get("error") or {},
                                                ensure_ascii=False)
                        await sess.queue.put({
                            "type": "execution.progress", "item_id": item.get("id"),
                            "detail": f"{itype} {'完成' if completed else '开始'}: {label[:2000]}",
                            "status": item.get("status"), "exit_code": item.get("exitCode"),
                            "output": output[-12000:],
                        })
                elif method == "thread/tokenUsage/updated":
                    await sess.queue.put({"type": "usage.updated", "usage": params.get("tokenUsage")})
                elif method == "turn/completed":
                    turn = params.get("turn", {})
                    if sess.turn_id and turn.get("id") != sess.turn_id:
                        continue
                    sess.busy = False
                    sess.turn_id = None
                    if turn.get("status") == "completed":
                        await sess.queue.put({"type": "executor.turn_completed",
                                              "stop_reason": "completed",
                                              "detail": "原生 turn 完成；实验交付仍以检查点为准"})
                    else:
                        await sess.queue.put({"type": "run.aborted",
                                              "detail": f"turn 终态: {turn.get('status')}",
                                              "error": turn.get("error")})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            sess.busy = False
            sess.turn_id = None
            await sess.queue.put({"type": "run.aborted",
                                  "detail": f"Codex 协议连接结束: {str(exc)[:500]}"})
