"""Per-challenge model selection. Only non-secret runtime choices are stored."""
from __future__ import annotations

import json
from typing import Any


RUNTIMES = {"brain": {"codex", "kimi"},
            "executor": {"codex", "kimi", "prime"},
            "reviewer": {"codex", "kimi"}, "post_review": {"codex", "kimi"}}
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
    provider = source.get("provider", runtime)
    if provider not in {"codex", "deepseek", "kimi", "prime"} or (provider == "deepseek" and runtime != "codex") or (provider != "deepseek" and provider != runtime):
        raise ValueError("提供方与原生运行时不匹配")
    if provider == "deepseek" and effort not in {"low", "high", "max"}:
        raise ValueError("DeepSeek 思考强度须为 low/high/max")
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
    result = {"runtime": runtime, "model_id": model.strip(),
              "reasoning_effort": effort}
    result['provider'] = provider
    if 'note' in source:
        if not isinstance(source['note'], str) or len(source['note']) > 2000:
            raise ValueError('求解者备注必须是最多 2000 字的文本')
        from . import config
        from .bohr_proxy import redact
        if redact(source['note'], config.sensitive_values()) != source['note']:
            raise ValueError('求解者备注不能包含密钥')
        result['note'] = source['note']
    return result


def from_challenge(row: Any, settings: dict[str, Any]) -> dict[str, dict[str, str]]:
    result = {}
    for role in ("brain", "executor"):
        raw = row[f"{role}_config_json"]
        value = json.loads(raw) if raw else None
        result[role] = choose(role, value, settings)
    return result


def roster(settings: dict) -> list[dict]:
    values = settings.get('solver_roster', [])
    if not isinstance(values, list) or len(values) > 50:
        raise ValueError('求解者条目须为最多50项的列表')
    result = []
    seen = set()
    for item in values:
        ident, name = item.get('id'), item.get('name')
        if not isinstance(ident, str) or not ident or ident in seen or len(ident) > 100:
            raise ValueError('求解者 ID 必须非空且唯一')
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError('求解者名称必须非空且最多200字')
        choice = choose('executor', item, settings)
        from .observation import strip_secrets
        if strip_secrets(name) != name or strip_secrets(ident) != ident:
            raise ValueError('求解者名称/ID不能包含密钥')
        seen.add(ident)
        result.append({'id': ident, 'name': name, **choice})
    return result

def solver(ident: str, settings: dict) -> dict:
    for item in roster(settings):
        if item['id'] == ident:
            return item
    raise ValueError('求解者条目不存在')
