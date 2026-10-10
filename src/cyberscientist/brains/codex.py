"""Codex BrainRuntime：codex app-server stdio JSON-RPC 适配器。

只实现探针核实的协议面；未知通知/请求类型记录后跳过或明确拒绝。
审批请求一律上报事件并以“不支持”应答，不做无边界自动同意。
"""
from __future__ import annotations
from .. import features

import asyncio
import glob
import json
import logging
import os
import re
from typing import Any, AsyncIterator

from .. import model_providers
from ..jsonrpc_stdio import JsonRpcStdio, ProtocolError
from ..codex_protocol import (CLIENT_INFO, deny_requests, initialize, open_thread,
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
                 effort: str | None = None, provider: str | None = None,fast_mode: bool | None = None):
        self.executable = executable or default_executable() or ""
        self.model = model
        self.effort = effort
        self.provider = provider
        self.fast_mode = fast_mode
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
        rpc = None
        try:
            rpc = JsonRpcStdio([self.executable, "app-server"],
                               env=model_providers.prepare(self.provider, native_brain_environment()),
                               name="codex-app-server")
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
                if rpc is not None:
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
                        if k in ("CS_TOOL_TOKEN", "CS_TOOL_ROLE", "CS_API_URL", 'CS_PUBLIC_RESEARCH_PROBE', 'CS_PUBLIC_PROBE_RECEIPTS')})
        from .. import model_providers
        env = model_providers.prepare(self.provider, env)
        self.rpc = JsonRpcStdio([self.executable, "app-server"],
                                env=env,
                                cwd=spec.get("working_directory"),
                                name="codex-app-server")
        try:
            await self.rpc.start()
            await initialize(self.rpc)
            params = thread_params(spec, self.model, self.effort, writable=False)
            model_providers.thread_provider(params, self.provider)
            from .. import codex_fast
            fast=await codex_fast.prepare(self.rpc,params,self.model,self.provider,spec.get('fast_mode',self.fast_mode))
            result,fast = await codex_fast.open_negotiated(self.rpc,params,fast,spec.get("resume_thread_id"))
            model_providers.verify_provider(result, self.provider)
            verify_thread_config(result, self.model, self.effort)
            fast=codex_fast.confirmed(fast,result);codex_fast.record(fast)
            if fast['requested'] is not None and self.provider in (None,'codex'): await codex_fast.observe_rates(self.rpc)
            if spec.get('run_id'):
                from .. import ops_digest
                ops_digest.record_session(spec['run_id'],spec.get('ops_role','brain'),result['thread']['id'],
                                          {'model':result.get('model'),'provider':result.get('modelProvider'),
                                           'reasoning_effort':result.get('reasoningEffort'),'fast_mode':fast})
        except BaseException:
            await self.rpc.stop()
            self.rpc = None
            raise
        self._requests_task = asyncio.create_task(deny_requests(
            self.rpc, self._approval_events.put))
        thread = result.get("thread", result)
        return SessionRef(runtime="codex", session_id=thread["id"],
                          raw={"thread": thread, "model": result.get("model"), "provider": result.get("modelProvider"),
                               "reasoning_effort": result.get("reasoningEffort"),'fast_mode':fast})

    async def review(self, session: SessionRef,
                     packet: dict[str, Any]) -> AsyncIterator[BrainEvent]:
        from .. import structured_output
        async for event in structured_output.review(self, session, packet):
            yield event

    async def _review_once(self, session: SessionRef,
                     packet: dict[str, Any]) -> AsyncIterator[BrainEvent]:
        assert self.rpc is not None
        from .. import structured_output
        prompt = structured_output.feedback_prompt(self._render_prompt(packet), packet)
        turn_params: dict[str, Any] = {
            "threadId": session.session_id,
            "input": [{"type": "text", "text": prompt}],
        }
        if self.effort:
            turn_params["effort"] = self.effort
        from .. import model_fallback
        rate_choice = {'runtime': 'codex', 'provider': self.provider or 'codex', 'model_id': self.model}
        rate_ticket = model_fallback.ticket(rate_choice)
        try:
            result = await self.rpc.request("turn/start", turn_params, timeout=30)
        except (asyncio.TimeoutError, ProtocolError, OSError) as exc:
            try:
                rejection = json.loads(str(exc))
            except (ValueError, TypeError):
                rejection = None
            # Standard JSON-RPC parse/method/parameter rejections are explicit
            # refusals. A timeout or transport error after sending is unknown.
            refused = isinstance(rejection, dict) and rejection.get('code') in (-32700, -32600, -32601, -32602)
            yield BrainEvent('error', {'message': str(exc) or 'turn/start回执超时，是否启动未知',
                'code': 'NATIVE_REQUEST_REJECTED' if refused else 'NATIVE_TURN_UNKNOWN'})
            return
        turn = result.get("turn", {})
        turn_id = turn.get("id")
        self._turn_id = turn_id
        final_text: list[str] = []
        error_msg: str | None = None
        unknown_turn = False
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
                            "item_type": itype, "command": item.get("command") if itype == "commandExecution" else None,
                        })
                    elif itype == "error":
                        error_msg = item.get("message", "未知错误")
                    # Private reasoning is not a public progress channel.
                elif method == "thread/tokenUsage/updated":
                    yield BrainEvent("usage", {"usage": params.get("tokenUsage"),
                                              "session_id": session.session_id})
                elif method == "turn/completed":
                    t = params.get("turn", {})
                    if t.get("id") == turn_id or not turn_id:
                        status = t.get("status")
                        if status != "completed":
                            error_msg = error_msg or str(t.get("error") or f"turn 终态: {status}")
                        break
                elif method == "error":
                    from .. import model_fallback, model_providers
                    native_error = params.get("error") or params.get("message") or "协议错误"
                    choice = {'runtime': 'codex', 'provider': self.provider or 'codex', 'model_id': self.model}
                    model_providers.record_throttle(choice, native_error, request_id='native:' + session.session_id)
                    if params.get('willRetry'):
                        model_fallback.note(choice, native_error, will_retry=True, request_id='native:' + session.session_id)
                        yield BrainEvent('progress', {'detail': '原生错误仍由CLI重试', 'will_retry': True})
                    if not params.get("willRetry"):
                        error_msg = str(params.get("error") or params.get("message") or "协议错误")
                # 未知通知：跳过但记录
        except (asyncio.TimeoutError, ProtocolError, OSError, StopAsyncIteration) as exc:
            error_msg = f"等待 turn 终态失败: {exc}"
            unknown_turn = True
        finally:
            self._turn_id = None
        while not self._approval_events.empty():
            yield BrainEvent("approval_request", self._approval_events.get_nowait())

        if error_msg:
            yield BrainEvent("error", {"message": error_msg, "code": 'NATIVE_TURN_UNKNOWN' if unknown_turn else 'NATIVE_FAILURE'})
            return
        from .. import model_fallback
        model_fallback.recovered(rate_choice, request_id='native:' + session.session_id, started_generation=rate_ticket)
        joined = "\n".join(final_text)
        yield structured_output.parse(joined, packet)

    @staticmethod
    def _render_prompt(packet: dict[str, Any]) -> str:
        if packet.get("protocol") == "role_task":
            from ..role_tasks import prompt
            return prompt(packet)
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
                "紧急指导：停止用kind=stop；改向用intent=change_direction/reframe；提交前要求交付用intent=deliver_before_submit。三类直接插入当前回合，普通补充用nudge并排队；送达仍须ACK。\n"
                "ReviewResult 结构（必须严格遵守）：\n"
                '{"schema_version":1,"message_type":"review_result",'
                '"frame_id":"见 ObservationFrame","disposition":"silent|intervene",'
                '"private_note_md":"...","watchlist":[],"guidance":null}\n'
                "watchlist 按研究需要列出，每项必须是对象："
                '{"id":"短标识","hypothesis_md":"假设","evidence_needed_md":"需要什么证据",'
                '"intervene_when_md":"何时介入","evidence_refs":[]}\n'
                "没有观察项就输出空数组 []；禁止输出字符串数组。\n"
                "guidance 非空时结构："
                '{"kind":"nudge|steer|stop|submit","intent":"continue|observe|reframe|change_direction|deliver_before_submit",'
                '"text_md":"...","reason_md":"...","evidence_refs":[],'
                '"expected_change_md":"...","revisit_when_md":"..."}\n'
                "kind=submit：结果包已可提交时发出；仅在已有 Run 授权、提交预算"
                "和去重检查通过后，系统自动用实验邮箱提交（不投递给执行器），"
                "随后异步等待评分；不扩大正式提交授权。\n"
                "提交前可用 research_review_package(trial_id,operation_id,package_path) 调用全新只读审查者；问题清单是建议，PI 决定修复或在 submit guidance.text_md 写明理由后照常提交。\n"
                "可用 research_shared(action=list) 查看本题追加式共享区与正式验证器版本；共享内容仍需执行器核验，不能自行修改验证器。\n"
                "已确认出分后可用 research_trace_variant(source_submission_id,operation_id,prediction_md,narrative_jsonl) 直接发起叙述变体；科学产物不变、消耗原提交额度，必须写预测，所有引用限原封存 cutoff；未知不重发。\n"
                "若 ObservationFrame.submission_prediction_version=1，submit guidance 可附 prediction_md，"
                "说明本次改动和预计 displayScore/harbor_score/trace_score 哪些分量如何变化；"
                "未提供则预测记为 unknown，不阻止已授权提交。可选 prediction_verdicts=[{submission_id,verdict:confirmed|refuted|unclear,note_md}]"
                "评判帧中的已确认预测，证据不清时用 unclear。\n"
                + ("只输出一个 JSON 代码块；可按需使用 research_trace 或 platform_scores，零读取可直接判断。\n\n"
                 if optional_read else "只输出一个 JSON 代码块，不使用工具。\n\n")
                + f"ObservationFrame:\n```json\n"
                f"{json.dumps(packet, ensure_ascii=False)}\n```"
            )
        return (
            "你是 CyberScientist 的大脑，负责研究方向的判断。\n"
            + features.science_instruction() +
            "研究简报之前先读user_prompt，标为用户建议；有证据时可不采纳并说明理由。收到用户更新时先读diff_md。"
            "以当前用户目标、Run 意图与授权为准。持续提出可检验假设并用真实证据迭代，"
            "不把满分或耗尽预算设为默认停止前提。若用户目标是观察系统闭环，"
            "在真实提交、评分反馈与经验提取完成且观察充分后可以 finish，"
            "明确停止依据和仍未知的事项。遇到阻塞先换一条已授权路线；仅额度边界或所有已授权渠道均用尽才暂停。\n"
            + (
                "干净复跑用 start_trial.fresh_executor_session=true，并提供clean_handoff={method_md,parameters_md,validation_md,pitfalls_md}。交接可以包含方法与计算设置（网格、步长、截断、收敛阈值、随机种子、超参数、镜像等）及其选择依据；不得包含探索得到的结果数值（最终答案、拟合系数、指标值、物理量等）。不得包含代码。新线程不resume。科学分完整版本可直接提交，回执未到时可继续工作，轨迹提示仅参考。\n"
                "本次 trigger=run_start：先核对输入中的官方题面、资源路径和评分约束。选择方法和环境前先查能力索引；research_brief 必填selected_capabilities=[能力ID]。读取 research_startup 同题策略卡索引与公开分布，正文用research_experience按需读取，输出 research_brief；开启初始方法审批时还须method_proposal={method_md,parameters_md,basis_md,outputs_md,capabilities:[能力ID]}，批准前不计算；方法大改时写major_change=true及major_change_reason_md。research_brief（problem_md/science_md/ranked_methods=[{name,reason_md}]/traps_md/parallel_preparation={contract,verifier,environment}/acceptance_md（评分在查什么：逐条摘出题面评分检查项；没有说明写未说明；内部精度目标必须对应检查项））。有environment_choice_contract时必须在research_brief内写environment_choice={mode:catalog,entry_id:目录ID,reason_md:依据}或{mode:from_zero,reason_md:依据}。目录只是起点，执行器先恢复并实际冒烟，失败换条目或从零搭建，可换基础镜像和安装依赖，运行中不保存版本。准备契约、验证器、环境并行。guidance.level 为 concrete_work_package 时在 research_brief 内写 work_package={algorithm_md,formula_md,parameter_ranges_md,expected_intermediate_md,test_cases_md,stop_conditions_md} 并派发具体 Trial；强模型收到目标/约束/验收。里程碑按验证器输出纠正科学假设与数值。"
                + ("需要补证时可按需读取已登记的公开轨迹；缺项记录 unknown，"
                 if optional_read else
                 "需要补证时使用已开放的只读工具；网络失败记录 unknown，")
                + "根据已有证据启动不依赖该缺项的有界 Trial。首个 Trial 写清待检验假设、"
                "资源试算、产物及停止条件；不以确认满分可达为启动条件。"
                "每项判断标明已读来源，外部指导单独归因。按同题策略卡索引读取相关正文后选择有区别的路线；research_brief 写 route_md/difference_md/advice_md/failed_routes=[{route_md,evidence_refs}]，开局和里程碑都更新，后端自动补正式分。用 research_experience 随时读取最新修订。\n"
                if packet.get("trigger") == "run_start" else
                ("必要时使用 research_trace 或 platform_scores 按需读取；公开分数分布可辅助路线排序；如实标注其来源、口径和 unknown。\n"
                 if optional_read else "不要使用任何工具。\n")
            ) +
            "根据下面的 ReviewPacket 做出一次判断。只输出一个 JSON 代码块，不要输出其他文字。\n\n"
            "Decision 结构（严格遵守；v2 待处理意图可增加指定条件字段）：\n"
            f'{{"schema_version":{2 if packet.get("lifecycle_version") == 2 else 1},"decision_id":"任意唯一字符串",'
            '"run_id":"见 ReviewPacket","observed_state_version":见 ReviewPacket,'
            '"summary":"一句话判断","evidence_refs":["引用见 ReviewPacket 事件"],'
            '"actions":[{"op":"..."}],"experience_proposals":[]}\n'
            "actions 中每个元素只能是以下形状之一（最多一个改变运行方向的主动作）：\n"
            '- {"op":"start_trial","goal":"...","success_check":"..."}\n'
            '- {"op":"steer","trial_id":"当前 Trial","message":"..."}\n'
            '- {"op":"wait","reason":"...","duration_seconds":1800}（时长可省略，最长由设置限制）\n'
            '- {"op":"pause","reason":"..."}\n'
            '- {"op":"promote_experience","experience_id":"...","revision_hash":"...",'
            '"reason":"...","evidence_refs":["..."]}（仅题内；全局由用户审批，勿用）\n'
            + ('- {"op":"finish","reason":"...","objective_assessment":{"status":"achieved|partial|not_achievable|stopped","evidence_refs":[],"remaining_md":"..."}}\n'
               '若 ReviewPacket 有 pending_intent，顶层必须给 pending_intent_resolution=replay|revise|drop；replay 重放原动作。\n'
               if packet.get("lifecycle_version") == 2 else '- {"op":"finish","reason":"..."}\n')
            + "最终评分未知或退步只作可见事实；PI 可修复或如实结束，并可选在 finish 中增加 "
            "finish_confirmation={token:反馈中的 confirmation_token,reason_md:明确确认原因}。\n"
            "旧 request_submission 会被明确拒绝：bundle_manifest_ref 尚无冻结包解析契约。"
            "提交建议仅在 requested/shadow 的 ReviewResult 中用 guidance.kind=submit，"
            "经现有授权、预算和去重检查执行实验邮箱提交；不扩大正式提交授权。"
            "不要在当前 Decision 中混入 ReviewResult。\n"
            "可选 prediction_verdicts=[{submission_id,verdict:confirmed|refuted|unclear,note_md}]，"
            "依据已确认评分判断帧中的预测。\n"
            "experience_proposals 每项：scope/challenge_id/title/body_md/applicability/"
            "evidence_refs 必填；可选 target_id（更新已有条目，先读库再决定新建/"
            "更新/不变，同主题勿重复新建）与 kind（仅限 "
            "heuristic/procedure/failure/platform/strategy 五值，勿自创）。"
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
