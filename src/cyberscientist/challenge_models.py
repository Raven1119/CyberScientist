"""Per-challenge model selection. Only non-secret runtime choices are stored."""
from __future__ import annotations

import json
from typing import Any


RUNTIMES = {"brain": {"codex", "kimi"},
            "executor": {"codex", "kimi", "prime"}}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def choose(role: str, supplied: dict[str, Any] | None,
           settings: dict[str, Any]) -> dict[str, str]:
    """Validate user-editable choices without accepting credentials or paths."""
    if role not in RUNTIMES:
        raise ValueError("未知模型角色")
    source = supplied if supplied is not None else settings[role]
    if not isinstance(source, dict):
        raise ValueError(f"{role} 模型配置必须为对象")
    runtime = source.get("runtime")
    model = source.get("model_id")
    effort = source.get("reasoning_effort")
    if role == "executor" and runtime == "prime" and supplied is None:
        profile_id = (settings.get("prime") or {}).get("llm_profile_id")
        profile = next((p for p in settings.get("llm_profiles", [])
                        if p.get("id") == profile_id), None)
        if profile:
            model = profile.get("model_id")
    if runtime not in RUNTIMES[role]:
        raise ValueError(f"{role} 运行时不受支持")
    if not isinstance(model, str) or not model.strip() or len(model) > 200:
        raise ValueError(f"{role} 模型 ID 必须是非空字符串")
    if effort not in EFFORTS:
        raise ValueError(f"{role} 思考强度不受支持")
    if role == "executor" and runtime == "prime" and supplied is not None:
        profile_id = (settings.get("prime") or {}).get("llm_profile_id")
        profile = next((p for p in settings.get("llm_profiles", [])
                        if p.get("id") == profile_id), None)
        if not profile or profile.get("model_id") != model.strip():
            raise ValueError("Prime 模型 ID 必须与当前 Prime Profile 的模型一致")
    return {"runtime": runtime, "model_id": model.strip(),
            "reasoning_effort": effort}


def from_challenge(row: Any, settings: dict[str, Any]) -> dict[str, dict[str, str]]:
    result = {}
    for role in ("brain", "executor"):
        raw = row[f"{role}_config_json"]
        value = json.loads(raw) if raw else None
        result[role] = choose(role, value, settings)
    return result
