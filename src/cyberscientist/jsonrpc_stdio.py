"""JSON-RPC over stdio（LF 分帧），供 Codex app-server 与 Prime RPC 适配器共用。"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable

log = logging.getLogger("cyberscientist.jsonrpc")


class ProtocolError(Exception):
    pass


class JsonRpcStdio:
    def __init__(self, argv: list[str], env: dict[str, str] | None = None,
                 cwd: str | None = None, name: str = "proc"):
        self.argv = argv
        self.env = env
        self.cwd = cwd
        self.name = name
        self.proc: asyncio.subprocess.Process | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._server_requests: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._notifications: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._stderr_tail: list[str] = []

    async def start(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(
            *self.argv, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=self.env, cwd=self.cwd)
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                log.warning("%s: 无法解析的帧，已忽略: %.120r", self.name, line)
                continue
            await self._dispatch(msg)
        # 进程退出：唤醒所有等待者
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ProtocolError(f"{self.name} 进程已退出"))
        self._pending.clear()

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                if msg.get("error") is not None:
                    fut.set_exception(ProtocolError(json.dumps(msg["error"])[:500]))
                else:
                    fut.set_result(msg.get("result"))
        elif "id" in msg and "method" in msg:
            # 服务器→客户端请求（审批等）
            await self._server_requests.put(msg)
        elif "method" in msg:
            await self._notifications.put(msg)

    async def request(self, method: str, params: dict[str, Any] | None = None,
                      timeout: float = 60.0) -> dict[str, Any]:
        if not self.proc or self.proc.stdin is None:
            raise ProtocolError(f"{self.name} 未启动")
        self._next_id += 1
        rid = self._next_id
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        frame = json.dumps({"id": rid, "method": method,
                            "params": params or {}}, ensure_ascii=False) + "\n"
        self.proc.stdin.write(frame.encode("utf-8"))
        await self.proc.stdin.drain()
        return await asyncio.wait_for(fut, timeout)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if not self.proc or self.proc.stdin is None:
            raise ProtocolError(f"{self.name} 未启动")
        frame = json.dumps({"method": method, "params": params or {}},
                           ensure_ascii=False) + "\n"
        self.proc.stdin.write(frame.encode("utf-8"))
        await self.proc.stdin.drain()

    def notifications(self) -> AsyncIterator[dict[str, Any]]:
        return _queue_iter(self._notifications)

    def server_requests(self) -> AsyncIterator[dict[str, Any]]:
        return _queue_iter(self._server_requests)

    async def next_server_request(self, timeout: float = 0.5) -> dict[str, Any] | None:
        try:
            return await asyncio.wait_for(self._server_requests.get(), timeout)
        except asyncio.TimeoutError:
            return None

    async def respond(self, req_id: Any, result: Any = None,
                      error: Any = None) -> None:
        msg: dict[str, Any] = {"id": req_id}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result
        await self.notify_special(msg)

    async def notify_special(self, msg: dict[str, Any]) -> None:
        if not self.proc or self.proc.stdin is None:
            raise ProtocolError(f"{self.name} 未启动")
        self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()

    async def stop(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self.proc:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), 5)
            except (ProcessLookupError, asyncio.TimeoutError):
                self.proc.kill()


async def _queue_iter(q: asyncio.Queue) -> AsyncIterator[Any]:
    while True:
        yield await q.get()
