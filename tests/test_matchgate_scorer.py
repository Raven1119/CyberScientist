import importlib.util
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCORER = ROOT / "challenges/flowforge-matchgate-swap-inverse-synthesis-v2-4019e745/scorer/score.py"
SPEC = importlib.util.spec_from_file_location("matchgate_scorer", SCORER)
scorer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scorer)


def identity(n=2, t=1, swap=(0, 1)):
    matrix = {"real": np.eye(n).tolist(), "imag": np.zeros((n, n)).tolist()}
    return {"swaps": [list(swap)] * t, "gaussians": [matrix for _ in range(t + 1)]}


def fake_endpoint(value):
    orbitals = np.array([[1.0], [0.0]], dtype=np.complex128)
    target = np.array([math.sqrt(1 - value), math.sqrt(value)], dtype=np.complex128)
    configs = scorer._configs(2, 1)
    return orbitals, target, configs


@pytest.mark.parametrize("value,points", [(.79, 0.0), (.80, 0.0),
    (.90, 25 * .10 / .19), (.99, 25.0), (1.0, 25.0)])
def test_public_fidelity_boundaries(value, points):
    orbitals, target, configs = fake_endpoint(value)
    actual = scorer.fidelity(orbitals, target, configs, identity(), 1)
    assert actual == pytest.approx(value, abs=1e-12)
    assert scorer.case_points(actual) == pytest.approx(points, abs=1e-10)


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(swaps=[]),
    lambda c: c.update(gaussians=c["gaussians"][:1]),
    lambda c: c.update(swaps=[[1, 0]]),
    lambda c: c.update(extra="not allowed"),
    lambda c: c["gaussians"][0].update(real=[[1, 0]]),
    lambda c: c["gaussians"][0].update(real=[[2, 0], [0, 1]]),
    lambda c: c["gaussians"][0].update(imag=[[float("nan"), 0], [0, 0]]),
])
def test_invalid_case_has_no_fidelity(mutate):
    orbitals, target, configs = fake_endpoint(1.0)
    candidate = identity()
    # A matrix is shared by the identity fixture; copy before mutating.
    candidate = json.loads(json.dumps(candidate))
    mutate(candidate)
    with pytest.raises(ValueError):
        scorer.fidelity(orbitals, target, configs, candidate, 1)


def test_unitarity_frobenius_boundary():
    near = identity()["gaussians"][0]
    near["real"][0][0] = 1 + 2e-9
    assert scorer._matrix(near, 2).shape == (2, 2)
    far = identity()["gaussians"][0]
    far["real"][0][0] = 1 + 1e-8
    with pytest.raises(ValueError, match="not unitary"):
        scorer._matrix(far, 2)


def test_gaussian_replay_matches_independent_exterior_matrix():
    rng = np.random.default_rng(410)
    source = rng.normal(size=(4, 4)) + 1j * rng.normal(size=(4, 4))
    unitary, _ = np.linalg.qr(source)
    configs = scorer._configs(4, 2)
    state = rng.normal(size=len(configs)) + 1j * rng.normal(size=len(configs))
    expected = np.array([[np.linalg.det(unitary[np.ix_(output, incoming)])
                          for incoming in configs] for output in configs]) @ state
    actual = state.copy()
    scorer._gaussian(actual, unitary, configs, scorer._basis(configs, 4))
    np.testing.assert_allclose(actual, expected, atol=1e-11)


def test_ordinary_swap_has_no_double_occupation_sign():
    # The first amplitude occupies both swapped modes; an ordinary qubit SWAP
    # leaves it unchanged, unlike a fermionic mode-permutation gate.
    orbitals = np.array([[1 / math.sqrt(2), 0], [0, 1],
                         [1 / math.sqrt(2), 0]], dtype=np.complex128)
    configs = scorer._configs(3, 2)
    initial = scorer._initial_state(orbitals, configs)
    expected = initial.copy()
    expected[1], expected[2] = initial[2], initial[1]
    assert scorer.fidelity(orbitals, expected, configs, identity(3), 1) == pytest.approx(1.0)


def test_public_manifest_pin_rejects_changed_endpoints(tmp_path):
    (tmp_path / "INSTANCE_MANIFEST.json").write_text(json.dumps({
        "schema": "matchgate-swap-instances/v2", "instances": {}, "cases": {}}))
    with pytest.raises(scorer.Unverified, match="manifest hash mismatch"):
        scorer._verified_instance_files(tmp_path)


def test_invalid_case_does_not_zero_valid_cases(tmp_path, monkeypatch):
    path = tmp_path / "science.zip"
    cases = {case_id: identity() for case_id in scorer.CASE_IDS}
    cases["Q2"]["swaps"] = []
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("outputs/submission.json", json.dumps({"schema": scorer.SCHEMA, "cases": cases}))
    monkeypatch.setattr(scorer, "_verified_instance_files", lambda _: {"cases": {}})
    monkeypatch.setattr(scorer, "_load_case", lambda *_: (*fake_endpoint(1.0), 1))
    result = scorer.evaluate(path, "synthetic-version", tmp_path)
    assert result["score"] == pytest.approx(75.0)
    assert result["components"]["Q2"]["status"] == "invalid"
    assert {result["components"][c]["status"] for c in ("Q1", "Q3", "Q4")} == {"valid"}


def test_endpoint_or_numerical_uncertainty_is_not_scored_zero(tmp_path, monkeypatch):
    path = tmp_path / "science.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("outputs/submission.json", json.dumps({
            "schema": scorer.SCHEMA,
            "cases": {case_id: identity() for case_id in scorer.CASE_IDS}}))
    monkeypatch.setattr(scorer, "_verified_instance_files", lambda _: {"cases": {}})
    monkeypatch.setattr(scorer, "_load_case", lambda *_: (*fake_endpoint(1.0), 1))
    monkeypatch.setattr(scorer, "fidelity", lambda *_: (_ for _ in ()).throw(scorer.Unverified("numerical")))
    with pytest.raises(scorer.Unverified, match="numerical"):
        scorer.evaluate(path, "synthetic-version", tmp_path)
