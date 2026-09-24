"""从大脑最终消息中提取 Decision JSON（Codex/Kimi 共用）。"""
from __future__ import annotations

import json
import re
from typing import Any

DECISION_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any] | None:
    candidates = []
    fence = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))
    m = DECISION_RE.search(text)
    if m:
        candidates.append(m.group(0))
    candidates.append(text)
    for raw in candidates:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("schema_version") == 1:
            return obj
    return None


def extract_decision(text: str, packet: dict[str, Any]) -> dict[str, Any] | None:
    obj = _extract_json(text)
    if obj is None:
        return None
    obj.setdefault("run_id", packet.get("run_id", ""))
    return obj


def extract_review_result(text: str) -> dict[str, Any] | None:
    """静默/请求审阅的 ReviewResult JSON（契约见 collaboration/CONTRACTS）。"""
    obj = _extract_json(text)
    if obj is None or obj.get("message_type") != "review_result":
        return None
    return obj


def extract_question_answer(text: str) -> dict[str, Any] | None:
    """研究正文是主答案；旧 choices 输出仅作为可读的历史兼容。"""
    obj = _extract_json(text)
    if obj is None:
        return None
    if obj.get("message_type") == "research_answer":
        body = obj.get("answer_md")
        native = obj.get("native_answers")
        if not isinstance(body, str) or not body.strip() or len(body) > 12000:
            return None
        if native is not None and not isinstance(native, dict):
            return None
        refs = obj.get("evidence_refs", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            return None
        return {"schema_version": 1, "message_type": "research_answer",
                "request_id": obj.get("request_id"), "answer_md": body,
                "evidence_refs": refs, "native_answers": native}
    answers = obj.get("answers")
    if not isinstance(answers, dict) or not answers:
        return None
    reason = str(obj.get("reason_md", ""))
    return {"schema_version": 1, "message_type": "research_answer",
            "request_id": None, "answer_md": reason or json.dumps(answers, ensure_ascii=False),
            "evidence_refs": [], "native_answers": answers,
            "answers": answers, "reason_md": reason}
