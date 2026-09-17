"""BrainRuntime 抽象：Codex / Kimi / Demo 三种实现共用。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass
class RuntimeHealth:
    installed: bool = False
    authenticated: bool | None = None   # None = 未知
    detail: str = ""
    version: str | None = None
    capabilities: dict[str, bool] = field(default_factory=dict)


@dataclass
class SessionRef:
    runtime: str
    session_id: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrainEvent:
    type: str          # token | message | decision | error | approval_request
    payload: dict[str, Any]


class BrainRuntime(Protocol):
    kind: str

    async def inspect(self) -> RuntimeHealth: ...
    async def open(self, spec: dict[str, Any]) -> SessionRef: ...
    def review(self, session: SessionRef, packet: dict[str, Any]) -> AsyncIterator[BrainEvent]: ...
    async def cancel(self, session: SessionRef) -> dict[str, Any]: ...
    async def close(self, session: SessionRef) -> None: ...
