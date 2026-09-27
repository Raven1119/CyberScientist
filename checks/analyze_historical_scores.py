"""Audit historical display-score formulas without inventing missing science scores."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cyberscientist import config


def formula_a(harbor: float, trace: float) -> float:
    return harbor * max(0.0, min((trace - 30.0) / 40.0, 1.0))


def formula_b(harbor: float, trace: float) -> float:
    return harbor * max(0.0, min(trace / 100.0, 1.0))


def formula_gate70(harbor: float, trace: float) -> float:
    """Pre-existing 70-point gate as a score-only hypothesis, not a platform contract."""
    return formula_b(harbor, trace) if trace < 70.0 else formula_a(harbor, trace)


def classify_formula(row: dict[str, Any], *, tolerance: float = 0.001) -> dict[str, Any]:
    harbor, trace, display = (row.get(key) for key in
                              ("harbor_score", "trace_score", "display_score"))
    if any(value is None for value in (harbor, trace, display)):
        return {"class": "missing", "error_a": None, "error_b": None,
                "error_gate70": None}
    error_a = abs(float(display) - formula_a(float(harbor), float(trace)))
    error_b = abs(float(display) - formula_b(float(harbor), float(trace)))
    a, b = error_a <= tolerance, error_b <= tolerance
    return {"class": ("both" if a and b else "formula_a" if a else
                      "formula_b" if b else "neither"),
            "error_a": error_a, "error_b": error_b,
            "error_gate70": abs(float(display) - formula_gate70(float(harbor), float(trace)))}


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    live = [row for row in rows if row.get("scoring_mode") == "live_task_grader"]
    counts: Counter[str] = Counter()
    reward_errors: list[float] = []
    replay_executed_count = 0
    by_challenge: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"sample_count": 0, "complete_score_count": 0,
                 "science_artifact_count": 0, "formula_classes": Counter()})
    anomalies = []
    gate_errors: list[float] = []
    distinguishable_below: list[float] = []
    distinguishable_above: list[float] = []
    for row in live:
        card = row.get("scorecard") or {}
        if not isinstance(card, dict):
            card = {}
        reward, harbor = card.get("harbor_reward"), row.get("harbor_score")
        if (type(reward) in (int, float) and type(harbor) in (int, float)):
            reward_errors.append(abs(harbor - 100 * reward))
        replay_executed_count += card.get("harbor_replay_executed") == 1
        result = classify_formula(row)
        kind = result["class"]
        counts[kind] += 1
        if result["error_gate70"] is not None:
            gate_errors.append(result["error_gate70"])
            if kind == "formula_b":
                distinguishable_below.append(float(row["trace_score"]))
            elif kind == "formula_a":
                distinguishable_above.append(float(row["trace_score"]))
        item = by_challenge[row["challenge_id"]]
        item["sample_count"] += 1
        item["complete_score_count"] += kind != "missing"
        item["science_artifact_count"] += bool(row.get("science_files"))
        item["formula_classes"][kind] += 1
        if kind in {"formula_b", "neither"}:
            anomalies.append({"attempt_id": row["attempt_id"],
                              "challenge_id": row["challenge_id"],
                              "class": kind,
                              "error_a": result["error_a"],
                              "error_b": result["error_b"],
                              "override_in_effect": row.get("override_in_effect"),
                              "score_is_final": row.get("score_is_final")})
    return {"live_count": len(live), "formula_classes": dict(counts),
            "gate70_hypothesis": {
                "complete_count": len(gate_errors),
                "max_abs_error": max(gate_errors) if gate_errors else None,
                "mismatch_count_at_0_001": sum(error > 0.001 for error in gate_errors),
                "max_distinguishable_below": max(distinguishable_below) if distinguishable_below else None,
                "min_distinguishable_above": min(distinguishable_above) if distinguishable_above else None,
            },
            "harbor_reward_x100": {
                "paired_count": len(reward_errors),
                "max_abs_error": max(reward_errors) if reward_errors else None,
                "mismatch_count_at_1e_6": sum(error > 1e-6 for error in reward_errors),
                "replay_executed_count": replay_executed_count,
            },
            "by_challenge": {cid: {**value, "formula_classes": dict(value["formula_classes"])}
                             for cid, value in sorted(by_challenge.items())},
            "anomalies": anomalies}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    ignored_parent = (config.WORKSPACE_ROOT / ".package-checks").resolve()
    if root.parent != ignored_parent or not root.name.startswith("scorer-re-"):
        raise ValueError("input must be a .package-checks/scorer-re-* directory")
    data = (root / "dataset.jsonl").read_bytes()
    summary = json.loads((root / "dataset_summary.json").read_text())
    if hashlib.sha256(data).hexdigest() != summary["dataset_sha256"]:
        raise ValueError("dataset hash mismatch; rebuild from raw receipts")
    rows = [json.loads(line) for line in data.splitlines()]
    result = analyze(rows)
    (root / "score_analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"live_count": result["live_count"],
                      "formula_classes": result["formula_classes"],
                      "harbor_reward_x100": result["harbor_reward_x100"],
                      "gate70_hypothesis": result["gate70_hypothesis"],
                      "challenge_count": len(result["by_challenge"]),
                      "live_with_science_artifacts": sum(
                          item["science_artifact_count"] for item in result["by_challenge"].values())},
                     sort_keys=True))


if __name__ == "__main__":
    main()
