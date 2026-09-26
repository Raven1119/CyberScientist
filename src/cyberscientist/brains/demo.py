"""Demo 大脑：产生 schema 合法的脚本化 Decision，驱动离线垂直切片。

Demo 输出只覆盖 UI/状态机测试，不作为真实联调证据。
"""
from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

from .base import BrainEvent, RuntimeHealth, SessionRef


class DemoBrain:
    kind = "demo"

    async def inspect(self) -> RuntimeHealth:
        return RuntimeHealth(
            installed=True, authenticated=None,
            detail="演示大脑：脚本化 Decision，不调用任何模型",
            version="demo-0.1")

    async def open(self, spec: dict[str, Any]) -> SessionRef:
        return SessionRef(runtime="demo", session_id=f"demo_brain_{uuid.uuid4().hex[:8]}")

    async def review(self, session: SessionRef,
                     packet: dict[str, Any]) -> AsyncIterator[BrainEvent]:
        if packet.get("protocol") == "executor_question":
            yield BrainEvent("question_answer", {
                "schema_version": 1, "message_type": "research_answer",
                "request_id": packet.get("request_id"),
                "answer_md": "演示回答：先核对已保存证据，再决定后续研究方向。",
                "evidence_refs": [], "native_answers": None})
            return
        if packet.get("protocol") == "experience_curation":
            yield BrainEvent("curation_result", {"result": {
                "schema_version": 1, "message_type": "curation_result",
                "summary": "演示整理完成，没有生成科学经验。", "experience_proposals": []}})
            return
        yield BrainEvent("token", {"text": "[demo] 审阅证据…"})
        trigger = packet.get("trigger", "run_start")
        n_trials = packet.get("trial_count", 0)
        decision: dict[str, Any] = {
            "schema_version": 2 if packet.get("lifecycle_version") == 2 else 1,
            "decision_id": f"dec_{uuid.uuid4().hex[:10]}",
            "run_id": packet.get("run_id", ""),
            "observed_state_version": packet.get("state_version", 0),
            "summary": "",
            "evidence_refs": ["demo://challenge/DEMO_CHALLENGE"],
            "actions": [],
            "experience_proposals": [],
        }
        if trigger == "user_steer" or packet.get("user_guidance"):
            decision["summary"] = "收到人工指导：调整当前 Trial 方向（演示）。"
            decision["actions"] = [{"op": "steer",
                                    "trial_id": packet.get("current_trial_id", ""),
                                    "message": packet.get("user_guidance",
                                                          "按指导调整（演示）")}]
        elif n_trials == 0:
            decision["summary"] = "尚无 Trial：先启动一轮最小验证（演示）。"
            decision["actions"] = [{
                "op": "start_trial",
                "goal": "验证 执行器→产物→证据 链路可恢复（演示）",
                "success_check": "checkpoint 记录产物清单与 hash（演示）"}]
        elif packet.get("latest_trial_status") == "done":
            decision["summary"] = "一轮已完成：积累演示经验并结束（演示）。"
            decision["actions"] = [{"op": "finish", "reason": "演示闭环完成"}]
            if packet.get("lifecycle_version") == 2:
                decision["actions"][0]["objective_assessment"] = {
                    "status": "partial", "evidence_refs": [], "remaining_md": "演示不证明科学目标"}
            decision["experience_proposals"] = [{
                "scope": "challenge", "challenge_id": packet.get("challenge_id"),
                "title": "演示：链路自检先于科学计算",
                "body_md": "任何题目先验证执行链路与证据留痕，再投入算力。（演示经验）",
                "applicability": "演示题目，不适用真实竞赛",
                "evidence_refs": ["demo://trial/latest"]}]
        else:
            decision["summary"] = "等待当前 Trial 产出新证据（演示）。"
            decision["actions"] = [{"op": "wait", "reason": "尚无新证据"}]
        yield BrainEvent("decision", {"decision": decision})

    async def cancel(self, session: SessionRef) -> dict[str, Any]:
        return {"status": "confirmed", "detail": "演示大脑已停止"}

    async def close(self, session: SessionRef) -> None:
        return None
