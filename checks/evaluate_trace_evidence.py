"""Report trace-model data sufficiency and score-only distributions."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from cyberscientist import config


def summarize(rows: list[dict[str, Any]], background: list[dict[str, Any]]) -> dict[str, Any]:
    live = [row for row in rows if row.get("scoring_mode") == "live_task_grader"]
    paired = [row for row in live if row.get("trace_score") is not None and
              row.get("trace_features") is not None]
    own_scores = [float(row["trace_score"]) for row in live
                  if row.get("trace_score") is not None]
    background_scores = [float(row["trace_score"]) for row in background
                         if row.get("trace_score") is not None]
    bundle_counts = Counter(row["bundle_sha256"] for row in paired
                            if row.get("bundle_sha256"))
    repeated = sum(count - 1 for count in bundle_counts.values() if count > 1)

    def distribution(values: list[float]) -> dict[str, Any]:
        return {"with_trace_score": len(values), "below_70": sum(value < 70 for value in values),
                "below_80": sum(value < 80 for value in values),
                "median": statistics.median(values) if values else None}

    return {
        "live_count": len(live), "paired_live_count": len(paired),
        "repeated_paired_bundle_count": repeated,
        "noise_status": "unknown" if not repeated else "repeat_samples_present",
        "model_status": "unavailable_no_paired_live_trace" if not paired else "requires_validation",
        "validated_mae": None, "validated_ge70_accuracy": None,
        "validated_ge80_accuracy": None, "misclassified_attempts": None,
        "own_live_distribution": distribution(own_scores),
        "background_count": len(background),
        "background_distribution": distribution(background_scores),
        "model_metadata_present": sum(row.get("model") is not None for row in live),
        "harness_metadata_present": sum(row.get("harness") is not None for row in live),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.parent != (config.WORKSPACE_ROOT / ".package-checks").resolve() or not root.name.startswith("scorer-re-"):
        raise ValueError("input must be a .package-checks/scorer-re-* directory")
    summary = json.loads((root / "dataset_summary.json").read_text())
    own_raw = (root / "dataset.jsonl").read_bytes()
    background_raw = (root / "background.jsonl").read_bytes()
    if hashlib.sha256(own_raw).hexdigest() != summary["dataset_sha256"]:
        raise ValueError("dataset hash mismatch")
    if hashlib.sha256(background_raw).hexdigest() != summary["background"]["background_sha256"]:
        raise ValueError("background hash mismatch")
    result = summarize([json.loads(line) for line in own_raw.splitlines()],
                       [json.loads(line) for line in background_raw.splitlines()])
    (root / "trace_evidence_analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
