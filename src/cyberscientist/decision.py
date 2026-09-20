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
                       allow_formal_submission: bool,
                       stalled_trial_id: str | None = None,
                       reported_trial_id: str | None = None) -> list[str]:
    errors: list[str] = []
    actions = decision.get("actions", [])
    if sum(1 for a in actions if a["op"] in DIRECTION_OPS) > 1:
        errors.append("同一 Decision 最多一个改变运行方向的主动作")
    for a in actions:
        op = a["op"]
        if op == "steer":
            # stalled Trial 保留会话与现场，正是需要大脑 steer 裁决的时刻；
            # reported_complete 等待验收时大脑也可 steer 追问（不改 Trial 状态）
            steerable = (
                has_active_trial and a.get("trial_id") == current_trial_id) or (
                stalled_trial_id is not None
                and a.get("trial_id") == stalled_trial_id) or (
                reported_trial_id is not None
                and a.get("trial_id") == reported_trial_id)
            if not steerable:
                if not has_active_trial and stalled_trial_id is None \
                        and reported_trial_id is None:
                    errors.append("steer 需要当前 Trial（活跃/待验收/停滞）")
                else:
                    errors.append("steer 的 trial_id 与当前 Trial 不符")
        if op == "start_trial" and has_active_trial:
            errors.append("已有活跃 Trial，不能同时 start_trial")
        if op == "request_submission" and not allow_formal_submission:
            errors.append("当前策略不允许正式提交（policy.allow_formal_submission=false）")
    return errors
