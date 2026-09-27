"""Join local AgentMaster submission traces to an existing owned-score snapshot.

Only metadata and hashes are written. Raw events and submission receipts stay
in their original local directories; the output directory must be ignored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonl_counts(path: Path) -> dict[str, Any]:
    event_types: Counter[str] = Counter()
    item_types: Counter[str] = Counter()
    rows = 0
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError(f"non-object event: {path}")
            rows += 1
            event_types[str(event.get("type") or event.get("step_type") or "unknown")] += 1
            item = event.get("item") or {}
            if isinstance(item, dict) and item.get("type"):
                item_types[str(item["type"])] += 1
    return {"rows": rows, "event_types": dict(sorted(event_types.items())),
            "item_types": dict(sorted(item_types.items()))}


def _file_record(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": _sha256(path), **_jsonl_counts(path)}


def _arg(argv: list[str], name: str) -> str | None:
    if argv.count(name) != 1:
        return None
    index = argv.index(name) + 1
    return argv[index] if index < len(argv) else None


def match(dataset: Path, agentmaster: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    agentmaster = agentmaster.resolve()
    scores = {}
    for line in dataset.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        aid = str(row["attempt_id"])
        if aid in scores:
            raise ValueError(f"duplicate scored Attempt: {aid}")
        scores[aid] = row

    records: dict[str, Path] = {}
    for sub_path in (agentmaster / "store" / "T0").rglob("submission.json"):
        if sub_path.parent.name != "submission":
            continue  # retry copies are not independent submissions
        submission = json.loads(sub_path.read_text())
        aid = submission.get("attempt_id")
        if aid is None:
            continue
        aid = str(aid)
        if aid in records:
            raise ValueError(f"duplicate local Attempt: {aid}")
        records[aid] = sub_path

    pairs = []
    for aid, score in scores.items():
        if aid not in records:
            continue
        sub_path = records[aid]
        iteration = sub_path.parent.parent
        submission = json.loads(sub_path.read_text())
        command_path = sub_path.parent / "command.json"
        argv = json.loads(command_path.read_text()).get("argv", []) if command_path.is_file() else []
        challenge_matches = _arg(argv, "--challenge-id") == score.get("challenge_id")
        upload = iteration / "raw.upload.jsonl"
        trace_matches = (_arg(argv, "--trace") is not None and
                         Path(_arg(argv, "--trace")).resolve() == upload.resolve())
        valid_join = submission.get("status") == "submitted" and challenge_matches and trace_matches
        local_grade_path = iteration / "grader" / "grader.json"
        local_grade = json.loads(local_grade_path.read_text()) if local_grade_path.is_file() else {}
        files = {name: _file_record(iteration / name) for name in
                 ("raw.jsonl", "raw.upload.jsonl", "traces/trace.jsonl")}
        pair = {
            "attempt_id": aid, "challenge_id": score.get("challenge_id"),
            "iteration": str(iteration), "submission_record": str(sub_path),
            "submission_record_sha256": _sha256(sub_path),
            "command_record_sha256": _sha256(command_path) if command_path.is_file() else None,
            "submitted": submission.get("status") == "submitted",
            "command_challenge_matches": challenge_matches,
            "command_trace_is_upload": trace_matches,
            "valid_join": bool(valid_join and files["raw.upload.jsonl"] and
                               files["raw.upload.jsonl"]["rows"] > 0),
            "scoring_mode": score.get("scoring_mode"),
            "score_is_final": score.get("score_is_final"),
            "trace_score": score.get("trace_score"),
            "harbor_score": score.get("harbor_score"),
            "display_score": score.get("display_score"),
            "score_snapshot_created_at": score.get("created_at"),
            "score_snapshot_updated_at": score.get("updated_at"),
            "local_grade_sha256": _sha256(local_grade_path) if local_grade else None,
            "local_grade_status": local_grade.get("status"),
            "local_grade_trace_score": local_grade.get("trace_score"),
            "local_grade_matches_snapshot": (
                local_grade.get("trace_score") == score.get("trace_score")
                if local_grade.get("trace_score") is not None else None),
            "files": files,
        }
        pairs.append(pair)

    by_challenge = defaultdict(lambda: {"paired": 0, "final_trace_score": 0})
    for pair in pairs:
        group = by_challenge[pair["challenge_id"]]
        group["paired"] += bool(pair["valid_join"])
        group["final_trace_score"] += bool(pair["valid_join"] and pair["score_is_final"]
                                           and pair["trace_score"] is not None)
    scored_trace = [pair for pair in pairs if pair["valid_join"] and
                    pair["trace_score"] is not None]
    summary = {
        "score_snapshot_sha256": _sha256(dataset),
        "score_snapshot_rows": len(scores),
        "local_attempt_ids_with_records": len(records),
        "id_overlap": len(pairs),
        "valid_joins": sum(pair["valid_join"] for pair in pairs),
        "paired_trace_scores": len(scored_trace),
        "paired_final_trace_scores": sum(bool(pair["score_is_final"]) for pair in scored_trace),
        "all_three_trace_files": sum(all(pair["files"].values()) for pair in pairs),
        "raw_equals_upload": sum(pair["files"]["raw.jsonl"] and
                                 pair["files"]["raw.upload.jsonl"] and
                                 pair["files"]["raw.jsonl"]["sha256"] ==
                                 pair["files"]["raw.upload.jsonl"]["sha256"]
                                 for pair in pairs),
        "local_grade_exact": sum(pair["local_grade_matches_snapshot"] is True for pair in pairs),
        "local_grade_disagrees": sum(pair["local_grade_matches_snapshot"] is False for pair in pairs),
        "local_grade_missing_trace_score": sum(pair["local_grade_matches_snapshot"] is None
                                               for pair in pairs),
        "trace_score_bins": dict(Counter(
            "under_70" if pair["trace_score"] < 70 else
            "70_to_under_80" if pair["trace_score"] < 80 else "80_or_more"
            for pair in scored_trace)),
        "by_challenge": dict(sorted(by_challenge.items())),
        "unmatched_scored_attempt_ids": sorted(set(scores) - set(records)),
    }
    return pairs, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--agentmaster", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to((Path.cwd() / ".package-checks").resolve()):
        raise ValueError("output must remain under this repository's .package-checks")
    pairs, summary = match(args.dataset, args.agentmaster)
    output.mkdir(parents=True, exist_ok=True)
    (output / "pairs.jsonl").write_text(
        "".join(json.dumps(pair, ensure_ascii=False, sort_keys=True) + "\n" for pair in pairs))
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items()
                      if key not in {"by_challenge", "unmatched_scored_attempt_ids"}}, sort_keys=True))


if __name__ == "__main__":
    main()
