"""Run historical science replays and controlled mutations INSIDE Bohrium.

Inputs are science-only ZIPs and a separate label manifest. Neither scores nor
traces are passed to score.py. This does not submit anything to the platform.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path


def mutations(good: Path, template: Path, target: Path) -> list[dict]:
    with zipfile.ZipFile(good) as archive:
        proof = archive.read("outputs/Problem.lean").decode()
        matching = json.loads(archive.read("outputs/PHYSICS_MATCH.json"))
    start = proof.index("theorem partTwo_branchRigidity")
    end = proof.index("end PairStructure", start)
    header = proof[start:proof.index(":= by", start)]
    variants = [
        ("M_missing_matching", proof, None, 90),
        ("M_wrong_T1_match", proof, matching | {"matches": matching["matches"] | {"T1": "R1"}}, 96),
        ("M_duplicate_matches", proof, matching | {"matches": matching["matches"] | {"T1": "R2"}}, 90),
        ("M_all_sorry", template.read_text(), matching, 0),
        ("M_T3_sorry", proof[:start] + header + ":= by\n  sorry\n\n" + proof[end:], matching, 70),
        ("M_T3_wrong_type", proof[:start] + "theorem partTwo_branchRigidity : True := by trivial\n\n" + proof[end:], matching, 70),
        ("M_T3_custom_axiom", proof[:start] + "axiom csInjected : False\n" + header
         + ":= by\n  exact False.elim csInjected\n\n" + proof[end:], matching, 70),
        ("M_missing_proof", None, matching, 0),
    ]
    target.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, source, match, expected in variants:
        package = target / (name + ".zip")
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            if source is not None:
                archive.writestr("outputs/Problem.lean", source)
            if match is not None:
                archive.writestr("outputs/PHYSICS_MATCH.json", json.dumps(match))
        rows.append({"sample": name, "package": str(package), "expected_science_score": expected,
                     "kind": "synthetic_not_platform_scored"})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorer", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--good-sample", default="E009")
    parser.add_argument("--samples", nargs="+", help="Explicit subset; omitted records remain unattempted")
    parser.add_argument("--skip-mutations", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    history = json.loads(args.labels.read_text())
    available = {row["sample"] for row in history}
    if args.samples and not set(args.samples) <= available:
        raise ValueError("requested historical sample is absent")
    unattempted = [row["sample"] for row in history if args.samples and row["sample"] not in args.samples]
    rows = []
    for label in history:
        if label["sample"] in unattempted:
            continue
        if not re.fullmatch(r"E\d+", label["sample"]):
            raise ValueError("invalid sample alias")
        package = args.inputs / (label["sample"] + ".zip")
        if hashlib.sha256(package.read_bytes()).hexdigest() != label["replay_zip_sha256"]:
            raise ValueError("replay ZIP differs from audited manifest")
        rows.append({"sample": label["sample"], "package": str(package),
                     "expected_science_score": label["expected_science_score"], "kind": "historical_final"})
    if not args.skip_mutations:
        rows += mutations(args.inputs / (args.good_sample + ".zip"), args.project / "Problem.lean", args.output / "mutations")
    env = dict(os.environ, CS_LEAN_PROJECT=str(args.project), CS_SCORER_VERSION=args.version)
    results = []
    for row in rows:
        started = time.monotonic()
        env["CS_SCORER_AUDIT_DIR"] = str(args.output / "diagnostics" / row["sample"])
        try:
            process = subprocess.run([sys.executable, str(args.scorer), row["package"]], env=env,
                                     capture_output=True, text=True, timeout=450)
            (args.output / (row["sample"] + ".stdout")).write_text(process.stdout)
            (args.output / (row["sample"] + ".stderr")).write_text(process.stderr)
            row["exit_code"] = process.returncode
            if process.returncode == 0:
                row["result"] = json.loads(process.stdout)
                row["absolute_error"] = abs(row["result"]["score"] - row["expected_science_score"])
            else:
                row["status"] = "unverified"
        except subprocess.TimeoutExpired:
            row.update(status="unverified", reason="evaluation deadline", exit_code=None)
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        results.append(row)
        (args.output / "results.json").write_text(json.dumps(results, indent=2))
        print(json.dumps({key: value for key, value in row.items() if key not in {"result", "package"}}), flush=True)
        # An infrastructure failure is shared by remaining cases: do not waste
        # the leased sandbox by blindly repeating an unavailable environment.
        if row.get("status") == "unverified":
            break
    summary = {}
    for kind in ("historical_final", "synthetic_not_platform_scored"):
        group = [row for row in results if row["kind"] == kind]
        numeric = [row for row in group if "absolute_error" in row]
        errors = [row["absolute_error"] for row in numeric]
        summary[kind] = {"attempted": len(group), "numeric": len(numeric),
                         "exact": sum(error == 0 for error in errors),
                         "mae": sum(errors) / len(errors) if errors else None,
                         "max_absolute_error": max(errors) if errors else None}
    summary["scorer_version"] = args.version
    summary["unattempted_history"] = unattempted + [row["sample"] for row in rows[len(results):] if row["kind"] == "historical_final"]
    summary["unattempted_mutations"] = [row["sample"] for row in rows[len(results):] if row["kind"] == "synthetic_not_platform_scored"]
    summary["scorer_file_sha256"] = hashlib.sha256(args.scorer.read_bytes()).hexdigest()
    summary["validation"] = "Fixed public rule; no label fitting. Known-label retrospective replay, not blinded evaluation."
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
