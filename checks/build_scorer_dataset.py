"""Rebuild the private CS-UP-03R dataset from hashed, ignored read-only receipts."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import statistics
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from cyberscientist import config, trace_selection

TRACE_TYPES = ("thought", "decision", "tool_call", "tool_result",
               "observation", "error", "artifact")
STAGES = {
    "setup": ("setup", "install", "environment", "配置", "环境", "安装"),
    "validation": ("validat", "verif", "test", "assert", "核验", "验证", "测试"),
    "computation": ("comput", "calculat", "simulat", "运行", "计算", "求解"),
    "analysis": ("analy", "inspect", "diagnos", "分析", "检查", "诊断"),
    "comparison": ("compar", "baseline", "benchmark", "对比", "比较", "基线"),
}
GENERIC_FIELDS = frozenset({"packaging", "executability", "output_coverage",
                             "result_fidelity", "trace_quality"})


def _verified_bytes(root: Path, relative: str, sha: str) -> bytes:
    path = root / relative
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError(f"raw hash mismatch: {relative}")
    return raw


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def classify(detail: dict[str, Any], challenge: dict[str, Any]) -> tuple[str, str]:
    """Return (observed scoring mode, round position), preserving ambiguity."""
    created = _instant(detail.get("createdAt"))
    start = _instant(challenge.get("roundStartAt"))
    end = _instant(challenge.get("roundEndAt"))
    position = ("unknown" if not created or not start or not end else
                "before" if created < start else "after" if created > end else "inside")
    card = detail.get("scorecard") or {}
    if not isinstance(card, dict):
        card = {}
    has_legacy = (_number(card.get("harbor_score")) is not None or
                  _number(card.get("trace_score")) is not None)
    status = str(detail.get("status") or "").lower()
    if status in {"failed", "needs_review", "pending_review", "draft"}:
        return ("unscored_or_needs_review", position)
    if has_legacy:
        return ("live_task_grader" if position == "inside" else
                "legacy_components_outside_round", position)
    if GENERIC_FIELDS.intersection(card) and (position == "after" or status == "late_scored"):
        return ("late_generic_arm", position)
    strategy = (challenge.get("scoring") or {}).get("strategy")
    if strategy in {"human_review_only", "llm_judge_topic_markdown"}:
        return (str(strategy), position)
    return ("unclassified", position)


def _bundle_features(raw: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) > 1000 or sum(info.file_size for info in members) > 200_000_000:
            raise ValueError("bundle exceeds extraction analysis limits")
        files = {info.filename: archive.read(info.filename) for info in members
                 if not info.is_dir()}
    selected = trace_selection.select(files)
    rows = list(selected.rows) if selected.readable else []
    texts = [" ".join(str(row.get(key) or "") for key in ("title", "body", "code"))
             for row in rows]
    lengths = [len(text) for text in texts]
    combined = "\n".join(texts).lower()
    log_text = "\n".join(raw.decode("utf-8", "replace") for name, raw in files.items()
                         if name.endswith((".log", ".txt")) and len(raw) <= 2_000_000)
    outputs = [str(row.get("tool_output")) for row in rows if row.get("tool_output")]
    science = {name: {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
               for name, content in files.items()
               if (name.startswith(("results/", "outputs/", "src/"))
                   or name in {"arm_manifest.json", "characterization.json"}
                   or name.endswith(".log"))}
    return {
        "bundle_members": sorted(files),
        "science_files": science,
        "trace_selection": {"rule": selected.rule,
                            "members": list(selected.selected_members),
                            "readable": selected.readable,
                            "unresolved_claims": list(selected.unresolved_claims)},
        "trace_features": {
            "step_count": len(rows),
            "type_counts": {kind: sum(row.get("step_type") == kind for row in rows)
                            for kind in TRACE_TYPES},
            "stage_coverage_heuristic": {stage: any(word in combined for word in words)
                                         for stage, words in STAGES.items()},
            "validation_step_count_heuristic": sum(
                any(word in text.lower() for word in STAGES["validation"]) for text in texts),
            "error_repair_pairs": sum(
                row.get("step_type") == "error" and
                any(next_row.get("step_type") in ("decision", "tool_call", "observation")
                    for next_row in rows[index + 1:])
                for index, row in enumerate(rows)),
            "narrative_length": {"total": sum(lengths), "min": min(lengths) if lengths else None,
                                 "median": statistics.median(lengths) if lengths else None,
                                 "max": max(lengths) if lengths else None},
            "tool_output_log_match_fraction": (
                sum(value in log_text for value in outputs) / len(outputs)) if outputs else None,
            "reference_fraction": (sum(bool(row.get("cs_ref") or row.get("cs_refs"))
                                       for row in rows) / len(rows)) if rows else None,
        },
        "raw_messages": [{"path": name, "bytes": len(content),
                           "sha256": hashlib.sha256(content).hexdigest()}
                          for name, content in files.items()
                          if name.rsplit("/", 1)[-1] == "raw_messages.jsonl"],
    }


def _build_background(root: Path) -> dict[str, Any] | None:
    manifest_path = root / "background_pages_manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    rows: list[dict[str, Any]] = []
    for cid, entry in manifest.items():
        if "error" in entry:
            raise ValueError(f"background page unavailable: {cid}")
        challenge_rows = 0
        for page in entry["pages"]:
            relative = page["relative_path"]
            if relative != f"raw/background/{cid}/page-{page['page']:03d}.json":
                raise ValueError(f"unexpected background path: {relative}")
            raw = _verified_bytes(root, relative, page["sha256"])
            if len(raw) != page["bytes"]:
                raise ValueError(f"background page size mismatch: {relative}")
            payload = json.loads(raw)
            if payload["page"] != page["page"] or payload["platform_total"] != entry["platform_total"]:
                raise ValueError(f"background page metadata mismatch: {relative}")
            for candidate in payload["rows"]:
                if set(candidate) != {"status", "display_score", "harbor_score", "trace_score"}:
                    raise ValueError(f"background page contains unexpected fields: {relative}")
                rows.append({"challenge_id": cid, "status": candidate["status"],
                             "display_score": _number(candidate["display_score"]),
                             "harbor_score": _number(candidate["harbor_score"]),
                             "trace_score": _number(candidate["trace_score"])})
                challenge_rows += 1
        if challenge_rows != entry["platform_total"]:
            raise ValueError(f"background total mismatch: {cid}")
    data = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()
    (root / "background.jsonl").write_bytes(data)
    return {"row_count": len(rows), "challenge_count": len(manifest),
            "with_trace_score": sum(row["trace_score"] is not None for row in rows),
            "background_sha256": hashlib.sha256(data).hexdigest()}


def build(root: Path) -> dict[str, Any]:
    root = root.resolve()
    inv = json.loads((root / "inventory.json").read_text())
    challenge_manifest = json.loads((root / "challenge_snapshots_manifest.json").read_text())
    raw_hashes = {path: value["sha256"] for path, value in inv["raw_files"].items()}
    challenges = {}
    for cid, entry in challenge_manifest.items():
        if "error" in entry:
            raise ValueError(f"challenge snapshot unavailable: {cid}")
        relative = f"raw/challenges/{cid}/detail.json"
        challenges[cid] = json.loads(_verified_bytes(root, relative, entry["sha256"]))
    rows = []
    for account in inv["accounts"]:
        for attempt in account["attempts"]:
            aid = str(attempt["id"])
            prefix = f"raw/accounts/{account['alias']}/attempts/{aid}/"
            detail_path = prefix + "detail.json"
            score_path = prefix + "score.json"
            if detail_path not in raw_hashes or score_path not in raw_hashes:
                raise ValueError(f"missing raw detail/score: {account['alias']}/{aid}")
            detail = json.loads(_verified_bytes(root, detail_path, raw_hashes[detail_path]))
            score = json.loads(_verified_bytes(root, score_path, raw_hashes[score_path]))
            cid = attempt["challenge_id"]
            challenge = challenges[cid]
            mode, position = classify(detail, challenge)
            card = detail.get("scorecard") or {}
            state = detail.get("scoringState") or {}
            result: dict[str, Any] = {
                "account_alias": account["alias"], "account_role": account["role"],
                "attempt_id": aid, "challenge_id": cid,
                "season_id": challenge.get("hackathonSeasonId"),
                "round_id": challenge.get("roundId"),
                "round_start_at": challenge.get("roundStartAt"),
                "round_end_at": challenge.get("roundEndAt"),
                "created_at": detail.get("createdAt"), "updated_at": detail.get("updatedAt"),
                "round_position": position, "scoring_mode": mode,
                "current_challenge_strategy": (challenge.get("scoring") or {}).get("strategy"),
                "status": detail.get("status"), "score_is_final": state.get("scoreIsFinal"),
                "override_in_effect": state.get("overrideInEffect"),
                "display_score": _number(state.get("displayScore")),
                "harbor_score": _number(card.get("harbor_score")),
                "trace_score": _number(card.get("trace_score")),
                "scorecard": card, "score_endpoint_status": score.get("status"),
                "model": detail.get("modelTag"), "harness": detail.get("harness"),
                "content_status": attempt["content"],
                "inline_trace_status": "unavailable_not_in_receipt",
                "bundle_sha256": attempt.get("files", {}).get("bundle.zip"),
                "local_links": attempt.get("local_links", []),
                "trace_features": None, "science_files": None,
                "raw_messages": None,
            }
            bundle_path = prefix + "bundle.zip"
            if bundle_path in raw_hashes and account["credential_available"]:
                bundle = _bundle_features(_verified_bytes(root, bundle_path, raw_hashes[bundle_path]))
                result.update(bundle)
            rows.append(result)
    rows.sort(key=lambda x: (x["created_at"] or "", x["attempt_id"], x["account_alias"]))
    data = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()
    (root / "dataset.jsonl").write_bytes(data)
    summary = {"attempt_count": len(rows),
               "scoring_modes": dict(Counter(row["scoring_mode"] for row in rows)),
               "live_by_challenge": dict(Counter(row["challenge_id"] for row in rows
                                                 if row["scoring_mode"] == "live_task_grader")),
               "with_bundle": sum(row["bundle_sha256"] is not None for row in rows),
               "live_with_bundle": sum(row["scoring_mode"] == "live_task_grader" and
                                       row["bundle_sha256"] is not None for row in rows),
               "dataset_sha256": hashlib.sha256(data).hexdigest(),
               "background": _build_background(root)}
    (root / "dataset_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def _validated_root(path: Path) -> Path:
    root = path.resolve()
    ignored_parent = (config.WORKSPACE_ROOT / ".package-checks").resolve()
    if root.parent != ignored_parent or not root.name.startswith("scorer-re-"):
        raise ValueError("input must be a .package-checks/scorer-re-* directory")
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    result = build(_validated_root(args.root))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
