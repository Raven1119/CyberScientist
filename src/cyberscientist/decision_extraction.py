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
    """执行器提问的大脑回答：{"answers": {"q0": "..."}, "reason_md": "..."}。"""
    obj = _extract_json(text)
    if obj is None or not isinstance(obj.get("answers"), dict) \
            or not obj["answers"]:
        return None
    return {"answers": obj["answers"],
            "reason_md": str(obj.get("reason_md", ""))[:500]}
