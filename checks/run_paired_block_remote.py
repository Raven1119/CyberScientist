"""Prepare pinned, pre-staged dependencies and replay proofs INSIDE Bohrium.

The host must provide verified archives under --staged. This script has no
credentials or platform authority. Its deadline leaves the host time to retrieve
evidence and delete the authorized sandbox. Never run it on the host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=1500)
    parser.add_argument("--only-broad", action="store_true", help="Full-cache follow-up for E000, with E009 as positive control")
    args = parser.parse_args()
    staged, output = args.staged.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + args.seconds
    status = {"status": "running", "steps": []}
    env = {k: v for k, v in os.environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
    env.update(NO_PROXY="*", no_proxy="*", MATHLIB_CACHE_DIR="/workspace/mathlib-cache")
    env["PATH"] = "/workspace/lean/bin:" + env["PATH"]
    project = Path("/workspace/paired-block-project")

    def save() -> None:
        (output / "status.json").write_text(json.dumps(status, indent=2))

    def run(name: str, argv: list[str], timeout: int) -> None:
        remaining = int(deadline - time.monotonic())
        if remaining < 10:
            raise TimeoutError("preparation/replay deadline reached")
        item = {"name": name, "argv": argv, "started_at": time.time()}
        status["steps"].append(item)
        save()
        with (output / (name + ".log")).open("w") as log:
            try:
                result = subprocess.run(argv, cwd=project, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=min(timeout, remaining))
                item["exit_code"] = result.returncode
                if result.returncode:
                    raise RuntimeError(f"{name} exited {result.returncode}")
            finally:
                item["ended_at"] = time.time()
                save()

    try:
        manifest = json.loads((staged / "manifest.json").read_text())
        for name, expected in manifest["sha256"].items():
            path = staged / name
            if path.resolve().parent != staged:
                raise ValueError("staged dependency escapes its directory")
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("staged dependency hash mismatch")
        project.mkdir()
        shutil.copytree(staged / "project", project, dirs_exist_ok=True)
        Path("/workspace/lean").mkdir()
        packages = project / ".lake/packages"
        packages.mkdir(parents=True)
        run("toolchain", ["tar", "--zstd", "-xf", str(staged / "lean.tar.zst"), "--no-same-owner",
                          "--strip-components=1", "-C", "/workspace/lean"], 120)
        run("sources", ["tar", "-xzf", str(staged / "packages.tar.gz"), "--no-same-owner", "-C", str(packages)], 90)
        revisions = []
        for package in json.loads((project / "lake-manifest.json").read_text())["packages"]:
            got = subprocess.check_output(["git", "-C", str(packages / package["name"]), "rev-parse", "HEAD"], text=True).strip()
            if got != package["rev"]:
                raise ValueError("dependency revision mismatch")
            revisions.append({"package": package["name"], "revision": got})
        (output / "dependency-revisions.json").write_text(json.dumps(revisions, indent=2))
        cache = Path(env["MATHLIB_CACHE_DIR"])
        cache.mkdir()
        shutil.copy2(staged / "curl-7.88.1", cache / "curl-7.88.1")
        (cache / "curl-7.88.1").chmod(0o755)
        # Public cache artifacts may be relayed by the host after a stalled
        # remote download. Their hashes are checked in the staged manifest.
        for path in staged.glob("*.ltar"):
            if path.name not in manifest["sha256"]:
                raise ValueError("cache artifact missing from staged manifest")
            shutil.copy2(path, cache / path.name)
        run("version", ["lean", "--version"], 20)
        modules = [line.split()[1] for line in (project / "PairCore.lean").read_text().splitlines() if line.startswith("import ")]
        if args.only_broad:
            run("full-cache", ["lake", "exe", "cache", "get"], 600)
        else:
            run("target-cache", ["lake", "exe", "cache", "get", *modules], 600)
        run("paircore", ["lake", "build", "PairCore"], 180)
        command = [sys.executable, str(staged / "replay_paired_block.py"), "--scorer", str(staged / "scorer/score.py"),
                   "--inputs", str(staged / "cases"), "--labels", str(staged / "labels.json"),
                   "--project", str(project), "--version", manifest["scorer_version"]]
        if args.only_broad:
            run("broad-import-replay", [*command, "--output", str(output / "broad"), "--samples", "E000", "E009", "--skip-mutations"], 180)
        else:
            run("core-replay", [*command, "--output", str(output / "core"), "--samples", "E002", "E005", "E009", "E013"], 900)
            status["core_finished"] = True
            save()
        # E000 imports all Mathlib; retain the original input and fetch its full
        # dependency closure only after the main proof/negative controls finish.
        if not args.only_broad and deadline - time.monotonic() > 360:
            run("full-cache", ["lake", "exe", "cache", "get"], min(600, int(deadline - time.monotonic()) - 150))
            run("broad-import-replay", [*command, "--output", str(output / "broad"), "--samples", "E000", "--skip-mutations"], 140)
        status["status"] = "completed"
    except Exception as exc:
        status.update(status="incomplete", reason=f"{type(exc).__name__}: {exc}")
    finally:
        status["ended_at"] = time.time()
        save()
    print(json.dumps(status))
    if status["status"] != "completed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
