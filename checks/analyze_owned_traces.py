"""Audit all retrievable owned Attempt traces without publishing their contents."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cyberscientist import config, trace_selection

STAGES = {
    "setup": ("setup", "install", "environment", "配置", "环境", "安装"),
    "validation": ("validat", "verif", "test", "assert", "核验", "验证", "测试"),
    "computation": ("comput", "calculat", "simulat", "运行", "计算", "求解"),
    "analysis": ("analy", "inspect", "diagnos", "分析", "检查", "诊断"),
    "comparison": ("compar", "baseline", "benchmark", "对比", "比较", "基线"),
}


def _verified(root: Path, relative: Path, digest: str) -> bytes:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"audit path escapes root: {relative}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"hash mismatch: {relative}")
    return raw


def _kind(row: dict[str, Any]) -> str:
    return str(row.get("type") or row.get("step_type") or "unknown")


def trace_features(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive features only; keyword matches are not quality judgments."""
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("trace rows must be objects")
    types = Counter(_kind(row) for row in rows)
    texts = [" ".join(str(row.get(key) or "") for key in ("title", "body", "code"))
             for row in rows]
    lengths = [len(value) for value in texts]
    lowered = [value.lower() for value in texts]
    return {
        "step_count": len(rows),
        "type_counts": dict(sorted(types.items())),
        "distinct_type_count": len(types),
        "stage_mentions_heuristic": {
            stage: sum(any(word in text for word in words) for text in lowered)
            for stage, words in STAGES.items()},
        "error_followed_by_action_within_3_steps_heuristic": sum(
            _kind(row) == "error" and any(
                _kind(next_row) in {"decision", "tool_call", "observation"}
                for next_row in rows[index + 1:index + 4])
            for index, row in enumerate(rows)),
        "text_chars_total": sum(lengths),
        "text_chars_median": statistics.median(lengths) if lengths else None,
        "nonempty_body_count": sum(bool(row.get("body")) for row in rows),
        "nonempty_code_count": sum(bool(row.get("code")) for row in rows),
    }


