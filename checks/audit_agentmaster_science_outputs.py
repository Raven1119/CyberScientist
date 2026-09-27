"""Check that paired submissions' local outputs match their sealed snapshots.

Only hashes, sizes, counts and scores are written to the ignored output directory.
No scientific answer or trace text is copied into the report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def file_index(root: Path) -> dict[str, tuple[int, str]]:
    if not root.is_dir():
        raise ValueError(f"missing output directory: {root}")
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlink in output directory: {path}")
        if path.is_file():
            files[str(path.relative_to(root))] = (
                path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
    return files


def audit(pair: dict) -> dict:
    iteration = Path(pair["iteration"])
    record = iteration / "submission/command.json"
    if hashlib.sha256(record.read_bytes()).hexdigest() != pair["command_record_sha256"]:
        raise ValueError("command record hash mismatch")
    argv = json.loads(record.read_text())["argv"]
    if argv.count("--outputs") != 1:
        raise ValueError("expected one --outputs argument")
    live = Path(argv[argv.index("--outputs") + 1])
    snapshot = iteration / "workspace_snapshot/outputs"
    live_files, sealed_files = file_index(live), file_index(snapshot)
    if live_files != sealed_files:
        raise ValueError(f"live outputs differ from snapshot: {pair['attempt_id']}")
    digest = hashlib.sha256(json.dumps(sealed_files, sort_keys=True).encode()).hexdigest()
    return {"attempt_id": pair["attempt_id"], "challenge_id": pair["challenge_id"],
            "score_is_final": pair["score_is_final"], "harbor_score": pair["harbor_score"],
            "trace_score": pair["trace_score"], "file_count": len(sealed_files),
            "total_bytes": sum(size for size, _ in sealed_files.values()),
            "output_tree_sha256": digest,
            "files": {name: {"bytes": size, "sha256": sha}
                      for name, (size, sha) in sorted(sealed_files.items())}}


def summarize(rows: list[dict]) -> dict:
    final = [row for row in rows if row["score_is_final"]]
    groups = defaultdict(list)
    for row in final:
        groups[row["challenge_id"]].append(row)
    return {"paired": len(rows), "final": len(final),
            "by_challenge": {challenge: {
                "n": len(group),
                "score_counts": dict(sorted(Counter(str(row["harbor_score"]) for row in group).items())),
                "distinct_output_trees": len({row["output_tree_sha256"] for row in group}),
            } for challenge, group in sorted(groups.items())}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to((Path.cwd() / ".package-checks").resolve()):
        raise ValueError("output must remain under .package-checks")
    pairs = [json.loads(line) for line in args.pairs.read_text().splitlines() if line.strip()]
    rows = [audit(pair) for pair in pairs if pair["valid_join"]]
    summary = summarize(rows)
    summary["pairs_sha256"] = hashlib.sha256(args.pairs.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    (output / "science_outputs.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    (output / "science_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"paired": summary["paired"], "final": summary["final"]}))


if __name__ == "__main__":
    main()
