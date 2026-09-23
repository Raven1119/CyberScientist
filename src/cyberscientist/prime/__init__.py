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
    async def close(self, session_id: str) -> None: ...


async def with_stall_watchdog(events: AsyncIterator[dict[str, Any]],
                              timeout: float) -> AsyncIterator[dict[str, Any]]:
    """执行器事件流挂起看门狗：timeout 秒无任何事件则上报一次 stalled。

    典型场景：模型流式调用无超时悬挂（Prime/DeepSeek 实测 8 分钟死寂）。
    stalled 只代表需要活性核对（A9）：上报后流保持开放，
    后续事件仍然透传；不替控制器判失败、不终止会话。
    """
    it = events.__aiter__()
    pending: asyncio.Task | None = None
    stalled = False
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(it.__anext__())
            try:
                # shield protects the reader from an idle timeout, not from
                # ownership cleanup when this wrapper is cancelled or closed.
                ev = await asyncio.wait_for(asyncio.shield(pending), timeout)
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError:
                if not stalled:
                    stalled = True
                    yield {"type": "trial.stalled",
                           "detail": f"{int(timeout)}s 无执行器事件；"
                                     f"仅活性告警，流保持开放"}
                continue
            pending = None
            stalled = False
            yield ev
    finally:
        if pending is not None:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        close = getattr(it, "aclose", None)
        if close is not None:
            await close()


class DemoPrime:
    """脚本化执行器：驱动演示 Run 的事件流，不调用任何外部服务。"""

    kind = "demo"

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
        self._scripts: dict[str, set[asyncio.Task]] = {}
        self._steer_pending: dict[str, str] = {}
        self._aborted: set[str] = set()

    async def inspect(self) -> PrimeHealth:
        return PrimeHealth(installed=True, version="demo-0.1",
                           detail="演示执行器：脚本化事件流，不调用外部服务")

    def _queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            raise ValueError("演示会话已关闭或不存在")
        return self._queues[session_id]

    async def start(self, spec: dict[str, Any]) -> str:
        sid = f"demo_prime_{uuid.uuid4().hex[:8]}"
        self._queues[sid] = asyncio.Queue()
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

        scripts = self._scripts.setdefault(session_id, set())
        task = asyncio.get_running_loop().create_task(_script())
        scripts.add(task)
        task.add_done_callback(scripts.discard)
        return ActionReceipt(status="accepted", detail="演示任务已排队",
                             operation_id=f"op_{uuid.uuid4().hex[:10]}")

    async def steer(self, session_id: str, text: str) -> ActionReceipt:
        self._queue(session_id)
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
        q = self._queues.get(session_id)
        if q is None:
            return
        while True:
            event = await q.get()
            if self._queues.get(session_id) is not q:
                return
            yield event

    async def close(self, session_id: str) -> None:
        # Remove the session before awaiting cancellation so neither a new prompt
        # nor a pending event reader can resume the closed session.
        q = self._queues.pop(session_id, None)
        scripts = self._scripts.pop(session_id, set())
        for task in scripts:
            task.cancel()
        if scripts:
            await asyncio.gather(*scripts, return_exceptions=True)
        self._steer_pending.pop(session_id, None)
        self._aborted.discard(session_id)
        if q is not None:
            while not q.empty():
                q.get_nowait()
            q.put_nowait(None)  # Wake an event reader waiting for the next item.


from .rpc import PrimeJsonlClient, PrimeRpc  # noqa: E402
from .kimi_acp import KimiExecutor  # noqa: E402
from .codex_exec import CodexExecutor  # noqa: E402