def bundle_features(raw: bytes, api_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Mirror selection while preserving schema validity and API/bundle separation."""
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) > 1000 or sum(item.file_size for item in members) > 200_000_000:
            raise ValueError("bundle exceeds analysis limit")
        if len({item.filename for item in members}) != len(members):
            raise ValueError("bundle has duplicate member names")
        files = {item.filename: archive.read(item.filename) for item in members
                 if not item.is_dir()}
    selected = trace_selection.select(files)
    rows = list(selected.rows)
    api_keys = Counter((_kind(row), row.get("title")) for row in api_rows)
    bundle_keys = Counter((_kind(row), row.get("title")) for row in rows)
    return {
        "selection_rule": selected.rule,
        "selected_members": list(selected.selected_members),
        "selected_readable": selected.readable,
        "selected_rows": len(rows),
        "schema_shaped_rows": sum(bool(row.get("title") and
                                       (row.get("type") or row.get("step_type"))) for row in rows),
        "api_title_type_overlap": sum((api_keys & bundle_keys).values()),
        "raw_messages_files": sum(name.rsplit("/", 1)[-1] == "raw_messages.jsonl"
                                  for name in files),
    }


def _trace(root: Path, author: str, aid: str, filename: str,
           digest: str) -> list[dict[str, Any]]:
    rows = json.loads(_verified(root, Path("raw") / author / aid / filename, digest))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"invalid trace: {author}/{aid}/{filename}")
    return rows


def analyze(root: Path) -> dict[str, Any]:
    accounts = json.loads((root / "owned_lists_summary.json").read_text())
    collected = json.loads((root / "trace_inventory.json").read_text())
    direct = json.loads((root / "direct_mailbox_inventory.json").read_text())
    exports = json.loads((root / "export_mismatch_summary.json").read_text())
    direct_by_id = {row["attempt_id"]: row for row in direct}
    collected_by_id = {row["attempt_id"]: row for row in collected}
    if len(collected_by_id) != len(collected) or len(direct_by_id) != len(direct):
        raise ValueError("duplicate collected Attempt")
    by_account: dict[str, dict[str, Any]] = {}
    attempts: list[dict[str, Any]] = []
    bundle_digests: Counter[str] = Counter()
    for account in accounts:
        author = account["author_id"]
        raw_list = _verified(root, Path("attempt-lists") / (author + ".json"),
                             account["list_sha256"])
        listed = json.loads(raw_list)["attempts"]
        stat = {"visible_attempts": len(listed), "advertised_positive": 0,
                "retrieved_positive": 0, "retrieved_rows": 0,
                "legacy_trace_score_count": 0, "legacy_paired_count": 0,
                "bundle_count": 0, "retrieval_errors": 0,
                "mailbox_role": account.get("mailbox_role")}
        if len(listed) != account["visible_attempts"]:
            raise ValueError("list count changed from manifest")
        for listing in listed:
            aid = str(listing["id"])
            if str(listing.get("authorId")) != author:
                raise ValueError("Attempt author mismatch")
            item = collected_by_id.pop(aid)
            if item["author_id"] != author:
                raise ValueError("collected author mismatch")
            operator_rows = _trace(root, author, aid, "trace.json", item["files"]["trace.json"])
            direct_item = direct_by_id.get(aid)
            if direct_item:
                if direct_item["author_id"] != author:
                    raise ValueError("direct author mismatch")
                chosen_rows = _trace(root, author, aid, "direct-trace.json",
                                     direct_item["files"]["direct-trace.json"])
                source = "direct_agent"
            else:
                chosen_rows = operator_rows
                source = "operator"
            card = listing.get("scorecard") or {}
            if not isinstance(card, dict):
                card = {}
            legacy_score = card.get("trace_score")
            has_legacy_score = type(legacy_score) in (int, float)
            advertised = (listing.get("traceCount") or 0) > 0
            stat["advertised_positive"] += advertised
            stat["retrieved_positive"] += bool(chosen_rows)
            stat["retrieved_rows"] += len(chosen_rows)
            stat["legacy_trace_score_count"] += has_legacy_score
            stat["legacy_paired_count"] += has_legacy_score and bool(chosen_rows)
            stat["retrieval_errors"] += bool(item["errors"] or
                                             (direct_item and direct_item["errors"]))
            bundle_name = ("direct-bundle.zip" if direct_item and
                           "direct-bundle.zip" in direct_item["files"] else "bundle.zip")
            bundle_inventory = (direct_item if bundle_name == "direct-bundle.zip" else item)
            bundle = None
            if bundle_inventory and bundle_name in bundle_inventory["files"]:
                digest = bundle_inventory["files"][bundle_name]
                raw = _verified(root, Path("raw") / author / aid / bundle_name, digest)
                bundle = {"sha256": digest, **bundle_features(raw, chosen_rows)}
                bundle_digests[digest] += 1
                stat["bundle_count"] += 1
            attempts.append({
                "author_id": author, "attempt_id": aid,
                "status": listing.get("status"),
                "advertised_trace_count": listing.get("traceCount"),
                "operator_trace_count": len(operator_rows),
                "retrieved_trace_count": len(chosen_rows), "trace_source": source,
                "trace_sha256": (direct_item["files"]["direct-trace.json"] if direct_item
                                  else item["files"]["trace.json"]),
                "features": trace_features(chosen_rows) if chosen_rows else None,
                "legacy_trace_score": legacy_score if has_legacy_score else None,
                "generic_trace_quality": card.get("trace_quality"),
                "bundle": bundle,
            })
        by_account[author] = stat
    if collected_by_id:
        raise ValueError("collected Attempt missing from account lists")
    if set(direct_by_id) - {row["attempt_id"] for row in attempts}:
        raise ValueError("direct Attempt missing from account lists")
    positive = [row for row in attempts if row["retrieved_trace_count"]]
    advertised = [row for row in attempts if (row["advertised_trace_count"] or 0) > 0]
    return {
        "account_count": len(accounts), "visible_attempts": len(attempts),
        "advertised_positive": len(advertised), "retrieved_positive": len(positive),
        "retrieved_steps": sum(row["retrieved_trace_count"] for row in positive),
        "advertised_but_unretrievable": len(advertised) - len(positive),
        "legacy_trace_score_count": sum(row["legacy_trace_score"] is not None for row in attempts),
        "legacy_paired_count": sum(row["legacy_trace_score"] is not None for row in positive),
        "bundle_count": sum(bundle_digests.values()),
        "unique_bundle_count": len(bundle_digests),
        "duplicate_bundle_groups": sum(count > 1 for count in bundle_digests.values()),
        "export_mismatch_statuses": dict(Counter(row["status"] for row in exports)),
        "by_account": by_account, "attempts": attempts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.parent != (config.WORKSPACE_ROOT / ".package-checks").resolve() or not root.name.startswith("trace-all-"):
        raise ValueError("input must be a .package-checks/trace-all-* directory")
    result = analyze(root)
    (root / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({key: result[key] for key in (
        "account_count", "visible_attempts", "advertised_positive", "retrieved_positive",
        "retrieved_steps", "advertised_but_unretrievable", "legacy_trace_score_count",
        "legacy_paired_count", "bundle_count", "unique_bundle_count",
        "duplicate_bundle_groups", "export_mismatch_statuses")}, sort_keys=True))


if __name__ == "__main__":
    main()
