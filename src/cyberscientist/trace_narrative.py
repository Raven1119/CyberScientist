"""Validate optional human-readable trace rows against durable Run evidence."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from . import arm_admission, db
from .observation import strip_secrets

MAX_BYTES = 1_000_000
MAX_ROWS = 1000
TEXT_FIELDS = ("title", "body", "code")


class InvalidTraceNarrative(ValueError):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons[:10]))


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _tool_ids(event: dict[str, Any]) -> set[str]:
    payload = event["payload"]
    ids = {str(payload[key]) for key in ("item_id", "tool_call_id", "operation_id")
           if isinstance(payload.get(key), (str, int))
           and not isinstance(payload[key], bool) and str(payload[key])}
    if event["type"].startswith("job."):
        ids.update("job:" + value for value in tuple(ids))
    if event["type"].startswith("sandbox."):
        ids.update("sandbox:" + value for value in tuple(ids))
    return ids


def _covers(row: dict[str, Any], projected: dict[str, Any]) -> bool:
    refs = row.get("cs_refs")
    if not isinstance(refs, list) or projected.get("cs_ref") not in refs:
        return False
    if row["step_type"] != projected.get("step_type"):
        return False
    if row["step_type"] in ("tool_call", "tool_result"):
        actual = str(projected.get("tool_call_id"))
        claimed = str(row.get("tool_call_id"))
        return claimed == actual or claimed == actual.removeprefix("job:").removeprefix("sandbox:")
    return True


def validate(raw: bytes, run_id: str, through_seq: int,
             package_files: Mapping[str, bytes],
             projected: list[dict[str, Any]],
             written_at: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (narrative rows, uncovered projection); raise with line reasons."""
    if len(raw) > MAX_BYTES:
        raise InvalidTraceNarrative([f"trace_narrative.jsonl 超过 {MAX_BYTES} 字节"])
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidTraceNarrative(["trace_narrative.jsonl 不是 UTF-8"]) from exc
    lines = [line for line in source.splitlines() if line.strip()]
    if not lines or len(lines) > MAX_ROWS:
        raise InvalidTraceNarrative([f"叙述步骤须为 1–{MAX_ROWS} 行"])
    events = {}
    for event in db.query("SELECT seq,recorded_at,type,payload FROM events"
                          " WHERE run_id=? AND seq<=?", (run_id, through_seq)):
        events[event["seq"]] = {"recorded_at": event["recorded_at"],
                                "type": event["type"],
                                "payload": json.loads(event["payload"])}
    ref_pattern = re.compile(rf"{re.escape(run_id)}#([1-9][0-9]*)\Z")
    writing_time = _time(written_at)
    rows: list[dict[str, Any]] = []
    reasons: list[str] = []
    for number, line in enumerate(lines, 1):
        prefix = f"第 {number} 行"
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            reasons.append(f"{prefix}: JSON 无法解析")
            continue
        if not isinstance(row, dict):
            reasons.append(f"{prefix}: 步骤必须是对象")
            continue
        unknown = set(row) - {"step_type", "title", "body", "code", "cs_refs",
                              "tool_call_id", "tool_output", "exit_code", "timestamp",
                              "annotation", "artifact_path", "sha256", "cost_usd"}
        if unknown:
            reasons.append(f"{prefix}: 不允许的字段：{', '.join(sorted(unknown))}")
        kind = row.get("step_type")
        if kind not in arm_admission.STEP_TYPES:
            reasons.append(f"{prefix}: step_type 不在七种类型内")
        refs = row.get("cs_refs")
        cited = []
        if not isinstance(refs, list) or not refs:
            reasons.append(f"{prefix}: cs_refs 至少需要一个本 Run 事件引用")
        else:
            for ref in refs:
                match = ref_pattern.fullmatch(ref) if isinstance(ref, str) else None
                event = events.get(int(match.group(1))) if match else None
                if event is None:
                    reasons.append(f"{prefix}: 引用不存在或超过封存截止序号：{str(ref)[:100]}")
                else:
                    cited.append(event)
        for field in TEXT_FIELDS:
            value = row.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > 12000):
                reasons.append(f"{prefix}: {field} 必须是有界文本")
            elif isinstance(value, str) and strip_secrets(value) != value:
                reasons.append(f"{prefix}: {field} 含受保护的密钥内容")
        if not any(isinstance(row.get(field), str) and row[field].strip()
                   for field in TEXT_FIELDS):
            reasons.append(f"{prefix}: title/body/code 至少一个须有内容")
        if kind in ("tool_call", "tool_result"):
            tool_id = row.get("tool_call_id")
            if not isinstance(tool_id, (str, int)) or isinstance(tool_id, bool) or not str(tool_id):
                reasons.append(f"{prefix}: tool_call_id 缺失或无效")
            elif not any(str(tool_id) in _tool_ids(event) for event in cited):
                reasons.append(f"{prefix}: tool_call_id 与引用事件不符")
            elif not any(_covers(row, step) for step in projected):
                reasons.append(f"{prefix}: 引用事件未记录相应的工具调用或结果")
        if "tool_output" in row:
            output = row["tool_output"]
            recorded = [event["payload"][key] for event in cited
                        for key in ("output", "tool_output", "stdout", "stderr")
                        if isinstance(event["payload"].get(key), str)]
            if (not isinstance(output, str) or
                    not any(output in value for value in recorded)):
                reasons.append(f"{prefix}: tool_output 不是引用事件输出的原文子串")
        if "exit_code" in row:
            value = row["exit_code"]
            if type(value) is not int or not any(value == event["payload"].get("exit_code")
                                                  for event in cited):
                reasons.append(f"{prefix}: exit_code 与引用事件不符")
        annotation = row.get("annotation", False)
        if type(annotation) is not bool:
            reasons.append(f"{prefix}: annotation 必须是布尔值")
        if annotation and kind in ("tool_call", "tool_result"):
            reasons.append(f"{prefix}: 事后注释不能充当工具调用或结果")
        stamp = _time(row.get("timestamp"))
        if stamp is None:
            reasons.append(f"{prefix}: timestamp 缺失或无效")
        elif annotation:
            if writing_time is None or abs((stamp - writing_time).total_seconds()) > 2:
                reasons.append(f"{prefix}: 事后注释时间须与叙述文件写作时间一致")
        elif not any(stamp == _time(event["recorded_at"]) for event in cited):
            reasons.append(f"{prefix}: timestamp 不是引用事件的记录时间")
        if "artifact_path" in row:
            path = row["artifact_path"]
            if (not isinstance(path, str) or path.startswith("/") or ".." in path.split("/")
                    or path not in package_files):
                reasons.append(f"{prefix}: artifact_path 不在提交包内")
            elif row.get("sha256") != hashlib.sha256(package_files[path]).hexdigest():
                reasons.append(f"{prefix}: artifact_path 的 sha256 不匹配")
        elif "sha256" in row:
            reasons.append(f"{prefix}: sha256 缺少 artifact_path")
        if "cost_usd" in row:
            cost = row["cost_usd"]
            if type(cost) not in (int, float) or not any(
                    cost == event["payload"].get("cost_usd") for event in cited):
                reasons.append(f"{prefix}: cost_usd 无引用事件中的真实费用")
        rows.append(row)
    if reasons:
        raise InvalidTraceNarrative(reasons)
    uncovered = [step for step in projected if not any(_covers(row, step) for row in rows)]
    return rows, uncovered
