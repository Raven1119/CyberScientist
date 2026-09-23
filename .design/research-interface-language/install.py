#!/usr/bin/env python3
"""Install this local design skill. Python 3.9+, standard library, no network.

Examples:
  python install.py --project "D:/Projects/App"
  python install.py --global --agent codex
  python install.py --project /work/app --agent claude --replace
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import sys
import tempfile
from datetime import datetime, timezone

NAME = "research-interface-language"
BEGIN = "<!-- BEGIN research-interface-language -->"
END = "<!-- END research-interface-language -->"
AGENTS = {"codex": ".agents", "kimi": ".kimi", "claude": ".claude"}
ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(source: Path) -> dict:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        part = PurePosixPath(relative)
        if part.is_absolute() or PureWindowsPath(relative).drive or ".." in part.parts or "\\" in relative:
            raise ValueError("Unsafe path in package manifest: " + relative)
        path = source / relative
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError("Package integrity check failed: " + relative)
    return manifest


def instruction_path(project: Path, agent: str) -> Path:
    if agent == "claude":
        return project / "CLAUDE.md"
    override = project / "AGENTS.override.md"
    if agent == "codex" and override.exists():
        if override.is_symlink():
            raise ValueError("Refusing to edit a symlinked AGENTS.override.md.")
        if override.read_bytes().strip():
            return override
    return project / "AGENTS.md"


def block_for(relative_skill: str) -> str:
    return f"""{BEGIN}
## Shared frontend design language

For frontend visual or interaction work, read
`{relative_skill}/SKILL.md` first.
Inspect its `assets/reference.html`, screenshots and relevant motion map.
Apply the V9 upstream-motion / cool-graphite baseline and namespaced tokens.
Keep project business behavior and layout; do not copy demo tasks or fake runs.
Do not replace approved motion with visual approximations.
Follow the skill's validation checklist and report actual test results.
{END}"""


def merged_instructions(old: bytes, block: str) -> bytes:
    """Preserve bytes outside the managed section, including BOM and CRLF."""
    newline = b"\r\n" if b"\r\n" in old else b"\n"
    start, end = BEGIN.encode(), END.encode()
    if old.count(start) != old.count(end) or old.count(start) > 1:
        raise ValueError("Managed instruction markers are malformed; no files changed.")
    encoded = block.encode("utf-8").replace(b"\n", newline)
    if start in old:
        a, b = old.index(start), old.index(end)
        if b < a:
            raise ValueError("Instruction markers are out of order; no files changed.")
        return old[:a] + encoded + old[b + len(end):]
    suffix = b"" if not old or old.endswith(newline * 2) else (newline if old.endswith(newline) else newline * 2)
    return old + suffix + encoded + newline


def same_install(destination: Path, manifest: dict, source: Path) -> bool:
    if not destination.is_dir() or destination.is_symlink():
        return False
    allowed = set(manifest["files"]) | {"manifest.json", ".installed.json"}
    actual = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    if actual - allowed:
        return False
    if any(p.is_symlink() for p in destination.rglob("*")):
        return False
    return all((destination / rel).is_file() and digest(destination / rel) == sha for rel, sha in manifest["files"].items()) and (destination / "manifest.json").is_file() and (destination / "manifest.json").read_bytes() == (source / "manifest.json").read_bytes()


def atomic_write(path: Path, data: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".ril-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(source: Path, *, project: Path | None, agent: str, replace: bool) -> dict:
    manifest = load_manifest(source)
    base = project.expanduser().resolve() if project is not None else Path.home().resolve()
    if not base.is_dir():
        raise ValueError("Project/home directory must already exist: " + str(base))
    skill_relative = f"{AGENTS[agent]}/skills/{NAME}"
    destination = base / skill_relative
    # Avoid writing through skill-directory symlinks to unrelated locations.
    for directory in [base / AGENTS[agent], base / AGENTS[agent] / "skills", destination]:
        if directory.is_symlink():
            raise ValueError("Refusing to replace or write through a symlink: " + str(directory))
    instruction = instruction_path(base, agent) if project is not None else None
    if instruction and instruction.is_symlink():
        raise ValueError("Refusing to edit a symlinked instruction file: " + str(instruction))
    if instruction and instruction.exists() and not instruction.is_file():
        raise ValueError("Instruction path is not a regular file: " + str(instruction))
    old = instruction.read_bytes() if instruction and instruction.exists() else b""
    new = merged_instructions(old, block_for(skill_relative)) if instruction else b""
    unchanged = same_install(destination, manifest, source)
    if destination.exists() and not unchanged and not replace:
        raise ValueError("A different or locally edited skill already exists. Use --replace to back it up before installing: " + str(destination))
    if source.resolve() == destination.resolve() and not unchanged:
        raise ValueError("Cannot replace the running source folder. Run the installer from a separate extracted copy.")
    backups = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_root = base / ".design-language-backups" / (NAME + "-" + stamp)
    if backup_root.parent.is_symlink():
        raise ValueError("Refusing to write backups through a symlink.")
    backup_skill = None
    stage = None
    installed_new = False
    try:
        if not unchanged:
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=".ril-stage-", dir=destination.parent))
            for relative in list(manifest["files"]) + ["manifest.json"]:
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, target)
            (stage / ".installed.json").write_text(json.dumps({"name": NAME, "version": manifest["version"], "agent": agent, "installed_at": stamp}, indent=2) + "\n", encoding="utf-8")
            if destination.exists():
                backup_root.mkdir(parents=True, exist_ok=True)
                backup_skill = backup_root / "previous-skill"
                shutil.move(str(destination), str(backup_skill))
                backups.append(str(backup_skill))
            os.replace(stage, destination)
            stage = None
            installed_new = True
        if instruction and new != old:
            if instruction.exists():
                backup_root.mkdir(parents=True, exist_ok=True)
                previous_doc = backup_root / (instruction.name + ".bak")
                previous_doc.write_bytes(old)
                backups.append(str(previous_doc))
            atomic_write(instruction, new)
    except Exception:
        if installed_new and destination.exists():
            shutil.rmtree(destination)
        if backup_skill and backup_skill.exists():
            shutil.move(str(backup_skill), str(destination))
        raise
    finally:
        if stage and stage.exists():
            shutil.rmtree(stage)
    return {"status": "already current" if unchanged and (not instruction or new == old) else "installed", "skill": str(destination), "instructions": str(instruction) if instruction else None, "backups": backups}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--project", type=Path, help="Existing project root; installs skill and adds a managed instruction block.")
    scope.add_argument("--global", dest="global_scope", action="store_true", help="Install to this user's skill directory only; does not edit global instructions.")
    parser.add_argument("--agent", choices=AGENTS, default="codex")
    parser.add_argument("--replace", action="store_true", help="Back up a different skill before replacement; never silently overwrite it.")
    args = parser.parse_args()
    try:
        result = install(ROOT, project=args.project, agent=args.agent, replace=args.replace)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Start a new agent session and ask it to use research-interface-language.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
