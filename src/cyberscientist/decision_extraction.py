"""从大脑最终消息中提取 Decision JSON（Codex/Kimi 共用）。"""
from __future__ import annotations

import json
import re
from typing import Any

DECISION_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_decision(text: str, packet: dict[str, Any]) -> dict[str, Any] | None:
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
            obj.setdefault("run_id", packet.get("run_id", ""))
            return obj
    return None
