"""Prime Agent RPC 适配器（协议按官方 docs/rpc.md v0.9.5 实现并经探针核实）。

协议要点（与 JSON-RPC 不同，是 type-tagged JSONL）：
- 命令: {"id"?: str, "type": "<command>", ...params}，LF 分帧
- 响应: {"type": "response", "command": ..., "success": bool, "id"?: ...}
- 事件: 其他带 type 的行（agent_start/agent_end/message_*/tool_execution_*）
- 服务器→客户端请求: {"type": "extension_ui_request", "id", "method", ...}
  必须以 {"type": "extension_ui_response", "id", ...} 应答，否则代理悬挂
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, AsyncIterator

from ..jsonrpc_stdio import ProtocolError
from . import ActionReceipt, PrimeHealth

log = logging.getLogger("cyberscientist.prime.rpc")


class PrimeJsonlClient:
    """prime-agent --mode rpc 子进程的薄封装。"""

    def __init__(self, argv: list[str], env: dict[str, str] | None = None,
                 cwd: str | None = None):
        self.argv = argv
        self.env = env
        self.cwd = cwd
        self.proc: asyncio.subprocess.Process | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader: asyncio.Task | None = None

    async def start(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(
            *self.argv, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=self.env, cwd=self.cwd)
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        while True:
            raw = await self.proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                log.warning("prime: 无法解析的帧: %.120r", line)
                continue
            mtype = msg.get("type")
            if mtype == "response":
                fut = self._pending.pop(str(msg.get("id")), None)
                if fut and not fut.done():
                    fut.set_result(msg)
            elif mtype == "extension_ui_request":
                # 服务器请求：入事件队列，由消费方应答
                await self._events.put(msg)
            else:
                await self._events.put(msg)
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ProtocolError("prime-agent 进程已退出"))
        self._pending.clear()

    async def command(self, ctype: str, params: dict[str, Any] | None = None,
                      timeout: float = 60.0) -> dict[str, Any]:
        if not self.proc or self.proc.stdin is None:
            raise ProtocolError("prime-agent 未启动")
        cid = uuid.uuid4().hex[:12]
        fut = asyncio.get_running_loop().create_future()
        self._pending[cid] = fut
        msg = {"id": cid, "type": ctype, **(params or {})}
        self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()
        return await asyncio.wait_for(fut, timeout)

    async def respond_ui(self, req_id: str, **fields: Any) -> None:
        if not self.proc or self.proc.stdin is None:
            raise ProtocolError("prime-agent 未启动")
        msg = {"type": "extension_ui_response", "id": req_id, **fields}
        self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()

    def events(self) -> AsyncIterator[dict[str, Any]]:
        return _qiter(self._events)

    async def stop(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self.proc:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), 5)
            except (ProcessLookupError, asyncio.TimeoutError):
                self.proc.kill()


async def _qiter(q: asyncio.Queue) -> AsyncIterator[Any]:
    while True:
        yield await q.get()


class PrimeRpc:
    """PrimeRuntime：独立 prime-agent 子进程，RPC 模式。"""

    kind = "prime-rpc"

    def __init__(self, executable: str, stall_timeout: float = 240.0):
        self.executable = executable
        self.stall_timeout = stall_timeout
        self._clients: dict[str, PrimeJsonlClient] = {}

    @staticmethod
    def _resolve_argv(executable: str) -> list[str]:
        import shutil
        exe = executable
        if not exe or (os.sep not in exe and not os.path.exists(exe)):
            exe = shutil.which("prime-agent") or ""
        if not exe:
            raise RuntimeError("prime-agent 未安装且未配置路径")
        # Windows：.cmd/.bat  shim 需要经 cmd 解释执行
        if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", exe]
        return [exe]

    # ---------- 探针 ----------
    async def inspect(self) -> PrimeHealth:
        import shutil
        exe = self.executable or shutil.which("prime-agent") or ""
        if not exe or not os.path.exists(exe):
            return PrimeHealth(
                installed=False,
                detail="prime-agent 未安装或路径无效",
                capabilities={"resume_conversation": False,
                              "steer_delivery": False,
                              "usage_reporting": False})
        health = PrimeHealth(installed=True, capabilities={
            "resume_conversation": True,   # 会话持久化（默认开启）
            "steer_delivery": True,        # 文档确认排队语义
            "usage_reporting": True,       # get_session_stats（成本由供应商定价计算）
        })
        try:
            proc = await asyncio.create_subprocess_exec(
                exe, "--version", stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            health.version = out.decode("utf-8", errors="replace").strip()[:120]
        except Exception as exc:  # noqa: BLE001
            health.detail = f"版本探针失败: {exc}"
            return health
        # 零模型调用探针：启动 RPC 模式 + get_state
        try:
            client = PrimeJsonlClient([exe, "--mode", "rpc", "--no-session"])
            await asyncio.wait_for(client.start(), timeout=30)
            resp = await client.command("get_state", timeout=30)
            if resp.get("success"):
                data = resp.get("data") or {}
                health.detail = (
                    "RPC get_state 探针成功（零模型调用）；"
                    f" sessionId={data.get('sessionId', '?')},"
                    f" isStreaming={data.get('isStreaming')}")
                health.raw_state_keys = sorted(data.keys())  # type: ignore[attr-defined]
            else:
                health.detail = f"get_state 被拒绝: {resp.get('error', '?')[:150]}"
                health.capabilities["steer_delivery"] = False
        except Exception as exc:  # noqa: BLE001
            health.detail = f"RPC 探针失败: {exc.__class__.__name__}: {str(exc)[:200]}"
            health.capabilities["steer_delivery"] = False
        finally:
            try:
                await client.stop()
            except Exception:  # noqa: BLE001
                pass
        return health

    # ---------- 会话 ----------
    async def start(self, spec: dict[str, Any]) -> str:
        session_dir = spec.get("session_dir")
        argv = self._resolve_argv(self.executable) + ["--mode", "rpc"]
        if spec.get("no_session", True):
            argv.append("--no-session")
        if session_dir:
            argv += ["--session-dir", str(session_dir)]
        if spec.get("provider"):
            argv += ["--provider", str(spec["provider"])]
        if spec.get("model"):
            argv += ["--model", str(spec["model"])]
        client = PrimeJsonlClient(argv, env=spec.get("env"), cwd=spec.get("cwd"))
        await asyncio.wait_for(client.start(), timeout=30)
        sid = f"prime_{uuid.uuid4().hex[:8]}"
        self._clients[sid] = client
        return sid

    def _client(self, session_id: str) -> PrimeJsonlClient:
        client = self._clients.get(session_id)
        if not client:
            raise ProtocolError(f"Prime 会话不存在: {session_id}")
        return client

    async def prompt(self, session_id: str, text: str) -> ActionReceipt:
        try:
            resp = await self._client(session_id).command(
                "prompt", {"message": text}, timeout=30)
        except Exception as exc:  # noqa: BLE001
            return ActionReceipt(status="unknown", detail=str(exc)[:200])
        if resp.get("success"):
            return ActionReceipt(status="accepted",
                                 detail="prompt 已被接受/排队（success=true）")
        return ActionReceipt(status="rejected", detail=str(resp.get("error"))[:200])

    async def steer(self, session_id: str, text: str) -> ActionReceipt:
        try:
            resp = await self._client(session_id).command(
                "steer", {"message": text}, timeout=30)
        except Exception as exc:  # noqa: BLE001
            return ActionReceipt(status="unknown", detail=str(exc)[:200])
        if resp.get("success"):
            # 文档语义：排队，当前回合工具调用完成后交付；消费以
            # session_action_update / 后续事件为准，accepted 不等于已生效
            return ActionReceipt(status="accepted",
                                 detail="steer 已排队；以会话事件确认消费")
        return ActionReceipt(status="rejected", detail=str(resp.get("error"))[:200])

    async def abort(self, session_id: str) -> ActionReceipt:
        try:
            resp = await self._client(session_id).command("abort", timeout=30)
        except Exception as exc:  # noqa: BLE001
            return ActionReceipt(status="unknown", detail=str(exc)[:200])
        if resp.get("success"):
            return ActionReceipt(status="accepted",
                                 detail="abort 已受理；以 agent_end/isStreaming=false 确认")
        return ActionReceipt(status="rejected", detail=str(resp.get("error"))[:200])

    async def state(self, session_id: str) -> dict[str, Any]:
        try:
            resp = await self._client(session_id).command("get_state", timeout=30)
            if resp.get("success"):
                data = dict(resp.get("data") or {})
                data["status"] = "streaming" if data.get("isStreaming") else "idle"
                return data
            return {"status": "error", "error": str(resp.get("error"))[:200]}
        except Exception as exc:  # noqa: BLE001
            return {"status": "unknown", "error": str(exc)[:200]}

    async def stats(self, session_id: str) -> dict[str, Any]:
        resp = await self._client(session_id).command("get_session_stats", timeout=30)
        return dict(resp.get("data") or {}) if resp.get("success") else {}

    def events(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """归一化事件流：把上游 RPC 事件映射为控制器词汇。

        词汇契约（与 DemoPrime 一致）：trial.started / execution.progress /
        checkpoint.created / steer.consumed / trial.completed / run.aborted。
        """
        raw = self._client(session_id).events()
        client = self._client(session_id)

        async def normalize() -> AsyncIterator[dict[str, Any]]:
            async for ev in raw:
                etype = ev.get("type", "")
                if etype == "extension_ui_request":
                    # 权限/确认请求必须应答，否则代理悬挂；策略：拒绝并留痕
                    method = ev.get("method", "?")
                    try:
                        await client.respond_ui(ev["id"], cancelled=True)
                    except ProtocolError:
                        pass
                    yield {"type": "approval.rejected",
                           "detail": f"已按策略拒绝 {method}（不自动同意）"}
                    continue
                if etype == "agent_start":
                    yield {"type": "execution.progress",
                           "detail": "代理开始处理任务"}
                elif etype == "tool_execution_start":
                    yield {"type": "execution.progress",
                           "detail": f"工具执行: {ev.get('toolName', '?')}"}
                elif etype == "tool_execution_end":
                    result = ev.get("result", {}) or {}
                    content = result.get("content", [])
                    text = content[0].get("text", "") if content else ""
                    yield {"type": "execution.progress",
                           "detail": f"工具完成({ev.get('toolName', '?')}): "
                                     f"{str(text)[:200]}"}
                elif etype == "compaction_end":
                    yield {"type": "checkpoint.created",
                           "detail": "会话压缩（上下文 checkpoint）"}
                elif etype == "agent_end":
                    yield {"type": "trial.completed",
                           "detail": "代理回合完成（agent_end）"}
                elif etype == "auto_retry_start":
                    yield {"type": "execution.progress",
                           "detail": f"自动重试第 {ev.get('attempt')} 次"}
                # message_* 高频增量不映射，保留在原始协议日志
        return with_stall_watchdog(normalize(), self.stall_timeout)

    async def respond_ui(self, session_id: str, req_id: str, **fields: Any) -> None:
        await self._client(session_id).respond_ui(req_id, **fields)

    async def close(self, session_id: str) -> None:
        client = self._clients.pop(session_id, None)
        if client:
            await client.stop()
