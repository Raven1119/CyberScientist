"""Prepare own hash-bound FigQA inputs on the host; evaluate only in Bohrium."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

CID = "lab-bench-figqa-figqa-0177-b4156bee"


def prepare(history: Path, output: Path) -> dict:
    from audit_agentmaster_grader_diagnostics import audit_receipt
    output.mkdir(parents=True, exist_ok=False)
    (output / "cases").mkdir()
    samples, excluded = [], []
    for iteration in sorted((history / "iterations").iterdir()):
        if not iteration.name.isdigit():
            continue
        raw_path = iteration / "grader/grader.raw.json"
        audit = audit_receipt(raw_path)
        if not audit or audit["challenge_id"] != CID or not audit["output_snapshot_verified"]:
            raise ValueError("unverified historical snapshot")
        receipt_path = iteration / "submission/stdout.log"
        receipt = json.loads(receipt_path.read_text())
        metadata = receipt["bundle_response"]["metadata"]
        bound = (receipt["bundle_sha256"] == metadata["bundle"]["sha256"]
                 and metadata["challenge_id"] == CID and receipt["challenge_id"] == CID
                 and str(metadata["attempt_id"]) == str(audit["attempt_id"]))
        alias = "F" + iteration.name
        if not bound:
            excluded.append({"sample": alias, "reason": "generated_received_bundle_mismatch",
                             "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()})
            continue
        path = output / "cases" / (alias + ".zip")
        source = iteration / "workspace_snapshot/outputs"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            # The full snapshot was audited above. Only the scored answer is
            # passed to this question's evaluator; no labels or trace metadata.
            info = zipfile.ZipInfo("outputs/answer.txt", (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (source / "answer.txt").read_bytes())
        samples.append({"sample": alias, "expected_science_score": audit["science_score"],
                        "replay_zip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "answer_sha256": hashlib.sha256((source / "answer.txt").read_bytes()).hexdigest(),
                        "score_receipt_sha256": audit["receipt_sha256"],
                        "output_tree_sha256": audit["output_tree_sha256"],
                        "received_bundle_sha256": metadata["bundle"]["sha256"],
                        "trace_score": audit["trace_score"], "display_score": audit["display_score"]})
    result = {"samples": samples, "excluded": excluded}
    (output / "manifest.json").write_text(json.dumps(result, indent=2))
    return result


def evaluate(corpus: Path, scorer: Path, output: Path, version: str) -> dict:
    """Scientific scoring and error aggregation: run this phase in Bohrium."""
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((corpus / "manifest.json").read_text())
    rows = []
    for sample in manifest["samples"]:
        path = corpus / "cases" / (sample["sample"] + ".zip")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sample["replay_zip_sha256"]:
            raise ValueError("replay input hash mismatch")
        process = subprocess.run([sys.executable, str(scorer), str(path)],
                                 env=dict(os.environ, CS_SCORER_VERSION=version),
                                 capture_output=True, text=True, timeout=20)
        (output / (sample["sample"] + ".stdout")).write_text(process.stdout)
        (output / (sample["sample"] + ".stderr")).write_text(process.stderr)
        row = sample | {"exit_code": process.returncode}
        if process.returncode == 0:
            row["result"] = json.loads(process.stdout)
            row["absolute_error"] = abs(row["result"]["score"] - sample["expected_science_score"])
        else:
            row["status"] = "unverified"
        rows.append(row)
    errors = [row["absolute_error"] for row in rows if "absolute_error" in row]
    result = {"scorer_version": version, "samples": rows, "excluded": manifest["excluded"],
              "numeric": len(errors), "exact": sum(error == 0 for error in errors),
              "mae": sum(errors) / len(errors) if errors else None,
              "max_absolute_error": max(errors) if errors else None,
              "validation": "Fixed public key and frozen option order; no historical label fitting. "
                            "Leave-one-label-out gives the same rule, not independent generalization evidence."}
    (output / "results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({key: value for key, value in result.items() if key not in {"samples", "excluded"}}))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--history", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("--corpus", type=Path, required=True)
    evaluate_parser.add_argument("--scorer", type=Path, required=True)
    evaluate_parser.add_argument("--output", type=Path, required=True)
    evaluate_parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        if not args.output.resolve().is_relative_to((Path.cwd() / ".package-checks").resolve()):
            raise ValueError("raw corpus must stay under .package-checks")
        result = prepare(args.history, args.output)
        print(json.dumps({"included": len(result["samples"]), "excluded": result["excluded"]}))
    else:
        evaluate(args.corpus, args.scorer, args.output, args.version)


if __name__ == "__main__":
    main()
