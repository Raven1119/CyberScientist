"""Offline ARM trace admission estimate. Never treats an estimate as platform scoring."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

STEP_TYPES = frozenset({"thought", "tool_call", "tool_result", "artifact",
                        "decision", "error", "observation"})
SIGNALS = ("log_anchor", "artifact_path", "paired_tool_calls", "declared_cost",
           "timeline", "substance")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _trace_rows(archive: zipfile.ZipFile) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    readable = True
    for name in archive.namelist():
        if not (name == "trace/trace.jsonl" or
                (name.startswith("traces/") and name.endswith(".jsonl"))):
            continue
        raw = archive.read(name).decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
            items = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            items = []
            for line in raw.splitlines():
                if line.strip():
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        readable = False
        rows.extend(item for item in items if isinstance(item, dict))
    return rows, readable


def _signal(ok: bool | None, detail: str, evidence: Any = None) -> dict[str, Any]:
    return {"ok": ok, "detail": detail, "evidence": evidence}


def check(bundle_bytes: bytes, protocol: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate documented signals on exactly the bytes about to be frozen.

    ``None`` in a signal means unavailable protocol context, never false evidence.
    The completeness value is explicitly only a local estimate.
    """
    protocol_hash = hashlib.sha256(json.dumps(protocol or {}, sort_keys=True,
                                                separators=(",", ":")).encode()).hexdigest()
    result: dict[str, Any] = {
        "verdict": "indeterminate", "protocol_sha256": protocol_hash,
        "signals": {name: _signal(None, "not evaluated") for name in SIGNALS},
        "typed_steps": 0, "step_types": [],
        "modalities": {"execution": False, "characterization": False, "trace": False},
        "manifest_errors": [], "completeness_estimate": {"kind": "local_estimate", "value": 0.0},
        "notes": [],
    }
    if not protocol or not protocol.get("fetched_at") or not protocol.get("source_sha256"):
        result["notes"].append("protocol snapshot missing or unverified")
        return result
    try:
        with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as archive:
            names = set(archive.namelist())
            if "arm_manifest.json" not in names:
                result["manifest_errors"].append("arm_manifest.json missing")
                result["verdict"] = "blocked"
                return result
            manifest = json.loads(archive.read("arm_manifest.json"))
            if str(manifest.get("arm_version")) not in ("1.0", "1.1"):
                result["notes"].append("unsupported arm_version")
                return result
            rows, readable = _trace_rows(archive)
            if not readable:
                result["notes"].append("trace could not be read in full")
                return result
            typed = [row for row in rows if row.get("step_type") in STEP_TYPES]
            kinds = {row["step_type"] for row in typed}
            result["typed_steps"] = len(typed)
            result["step_types"] = sorted(kinds)
            modalities = result["modalities"]
            execution = manifest.get("execution") or {}
            modalities["execution"] = (isinstance(execution, dict)
                and isinstance(manifest.get("entrypoint"), str)
                and manifest["entrypoint"] in names
                and isinstance(execution.get("log_path"), str)
                and execution["log_path"] in names)
            char = manifest.get("characterization") or {}
            modalities["characterization"] = "characterization.json" in names
            modalities["trace"] = bool(rows)
            result["completeness_estimate"]["value"] = round(sum(modalities.values()) / 3, 3)

            artifacts = [r["artifact_path"] for r in typed
                         if r["step_type"] == "artifact" and
                         isinstance(r.get("artifact_path"), str) and r["artifact_path"] in names]
            result["signals"]["artifact_path"] = _signal(bool(artifacts),
                "artifact step references an existing bundle member", artifacts[:5])
            def call_id(row):
                value = row.get("tool_call_id")
                return (type(value).__name__, value) if (
                    (isinstance(value, str) and bool(value)) or
                    (type(value) is int)) else None
            calls = {value for r in typed if r["step_type"] == "tool_call"
                     if (value := call_id(r)) is not None}
            pairs = calls & {value for r in typed if r["step_type"] == "tool_result"
                             if (value := call_id(r)) is not None}
            result["signals"]["paired_tool_calls"] = _signal(bool(pairs),
                "real call and result share tool_call_id", [v for _, v in sorted(pairs, key=str)[:5]])
            substance = sum(len(str(r.get(k) or "")) for r in typed for k in ("title", "body", "code"))
            admission = protocol.get("trace_anti_fraud", {}).get("admission", {})
            thresholds = admission.get("thresholds", {})
            min_chars = int(thresholds.get("substance_narrative_chars", 30))
            result["signals"]["substance"] = _signal(
                len(typed) >= int(thresholds.get("substance_typed_steps", 2))
                and len(kinds) >= int(thresholds.get("substance_distinct_step_types", 2))
                and substance >= min_chars,
                f"{len(typed)} typed steps; {len(kinds)} types; {substance} chars")
            costs = [r.get("cost_usd") for r in typed if type(r.get("cost_usd")) in (int, float)]
            result["signals"]["declared_cost"] = _signal(
                sum(costs) >= float(thresholds.get("declared_cost_usd", 0.01)),
                "declared cost only; absent costs are not zero", len(costs))
            log_path = execution.get("log_path")
            anchored = False
            if isinstance(log_path, str) and log_path in names:
                log = archive.read(log_path).decode("utf-8", "replace")
                for row in typed:
                    for key in ("body", "title", "tool_output"):
                        for line in str(row.get(key) or "").splitlines():
                            sample = line.strip()[:80]
                            if len(sample) >= 12 and sample in log:
                                anchored = True
                                break
                        if anchored: break
                    if anchored: break
            result["signals"]["log_anchor"] = _signal(anchored,
                "typed step text appears in the declared execution log")
            ran_at = _parse_time(execution.get("ran_at") or manifest.get("ran_at"))
            wall = execution.get("wall_time_s")
            if ran_at and type(wall) in (int, float) and wall >= 0:
                slack = timedelta(seconds=max(2 * wall, 600))
                timestamps = {_parse_time(r.get("timestamp")) for r in typed}
                timestamps.discard(None)
                valid = [t for t in timestamps if ran_at - slack <= t <= ran_at + timedelta(seconds=wall) + slack]
                result["signals"]["timeline"] = _signal(len(valid) >= int(thresholds.get("timeline_distinct_timestamps", 2)),
                    f"{len(valid)} distinct timestamps inside declared execution window")
            else:
                result["signals"]["timeline"] = _signal(None,
                    "ran_at or wall_time_s unavailable; timeline not inferred")
            true_signals = sum(s["ok"] is True for s in result["signals"].values())
            unknown_signals = sum(s["ok"] is None for s in result["signals"].values())
            required = int(admission.get("signals_required", 1))
            if true_signals >= required and all(modalities.values()):
                result["verdict"] = "admitted"
            elif true_signals + unknown_signals >= required:
                result["verdict"] = "indeterminate"
            else:
                result["verdict"] = "blocked"
            if not all(modalities.values()):
                result["manifest_errors"].append("required modality missing")
                if result["verdict"] == "admitted": result["verdict"] = "blocked"
    except (zipfile.BadZipFile, ValueError, KeyError, TypeError) as exc:
        result["manifest_errors"].append(type(exc).__name__)
        result["verdict"] = "blocked"
    return result
