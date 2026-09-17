"""Kimi Code 大脑适配边界。

当前环境未发现可独立调用的 kimi CLI（--wire），因此只提供明确的
“未接入”状态，不把它伪装成普通聊天 API。接入时按 INTEGRATIONS.md
的 kimi --wire JSON-RPC 协议实现，与 Codex 共用 BrainRuntime 契约。
"""
from __future__ import annotations
from typing import Any, AsyncIterator

from .base import BrainEvent, RuntimeHealth, SessionRef


class KimiBrain:
    kind = "kimi"

    async def inspect(self) -> RuntimeHealth:
        return RuntimeHealth(
            installed=False,
            authenticated=None,
            detail="未在本机发现 kimi --wire 可执行文件；该大脑尚未接入，"
                   "不会退化为普通 LLM API",
            capabilities={"resume_conversation": False, "resume_kernel": False,
                          "steer_delivery": False, "usage_reporting": False})

    async def open(self, spec: dict[str, Any]) -> SessionRef:
        raise RuntimeError("Kimi 大脑尚未接入")

    async def review(self, session: SessionRef,
                     packet: dict[str, Any]) -> AsyncIterator[BrainEvent]:
        yield BrainEvent("error", {"message": "Kimi 大脑尚未接入"})
        return

    async def cancel(self, session: SessionRef) -> dict[str, Any]:
        return {"status": "rejected", "detail": "Kimi 大脑尚未接入"}

    async def close(self, session: SessionRef) -> None:
        return None
