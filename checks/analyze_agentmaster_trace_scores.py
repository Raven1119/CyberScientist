"""Exploratory structural audit of final, locally paired historical traces.

This does not reconstruct the platform's normalized trace or assert causality.
It writes only metadata under the repository's ignored .package-checks tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


FEATURES = ("upload_events", "projected_rows", "completed_commands",
            "failed_commands", "agent_messages", "message_chars", "file_changes")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(pair: dict[str, Any]) -> dict[str, Any]:
    """Hash-check both local trace sources before deriving content-free counts."""
    files = pair["files"]
    for name in ("raw.upload.jsonl", "traces/trace.jsonl"):
        record = files[name]
        if record is None or _hash(Path(record["path"])) != record["sha256"]:
            raise ValueError(f"trace hash mismatch: {pair['attempt_id']} {name}")
    events = [json.loads(line) for line in Path(files["raw.upload.jsonl"]["path"]).read_text().splitlines()
              if line.strip()]
    projection = [json.loads(line) for line in Path(files["traces/trace.jsonl"]["path"]).read_text().splitlines()
                  if line.strip()]
    completed = [event.get("item") for event in events if event.get("type") == "item.completed"
                 and isinstance(event.get("item"), dict)]
    commands = [item for item in completed if item.get("type") == "command_execution"]
    messages = [item for item in completed if item.get("type") == "agent_message"]
    features = {
        "upload_events": len(events), "projected_rows": len(projection),
        "completed_commands": len(commands),
        "failed_commands": sum(item.get("exit_code") not in (0, None) for item in commands),
        "agent_messages": len(messages),
        "message_chars": sum(len(str(item.get("text") or "")) for item in messages),
        "file_changes": sum(item.get("type") == "file_change" for item in completed),
    }
    return {"attempt_id": pair["attempt_id"], "challenge_id": pair["challenge_id"],
            "trace_score": pair["trace_score"], "score_is_final": pair["score_is_final"],
            "harbor_score": pair.get("harbor_score"),
            "features": features}


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for start in range(len(order)):
        if start and values[order[start]] == values[order[start - 1]]:
            continue
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for index in order[start:end]:
            ranks[index] = rank
    return ranks


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) != len(y) or len(x) < 3:
        return None
    a, b = _ranks(x), _ranks(y)
    ma, mb = statistics.mean(a), statistics.mean(b)
    numerator = sum((u - ma) * (v - mb) for u, v in zip(a, b))
    denominator = (sum((u - ma) ** 2 for u in a) * sum((v - mb) ** 2 for v in b)) ** 0.5
    return numerator / denominator if denominator else None


def _balanced_accuracy(actual: list[bool], predicted: list[bool]) -> float:
    recalls = [sum(p == label for p, a in zip(predicted, actual) if a == label) /
               sum(a == label for a in actual) for label in (False, True)
               if any(a == label for a in actual)]
    return statistics.mean(recalls)


def _fit_stump(rows: list[dict[str, Any]], feature: str, cutoff: float):
    values = sorted({row["features"][feature] for row in rows})
    thresholds = [values[0] - 1] + [(a + b) / 2 for a, b in zip(values, values[1:])] + [values[-1]]
    actual = [row["trace_score"] >= cutoff for row in rows]
    candidates = []
    for threshold in thresholds:
        for low_is_positive in (True, False):
            predicted = [(row["features"][feature] <= threshold) == low_is_positive for row in rows]
            candidates.append((_balanced_accuracy(actual, predicted),
                               sum(p == a for p, a in zip(predicted, actual)),
                               threshold, low_is_positive))
    _, _, threshold, low_is_positive = max(candidates, key=lambda x: (x[0], x[1], -abs(x[2])))
    return lambda row: (row["features"][feature] <= threshold) == low_is_positive


def leave_one_challenge_out(rows: list[dict[str, Any]], feature: str | None,
                            cutoff: float) -> dict[str, Any]:
    """Fit on other challenges only; preserve all held-out predictions."""
    predictions = []
    for challenge in sorted({row["challenge_id"] for row in rows}):
        train = [row for row in rows if row["challenge_id"] != challenge]
        test = [row for row in rows if row["challenge_id"] == challenge]
        if not train:
            raise ValueError("need at least two challenges")
        if feature is None:
            positive = sum(row["trace_score"] >= cutoff for row in train)
            majority = positive * 2 >= len(train)
            predict = lambda row: majority
        else:
            predict = _fit_stump(train, feature, cutoff)
        for row in test:
            predictions.append({"attempt_id": row["attempt_id"], "challenge_id": challenge,
                                "actual": row["trace_score"] >= cutoff,
                                "predicted": bool(predict(row))})
    actual = [row["actual"] for row in predictions]
    predicted = [row["predicted"] for row in predictions]
    return {"n": len(rows), "correct": sum(a == p for a, p in zip(actual, predicted)),
            "accuracy": sum(a == p for a, p in zip(actual, predicted)) / len(rows),
            "balanced_accuracy": _balanced_accuracy(actual, predicted),
            "false_positive": sum(p and not a for a, p in zip(actual, predicted)),
            "false_negative": sum(a and not p for a, p in zip(actual, predicted)),
            "predictions": predictions}


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    final = [row for row in rows if row["score_is_final"] and
             row["trace_score"] is not None]
    if not final:
        raise ValueError("no final paired scores")
    by_challenge = defaultdict(list)
    for row in final:
        by_challenge[row["challenge_id"]].append(row)
    structural = {}
    for feature in FEATURES:
        structural[feature] = {
            "pooled_spearman": spearman([r["features"][feature] for r in final],
                                          [r["trace_score"] for r in final]),
            "within_challenge_spearman": {
                key: spearman([r["features"][feature] for r in group],
                              [r["trace_score"] for r in group])
                for key, group in by_challenge.items() if len(group) >= 3},
        }
    groups = {}
    for challenge, group in sorted(by_challenge.items()):
        low = [r for r in group if r["trace_score"] < 70]
        high = [r for r in group if r["trace_score"] >= 80]
        groups[challenge] = {
            "final_count": len(group), "under_70": len(low), "80_or_more": len(high),
            "upload_events_median_under_70": statistics.median(
                r["features"]["upload_events"] for r in low) if low else None,
            "upload_events_median_80_or_more": statistics.median(
                r["features"]["upload_events"] for r in high) if high else None,
        }
    cv = {str(cutoff): {
        "majority": leave_one_challenge_out(final, None, cutoff),
        "upload_events": leave_one_challenge_out(final, "upload_events", cutoff),
        "failed_commands": leave_one_challenge_out(final, "failed_commands", cutoff),
    } for cutoff in (70, 80)}
    with_harbor = [row for row in final if row["harbor_score"] is not None]
    return {"paired_rows": len(rows), "final_rows": len(final),
            "score_counts": dict(sorted(Counter(r["trace_score"] for r in final).items())),
            "nonfinal_score_counts": dict(sorted(Counter(r["trace_score"] for r in rows
                                                       if not r["score_is_final"]).items())),
            "harbor_trace_pooled_spearman": spearman(
                [r["harbor_score"] for r in with_harbor],
                [r["trace_score"] for r in with_harbor]),
            "feature_correlations": structural, "by_challenge": groups,
            "leave_one_challenge_out": cv}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to((Path.cwd() / ".package-checks").resolve()):
        raise ValueError("output must remain in this repository's .package-checks")
    pairs = [json.loads(line) for line in args.pairs.read_text().splitlines() if line.strip()]
    rows = [extract(pair) for pair in pairs if pair["valid_join"]]
    report = analyze(rows)
    report["pairs_sha256"] = _hash(args.pairs)
    output.mkdir(parents=True, exist_ok=True)
    (output / "features.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    (output / "analysis.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"paired_rows": report["paired_rows"], "final_rows": report["final_rows"],
                      "cv": {cutoff: {name: {key: result[key] for key in ("correct", "n", "balanced_accuracy")}
                                      for name, result in methods.items()}
                             for cutoff, methods in report["leave_one_challenge_out"].items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
