"""Rebuild science-only replay ZIPs from hash-paired local historical records.

No scientific program is run on the host. Raw submissions and identities remain
under .package-checks; these new ZIPs are not the original received ARM bundles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from audit_agentmaster_science_outputs import audit

CHALLENGE_ID = "flowforge-paired-block-boundary-projection-v10-fe06025a"


def prepare(pairs_file: Path, challenge_root: Path, output: Path) -> list[dict]:
    output.mkdir(parents=True, exist_ok=False)
    cases = output / "cases"
    cases.mkdir()
    rows = []
    for pair in map(json.loads, pairs_file.read_text().splitlines()):
        if (pair["challenge_id"] != CHALLENGE_ID or not pair["valid_join"]
                or not pair["score_is_final"] or pair["scoring_mode"] != "live_task_grader"):
            continue
        checked = audit(pair)
        iteration = Path(pair["iteration"])
        receipt_file = iteration / "submission/stdout.log"
        receipt = json.loads(receipt_file.read_text())
        metadata = receipt["bundle_response"]["metadata"]
        if (receipt["status"] != "submitted" or receipt["challenge_id"] != CHALLENGE_ID
                or metadata["challenge_id"] != CHALLENGE_ID
                or str(receipt["attempt_id"]) != str(pair["attempt_id"])
                or str(metadata["attempt_id"]) != str(pair["attempt_id"])
                or receipt["bundle_sha256"] != metadata["bundle"]["sha256"]):
            raise ValueError("submission-to-received-bundle binding failed")
        alias = "E" + iteration.name
        if not iteration.name.isdigit() or any(row["sample"] == alias for row in rows):
            raise ValueError("invalid or duplicate sample alias")
        package = cases / (alias + ".zip")
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(checked["files"]):
                # Stable metadata makes file-management replay reproducible.
                info = zipfile.ZipInfo("outputs/" + name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, (iteration / "workspace_snapshot/outputs" / name).read_bytes())
        rows.append({"sample": alias, "attempt_id": pair["attempt_id"],
                     "expected_science_score": pair["harbor_score"],
                     "source_iteration": str(iteration), "science_files": checked["files"],
                     "received_bundle_sha256": metadata["bundle"]["sha256"],
                     "replay_zip_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
                     "submission_receipt_sha256": hashlib.sha256(receipt_file.read_bytes()).hexdigest()})
    if not rows:
        raise ValueError("no final hash-paired historical samples")
    project = challenge_root / "inputs/data/environment/project"
    shutil.copytree(project, output / "project", ignore=shutil.ignore_patterns(".lake", ".git", "__pycache__"))
    (output / "samples.json").write_text(json.dumps(rows, indent=2))
    (output / "labels.json").write_text(json.dumps([
        {key: row[key] for key in ("sample", "expected_science_score", "replay_zip_sha256")} for row in rows], indent=2))
    (output / "provenance.json").write_text(json.dumps({
        "pairs_sha256": hashlib.sha256(pairs_file.read_bytes()).hexdigest(),
        "challenge_snapshot_sha256": hashlib.sha256((challenge_root / "challenge.json").read_bytes()).hexdigest(),
        "replay_format": "new science-only ZIP; never an original bundle hash match"}, indent=2))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--challenge-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((Path.cwd() / ".package-checks").resolve()):
        raise ValueError("output must remain under .package-checks")
    rows = prepare(args.pairs, args.challenge_root, args.output)
    print(json.dumps({"final_samples": len(rows), "aliases": [row["sample"] for row in rows]}))


if __name__ == "__main__":
    main()
