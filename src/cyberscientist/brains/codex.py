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

from ..decision_extraction import (extract_decision, extract_question_answer,
                                   extract_review_result)
from ..jsonrpc_stdio import JsonRpcStdio, ProtocolError
from ..codex_protocol import (CLIENT_INFO, deny_requests, initialize,
                              native_brain_environment, thread_params,
                              verify_thread_config)
from .base import BrainEvent, RuntimeHealth, SessionRef

log = logging.getLogger("cyberscientist.brain.codex")

def default_executable() -> str | None:
    for candidate in (
        os.environ.get("CODEX_EXECUTABLE"),
        _which("codex"),
        os.path.expanduser("~/.local/bin/codex"),
        os.path.expanduser("~/.codex/.sandbox-bin/codex.exe"),
        *sorted(glob.glob(os.path.expanduser(
            "~/AppData/Local/OpenAI/Codex/bin/*/codex.exe"))),
    ):
        if candidate and os.path.exists(candidate) and (
                os.name == "nt" or not candidate.lower().endswith(".exe")):
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
        self._turn_id: str | None = None
        self._requests_task: asyncio.Task | None = None
        self._approval_events: asyncio.Queue = asyncio.Queue()
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
        rpc = JsonRpcStdio([self.executable, "app-server"],
                           env=native_brain_environment(), name="codex-app-server")
        try:
            await asyncio.wait_for(rpc.start(), 15)
            result = await initialize(rpc)
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
        env = native_brain_environment()
        if spec.get("mcp_servers"):
            env.update({k: v for k, v in (spec.get("env") or {}).items()
                        if k in ("CS_TOOL_TOKEN", "CS_TOOL_ROLE", "CS_API_URL")})
        self.rpc = JsonRpcStdio([self.executable, "app-server"],
                                env=env,
                                cwd=spec.get("working_directory"),
                                name="codex-app-server")
        try:
            await self.rpc.start()
            await initialize(self.rpc)
            result = await self.rpc.request("thread/start", thread_params(
                spec, self.model, self.effort, writable=False), timeout=60)
            verify_thread_config(result, self.model, self.effort)
        except BaseException:
            await self.rpc.stop()
            self.rpc = None
            raise
        self._requests_task = asyncio.create_task(deny_requests(
            self.rpc, self._approval_events.put))
        thread = result.get("thread", result)
        return SessionRef(runtime="codex", session_id=thread["id"],
                          raw={"thread": thread, "model": result.get("model"),
                               "reasoning_effort": result.get("reasoningEffort")})

    async def review(self, session: SessionRef,
                     packet: dict[str, Any]) -> AsyncIterator[BrainEvent]:
        assert self.rpc is not None
        prompt = self._render_prompt(packet)
        turn_params: dict[str, Any] = {
            "threadId": session.session_id,
            "input": [{"type": "text", "text": prompt}],
        }
        if self.effort:
            turn_params["effort"] = self.effort
        result = await self.rpc.request("turn/start", turn_params, timeout=30)
        turn = result.get("turn", {})
        turn_id = turn.get("id")
        self._turn_id = turn_id
        final_text: list[str] = []
        error_msg: str | None = None
        notif_iter = self.rpc.notifications()
        try:
            while True:
                msg = await asyncio.wait_for(notif_iter.__anext__(), timeout=600)
                method, params = msg.get("method"), msg.get("params", {})
                if params.get("threadId", session.session_id) != session.session_id:
                    continue
                while not self._approval_events.empty():
                    yield BrainEvent("approval_request", self._approval_events.get_nowait())
                if method in ("item/started", "item/completed"):
                    item = params.get("item", {})
                    itype = item.get("type")
                    completed = method == "item/completed"
                    if itype in ("agentMessage", "agent_message") and completed:
                        text = item.get("text", "")
                        if item.get("phase") == "commentary":
                            yield BrainEvent("progress", {
                                "detail": text, "item_id": item.get("id")})
                        else:
                            final_text.append(text)
                            yield BrainEvent("message", {"text": text})
                    elif itype in ("commandExecution", "fileChange", "mcpToolCall", "webSearch"):
                        label = (item.get("command") or item.get("query") or
                                 item.get("tool") or str(item.get("changes") or ""))
                        output = item.get("aggregatedOutput") or ""
                        if itype == "mcpToolCall":
                            output = json.dumps(item.get("result") or item.get("error") or {},
                                                ensure_ascii=False)
                        yield BrainEvent("progress", {
                            "detail": f"{itype} {'完成' if completed else '开始'}: {label[:2000]}",
                            "status": item.get("status"), "exit_code": item.get("exitCode"),
                            "output": output[-12000:], "item_id": item.get("id"),
                        })
                    elif itype == "error":
                        error_msg = item.get("message", "未知错误")
                    # Private reasoning is not a public progress channel.
                elif method == "thread/tokenUsage/updated":
                    yield BrainEvent("usage", {"usage": params.get("tokenUsage")})
                elif method == "turn/completed":
                    t = params.get("turn", {})
                    if t.get("id") == turn_id or not turn_id:
                        status = t.get("status")
                        if status != "completed":
                            error_msg = error_msg or str(t.get("error") or f"turn 终态: {status}")
                        break
                elif method == "error":
                    if not params.get("willRetry"):
                        error_msg = str(params.get("error") or params.get("message") or "协议错误")
                # 未知通知：跳过但记录
        except (asyncio.TimeoutError, ProtocolError) as exc:
            error_msg = f"等待 turn 终态失败: {exc}"
        finally:
            self._turn_id = None
        while not self._approval_events.empty():
            yield BrainEvent("approval_request", self._approval_events.get_nowait())

        if error_msg:
            yield BrainEvent("error", {"message": error_msg})
            return
        joined = "\n".join(final_text)
        if packet.get("protocol") == "experience_curation":
            from ..curation import extract
            result = extract(joined)
            if result is None:
                yield BrainEvent("error", {"message": "最终消息中未找到合法 CurationResult JSON"})
            else:
                yield BrainEvent("curation_result", {"result": result})
            return
        if packet.get("protocol") == "review_result":
            result = extract_review_result(joined)
            if result is None:
                yield BrainEvent("error", {
                    "message": "最终消息中未找到合法 ReviewResult JSON"})
                return
            yield BrainEvent("review_result", {"result": result})
            return
        if packet.get("protocol") == "executor_question":
            answer = extract_question_answer(joined)
            if answer is None:
                yield BrainEvent("error", {
                    "message": "最终消息中未找到合法回答 JSON"})
                return
            yield BrainEvent("question_answer", answer)
            return
        decision = extract_decision(joined, packet)
        if decision is None:
            yield BrainEvent("error",
                             {"message": "最终消息中未找到合法 Decision JSON"})
            return
        yield BrainEvent("decision", {"decision": decision})

    @staticmethod
    def _render_prompt(packet: dict[str, Any]) -> str:
        optional_read = packet.get("sparse_brain_version") == 1
        if packet.get("protocol") == "experience_curation":
            from ..curation import prompt
            return prompt(packet)
        if packet.get("protocol") == "executor_question":
            from .kimi import _question_prompt
            return _question_prompt(packet)
        if packet.get("protocol") == "review_result":
            from .kimi import _brain_instruction
            return (
                _brain_instruction() + "\n\n"
                "ReviewResult 结构（必须严格遵守）：\n"
                '{"schema_version":1,"message_type":"review_result",'
                '"frame_id":"见 ObservationFrame","disposition":"silent|intervene",'
                '"private_note_md":"...","watchlist":[],"guidance":null}\n'
                "watchlist 最多 3 项，每项必须是对象："
                '{"id":"短标识","hypothesis_md":"假设","evidence_needed_md":"需要什么证据",'
                '"intervene_when_md":"何时介入","evidence_refs":[]}\n'
                "没有观察项就输出空数组 []；禁止输出字符串数组。\n"
                "guidance 非空时结构："
                '{"kind":"nudge|steer|stop|submit","intent":"continue|observe|reframe",'
                '"text_md":"...","reason_md":"...","evidence_refs":[],'
                '"expected_change_md":"...","revisit_when_md":"..."}\n'
                "kind=submit：结果包已可提交时发出；仅在已有 Run 授权、提交预算"
                "和去重检查通过后，系统自动用实验邮箱提交（不投递给执行器），"
                "随后异步等待评分；不扩大正式提交授权。\n"
                + ("只输出一个 JSON 代码块；可按需使用 research_trace，零读取可直接判断。\n\n"
                 if optional_read else "只输出一个 JSON 代码块，不使用工具。\n\n")
                + f"ObservationFrame:\n```json\n"
                f"{json.dumps(packet, ensure_ascii=False)}\n```"
            )
        return (
            "你是 CyberScientist 的大脑，负责研究方向的判断。\n"
            "以当前用户目标、Run 意图与授权为准。持续提出可检验假设并用真实证据迭代，"
            "不把满分或耗尽预算设为默认停止前提。若用户目标是观察系统闭环，"
            "在真实提交、评分反馈与经验提取完成且观察充分后可以 finish，"
            "明确停止依据和仍未知的事项。pause 用于必须等用户才能推进的抉择。\n"
            + (
                "本次 trigger=run_start：先核对输入中的官方题面、资源路径和评分约束。"
                + ("需要补证时可按需读取已登记的公开轨迹；缺项记录 unknown，"
                 if optional_read else
                 "需要补证时使用已开放的只读工具；网络失败记录 unknown，")
                + "根据已有证据启动不依赖该缺项的有界 Trial。首个 Trial 写清待检验假设、"
                "资源试算、产物及停止条件；不以确认满分可达为启动条件。"
                "每项判断标明已读来源，外部指导单独归因。\n"
                if packet.get("trigger") == "run_start" else
                ("必要时仅使用 research_trace 按需读取；不要求先读后答。\n"
                 if optional_read else "不要使用任何工具。\n")
            ) +
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
            '- {"op":"promote_experience","experience_id":"...","revision_hash":"...",'
            '"reason":"...","evidence_refs":["..."]}（仅题内；全局由用户审批，勿用）\n'
            '- {"op":"finish","reason":"..."}\n'
            "旧 request_submission 会被明确拒绝：bundle_manifest_ref 尚无冻结包解析契约。"
            "提交建议仅在 requested/shadow 的 ReviewResult 中用 guidance.kind=submit，"
            "经现有授权、预算和去重检查执行实验邮箱提交；不扩大正式提交授权。"
            "不要在当前 Decision 中混入 ReviewResult。\n"
            "experience_proposals 每项：scope/challenge_id/title/body_md/applicability/"
            "evidence_refs 必填；可选 target_id（更新已有条目，先读库再决定新建/"
            "更新/不变，同主题勿重复新建）与 kind（仅限 "
            "heuristic/procedure/failure/platform 四值，勿自创）。"
            "题内提议直接生效为 active；全局提议落 candidate 待用户审批。\n\n"
            f"ReviewPacket:\n```json\n{json.dumps(packet, ensure_ascii=False)}\n```"
        )

    async def cancel(self, session: SessionRef) -> dict[str, Any]:
        if not self.rpc or not self._turn_id:
            return {"status": "rejected", "detail": "无活动会话"}
        try:
            await self.rpc.request(
                "turn/interrupt", {"threadId": session.session_id,
                                   "turnId": self._turn_id}, timeout=10)
            return {"status": "accepted",
                    "detail": "已发送 turn/interrupt；生效以 turn/completed 为准"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "unknown", "detail": str(exc)[:200]}

    async def close(self, session: SessionRef) -> None:
        if self._requests_task:
            self._requests_task.cancel()
            await asyncio.gather(self._requests_task, return_exceptions=True)
            self._requests_task = None
        if self.rpc:
            await self.rpc.stop()
            self.rpc = None
