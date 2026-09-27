"""Audit locally saved, unredacted historical grader diagnostics.

Source receipts and per-Attempt rows stay in the ignored .package-checks directory.
The script does not call the platform, run scientific code, or score a new trace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def output_index(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise ValueError(f"missing output directory: {root}")
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlink in output directory: {path}")
        if path.is_file():
            files[str(path.relative_to(root))] = sha256(path)
    return files


def audit_receipt(raw_path: Path) -> dict | None:
    raw = json.loads(raw_path.read_text())
    detail = raw.get("detail") or {}
    result = detail.get("resultsJson")
    if not isinstance(result, dict):
        return None
    iteration = raw_path.parent.parent
    submission_path = iteration / "submission/submission.json"
    command_path = iteration / "submission/command.json"
    stdout_path = iteration / "submission/stdout.log"
    grade_path = iteration / "grader/grader.json"
    submission = json.loads(submission_path.read_text())
    argv = json.loads(command_path.read_text())["argv"]
    submit_receipt = json.loads(stdout_path.read_text())
    grade = json.loads(grade_path.read_text())
    attempt_id = str(raw["attempt_id"])
    challenge_id = detail["challengeId"]
    if (str(submission.get("attempt_id")) != attempt_id or
            str(grade.get("attempt_id")) != attempt_id or
            str(submit_receipt.get("attempt_id")) != attempt_id or
            submission.get("status") != "submitted" or grade.get("status") != "scored" or
            not submit_receipt.get("bundle_sha256") or
            argv.count("--challenge-id") != 1 or argv.count("--trace") != 1 or
            argv.count("--outputs") != 1 or
            argv[argv.index("--challenge-id") + 1] != challenge_id or
            abs(float(grade["score"]) - float(result["score_percent"])) > 0.001):
        raise ValueError(f"receipt, submission, command or grade mismatch: {raw_path}")
    live_outputs = output_index(Path(argv[argv.index("--outputs") + 1]))
    sealed_outputs = output_index(iteration / "workspace_snapshot/outputs")
    if live_outputs != sealed_outputs:
        raise ValueError(f"live outputs differ from sealed snapshot: {raw_path}")
    output_tree_hash = hashlib.sha256(json.dumps(sealed_outputs, sort_keys=True).encode()).hexdigest()
    trace_path = Path(argv[argv.index("--trace") + 1])
    trace_exact = trace_path.is_file() and trace_path.resolve() in {
        (iteration / "raw.jsonl").resolve(),
        (iteration / "raw.upload.jsonl").resolve(),
    }
    features = None
    trace_hash = None
    if trace_exact:
        trace_hash = sha256(trace_path)
        events = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
        completed = [e.get("item") for e in events if e.get("type") == "item.completed"
                     and isinstance(e.get("item"), dict)]
        commands = [item for item in completed if item.get("type") == "command_execution"]
        features = {"upload_events": len(events), "completed_commands": len(commands),
                    "successful_commands": sum(item.get("exit_code") == 0 for item in commands)}
    reasons = result.get("trace_low_score_reasons") or []
    if not all(isinstance(reason, dict) and "code" in reason and
               "score_effect" in reason for reason in reasons):
        raise ValueError(f"unexpected reason format: {raw_path}")
    factor = (detail.get("scoringDetails") or {}).get("trace_factor")
    decision = result["trace_decision"]
    expected = {"accept": 1.0, "review": result["trace_score"] / 100,
                "block": 0.0}.get(decision)
    if expected is None or factor is None:
        raise ValueError(f"unknown decision or absent trace factor: {raw_path}")
    return {"attempt_id": attempt_id, "challenge_id": challenge_id,
            "engine": result["trace_score_engine"], "decision": decision,
            "science_score": result["harbor_score"], "trace_score": result["trace_score"],
            "display_score": result["score_percent"], "factor": factor,
            "expected_factor": expected,
            "factor_error": abs(factor - expected),
            "display_error": abs(result["score_percent"] - result["harbor_score"] * factor),
            "reasons": [{"code": reason["code"], "score_effect": reason["score_effect"]}
                        for reason in reasons],
            "missing_evidence_count": len(result.get("trace_missing_evidence") or []),
            "exact_trace_input_available": trace_exact,
            "trace_sha256": trace_hash, "trace_features": features,
            "output_tree_sha256": output_tree_hash, "output_file_count": len(sealed_outputs),
            "bundle_sha256": submit_receipt["bundle_sha256"],
            "receipt_sha256": sha256(raw_path), "command_sha256": sha256(command_path),
            "grade_sha256": sha256(grade_path)}


def summarize(rows: list[dict]) -> dict:
    by_decision = defaultdict(list)
    for row in rows:
        by_decision[row["decision"]].append(row)
    reason_counts = Counter(reason["code"] for row in rows for reason in row["reasons"])
    output_groups = defaultdict(list)
    bundle_groups = defaultdict(list)
    for row in rows:
        output_groups[(row["challenge_id"], row["output_tree_sha256"])].append(row)
        bundle_groups[(row["challenge_id"], row["bundle_sha256"])].append(row)
    effects = defaultdict(set)
    for row in rows:
        for reason in row["reasons"]:
            effects[reason["code"]].add(reason["score_effect"])
    return {"count": len(rows),
            "exact_trace_input_count": sum(row["exact_trace_input_available"] for row in rows),
            "distinct_output_trees": len(output_groups),
            "distinct_bundles": len(bundle_groups),
            "same_bundle_different_science_groups": sum(
                len({row["science_score"] for row in group}) > 1
                for group in bundle_groups.values()),
            "same_output_different_science_groups": sum(
                len({row["science_score"] for row in group}) > 1
                for group in output_groups.values()),
            "engines": dict(Counter(row["engine"] for row in rows)),
            "decisions": {decision: {
                "count": len(group),
                "min_trace_score": min(row["trace_score"] for row in group),
                "max_trace_score": max(row["trace_score"] for row in group),
                "no_reason_count": sum(not row["reasons"] for row in group),
            } for decision, group in sorted(by_decision.items())},
            "max_factor_error": max(row["factor_error"] for row in rows),
            "max_display_error": max(row["display_error"] for row in rows),
            "reason_counts": dict(sorted(reason_counts.items())),
            "reason_effects": {code: sorted(values) for code, values in sorted(effects.items())},
            "no_execution_reason_with_successful_commands": sum(
                row["exact_trace_input_available"] and
                row["trace_features"]["successful_commands"] > 0 and
                any(reason["code"] == "N09_NO_EXECUTION_EVIDENCE" for reason in row["reasons"])
                for row in rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentmaster", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to((Path.cwd() / ".package-checks").resolve()):
        raise ValueError("output must remain under .package-checks")
    paths = sorted((args.agentmaster / "store/T0").glob(
        "*/iterations/*/grader/grader.raw.json"))
    rows = [row for path in paths if (row := audit_receipt(path)) is not None]
    if not rows:
        raise ValueError("no unredacted grader diagnostics")
    summary = summarize(rows)
    output.mkdir(parents=True, exist_ok=True)
    (output / "diagnostics.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"count": summary["count"],
                      "exact_trace_input_count": summary["exact_trace_input_count"],
                      "max_factor_error": summary["max_factor_error"],
                      "max_display_error": summary["max_display_error"]}, sort_keys=True))


if __name__ == "__main__":
    main()
