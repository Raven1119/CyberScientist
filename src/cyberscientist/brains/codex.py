"""Codex BrainRuntime：codex app-server stdio JSON-RPC 适配器。

只实现探针核实的协议面；未知通知/请求类型记录后跳过或明确拒绝。
审批请求一律上报事件并以“不支持”应答，不做无边界自动同意。
"""
from __future__ import annotations

import asyncio
import glob
import json
import logging
import os
import re
from typing import Any, AsyncIterator

from ..decision_extraction import extract_decision
from ..jsonrpc_stdio import JsonRpcStdio, ProtocolError
from .base import BrainEvent, RuntimeHealth, SessionRef

log = logging.getLogger("cyberscientist.brain.codex")

CLIENT_INFO = {"name": "cyberscientist", "version": "0.1.0"}


def default_executable() -> str | None:
    for candidate in (
        os.environ.get("CODEX_EXECUTABLE"),
        _which("codex"),
        os.path.expanduser("~/.codex/.sandbox-bin/codex.exe"),
        *sorted(glob.glob(os.path.expanduser(
            "~/AppData/Local/OpenAI/Codex/bin/*/codex.exe"))),
    ):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


class CodexBrain:
    kind = "codex"

    def __init__(self, executable: str | None = None, model: str | None = None,
                 effort: str | None = None):
        self.executable = executable or default_executable() or ""
        self.model = model
        self.effort = effort
        self.rpc: JsonRpcStdio | None = None
        self.server_version: str | None = None
        self.capabilities: dict[str, bool] = {
            "resume_conversation": False,   # 未实测，保守
            "resume_kernel": False,
            "steer_delivery": False,
            "usage_reporting": False,
        }

    async def inspect(self) -> RuntimeHealth:
        if not self.executable or not os.path.exists(self.executable):
            return RuntimeHealth(installed=False,
                                 detail=f"codex 可执行文件不可用: {self.executable or '未配置'}")
        health = RuntimeHealth(installed=True, capabilities=dict(self.capabilities))
        # 真实握手探针：initialize，零模型调用
        rpc = JsonRpcStdio([self.executable, "app-server"], name="codex-app-server")
        try:
            await asyncio.wait_for(rpc.start(), 15)
            result = await rpc.request(
                "initialize", {"clientInfo": CLIENT_INFO, "capabilities": {}},
                timeout=30)
            info = result if isinstance(result, dict) else {}
            # 实测 0.154：initialize 返回 userAgent/codexHome/platformFamily，
            # 无 serverInfo 字段；版本取自 userAgent。
            ua = info.get("userAgent", "")
            m = re.search(r"/(\d+\.\S+?) ", ua)
            health.version = (m.group(1) if m else None)
            # 握手不验证登录态：身份可用性保持未知，不谎报已登录
            health.authenticated = None
            health.detail = "app-server 握手成功（initialize），未发起模型调用；" \
                            f" codexHome={info.get('codexHome', '?')}；" \
                            "登录态未由握手验证（需登录状态探针）"
            health.raw = {"initialize_result": info}  # type: ignore[attr-defined]
            self.server_version = health.version
        except Exception as exc:  # noqa: BLE001 — 探针要如实报告任何失败
            health.authenticated = None
            health.detail = f"握手失败: {exc.__class__.__name__}: {str(exc)[:200]}"
        finally:
            try:
                await rpc.stop()
            except Exception:  # noqa: BLE001
                pass
        return health

    async def open(self, spec: dict[str, Any]) -> SessionRef:
        if not self.executable:
            raise RuntimeError("codex 未安装或未配置")
        self.rpc = JsonRpcStdio([self.executable, "app-server"],
                                cwd=spec.get("working_directory"),
                                name="codex-app-server")
        await self.rpc.start()
        await self.rpc.request("initialize",
                               {"clientInfo": CLIENT_INFO, "capabilities": {}},
                               timeout=30)
        params: dict[str, Any] = {
            "approvalPolicy": "never",       # 大脑只读证据 + 输出 Decision
            "sandboxPolicy": {"type": "readOnly"},
        }
        if self.model:
            params["model"] = self.model
        if self.effort:
            params["effort"] = self.effort
        if spec.get("instructions"):
            params["userInstructions"] = spec["instructions"]
        try:
            result = await self.rpc.request("thread/start", params, timeout=30)
        except ProtocolError:
            # 旧版本 thread/start 不支持 effort：降级重试一次
            if "effort" not in params:
                raise
            params.pop("effort")
            result = await self.rpc.request("thread/start", params, timeout=30)
        thread = result.get("thread", result)
        return SessionRef(runtime="codex", session_id=thread["id"],
                          raw={"thread": thread})

    async def review(self, session: SessionRef,
                     packet: dict[str, Any]) -> AsyncIterator[BrainEvent]:
        assert self.rpc is not None
        prompt = self._render_prompt(packet)
        result = await self.rpc.request("turn/start", {
            "threadId": session.session_id,
            "input": [{"type": "text", "text": prompt}],
        }, timeout=30)
        turn = result.get("turn", {})
        turn_id = turn.get("id")
        final_text: list[str] = []
        error_msg: str | None = None
        notif_iter = self.rpc.notifications()
        try:
            while True:
                msg = await asyncio.wait_for(notif_iter.__anext__(), timeout=600)
                method, params = msg.get("method"), msg.get("params", {})
                if method == "item/completed":
                    item = params.get("item", {})
                    itype = item.get("type")
                    if itype == "agent_message":
                        text = item.get("text", "")
                        final_text.append(text)
                        yield BrainEvent("message", {"text": text})
                    elif itype == "reasoning":
                        yield BrainEvent("token", {"text": item.get("text", "")[:2000]})
                    elif itype == "error":
                        error_msg = item.get("message", "未知错误")
                    # 其他 item 类型保留在原始协议日志，不透传浏览器
                elif method == "turn/completed":
                    t = params.get("turn", {})
                    if t.get("id") == turn_id or not turn_id:
                        status = t.get("status")
                        if status != "completed":
                            error_msg = error_msg or f"turn 终态: {status}"
                        break
                elif method == "error":
                    error_msg = params.get("message", "协议错误")
                # 未知通知：跳过但记录
        except (asyncio.TimeoutError, ProtocolError) as exc:
            error_msg = f"等待 turn 终态失败: {exc}"
        # 审批/服务器请求：明确拒绝，不悬挂
        while True:
            req = await self.rpc.next_server_request(timeout=0.1)
            if req is None:
                break
            yield BrainEvent("approval_request",
                             {"method": req.get("method"),
                              "detail": "该请求类型暂不支持自动处理，已拒绝"})
            await self.rpc.respond(req["id"],
                                   error={"code": -32601,
                                          "message": "unsupported by cyberscientist policy"})

        if error_msg:
            yield BrainEvent("error", {"message": error_msg})
            return
        decision = extract_decision("\n".join(final_text), packet)
        if decision is None:
            yield BrainEvent("error",
                             {"message": "最终消息中未找到合法 Decision JSON"})
            return
        yield BrainEvent("decision", {"decision": decision})

    @staticmethod
    def _render_prompt(packet: dict[str, Any]) -> str:
        return (
            "你是 CyberScientist 的大脑，负责研究方向的判断，不直接执行工具。\n"
            "根据下面的 ReviewPacket 做出一次判断。只输出一个 JSON 代码块，不要输出其他文字。\n\n"
            "Decision 结构（必须严格遵守，不得增删顶层字段）：\n"
            '{"schema_version":1,"decision_id":"任意唯一字符串",'
            '"run_id":"见 ReviewPacket","observed_state_version":见 ReviewPacket,'
            '"summary":"一句话判断","evidence_refs":["引用见 ReviewPacket 事件"],'
            '"actions":[{"op":"..."}],"experience_proposals":[]}\n'
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
        if not self.rpc:
            return {"status": "rejected", "detail": "无活动会话"}
        try:
            await self.rpc.request(
                "turn/interrupt", {"threadId": session.session_id}, timeout=10)
            return {"status": "accepted",
                    "detail": "已发送 turn/interrupt；生效以 turn/completed 为准"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "unknown", "detail": str(exc)[:200]}

    async def close(self, session: SessionRef) -> None:
        if self.rpc:
            await self.rpc.stop()
            self.rpc = None
