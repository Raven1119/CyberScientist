"""PrimeRuntime 抽象 + Demo 执行器 + RPC 协议壳。"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass
class PrimeHealth:
    installed: bool = False
    detail: str = ""
    version: str | None = None
    capabilities: dict[str, bool] = field(default_factory=dict)


@dataclass
class ActionReceipt:
    status: str = "unknown"      # accepted | confirmed | rejected | unknown
    detail: str = ""
    operation_id: str | None = None


class PrimeRuntime(Protocol):
    kind: str

    async def inspect(self) -> PrimeHealth: ...
    async def start(self, spec: dict[str, Any]) -> str: ...          # 返回 session_id
    async def prompt(self, session_id: str, text: str) -> ActionReceipt: ...
    async def steer(self, session_id: str, text: str) -> ActionReceipt: ...
    async def abort(self, session_id: str) -> ActionReceipt: ...
    async def state(self, session_id: str) -> dict[str, Any]: ...
    def events(self, session_id: str) -> AsyncIterator[dict[str, Any]]: ...


class DemoPrime:
    """脚本化执行器：驱动演示 Run 的事件流，不调用任何外部服务。"""

    kind = "demo"

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
        self._steer_pending: dict[str, str] = {}
        self._aborted: set[str] = set()

    async def inspect(self) -> PrimeHealth:
        return PrimeHealth(installed=True, version="demo-0.1",
                           detail="演示执行器：脚本化事件流，不调用外部服务")

    def _queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    async def start(self, spec: dict[str, Any]) -> str:
        sid = f"demo_prime_{uuid.uuid4().hex[:8]}"
        return sid

    async def prompt(self, session_id: str, text: str) -> ActionReceipt:
        q = self._queue(session_id)
        self._aborted.discard(session_id)  # 新任务即恢复 engagement

        async def _script() -> None:
            if session_id in self._aborted:
                await q.put({"type": "run.aborted"})
                return
            await q.put({"type": "trial.started", "detail": "执行器接收任务（演示）"})
            await asyncio.sleep(0.8)
            await q.put({"type": "execution.progress",
                         "detail": "整理输入清单与运行目录（演示）"})
            await asyncio.sleep(0.8)
            steer = self._steer_pending.pop(session_id, None)
            if steer:
                await q.put({"type": "steer.consumed", "detail": steer})
            await asyncio.sleep(0.6)
            await q.put({"type": "checkpoint.created",
                         "detail": "阶段证据与恢复信息已保存（演示）"})
            await asyncio.sleep(0.6)
            await q.put({"type": "trial.completed",
                         "detail": "产物清单与 hash 已登记（演示）"})
            self._aborted.discard(session_id)

        asyncio.get_running_loop().create_task(_script())
        return ActionReceipt(status="accepted", detail="演示任务已排队",
                             operation_id=f"op_{uuid.uuid4().hex[:10]}")

    async def steer(self, session_id: str, text: str) -> ActionReceipt:
        self._steer_pending[session_id] = text
        return ActionReceipt(status="accepted", detail="指导已排队（演示），"
                                                     "消费后以 steer.consumed 确认",
                             operation_id=f"op_{uuid.uuid4().hex[:10]}")

    async def abort(self, session_id: str) -> ActionReceipt:
        self._aborted.add(session_id)
        return ActionReceipt(status="confirmed", detail="演示会话已停止")

    async def state(self, session_id: str) -> dict[str, Any]:
        return {"status": "idle", "session_id": session_id}

    async def events(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        q = self._queue(session_id)
        while True:
            yield await q.get()


class PrimeRpc:
    """prime-agent --mode rpc 适配壳。

    上游协议细节（请求/响应帧形状）尚未在本机核实——prime-agent 未安装。
    适配器只做两件事：inspect 如实报告未安装；协议发送前以 get_state
    最小探针为准，未核实前不把任何帧语义当成已确认。
    """

    kind = "prime-rpc"

    def __init__(self, executable: str):
        self.executable = executable
        self._verified = False

    async def inspect(self) -> PrimeHealth:
        import os
        if not self.executable or not os.path.exists(self.executable):
            return PrimeHealth(
                installed=False,
                detail="prime-agent 未安装；RPC 协议（prompt/steer/abort/get_state，"
                       "stdin/stdout JSONL）按官方文档实现但未经真实探针核实",
                capabilities={"resume_conversation": False,
                              "steer_delivery": False,
                              "usage_reporting": False})
        return PrimeHealth(
            installed=True, detail="可执行文件存在，但 RPC 帧格式未经 get_state "
                                   "探针核实，能力标记保持保守",
            capabilities={"resume_conversation": False,
                          "steer_delivery": False,
                          "usage_reporting": False})

    async def start(self, spec: dict[str, Any]) -> str:
        raise RuntimeError("Prime RPC 未经 get_state 探针核实，拒绝启动真实会话")

    async def prompt(self, session_id: str, text: str) -> ActionReceipt:
        return ActionReceipt(status="rejected", detail="Prime 未接入")

    async def steer(self, session_id: str, text: str) -> ActionReceipt:
        return ActionReceipt(status="rejected", detail="Prime 未接入")

    async def abort(self, session_id: str) -> ActionReceipt:
        return ActionReceipt(status="rejected", detail="Prime 未接入")

    async def state(self, session_id: str) -> dict[str, Any]:
        return {"status": "unavailable"}

    async def events(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        if False:
            yield {}
        return
