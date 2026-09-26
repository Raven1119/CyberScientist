"""Pure, conservative mirror of the ARM snapshot's trace_row_selection rules."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Any


@dataclass(frozen=True)
class TraceSelection:
    bundle_root: str
    selected_members: tuple[str, ...]
    rule: str
    rows: tuple[dict[str, Any], ...]
    unresolved_claims: tuple[str, ...]
    readable: bool


def bundle_root(files: Mapping[str, bytes]) -> str:
    names = tuple(files)
    top = {name.split("/", 1)[0] for name in names}
    return (next(iter(top)) + "/" if len(top) == 1 and
            all("/" in name for name in names) else "")


def select(files: Mapping[str, bytes]) -> TraceSelection:
    """Select only the rows the platform would judge, without modifying inputs.

    The protocol is an ordered first-match rule set.  A missing .jsonl pointer
    records an unresolved claim even when a directory fallback is available.
    """
    names = tuple(files)
    root = bundle_root(files)
    manifest_name = root + "arm_manifest.json"
    if manifest_name not in files:
        raise ValueError("arm_manifest.json missing at bundle root")
    try:
        manifest = json.loads(files[manifest_name])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("arm_manifest.json cannot be parsed") from exc
    if not isinstance(manifest, dict):
        raise ValueError("arm_manifest.json must be an object")
    pointer = manifest.get("trace")
    if "trace" in manifest and not isinstance(pointer, (str, dict)):
        raise ValueError("manifest.trace has invalid type")
    selected: tuple[str, ...] = ()
    rule = "none"
    unresolved: tuple[str, ...] = ()
    if isinstance(pointer, str) and pointer.endswith(".jsonl"):
        member = root + pointer
        if member in files:
            selected, rule = (member,), "manifest_pointer"
        else:
            unresolved = (pointer,)
    if not selected:
        for directory in ("traces/", "trace/"):
            eligible = tuple(sorted(name for name in names
                if name.startswith(root + directory) and name.endswith(".jsonl")
                and name.rsplit("/", 1)[-1] != "raw_messages.jsonl"))
            if eligible:
                selected, rule = eligible, "directory_scan"
                break
    if not selected:
        for candidate in ("traces/trace.json", "trace.json"):
            if root + candidate in files:
                selected, rule = (root + candidate,), "legacy_json_array"
                break
    rows: list[dict[str, Any]] = []
    readable = True
    for member in selected:
        try:
            raw = files[member].decode("utf-8")
            if rule == "legacy_json_array":
                parsed = json.loads(raw)
                if not isinstance(parsed, list) or not all(isinstance(row, dict) for row in parsed):
                    raise ValueError("legacy trace is not an array of steps")
                rows.extend(parsed)
            else:
                for line in raw.splitlines():
                    if line.strip():
                        parsed = json.loads(line)
                        if not isinstance(parsed, dict):
                            raise ValueError("JSONL trace row is not an object")
                        rows.append(parsed)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            readable = False
    return TraceSelection(root, selected, rule, tuple(rows), unresolved, readable)
