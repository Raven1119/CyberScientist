"""Reconstruct the public paired-block rubric; run Lean only in Bohrium.

The immutable project is an external prerequisite, never taken from a candidate.
Set CS_LEAN_PROJECT to its prepared directory. Historical agreement is evidence
about tested inputs, not a claim to possess the hidden platform verifier.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

CHALLENGE_ID = "flowforge-paired-block-boundary-projection-v10-fe06025a"
PROJECT_HASHES = {
    "PairCore.lean": "26e3be2cee9df5d5b021f3c4662386db3974b51fbb0b07a03616b9fb36a73415",
    "Problem.lean": "e2ef57d93676b310b8dc43d836c40dfcdebdfe7f3476bf66b5c40c7bd82d5cdb",
    "lean-toolchain": "2bdc48adfa58d0017e538a0ad117c5d73d35deec879978f909406a80c8037273",
    "lakefile.toml": "d9698381e02837db51d2b5e5bd746d7514db9b57a805015b7d8f4a80eb79d2e3",
    "lake-manifest.json": "7d78a9a7f1ff478f6a609653c74817d10e199b9425daf26d9c1027fa53375fef",
}
THEOREMS = {
    "T1": ("partOne_boundaryProjection", 40, "u hu"),
    "T2": ("partTwo_gapNonnegative", 30, "v0 v1 w0 w1 hv hw"),
    "T3": ("partTwo_branchRigidity", 20, "v0 v1 w0 w1 hv hw"),
}
QUIZ_ID = "paired-block-physical-correspondence-matching-v1"
# Public option meanings: covariance projection; local Cauchy remainder;
# balanced biases plus both alignments. Confirmed by historical full-score files.
MATCHES = {"T1": "R7", "T2": "R2", "T3": "R9"}
BONUS = {"T1": 4, "T2": 3, "T3": 3}
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}


class Unverified(ValueError):
    """Infrastructure or unsupported input prevents a numeric judgment."""


def match_points(payload: object, lean_score: int) -> dict:
    """Public format constraints and the explicit 90-point eligibility gate."""
    valid = (
        isinstance(payload, dict)
        and set(payload) == {"schema_version", "quiz_id", "matches"}
        and type(payload["schema_version"]) is int and payload["schema_version"] == 1
        and payload["quiz_id"] == QUIZ_ID
        and isinstance(payload["matches"], dict)
        and set(payload["matches"]) == set(MATCHES)
    )
    values = list(payload["matches"].values()) if valid else []
    valid = bool(valid and all(isinstance(v, str) and v in {f"R{i}" for i in range(1, 11)} for v in values)
                 and len(set(values)) == 3)
    eligible = lean_score == 90
    points = {key: weight if valid and eligible and payload["matches"][key] == MATCHES[key] else 0
              for key, weight in BONUS.items()}
    return {"format_valid": valid, "eligible": eligible, "points": points, "score": sum(points.values())}


def read_artifacts(package: Path) -> tuple[bytes | None, object]:
    """Read only the two scientific artifacts; never unpack or execute ZIP paths."""
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 5000:
            raise Unverified("ambiguous or excessive archive members")
        if any(name.startswith("/") or "\\" in name or ".." in PurePosixPath(name).parts for name in names):
            raise Unverified("unsafe archive member path")
        candidates = [name for name in names if name == "outputs/Problem.lean" or name.endswith("/outputs/Problem.lean")]
        if len(candidates) > 1:
            raise Unverified("multiple candidate Problem.lean paths")
        if not candidates:
            return None, None
        proof_name = candidates[0]
        if archive.getinfo(proof_name).file_size > 1_000_000:
            raise Unverified("Problem.lean exceeds evaluator limit")
        source = archive.read(proof_name)
        match_name = proof_name.removesuffix("Problem.lean") + "PHYSICS_MATCH.json"
        matching = None
        if match_name in names:
            if archive.getinfo(match_name).file_size > 100_000:
                raise Unverified("matching file exceeds evaluator limit")
            try:
                matching = json.loads(archive.read(match_name).decode("utf-8-sig"))
            except (ValueError, UnicodeError):
                pass  # Public rubric explicitly gives malformed matching zero bonus.
        return source, matching


def run_lean(project: Path, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    installed = Path("/workspace/cs-elan/bin/lake")
    lake = str(installed) if installed.is_file() else "lake"
    if installed.is_file():
        env["ELAN_HOME"] = "/workspace/cs-elan"
    try:
        result = subprocess.run([lake, "env", "lean", *args], cwd=project, env=env,
                                capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Unverified(f"Lean unavailable or timed out: {type(exc).__name__}") from exc
    if audit_directory := os.environ.get("CS_SCORER_AUDIT_DIR"):
        audit = Path(audit_directory)
        audit.mkdir(parents=True, exist_ok=True)
        record = {"arguments": args, "exit_code": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr}
        if len(args) == 1 and Path(args[0]).is_file():
            record["compiled_source"] = Path(args[0]).read_text()
        (audit / (uuid.uuid4().hex + ".json")).write_text(json.dumps(record, ensure_ascii=False))
    if result.returncode not in (0, 1):
        raise Unverified(f"Lean runtime failed with exit {result.returncode}")
    return result


def verify_project(project: Path) -> str:
    for name, expected in PROJECT_HASHES.items():
        candidate = project / name
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            raise Unverified(f"immutable project missing or changed: {name}")
    version = run_lean(project, ["--version"], 30)
    if version.returncode or not re.search(r"Lean \(version 4\.32\.2(?:,|\))", version.stdout):
        raise Unverified("required Lean 4.32.2 toolchain not verified")
    # A valid environment must load supplied definitions before any candidate.
    with tempfile.TemporaryDirectory(prefix="cs-probe-", dir=project) as tmp:
        probe = Path(tmp) / "Probe.lean"
        probe.write_text("import PairCore\n#check PairStructure.branchGap\n", encoding="utf8")
        result = run_lean(project, [str(probe)])
        if result.returncode:
            raise Unverified("pinned PairCore/dependencies cannot be loaded")
    return version.stdout.strip()


def expected_check(template: str, name: str, arguments: str) -> str:
    # The template hash was verified before use, and its statements are NOT
    # taken from the submitted proof (a proof of True must not earn points).
    match = re.search(r"theorem " + re.escape(name) + r"\b([\s\S]*?) := by\s+sorry", template)
    if not match:
        raise Unverified(f"trusted theorem template not recognized: {name}")
    return ("\nopen scoped BigOperators Matrix ComplexConjugate\nnamespace PairStructure\n"
            + "example" + match.group(1) + " := by\n  exact PairStructure."
            + name + " " + arguments + "\nend PairStructure\n"
            + "#print axioms PairStructure." + name + "\n")


def parse_axioms(output: str, name: str) -> list[str]:
    full_name = "PairStructure." + name
    matches = re.findall(r"'" + re.escape(full_name) + r"' depends on axioms: \[([^\]]*)\]", output)
    empty = re.findall(r"'" + re.escape(full_name) + r"' does not depend on any axioms", output)
    if len(matches) + len(empty) != 1:
        raise Unverified(f"missing or ambiguous axiom report: {name}")
    return sorted(part.strip() for part in matches[0].split(",") if part.strip()) if matches else []


def assess_proof(source: bytes, project: Path) -> tuple[dict, str]:
    version = verify_project(project)
    try:
        proof = source.decode("utf-8-sig")
    except UnicodeError:
        return {key: {"points": 0, "status": "invalid_utf8"} for key in THEOREMS}, version
    template = (project / "Problem.lean").read_text()
    components = {}
    with tempfile.TemporaryDirectory(prefix="cs-proof-", dir=project) as tmp:
        for key, (name, weight, arguments) in THEOREMS.items():
            candidate = Path(tmp) / (key + ".lean")
            candidate.write_text(proof + "\n" + expected_check(template, name, arguments), encoding="utf8")
            result = run_lean(project, [str(candidate)])
            combined = result.stdout + result.stderr
            digest = hashlib.sha256(combined.encode()).hexdigest()
            if result.returncode:
                if "error:" not in combined:
                    raise Unverified(f"Lean failed without a compiler diagnostic: {key}")
                components[key] = {"points": 0, "status": "compile_or_type_error", "diagnostic_sha256": digest}
                continue
            axioms = parse_axioms(combined, name)
            unsupported = sorted(set(axioms) - ALLOWED_AXIOMS)
            components[key] = {"points": 0 if unsupported else weight,
                               "status": "untrusted_axioms" if unsupported else "verified",
                               "axioms": axioms, "diagnostic_sha256": digest}
    # Submitted Lean can execute metaprograms; do not accept mutated trusted inputs.
    for name, expected in PROJECT_HASHES.items():
        if hashlib.sha256((project / name).read_bytes()).hexdigest() != expected:
            raise Unverified(f"trusted file changed during evaluation: {name}")
    return components, version


def evaluate(package: Path, project: Path, scorer_version: str) -> dict:
    source, matching = read_artifacts(package)
    if source is None:
        components = {key: {"points": 0, "status": "missing_artifact"} for key in THEOREMS}
        lean_version = None
    else:
        components, lean_version = assess_proof(source, project)
    lean_score = sum(item["points"] for item in components.values())
    physics = match_points(matching, lean_score)
    return {"score": lean_score + physics["score"],
            "components": {"lean": components, "lean_score": lean_score, "physics": physics,
                           "lean_version": lean_version,
                           "proof_sha256": hashlib.sha256(source).hexdigest() if source is not None else None},
            "confidence": "low",
            "notes": "Experimental public-rubric reconstruction; historical Lean replay has not completed. "
                     "Not the hidden official verifier. "
                     "Requires supplied definitions, exact theorem types, and trusted kernel axioms; "
                     "physics bonus is eligible only at 90 Lean points. No trace score is inferred.",
            "scorer_version": scorer_version}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: score.py science_package.zip")
    try:
        output = evaluate(Path(sys.argv[1]), Path(os.environ.get("CS_LEAN_PROJECT", "/workspace/paired-block-project")),
                          os.environ["CS_SCORER_VERSION"])
    except (Unverified, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "unverified", "reason": str(exc)}), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
