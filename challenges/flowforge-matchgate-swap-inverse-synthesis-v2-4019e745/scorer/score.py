"""Public endpoint score for the four Matchgate/SWAP instances.

This replays Gaussian blocks on the fixed-particle occupation basis. Adjacent
qubit SWAPs exchange basis amplitudes without a fermionic double-occupation
sign. Immutable public instance files are verified against their manifest.
The scorer never uses the organizer's private reference circuit.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath

import numpy as np

CHALLENGE_ID = "flowforge-matchgate-swap-inverse-synthesis-v2-4019e745"
RESOURCE_SHA256 = "3ed0a9a79f63504b8a6d7c84022dee9bc458aaf15bc23096d4e60b5c3f316e74"
MANIFEST_SHA256 = "6ea87887ce793b9ce9c77fedb3f9f3a5891766c2be976f87d2558bf577da3bb4"
SCHEMA = "matchgate-swap-submission/v1"
CASE_IDS = ("Q1", "Q2", "Q3", "Q4")
UNITARY_TOLERANCE = 1e-8
FULL_FIDELITY = 0.99
ZERO_FIDELITY = 0.80


class Unverified(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _configs(n: int, k: int) -> np.ndarray:
    return np.fromiter((mode for row in itertools.combinations(range(n), k) for mode in row),
                       dtype=np.int16, count=math.comb(n, k) * k).reshape(-1, k)


def _basis(configs: np.ndarray, n: int):
    masks = np.bitwise_or.reduce(np.left_shift(np.uint32(1), configs.astype(np.uint32)), axis=1)
    index = np.full(1 << n, -1, dtype=np.int32)
    index[masks] = np.arange(len(masks), dtype=np.int32)
    pairs = []
    for mode in range(n - 1):
        left_bit, right_bit = 1 << mode, 1 << (mode + 1)
        left = np.flatnonzero(((masks & left_bit) != 0) & ((masks & right_bit) == 0)).astype(np.int32)
        right = index[masks[left] ^ (left_bit | right_bit)]
        if np.any(right < 0):
            raise Unverified("occupation basis is incomplete")
        both = np.flatnonzero((masks & (left_bit | right_bit)) == (left_bit | right_bit)).astype(np.int32)
        pairs.append((left, right, both))
    return pairs


def _matrix(raw: object, n: int) -> np.ndarray:
    if not isinstance(raw, dict) or set(raw) != {"real", "imag"}:
        raise ValueError("Gaussian matrix has extra or missing fields")
    for component in (raw["real"], raw["imag"]):
        if (not isinstance(component, list) or len(component) != n
                or any(not isinstance(row, list) or len(row) != n for row in component)):
            raise ValueError("Gaussian matrix has wrong dimensions")
        if any(type(value) not in (int, float) or not math.isfinite(value)
               for row in component for value in row):
            raise ValueError("Gaussian matrix has non-finite or nonnumeric entries")
    matrix = np.asarray(raw["real"], dtype=np.float64) + 1j * np.asarray(raw["imag"], dtype=np.float64)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Gaussian matrix overflows")
    if np.linalg.norm(matrix.conj().T @ matrix - np.eye(n), ord="fro") > UNITARY_TOLERANCE:
        raise ValueError("Gaussian matrix is not unitary")
    return matrix


def _circuit(raw: object, n: int, t: int):
    if not isinstance(raw, dict) or set(raw) != {"swaps", "gaussians"}:
        raise ValueError("case has extra or missing fields")
    swaps, gaussians = raw["swaps"], raw["gaussians"]
    if not isinstance(swaps, list) or len(swaps) != t:
        raise ValueError("wrong SWAP count")
    if not isinstance(gaussians, list) or len(gaussians) != t + 1:
        raise ValueError("wrong Gaussian count")
    modes = []
    for pair in swaps:
        if (not isinstance(pair, list) or len(pair) != 2 or
                any(type(value) is not int for value in pair) or
                not 0 <= pair[0] < n - 1 or pair[1] != pair[0] + 1):
            raise ValueError("SWAP must use an ordered adjacent pair")
        modes.append(pair[0])
    return modes, [_matrix(item, n) for item in gaussians]


def _mix(state: np.ndarray, pair, gate: np.ndarray) -> None:
    left, right, both = pair
    a, b = state[left].copy(), state[right].copy()
    state[left] = gate[0, 0] * a + gate[0, 1] * b
    state[right] = gate[1, 0] * a + gate[1, 1] * b
    if len(both):
        state[both] *= np.linalg.det(gate)


def _gaussian(state: np.ndarray, matrix: np.ndarray, configs: np.ndarray, pairs) -> None:
    """Apply the exterior power of U using adjacent Givens factors."""
    n = matrix.shape[0]
    triangular = matrix.copy()
    factors = []
    for column in range(n - 1):
        for row in range(n - 1, column, -1):
            upper, lower = triangular[row - 1, column], triangular[row, column]
            if abs(lower) < 1e-15:
                continue
            radius = math.hypot(abs(upper), abs(lower))
            rotation = np.array([[upper.conjugate(), lower.conjugate()],
                                 [-lower, upper]], dtype=np.complex128) / radius
            triangular[[row - 1, row]] = rotation @ triangular[[row - 1, row]]
            factors.append((row - 1, rotation.conj().T))
    diagonal = np.diag(triangular)
    if np.linalg.norm(triangular - np.diag(diagonal), ord="fro") > 1e-7:
        raise Unverified("Gaussian decomposition is numerically unstable")
    for start in range(0, len(state), 16384):
        end = min(start + 16384, len(state))
        state[start:end] *= np.prod(diagonal[configs[start:end]], axis=1)
    for mode, rotation in reversed(factors):
        _mix(state, pairs[mode], rotation)


def _initial_state(orbitals: np.ndarray, configs: np.ndarray) -> np.ndarray:
    state = np.empty(len(configs), dtype=np.complex128)
    for start in range(0, len(state), 4096):
        end = min(start + 4096, len(state))
        state[start:end] = np.linalg.det(orbitals[configs[start:end]])
    return state


def fidelity(orbitals: np.ndarray, target: np.ndarray, configs: np.ndarray,
             raw_circuit: object, t: int) -> float:
    n, k = orbitals.shape
    if (configs.shape != (math.comb(n, k), k) or target.shape != (len(configs),)
            or not np.all(np.isfinite(orbitals)) or not np.all(np.isfinite(target))):
        raise Unverified("public endpoint arrays are invalid")
    swaps, gaussians = _circuit(raw_circuit, n, t)
    pairs = _basis(configs, n)
    state = _initial_state(orbitals, configs)
    for layer, matrix in enumerate(gaussians):
        _gaussian(state, matrix, configs, pairs)
        if layer < t:
            left, right, _ = pairs[swaps[layer]]
            state[left], state[right] = state[right].copy(), state[left].copy()
    value = float(abs(np.vdot(target, state)) ** 2)
    if not math.isfinite(value):
        raise Unverified("fidelity is not finite")
    return value


def case_points(fidelity_value: float) -> float:
    return 25.0 * max(0.0, min(1.0, (fidelity_value - ZERO_FIDELITY) /
                                  (FULL_FIDELITY - ZERO_FIDELITY)))


def _verified_instance_files(resource_dir: Path) -> dict:
    manifest_path = resource_dir / "INSTANCE_MANIFEST.json"
    raw = manifest_path.read_bytes()
    if _sha(raw) != MANIFEST_SHA256:
        raise Unverified("public instance manifest hash mismatch")
    manifest = json.loads(raw)
    if manifest.get("schema") != "matchgate-swap-instances/v2":
        raise Unverified("public instance manifest schema changed")
    for name, item in manifest["instances"].items():
        path = resource_dir / name
        if (path.stat().st_size != item["bytes"] or _sha(path.read_bytes()) != item["sha256"]):
            raise Unverified("public instance hash mismatch: " + name)
    return manifest


def _load_case(resource_dir: Path, manifest: dict, case_id: str):
    item = manifest["cases"][case_id]
    n, k, t = (int(item[name]) for name in ("n", "k", "t"))
    configs = _configs(n, k)
    if item["format"] == "monolithic-v1":
        with np.load(resource_dir / item["file"], allow_pickle=False) as source:
            if (int(source["n"]) != n or int(source["k"]) != k or int(source["t"]) != t
                    or not np.array_equal(source["configs"], configs)):
                raise Unverified("public configuration order mismatch")
            return source["initial_orbitals"], source["target_amplitudes"], configs, t
    if item["format"] != "sharded-target-v1":
        raise Unverified("unknown public instance layout")
    with np.load(resource_dir / item["meta"], allow_pickle=False) as source:
        if (int(source["n"]) != n or int(source["k"]) != k or int(source["t"]) != t
                or int(source["configuration_count"]) != len(configs)
                or int(source["shard_count"]) != len(item["target_parts"])):
            raise Unverified("public Q4 metadata mismatch")
        orbitals = source["initial_orbitals"]
    parts = []
    cursor = 0
    for name in item["target_parts"]:
        with np.load(resource_dir / name, allow_pickle=False) as source:
            if int(source["start"]) != cursor:
                raise Unverified("public Q4 shard ordering mismatch")
            part = source["target_amplitudes"]
            cursor = int(source["stop"])
            if len(part) != cursor - sum(len(x) for x in parts):
                raise Unverified("public Q4 shard boundary mismatch")
            parts.append(part)
    target = np.concatenate(parts)
    if (len(target) != len(configs) or target.dtype != np.complex128
            or _sha(target.tobytes()) != item["target_sha256"]):
        raise Unverified("public Q4 target hash mismatch")
    return orbitals, target, configs, t


def evaluate(package: Path, version: str, resource_dir: Path) -> dict:
    manifest = _verified_instance_files(resource_dir)
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        if (len(names) > 5000 or len(names) != len(set(names))
                or any(n.startswith("/") or "\\" in n or ".." in PurePosixPath(n).parts for n in names)):
            raise Unverified("ambiguous or unsafe package")
        candidates = [name for name in names if name == "outputs/submission.json"
                      or name.endswith("/outputs/submission.json")]
        if len(candidates) != 1 or archive.getinfo(candidates[0]).file_size > 5_000_000:
            raise Unverified("exactly one bounded outputs/submission.json is required")
        candidate = json.loads(archive.read(candidates[0]))
    if (not isinstance(candidate, dict) or set(candidate) != {"schema", "cases"}
            or candidate["schema"] != SCHEMA or not isinstance(candidate["cases"], dict)
            or set(candidate["cases"]) != set(CASE_IDS)):
        raise Unverified("submission schema or case set is invalid")
    components = {}
    for case_id in CASE_IDS:
        orbitals, target, configs, t = _load_case(resource_dir, manifest, case_id)
        try:
            value = fidelity(orbitals, target, configs, candidate["cases"][case_id], t)
        except Unverified:
            raise
        except ValueError as exc:
            components[case_id] = {"status": "invalid", "score": 0.0, "fidelity": None,
                                   "reason": str(exc)[:180]}
        else:
            components[case_id] = {"status": "valid", "score": case_points(value),
                                   "fidelity": value}
    return {"score": sum(item["score"] for item in components.values()),
            "components": components, "confidence": "medium",
            "notes": "Public fixed endpoints and 25x4 fidelity formula; synthetic controls validated. "
                     "No platform Matchgate receipt calibration or hidden-wrapper equivalence claimed.",
            "scorer_version": version}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: score.py science_package.zip")
    try:
        path = Path(os.environ["CS_MATCHGATE_INSTANCE_DIR"])
        result = evaluate(Path(sys.argv[1]), os.environ["CS_SCORER_VERSION"], path)
    except (Unverified, OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "unverified", "reason": str(exc)}), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
