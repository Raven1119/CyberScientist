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


def native_trace_index(t0: Path) -> dict[str, list[Path]]:
    index = defaultdict(list)
    for name in ("raw.jsonl", "raw.upload.jsonl"):
        paths = list(t0.glob(f"*/iterations/*/{name}")) + list(t0.glob(f"*/harvest/{name}"))
        for path in sorted(paths):
            index[sha256(path)].append(path)
    return index


def audit_receipt(raw_path: Path, trace_index: dict[str, list[Path]] | None = None) -> dict | None:
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
            not (submit_receipt.get("bundle_response") or {}).get("native_trace_sha256") or
            argv.count("--challenge-id") != 1 or argv.count("--trace") != 1 or
            argv.count("--outputs") != 1 or
            argv[argv.index("--challenge-id") + 1] != challenge_id or
            abs(float(grade["score"]) - float(result["score_percent"])) > 0.001):
        raise ValueError(f"receipt, submission, command or grade mismatch: {raw_path}")
    live_outputs = output_index(Path(argv[argv.index("--outputs") + 1]))
    sealed_path = iteration / "workspace_snapshot/outputs"
    snapshot_verified = sealed_path.is_dir()
    if snapshot_verified:
        sealed_outputs = output_index(sealed_path)
        if live_outputs != sealed_outputs:
            raise ValueError(f"live outputs differ from sealed snapshot: {raw_path}")
    output_tree_hash = hashlib.sha256(json.dumps(live_outputs, sort_keys=True).encode()).hexdigest()
    trace_path = Path(argv[argv.index("--trace") + 1])
    trace_exact = trace_path.is_file() and trace_path.resolve() in {
        (iteration / "raw.jsonl").resolve(),
        (iteration / "raw.upload.jsonl").resolve(),
    }
    features = None
    trace_hash = None
    if trace_exact:
        trace_hash = sha256(trace_path)
    receipt_trace_hash = submit_receipt["bundle_response"]["native_trace_sha256"]
    trace_receipt_match = trace_exact and trace_hash == receipt_trace_hash
    candidates = (trace_index or {}).get(receipt_trace_hash, [])
    source = trace_path if trace_receipt_match else next(
        (path for path in candidates if path.parent == iteration),
        candidates[0] if candidates else None)
    source_kind = ("command" if trace_receipt_match else
                   "same_iteration_snapshot" if source is not None and source.parent == iteration else
                   "other_iteration" if source is not None else "unavailable")
    if source is not None:
        if sha256(source) != receipt_trace_hash:
            raise ValueError(f"indexed native trace changed: {source}")
        events = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
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
            "command_trace_path_available": trace_exact,
            "trace_receipt_match": trace_receipt_match,
            "native_trace_content_available": source is not None,
            "native_trace_source_kind": source_kind,
            "command_trace_sha256": trace_hash,
            "native_trace_sha256": receipt_trace_hash, "trace_features": features,
            "output_tree_sha256": output_tree_hash, "output_file_count": len(live_outputs),
            "output_snapshot_verified": snapshot_verified,
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
    native_trace_groups = defaultdict(list)
    for row in rows:
        output_groups[(row["challenge_id"], row["output_tree_sha256"])].append(row)
        bundle_groups[(row["challenge_id"], row["bundle_sha256"])].append(row)
        native_trace_groups[row["native_trace_sha256"]].append(row)
    effects = defaultdict(set)
    for row in rows:
        for reason in row["reasons"]:
            effects[reason["code"]].add(reason["score_effect"])
    return {"count": len(rows),
            "sealed_output_count": sum(row["output_snapshot_verified"] for row in rows),
            "command_trace_path_count": sum(row["command_trace_path_available"] for row in rows),
            "trace_receipt_match_count": sum(row["trace_receipt_match"] for row in rows),
            "native_trace_content_count": sum(row["native_trace_content_available"] for row in rows),
            "native_trace_source_kinds": dict(Counter(row["native_trace_source_kind"] for row in rows)),
            "cross_task_native_trace_reuse_groups": sum(
                len({row["challenge_id"] for row in group}) > 1
                for group in native_trace_groups.values()),
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
                row["native_trace_content_available"] and
                row["trace_features"]["successful_commands"] > 0 and
                any(reason["code"] == "N09_NO_EXECUTION_EVIDENCE" for reason in row["reasons"])
                for row in rows)}


def verify_older_pairs(path: Path) -> dict:
    pairs = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    valid = [pair for pair in pairs if pair["valid_join"]]
    matched = 0
    for pair in valid:
        receipt = json.loads((Path(pair["iteration"]) / "submission/stdout.log").read_text())
        native_sha = (receipt.get("bundle_response") or {}).get("native_trace_sha256")
        upload = pair["files"]["raw.upload.jsonl"]
        if (upload and sha256(Path(upload["path"])) == upload["sha256"] and
                native_sha == upload["sha256"]):
            matched += 1
    return {"pairs_sha256": sha256(path), "valid_joins": len(valid),
            "native_trace_receipt_matches": matched}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentmaster", type=Path, required=True)
    parser.add_argument("--older-pairs", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to((Path.cwd() / ".package-checks").resolve()):
        raise ValueError("output must remain under .package-checks")
    t0 = args.agentmaster / "store/T0"
    paths = sorted(list(t0.glob("*/iterations/*/grader/grader.raw.json")) +
                   list(t0.glob("*/harvest/grader/grader.raw.json")))
    trace_index = native_trace_index(t0)
    rows = [row for path in paths if (row := audit_receipt(path, trace_index)) is not None]
    if not rows:
        raise ValueError("no unredacted grader diagnostics")
    summary = summarize(rows)
    if args.older_pairs is not None:
        summary["older_pairs"] = verify_older_pairs(args.older_pairs)
    output.mkdir(parents=True, exist_ok=True)
    (output / "diagnostics.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"count": summary["count"],
                      "trace_receipt_match_count": summary["trace_receipt_match_count"],
                      "native_trace_content_count": summary["native_trace_content_count"],
                      "max_factor_error": summary["max_factor_error"],
                      "max_display_error": summary["max_display_error"]}, sort_keys=True))


if __name__ == "__main__":
    main()
