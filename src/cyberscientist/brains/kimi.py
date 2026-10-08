"""Kimi Code 大脑：`kimi acp`（Agent Client Protocol, JSON-RPC 2.0 stdio）适配器。

事实修正：Kimi Code 2.0（TypeScript）已移除 `--wire`；当前程序化接入面为
`kimi acp`。协议面按官方 ACP 文档 + 实际版本探针实现：
- initialize 协商版本与能力
- session/new 建会话；session/load 恢复
- session/prompt 跑一个回合，session/update 流式推送 agent_message_chunk
- 反向 RPC session/request_permission 必须应答：默认拒绝并上报事件
"""
from __future__ import annotations
from .. import features

import asyncio
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, AsyncIterator

from ..jsonrpc_stdio import JsonRpcStdio, ProtocolError
from .base import BrainEvent, RuntimeHealth, SessionRef

log = logging.getLogger("cyberscientist.brain.kimi")

ACP_PROTOCOL_VERSION = 1

_BRAIN_PROMPT_PATH = (Path(__file__).resolve().parent.parent.parent.parent
                      / "prompts" / "collaboration" / "brain.md")


def _brain_instruction() -> str:
    try:
        return features.render_science_policy(_BRAIN_PROMPT_PATH.read_text(encoding="utf-8").strip())
    except OSError:
        return ""


