"""Build pinned, offline conversion variants for 63 locally archived v8 traces.

Outputs include raw research evidence and must stay in an ignored directory.
The original CLI installation and the upstream scorer are never modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess

from audit_agentmaster_grader_diagnostics import native_trace_index


CLI_SHA = "d231fefe0f11a481866aeae399906fc587e75d95c0cf08ff405b3f6f7ee48b03"
SOURCE_SHA = "afafd718c1eca6c25fa81231905988b436ff03684581d0410f8cc549599dfa46"
SOURCE_COMMIT = "81c434907e7b0a2feccc79236f6601f7abbc1d84"
OLD = "    if (opencodeEventLike(rows))\n        return convertOpenCodeEvents(rows, source);"
NEW = ("    if (opencodeEventLike(rows) && !(codexEventLike(rows) && "
       "rows.every((row) => ![\"step_start\", \"step_finish\", \"text\", \"tool_use\"]"
       ".includes(stringValue(row.type) || \"\"))))\n"
       "        return convertOpenCodeEvents(rows, source);")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def counts(items: list[dict], native: bool = False) -> dict[str, int]:
    if native:
        calls = Counter(str(x.get("item", {}).get("id")) for x in items
                        if x.get("type") == "item.started" and x.get("item", {}).get("type") == "command_execution")
        results = Counter(str(x.get("item", {}).get("id")) for x in items
                          if x.get("type") == "item.completed" and x.get("item", {}).get("type") == "command_execution")
        errors = sum(x.get("type") == "error" or
                     x.get("type") == "item.completed" and x.get("item", {}).get("type") == "error"
                     for x in items)
    else:
        calls = Counter(str(x.get("tool_call_id")) for x in items if x.get("step_type") == "tool_call")
        results = Counter(str(x.get("tool_call_id")) for x in items if x.get("step_type") == "tool_result")
        errors = sum(x.get("step_type") == "error" for x in items)
    return {"events": len(items), "paired_tool_calls": sum((calls & results).values()),
            "errors": errors}


def semantic_digest(items: list[dict]) -> str:
    """Ignore only CLI-generated wall-clock fallback timestamps."""
    stable = [{k: v for k, v in row.items() if k != "timestamp"} for row in items]
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--agentmaster", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if not (out / ".ignored-evidence").exists():
        raise SystemExit("Output must be an explicitly marked ignored evidence directory")
    assert digest(args.cli) == CLI_SHA, "CLI hash changed"
    assert digest(args.upstream / "src/index.ts") == SOURCE_SHA, "scorer source hash changed"
    assert subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True).strip() == SOURCE_COMMIT
    if "MIT License" not in (args.upstream / "LICENSE").read_text():
        raise ValueError("upstream license changed")
    records = rows(args.diagnostics)
    if len(records) != 63 or len({x["attempt_id"] for x in records}) != 63:
        raise ValueError("expected 63 distinct historical receipts")
    index = native_trace_index(args.agentmaster / "store/T0")
    copy = out / "playground-cli-fixed.js"
    original = args.cli.read_text()
    if original.count(OLD) != 1:
        raise ValueError("expected one pinned OpenCode/Codex precedence branch")
    copy.write_text(original.replace(OLD, NEW, 1))
    # The bundled CLI imports one sibling module; preserve its exact bytes.
    sibling = args.cli.with_name("task-authoring.js")
    (out / "task-authoring.js").write_bytes(sibling.read_bytes())
    (out / "package.json").write_text('{"type":"module"}\n')
    patch = "".join(difflib.unified_diff(original.splitlines(keepends=True),
        copy.read_text().splitlines(keepends=True), fromfile="a/dist/index.js", tofile="b/dist/index.js", n=3))
    changed = [line for line in patch.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    if len(changed) > 20:
        raise ValueError("conversion patch exceeds 20 changed lines")
    (out / "converter.patch").write_text(patch)
    # The bundled CLI only takes a local trace path. Remove login context and
    # block Node network primitives in both the unchanged and patched processes.
    preload = out / "offline.cjs"
    preload.write_text(
        "globalThis.fetch=()=>{throw Error('offline conversion: fetch blocked')};\n"
        "for(const name of ['http','https'])require(name).request=()=>{throw Error('offline conversion: request blocked')};\n"
        "require('net').connect=()=>{throw Error('offline conversion: connect blocked')};\n"
    )
    isolated_home = out / "empty-home"
    isolated_home.mkdir(exist_ok=True)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(isolated_home),
           "LANG": "C.UTF-8", "NODE_OPTIONS": "--require=" + str(preload)}
    details = []
    for number, record in enumerate(records, 1):
        key = f"S{number:02d}"
        paths = index.get(record["native_trace_sha256"], [])
        same = [path for path in paths if path.parent.parent.parent.name == record["challenge_id"]]
        path = same[0] if same else paths[0] if paths else None
        entry = {"sample": key, "attempt_id": record["attempt_id"],
                 "native_sha256": record["native_trace_sha256"], "source_kind": record["native_trace_source_kind"]}
        if path is None:
            entry["missing_reason"] = "hashed native trace unavailable"
            details.append(entry)
            continue
        if digest(path) != record["native_trace_sha256"]:
            raise ValueError(f"trace hash changed for {key}")
        entry["native_path"] = str(path)
        entry["native"] = {"path": str(path), "sha256": digest(path), **counts(rows(path), native=True)}
        for variant, cli in (("cli", args.cli), ("fix", copy)):
            target = out / "converted" / key / f"{variant}.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            child = subprocess.run(["node", str(cli), "trace", "convert", "--trace", str(path),
                                    "--out", str(target)], env=env, capture_output=True,
                                   text=True, timeout=40)
            if child.returncode != 0:
                entry[variant] = {"missing_reason": "conversion failed", "exit_code": child.returncode,
                                  "stderr_excerpt": child.stderr[:300]}
                continue
            converted = rows(target)
            entry[variant] = {"path": str(target), "sha256": digest(target),
                              "semantic_sha256": semantic_digest(converted), **counts(converted)}
        details.append(entry)
    with (out / "conversions.jsonl").open("w") as stream:
        for item in details:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    changed_samples = [x["sample"] for x in details if "sha256" in x.get("cli", {})
                       and "sha256" in x.get("fix", {})
                       and x["cli"]["sha256"] != x["fix"]["sha256"]]
    semantic_changes = [x["sample"] for x in details if "semantic_sha256" in x.get("cli", {})
                        and "semantic_sha256" in x.get("fix", {})
                        and x["cli"]["semantic_sha256"] != x["fix"]["semantic_sha256"]]
    e008 = [x for x in details if x["native_sha256"] == "81d5f8c96597b178757826e03d0f6ea15ed1b43cb79ee2ecf06f13db675aa538"]
    if len(e008) != 1 or e008[0]["cli"]["events"] != 1 or e008[0]["cli"]["errors"] != 1 or e008[0]["fix"]["paired_tool_calls"] <= 0:
        raise ValueError("E008 conversion regression not reproduced")
    summary = {"rows": len(details), "native_found": sum("native" in x for x in details),
               "cli_ok": sum("sha256" in x.get("cli", {}) for x in details),
               "fix_ok": sum("sha256" in x.get("fix", {}) for x in details),
               "changed_samples": changed_samples, "semantic_changed_samples": semantic_changes,
               "timestamp_only_changed_samples": sorted(set(changed_samples) - set(semantic_changes)),
               "e008_sample": e008[0]["sample"], "patched_cli_sha256": digest(copy),
               "patch_changed_lines": len(changed), "source_sha256": SOURCE_SHA, "cli_sha256": CLI_SHA}
    (out / "conversion-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
