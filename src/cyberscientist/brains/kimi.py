"""Kimi Code 大脑：`kimi acp`（Agent Client Protocol, JSON-RPC 2.0 stdio）适配器。

事实修正：Kimi Code 2.0（TypeScript）已移除 `--wire`；当前程序化接入面为
`kimi acp`。协议面按官方 ACP 文档 + 实际版本探针实现：
- initialize 协商版本与能力
- session/new 建会话；session/load 恢复
- session/prompt 跑一个回合，session/update 流式推送 agent_message_chunk
- 反向 RPC session/request_permission 必须应答：默认拒绝并上报事件
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from typing import Any, AsyncIterator

from ..decision_extraction import extract_decision
from ..jsonrpc_stdio import JsonRpcStdio, ProtocolError
from .base import BrainEvent, RuntimeHealth, SessionRef

log = logging.getLogger("cyberscientist.brain.kimi")

ACP_PROTOCOL_VERSION = 1


def default_executable() -> str | None:
    for candidate in (
        os.environ.get("KIMI_EXECUTABLE"),
        shutil.which("kimi"),
        os.path.expanduser("~/AppData/Roaming/npm/kimi.cmd"),
    ):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


class KimiBrain:
    kind = "kimi"

    def __init__(self, executable: str | None = None, model: str | None = None,
                 effort: str | None = None):
        self.executable = executable or default_executable() or ""
        self.model = model
        self.effort = effort
        self.rpc: JsonRpcStdio | None = None
        self.server_version: str | None = None
        self.session_id: str | None = None
        self.capabilities: dict[str, bool] = {
            "resume_conversation": False,   # session/load 未实测
            "resume_kernel": False,
            "steer_delivery": False,        # ACP 无 steer；用 follow-up prompt 模拟
            "usage_reporting": False,       # update 里可能有 token 统计，未核实
        }

    # ---------- 进程管理 ----------
    def _argv(self, extra: list[str] | None = None) -> list[str]:
        exe = self.executable
        if not exe:
            raise RuntimeError("kimi 可执行文件不可用")
        if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
            argv: list[str] = ["cmd", "/c", exe]
        else:
            argv = [exe]
        return argv + (extra or [])

    async def _spawn(self, extra: list[str],
                     cwd: str | None = None) -> JsonRpcStdio:
        rpc = JsonRpcStdio(self._argv(extra), cwd=cwd, name="kimi-acp")
        await asyncio.wait_for(rpc.start(), timeout=30)
        return rpc

    async def _initialize(self, rpc: JsonRpcStdio) -> dict[str, Any]:
        """initialize 握手；不声明 fs/terminal 能力 → 引擎本地处理 IO。"""
        return await rpc.request(
            "initialize",
            {"protocolVersion": ACP_PROTOCOL_VERSION,
             "clientCapabilities": {"fs": {"readTextFile": False,
                                           "writeTextFile": False},
                                    "terminal": False}},
            timeout=30)

    # ---------- 探针 ----------
    async def inspect(self) -> RuntimeHealth:
        if not self.executable or not os.path.exists(self.executable):
            return RuntimeHealth(
                installed=False,
                detail=f"kimi 可执行文件不可用: {self.executable or '未安装'}",
                capabilities=dict(self.capabilities))
        health = RuntimeHealth(installed=True, capabilities=dict(self.capabilities))
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._argv(["--version"]),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            health.version = out.decode("utf-8", errors="replace").strip()[:120]
        except Exception as exc:  # noqa: BLE001
            health.detail = f"版本探针失败: {exc}"
            return health
        rpc: JsonRpcStdio | None = None
        try:
            rpc = await self._spawn(["acp"])
            result = await self._initialize(rpc)
            agent = result.get("agentInfo", {}) if isinstance(result, dict) else {}
            self.server_version = agent.get("version")
            caps = result.get("capabilities", {}) if isinstance(result, dict) else {}
            health.detail = (
                f"ACP initialize 成功（protocolVersion={result.get('protocolVersion')}），"
                f"agent={agent.get('name', '?')} {agent.get('version', '?')}，"
                "未发起模型调用")
            health.raw = {"initialize_result": {  # type: ignore[attr-defined]
                "protocolVersion": result.get("protocolVersion"),
                "agentInfo": agent,
                "capabilities": caps,
                "authMethods": result.get("authMethods")}}
        except Exception as exc:  # noqa: BLE001
            health.detail = f"ACP 握手失败: {exc.__class__.__name__}: {str(exc)[:200]}"
        finally:
            if rpc:
                try:
                    await rpc.stop()
                except Exception:  # noqa: BLE001
                    pass
        return health

    # ---------- 会话 ----------
    async def open(self, spec: dict[str, Any]) -> SessionRef:
        if not self.executable:
            raise RuntimeError("kimi 未安装或未配置")
        self.rpc = await self._spawn(["acp"], cwd=spec.get("working_directory"))
        try:
            await self._initialize(self.rpc)
            result = await self.rpc.request(
                "session/new",
                {"cwd": spec.get("working_directory") or os.getcwd(),
                 "mcpServers": []},
                timeout=30)
            self.session_id = result.get("sessionId")
            if not self.session_id:
                raise RuntimeError(f"session/new 未返回 sessionId: {result}")
            if self.model:
                try:
                    await self.rpc.request(
                        "session/set_model",
                        {"sessionId": self.session_id, "modelId": self.model},
                        timeout=15)
                except ProtocolError as exc:
                    log.warning("set_model 失败（沿用默认模型）: %s", exc)
            if self.effort:
                # ACP thinking 档位：low|high|max；UI 通用档映射
                mapped = {"low": "low", "medium": "high", "high": "high",
                          "xhigh": "max", "max": "max"}.get(self.effort,
                                                            self.effort)
                try:
                    await self.rpc.request(
                        "session/set_config_option",
                        {"sessionId": self.session_id, "configId": "thinking",
                         "value": mapped}, timeout=15)
                except ProtocolError as exc:
                    log.warning("set thinking=%s 失败（沿用默认）: %s", mapped, exc)
        except Exception:
            await self.rpc.stop()
            self.rpc = None
            raise
        return SessionRef(runtime="kimi", session_id=self.session_id,
                          raw={"model": self.model})

    async def review(self, session: SessionRef,
                     packet: dict[str, Any]) -> AsyncIterator[BrainEvent]:
        assert self.rpc is not None
        prompt_text = self._render_prompt(packet)
        notif_iter = self.rpc.notifications()
        final_text: list[str] = []
        error_msg: str | None = None

        async def watch_turn() -> None:
            try:
                async for msg in notif_iter:
                    if msg.get("method") != "session/update":
                        continue
                    update = msg.get("params", {}).get("update", {})
                    # 实测形状：{"sessionUpdate": "agent_message_chunk",
                    #            "content": {"type": "text", "text": "..."}}
                    if update.get("sessionUpdate") == "agent_message_chunk":
                        content = update.get("content", {})
                        if isinstance(content, dict):
                            final_text.append(content.get("text", ""))
                    # 思考/工具事件不透传浏览器，保留在原始协议日志
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                final_text.append(f"[事件流异常: {exc}]")

        watcher = asyncio.create_task(watch_turn())
        prompt_task = asyncio.create_task(
            self.rpc.request(
                "session/prompt",
                {"sessionId": session.session_id,
                 "prompt": [{"type": "text", "text": prompt_text}]},
                timeout=900))
        try:
            while not prompt_task.done():
                await asyncio.sleep(0.2)
                await self._answer_pending()
            result = prompt_task.result()
            stop = result.get("stopReason") if isinstance(result, dict) else None
            if stop and stop != "end_turn":
                error_msg = f"turn stopReason: {stop}"
        except (asyncio.TimeoutError, ProtocolError) as exc:
            error_msg = f"prompt 失败: {exc.__class__.__name__}: {str(exc)[:300]}"
        finally:
            watcher.cancel()
            async for ev in self._drain_requests():
                yield ev

        if error_msg:
            yield BrainEvent("error", {"message": error_msg})
            return
        # 流式 chunk 是增量片段，必须无缝拼接（不能用换行）
        joined = "".join(final_text)
        if os.environ.get("CS_DEBUG_BRAIN"):
            print(f"[kimi-brain raw {len(joined)} chars]: {joined[:800]}",
                  file=sys.stderr)
        decision = extract_decision(joined, packet)
        if joined.strip():
            yield BrainEvent("raw", {"text": joined})
        if decision is None:
            yield BrainEvent("error",
                             {"message": "最终消息中未找到合法 Decision JSON"})
            return
        yield BrainEvent("decision", {"decision": decision})

    async def _answer_pending(self) -> None:
        """循环内应答权限请求（不产出事件）。"""
        assert self.rpc is not None
        while True:
            req = await self.rpc.next_server_request(timeout=0.1)
            if req is None:
                return
            await self._respond(req)

    async def _drain_requests(self) -> AsyncIterator[BrainEvent]:
        """回合结束后应答滞留的反向 RPC 并产出事件。"""
        assert self.rpc is not None
        while True:
            req = await self.rpc.next_server_request(timeout=0.1)
            if req is None:
                return
            ev = await self._respond(req)
            if ev:
                yield ev

    async def _respond(self, req: dict[str, Any]) -> BrainEvent | None:
        assert self.rpc is not None
        params = req.get("params", {})
        if req.get("method") == "session/request_permission":
            tool = params.get("toolCall", {})
            ev = BrainEvent("approval_request", {
                "action": tool.get("title", ""),
                "description": str(tool.get("rawInput", ""))[:500],
                "policy": "默认不自动同意；已拒绝"})
            await self.rpc.respond(req["id"], result={
                "outcome": {"selected": ["reject_once"]}})
            return ev
        ev = BrainEvent("approval_request", {
            "method": req.get("method"),
            "detail": "该请求类型暂不支持，已拒绝"})
        await self.rpc.respond(
            req["id"], error={"code": -32601,
                              "message": "unsupported by policy"})
        return ev

    @staticmethod
    def _render_prompt(packet: dict[str, Any]) -> str:
        return (
            "你是 CyberScientist 的大脑，负责研究方向的判断，不直接执行工具。\n"
            "根据下面的 ReviewPacket 做出一次判断。只输出一个 JSON 代码块，不要输出其他文字，"
            "不要使用任何工具。\n\n"
            "Decision 结构（必须严格遵守，不得增删顶层字段）：\n"
            '{"schema_version":1,"decision_id":"任意唯一字符串",'
            '"run_id":"见 ReviewPacket","observed_state_version":见 ReviewPacket,'
            '"summary":"一句话判断","evidence_refs":["引用见 ReviewPacket 事件"],'
            '"actions":[{"op":"..."}],'
            '"experience_proposals":[]}\n'
            "actions 中每个元素只能是以下形状之一（1-3 个，最多一个主动作）：\n"
            '- {"op":"start_trial","goal":"...","success_check":"..."}\n'
            '- {"op":"steer","trial_id":"当前 Trial","message":"..."}\n'
            '- {"op":"wait","reason":"..."}\n'
            '- {"op":"pause","reason":"..."}\n'
            '- {"op":"refresh_platform","reason":"..."}\n'
            '- {"op":"request_submission","trial_id":"...","bundle_manifest_ref":"..."}\n'
            '- {"op":"promote_experience","experience_id":"...","revision_hash":"...",'
            '"reason":"...","evidence_refs":["..."]}\n'
            '- {"op":"finish","reason":"..."}\n\n'
            f"ReviewPacket:\n```json\n{json.dumps(packet, ensure_ascii=False)}\n```"
        )

    async def cancel(self, session: SessionRef) -> dict[str, Any]:
        if not self.rpc or not self.session_id:
            return {"status": "rejected", "detail": "无活动会话"}
        try:
            await self.rpc.request(
                "session/cancel", {"sessionId": self.session_id}, timeout=15)
            return {"status": "accepted",
                    "detail": "已发送 session/cancel；以 prompt 终态为准"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "unknown", "detail": str(exc)[:200]}

    async def close(self, session: SessionRef) -> None:
        if self.rpc:
            try:
                if self.session_id:
                    await self.rpc.request(
                        "session/close", {"sessionId": self.session_id},
                        timeout=10)
            except Exception:  # noqa: BLE001
                pass
            await self.rpc.stop()
            self.rpc = None
