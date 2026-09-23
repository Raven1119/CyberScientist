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
        self._stderr_task: asyncio.Task | None = None
        self._stderr_tail: list[str] = []

    async def start(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(
            *self.argv, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=self.env, cwd=self.cwd, limit=8 * 1024 * 1024)
        self._reader_task = asyncio.create_task(self._read_loop())
        # A8：stderr 必须持续消费，否则管道写满会阻塞子进程
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            self._stderr_tail.append(text[:300])
            del self._stderr_tail[:-20]  # 只保留尾窗，有界
            log.debug("%s stderr: %.200s", self.name, text)

    def stderr_tail(self) -> list[str]:
        return list(self._stderr_tail)

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        failure = ProtocolError(f"{self.name} 协议连接已关闭")
        try:
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    log.warning("%s: 无法解析的帧，已忽略", self.name)
                    continue
                if isinstance(msg, dict):
                    await self._dispatch(msg)
        except (OSError, ValueError) as exc:
            failure = ProtocolError(f"{self.name} 读取协议失败: {type(exc).__name__}")
        finally:
            # EOF must wake stream consumers too, not only pending requests.
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(failure)
            self._pending.clear()
            self._notifications.put_nowait(failure)
            self._server_requests.put_nowait(failure)

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
        frame = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                            "params": params or {}}, ensure_ascii=False) + "\n"
        try:
            self.proc.stdin.write(frame.encode("utf-8"))
            await self.proc.stdin.drain()
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(rid, None)

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
            item = await asyncio.wait_for(self._server_requests.get(), timeout)
            if isinstance(item, Exception):
                raise item
            return item
        except asyncio.TimeoutError:
            return None

    async def respond(self, req_id: Any, result: Any = None,
                      error: Any = None) -> None:
        # JSON-RPC 2.0 响应必须带 jsonrpc 字段：ACP 较新的代码路径
        # （elicitation 等）严格校验，缺字段会被当作 RPC 失败回退
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
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
        tasks = [t for t in (self._reader_task, self._stderr_task)
                 if t and t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        for pending in self._pending.values():
            if not pending.done():
                pending.set_exception(ProtocolError(f"{self.name} 已停止"))
        self._pending.clear()
        proc, self.proc = self.proc, None
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), 5)
            except ProcessLookupError:
                pass
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._reader_task = self._stderr_task = None


async def _queue_iter(q: asyncio.Queue) -> AsyncIterator[Any]:
    while True:
        item = await q.get()
        if isinstance(item, Exception):
            raise item
        yield item
