#!/usr/bin/env python3
"""Read-only review context report; old Runs are labeled approximate."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import statistics
from pathlib import Path


FIELDS = ("run_id", "review_id", "review_index", "mode", "trigger", "packet_bytes",
          "tokens_last_total", "tokens_input", "tokens_cached", "tokens_output",
          "latency_s", "trace_reads", "outcome", "direction_changed",
          "silent_direction_within_window", "quality")


def rows(conn: sqlite3.Connection, run_id: str | None = None,
         window_events: int = 20) -> list[dict]:
    params = (run_id,) if run_id else ()
    where = "WHERE run_id=?" if run_id else ""
    events = conn.execute(f"SELECT run_id,seq,type,payload,recorded_at FROM events {where}"
                          " ORDER BY run_id,seq", params).fetchall()
    groups: dict[str, list[dict]] = {}
    for row in events:
        groups.setdefault(row["run_id"], []).append(dict(row) | {"payload": json.loads(row["payload"])})
    output = []
    for rid, group in groups.items():
        metrics = [e for e in group if e["type"] == "brain.review_metrics"]
        if metrics:
            for index, event in enumerate(metrics, 1):
                payload = event["payload"]
                later = [e for e in group if event["seq"] < e["seq"] <= event["seq"] + window_events]
                output.append({k: payload.get(k) for k in FIELDS} |
                              {"run_id": rid, "review_index": index, "quality": "measured",
                               "silent_direction_within_window":
                               any(e["type"] in ("trial.created", "run.finished", "guidance.queued")
                                   for e in later) if payload.get("outcome") == "silent" else None})
            continue
        starts = [e for e in group if e["type"] == "brain.review_started"]
        for index, start in enumerate(starts, 1):
            end_seq = starts[index]["seq"] if index < len(starts) else float("inf")
            interval = [e for e in group if start["seq"] < e["seq"] < end_seq]
            usage = [e["payload"].get("usage", {}).get("last", {}) for e in interval
                     if e["type"] == "brain.usage.updated"]
            last = usage[-1] if usage else {}
            outcome = "error" if any(e["type"] == "brain.error" for e in interval) else "unknown"
            output.append({"run_id": rid, "review_id": start["payload"].get("review_id"),
                           "review_index": index, "mode": start["payload"].get("mode"),
                           "trigger": start["payload"].get("trigger"), "packet_bytes": None,
                           "tokens_last_total": last.get("totalTokens"),
                           "tokens_input": last.get("inputTokens"),
                           "tokens_cached": last.get("cachedInputTokens"),
                           "tokens_output": last.get("outputTokens"),
                           "latency_s": None, "trace_reads": sum(e["type"] == "brain.trace_read" for e in interval),
                           "outcome": outcome, "direction_changed": None,
                           "silent_direction_within_window": None, "quality": "approximate"})
    return output


def summarize(data: list[dict]) -> dict:
    tokens = [r["tokens_last_total"] for r in data if type(r["tokens_last_total"]) in (int, float)]
    latency = sorted(r["latency_s"] for r in data if type(r["latency_s"]) in (int, float))
    outcomes: dict[str, int] = {}
    for item in data:
        outcomes[item["outcome"] or "unknown"] = outcomes.get(item["outcome"] or "unknown", 0) + 1
    return {"reviews": len(data), "measured": sum(r["quality"] == "measured" for r in data),
            "tokens_last_total_median": statistics.median(tokens) if tokens else None,
            "tokens_last_total_growth_first_to_last": tokens[-1] - tokens[0] if len(tokens) > 1 else None,
            "latency_p90_s": latency[max(0, (len(latency) * 9 + 9) // 10 - 1)] if latency else None,
            "outcome_counts": outcomes,
            "silent_direction_changed_rate": (sum(r["silent_direction_within_window"] is True for r in data
                                                  if r["outcome"] == "silent" and r["quality"] == "measured") /
                                              sum(r["outcome"] == "silent" and r["quality"] == "measured" for r in data))
                                             if any(r["outcome"] == "silent" and r["quality"] == "measured" for r in data) else None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--window-events", type=int, default=20)
    args = parser.parse_args()
    uri = f"file:{args.database.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    data = rows(conn, args.run_id, args.window_events)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(data)
    print(json.dumps(summarize(data), ensure_ascii=False))


if __name__ == "__main__":
    main()
