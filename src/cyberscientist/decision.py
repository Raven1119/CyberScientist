"""Decision 校验：contracts/decision.schema.json 结构 + 后端语义校验。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "decision.schema.json"


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


_SCHEMA = None


def validate_structure(decision: dict[str, Any]) -> list[str]:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = load_schema()
    try:
        jsonschema.validate(decision, _SCHEMA)
        return []
    except jsonschema.ValidationError as exc:
        return [f"{'.'.join(str(p) for p in exc.absolute_path) or '(root)'}: {exc.message}"]


DIRECTION_OPS = {"start_trial", "request_submission", "finish"}


def validate_semantics(decision: dict[str, Any], *,
                       has_active_trial: bool,
                       current_trial_id: str | None,
                       allow_formal_submission: bool) -> list[str]:
    errors: list[str] = []
    actions = decision.get("actions", [])
    if sum(1 for a in actions if a["op"] in DIRECTION_OPS) > 1:
        errors.append("同一 Decision 最多一个改变运行方向的主动作")
    for a in actions:
        op = a["op"]
        if op == "steer":
            if not has_active_trial:
                errors.append("steer 需要活跃 Trial")
            elif a.get("trial_id") != current_trial_id:
                errors.append("steer 的 trial_id 与当前 Trial 不符")
        if op == "start_trial" and has_active_trial:
            errors.append("已有活跃 Trial，不能同时 start_trial")
        if op == "request_submission" and not allow_formal_submission:
            errors.append("当前策略不允许正式提交（policy.allow_formal_submission=false）")
    return errors
