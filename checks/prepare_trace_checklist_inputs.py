"""Prepare ignored, verified v6 checklist inputs from local historical archives."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from audit_agentmaster_grader_diagnostics import output_index
from build_trace_conversion_variants import CLI_SHA, digest


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def submission_index(root: Path) -> dict[str, Path]:
    index = {}
    for path in (*root.glob("*/iterations/*/submission/submission.json"),
                 *root.glob("*/harvest/submission/submission.json")):
        value = json.loads(path.read_text()).get("attempt_id")
        if value is not None:
            key = str(value)
            if key in index:
                raise ValueError("duplicate submission ID in local archive")
            index[key] = path.parent.parent
    return index


def context(iteration: Path, expected_tree: str | None, root: Path, sample: str) -> tuple[str, str]:
    challenge_path = iteration / "challenge.json"
    if not challenge_path.is_file() and iteration.name == "harvest":
        challenge_path = iteration.parent / "challenge.json"
    challenge = json.loads(challenge_path.read_text())
    text = challenge["raw"]["content"]
    if not isinstance(text, str) or not text:
        raise ValueError(f"missing local task for {sample}")
    task = root / "tasks" / (sample + ".txt")
    task.parent.mkdir(exist_ok=True)
    task.write_text(text)
    outputs = iteration / "workspace_snapshot/outputs"
    if not outputs.is_dir():
        argv = json.loads((iteration / "submission/command.json").read_text())["argv"]
        outputs = Path(argv[argv.index("--outputs") + 1])
    if not outputs.is_dir():
        raise ValueError(f"missing outputs for {sample}")
    if expected_tree:
        tree = hashlib.sha256(json.dumps(output_index(outputs), sort_keys=True).encode()).hexdigest()
        if tree != expected_tree:
            raise ValueError(f"output snapshot changed for {sample}")
    return str(task), str(outputs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversions", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--older-pairs", type=Path, required=True)
    parser.add_argument("--agentmaster", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.out.resolve()
    if not (root / ".ignored-evidence").exists():
        raise ValueError("output must be an explicitly marked ignored directory")
    if digest(args.cli) != CLI_SHA:
        raise ValueError("installed CLI hash changed")
    conversions = read_jsonl(args.conversions)
    diagnostics = read_jsonl(args.diagnostics)
    older = read_jsonl(args.older_pairs)
    if digest(args.older_pairs) != "71fa7fad213fc4855b039d3dee5436d70b5f5f1a7268fa0fce73234a9fe5ba9a":
        raise ValueError("older-pair source hash changed")
    if not (len(conversions), len(diagnostics), len(older)) == (63, 63, 71):
        raise ValueError("expected 63 main and 71 older records")
    by_attempt = {row["attempt_id"]: row for row in diagnostics}
    local = submission_index(args.agentmaster / "store/T0")
    output = []
    metadata = []
    for row in conversions:
        sample = row["sample"]
        receipt = by_attempt[row["attempt_id"]]
        iteration = local[row["attempt_id"]]
        raw_receipt = iteration / "grader/grader.raw.json"
        if digest(raw_receipt) != receipt["receipt_sha256"]:
            raise ValueError(f"v8 receipt changed for {sample}")
        recorded = json.loads(raw_receipt.read_text())["detail"]["resultsJson"]
        if (recorded["trace_score"] != receipt["trace_score"] or
                recorded["trace_decision"] != receipt["decision"] or
                [r["code"] for r in recorded.get("trace_low_score_reasons") or []]
                != [r["code"] for r in receipt["reasons"]]):
            raise ValueError(f"v8 labels no longer match source receipt for {sample}")
        task, artifacts = context(iteration, receipt["output_tree_sha256"], root, sample)
        metadata.append({"sample": sample, "group": "main", "score": receipt["trace_score"],
                         "decision": receipt["decision"], "reasons": [item["code"] for item in receipt["reasons"]],
                         "native_sha256": receipt["native_trace_sha256"],
                         "native_path": row["native_path"], "source_kind": receipt["native_trace_source_kind"]})
        for variant in ("cli", "fix", "native"):
            value = row[variant]
            output.append({"sample": sample, "variant": variant, "trace": value["path"],
                           "expected_sha256": value["sha256"], "task": task, "outputs": artifacts})
    fixed = root / "playground-cli-fixed.js"
    if not fixed.is_file():
        raise ValueError("run W1 first; patched CLI missing")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(root / "empty-home"),
           "LANG": "C.UTF-8", "NODE_OPTIONS": "--require=" + str(root / "offline.cjs")}
    for number, pair in enumerate(older, 1):
        sample = f"A{number:02d}"
        if not pair["valid_join"] or pair["trace_score"] is None:
            raise ValueError(f"invalid old pair {sample}")
        iteration = Path(pair["iteration"])
        native = Path(pair["files"]["raw.upload.jsonl"]["path"])
        if digest(native) != pair["files"]["raw.upload.jsonl"]["sha256"]:
            raise ValueError(f"old trace changed {sample}")
        task, artifacts = context(iteration, None, root, sample)
        metadata.append({"sample": sample, "group": "older", "score": pair["trace_score"],
                         "score_is_final": pair["score_is_final"]})
        for variant, cli in (("cli", args.cli), ("fix", fixed)):
            target = root / "older-converted" / sample / (variant + ".jsonl")
            target.parent.mkdir(parents=True, exist_ok=True)
            child = subprocess.run(["node", str(cli), "trace", "convert", "--trace", str(native),
                                    "--out", str(target)], env=env, capture_output=True,
                                   text=True, timeout=40)
            if child.returncode:
                raise ValueError(f"old conversion failed {sample} {variant}: {child.returncode}")
            output.append({"sample": sample, "variant": variant, "trace": str(target),
                           "expected_sha256": digest(target), "task": task, "outputs": artifacts})
    (root / "checklist-manifest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2))
    (root / "checklist-labels.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(json.dumps({"main": len(conversions), "older": len(older), "checklist_inputs": len(output)}))


if __name__ == "__main__":
    main()