def _question_prompt(packet: dict[str, Any]) -> str:
    """Codex/Kimi share the same open research-answer contract."""
    if packet.get("sparse_brain_version") != 1:
        return (
            _brain_instruction() + '\n\n' +
            "你是 CyberScientist 大脑；从下列原生问题选项中回答。"
            "只输出 JSON："
            '{"schema_version":1,"answers":{"<问题id>":"<选项 const>"},'
            '"reason_md":"完整理由"}\n'
            f"上下文与问题:\n```json\n{json.dumps(packet, ensure_ascii=False)}\n```")
    return (
        _brain_instruction() + "\n\n"
        "执行器提出了一个研究问题。它给出的选项仅供参考，你可以同意、否定前提、"
        "给出第三条路线或保留未知。保持独立研究判断，无须刻意反对。"
        "已有高层研究状态与用户约束在输入中。确有需要时可自行调用 research_trace"
        " 查看本次审阅范围内的公开记录，或调用 platform_scores 查看匿名分布；"
        "分布只作参考，零读取也可以直接回答。不运行 Shell。\n"
        "只输出一个 JSON 代码块，不要输出其他文字：\n"
        '{"schema_version":1,"message_type":"research_answer",'
        '"request_id":"与输入相同","answer_md":"完整研究判断",'
        '"evidence_refs":[],"native_answers":null}\n'
        "如确实选择了原表单选项，可将原题 id 到合法值放入 native_answers；"
        "无法无损表示时保持 null。完整判断始终写入 answer_md。\n\n"
        f"上下文与问题:\n```json\n{json.dumps(packet, ensure_ascii=False)}\n```"
    )


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
                     cwd: str | None = None,
                     spec_env: dict[str, str] | None = None) -> JsonRpcStdio:
        from ..codex_protocol import NATIVE_BRAIN_SHELL_ENV_KEYS
        allowed = (*NATIVE_BRAIN_SHELL_ENV_KEYS, 'KIMI_API_KEY', 'MOONSHOT_API_KEY')
        env = {k: os.environ[k] for k in allowed if k in os.environ}
        if spec_env:
            env.update({k: v for k, v in spec_env.items()
                        if k in ("CS_TOOL_TOKEN", "CS_TOOL_ROLE", "CS_API_URL")})
        rpc = JsonRpcStdio(self._argv(extra), cwd=cwd, env=env, name="kimi-acp")
        try:
            await asyncio.wait_for(rpc.start(), timeout=30)
        except BaseException:
            await rpc.stop()
            raise
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
        self.rpc = await self._spawn(["acp"], cwd=spec.get("working_directory"),
                                     spec_env=spec.get("env"))
        try:
            await self._initialize(self.rpc)
            result = await self.rpc.request(
                "session/new",
                {"cwd": spec.get("working_directory") or os.getcwd(),
                 "mcpServers": spec.get("mcp_servers") or []},
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
                    raise RuntimeError(f"所选 Kimi 模型不可用：{self.model}") from exc
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
        from .. import structured_output
        async for event in structured_output.review(self, session, packet):
            yield event

    async def _review_once(self, session: SessionRef,
                     packet: dict[str, Any]) -> AsyncIterator[BrainEvent]:
        assert self.rpc is not None
        from .. import structured_output
        prompt_text = structured_output.feedback_prompt(self._render_prompt(packet), packet)
        notif_iter = self.rpc.notifications()
        final_text: list[str] = []
        error_msg: str | None = None
        unknown_turn = False

        async def watch_turn() -> None:
            nonlocal error_msg, unknown_turn
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
                error_msg = f"事件流异常: {exc}"
                unknown_turn = True

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
        except (asyncio.TimeoutError, ProtocolError, OSError) as exc:
            error_msg = f"prompt 失败: {exc.__class__.__name__}: {str(exc)[:300]}"
            unknown_turn = True
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            async for ev in self._drain_requests():
                yield ev

        if error_msg:
            yield BrainEvent("error", {"message": error_msg, "code": 'NATIVE_TURN_UNKNOWN' if unknown_turn else 'NATIVE_FAILURE'})
            return
        # 流式 chunk 是增量片段，必须无缝拼接（不能用换行）
        joined = "".join(final_text)
        if os.environ.get("CS_DEBUG_BRAIN"):
            print(f"[kimi-brain raw {len(joined)} chars]: {joined[:800]}",
                  file=sys.stderr)
        if joined.strip():
            yield BrainEvent("raw", {"text": joined})
        yield structured_output.parse(joined, packet)

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
        if packet.get('protocol') == 'role_task':
            from ..role_tasks import prompt
            return prompt(packet)
        if packet.get("protocol") == "experience_curation":
            from ..curation import prompt
            return prompt(packet)
        if packet.get("protocol") == "executor_question":
            return _question_prompt(packet)
        if packet.get("protocol") == "review_result":
            return (
                _brain_instruction() + "\n\n"
                "ReviewResult 结构（必须严格遵守）：\n"
                '{"schema_version":1,"message_type":"review_result",'
                '"frame_id":"见 ObservationFrame","disposition":"silent|intervene",'
                '"private_note_md":"...","watchlist":[],"guidance":null}\n'
                "watchlist 按研究需要列出，每项必须是对象："
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
                "提交前可用 research_review_package(trial_id,operation_id,package_path) 调用全新只读审查者；问题清单是建议，PI 决定修复或在 submit guidance.text_md 写明理由后照常提交。\n"
                "若 ObservationFrame.submission_prediction_version=1，submit guidance 可附 prediction_md，"
                "说明本次改动和预计 displayScore/harbor_score/trace_score 哪些分量如何变化；"
                "未提供则预测记为 unknown，不阻止已授权提交。可选 prediction_verdicts=[{submission_id,verdict:confirmed|refuted|unclear,note_md}]"
                "评判帧中的已确认预测，证据不清时用 unclear。\n"
                + ("只输出一个 JSON 代码块；可按需使用 research_trace 或 platform_scores，零读取可直接判断。\n\n"
                 if packet.get("sparse_brain_version") == 1 else
                 "只输出一个 JSON 代码块，不使用工具。\n\n")
                + f"ObservationFrame:\n```json\n"
                f"{json.dumps(packet, ensure_ascii=False)}\n```"
            )
        return (
            "你是 CyberScientist 的大脑，负责研究方向的判断。\n"
            "目标与停止条件以本 Run 的用户指导和 authorization.note 为准。"
            "在授权范围内主动检验假设；用户要求实验闭环时，完成提交、反馈和经验整理即可收尾，"
            "不擅自增加必须满分的条件。finish 必须说明已完成的目标、证据和未解决项。"
            "遇到阻塞先尝试其他已授权路线；额度或全部渠道均耗尽时才暂停。\n"
            + (
                features.science_instruction() +
                "干净复跑用 start_trial.fresh_executor_session=true，并提供clean_handoff={method_md,parameters_md,pitfalls_md}；不含代码或探索产出数值，参数只含题面/确定输入。新线程不resume。科学分完整版本可直接提交，回执未到时可继续工作，轨迹提示仅参考。\n"
                "本次 trigger=run_start：先核对输入中的官方题面、资源路径和评分约束。读取 research_startup 全部同题策略卡与公开分布，输出 research_brief；开启初始方法审批时还须method_proposal={method_md,parameters_md,basis_md,outputs_md,capabilities:[能力ID]}，批准前不计算；方法大改时写major_change=true及major_change_reason_md。research_brief（problem_md/science_md/ranked_methods=[{name,reason_md}]/traps_md/parallel_preparation={contract,verifier,environment}/acceptance_md）。准备契约、验证器、环境并行。guidance.level 为 concrete_work_package 时再写 work_package={algorithm_md,formula_md,parameter_ranges_md,expected_intermediate_md,test_cases_md,stop_conditions_md} 并派发具体 Trial；强模型收到目标/约束/验收。里程碑按验证器输出纠正科学假设与数值。"
                "需要补证时使用已开放的只读工具；网络失败记录 unknown，"
                "根据已有证据启动不依赖该缺项的有界 Trial。首个 Trial 写清待检验假设、"
                "资源试算、产物及停止条件；不以确认满分可达为启动条件。"
                "每项判断标明已读来源，外部指导单独归因。通读全部同题策略卡后选择有区别的路线；research_brief 写 route_md/difference_md/advice_md/failed_routes=[{route_md,evidence_refs}]，开局和里程碑都更新，后端自动补正式分。用 research_experience 随时读取最新修订。\n"
                if packet.get("trigger") == "run_start" else
                "必要时可使用 research_trace 或 platform_scores；公开分布可辅助路线排序；保留来源、口径和 unknown。\n"
            ) +
            "根据下面的 ReviewPacket 做出一次判断。只输出一个 JSON 代码块，不要输出其他文字。\n\n"
            "Decision 结构（严格遵守；v2 待处理意图可增加指定条件字段）：\n"
            f'{{"schema_version":{2 if packet.get("lifecycle_version") == 2 else 1},"decision_id":"任意唯一字符串",'
            '"run_id":"见 ReviewPacket","observed_state_version":见 ReviewPacket,'
            '"summary":"一句话判断","evidence_refs":["引用见 ReviewPacket 事件"],'
            '"actions":[{"op":"..."}],'
            '"experience_proposals":[]}\n'
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
