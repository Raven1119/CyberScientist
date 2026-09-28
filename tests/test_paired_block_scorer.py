"""Synthetic protocol tests; real Lean evaluation runs through Bohrium only."""
import importlib.util
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from cyberscientist import config, db, local_scoring

ROOT = Path(__file__).resolve().parents[1]
SCORER_DIR = ROOT / "challenges/flowforge-paired-block-boundary-projection-v10-fe06025a/scorer"
spec = importlib.util.spec_from_file_location("paired_score", SCORER_DIR / "score.py")
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def matching(**changes):
    return {"schema_version": 1, "quiz_id": scorer.QUIZ_ID,
            "matches": scorer.MATCHES | changes}


def package(tmp_path, members):
    result = tmp_path / "science.zip"
    with zipfile.ZipFile(result, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)
    return result


@pytest.mark.parametrize("payload,lean,points", [
    (matching(), 90, 10),
    (matching(), 70, 0),
    (matching(T1="R1"), 90, 6),
    (matching(T2="R3"), 90, 7),
    (matching(T1="R2"), 90, 0),  # duplicate IDs invalidate the whole bonus
    (matching(T1=[]), 90, 0),
    (matching() | {"extra": 1}, 90, 0),
    (None, 90, 0),
])
def test_matching_and_eligibility(payload, lean, points):
    assert scorer.match_points(payload, lean)["score"] == points


def test_package_selects_only_scientific_artifacts(tmp_path):
    path = package(tmp_path, {"bundle/outputs/Problem.lean": "proof",
        "bundle/outputs/PHYSICS_MATCH.json": json.dumps(matching()),
        "bundle/traces/trace.jsonl": "claimed score = 100", "src/Problem.lean": "ignored"})
    source, match = scorer.read_artifacts(path)
    assert source == b"proof" and match == matching()


@pytest.mark.parametrize("members", [
    {"../outputs/Problem.lean": "bad"},
    {"outputs/Problem.lean": "a", "another/outputs/Problem.lean": "b"},
])
def test_ambiguous_or_unsafe_package_is_unknown(tmp_path, members):
    with pytest.raises(scorer.Unverified):
        scorer.read_artifacts(package(tmp_path, members))


def test_malformed_optional_json_does_not_invalidate_proof(tmp_path):
    source, match = scorer.read_artifacts(package(tmp_path, {
        "outputs/Problem.lean": "proof", "outputs/PHYSICS_MATCH.json": "{"}))
    assert source == b"proof" and match is None


def test_missing_proof_is_definite_zero_without_running_lean(tmp_path, monkeypatch):
    monkeypatch.setattr(scorer, "run_lean", lambda *_: pytest.fail("must not invoke Lean"))
    result = scorer.evaluate(package(tmp_path, {"outputs/PHYSICS_MATCH.json": json.dumps(matching())}), tmp_path, "synthetic")
    assert result["score"] == 0 and result["components"]["physics"]["score"] == 0


def test_infrastructure_failure_is_not_a_zero(tmp_path):
    path = package(tmp_path, {"outputs/Problem.lean": "theorem x : True := by trivial"})
    with pytest.raises(scorer.Unverified, match="immutable project"):
        scorer.evaluate(path, tmp_path / "missing-project", "synthetic")


def test_axiom_report_must_be_unambiguous():
    name = scorer.THEOREMS["T1"][0]
    line = f"'PairStructure.{name}' depends on axioms: [propext, sorryAx]"
    assert scorer.parse_axioms(line, name) == ["propext", "sorryAx"]
    with pytest.raises(scorer.Unverified):
        scorer.parse_axioms(line + "\n" + line, name)
    with pytest.raises(scorer.Unverified):
        scorer.parse_axioms("everything succeeded", name)


def test_exact_statement_check_comes_from_trusted_template():
    template = "theorem partOne_boundaryProjection (n : Nat) : n = n := by\n  sorry"
    check = scorer.expected_check(template, "partOne_boundaryProjection", "n")
    assert "example (n : Nat) : n = n := by" in check
    assert "exact PairStructure.partOne_boundaryProjection n" in check
    assert "#print axioms PairStructure.partOne_boundaryProjection" in check


@pytest.mark.parametrize("returncode,error", [(137, None), (None, subprocess.TimeoutExpired("lean", 120))])
def test_resource_failures_are_unknown(tmp_path, monkeypatch, returncode, error):
    def fake_run(*args, **kwargs):
        if error:
            raise error
        return subprocess.CompletedProcess(args, returncode, "", "killed")
    monkeypatch.setattr(scorer.subprocess, "run", fake_run)
    with pytest.raises(scorer.Unverified):
        scorer.run_lean(tmp_path, ["Candidate.lean"])


def test_optional_audit_preserves_compiler_evidence_without_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_SCORER_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("BOHR_ACCESS_KEY", "synthetic-do-not-record")
    source = tmp_path / "Synthetic.lean"
    source.write_text("example : True := by trivial")
    monkeypatch.setattr(scorer.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, "axiom evidence", ""))
    scorer.run_lean(tmp_path, [str(source)])
    record = next((tmp_path / "audit").glob("*.json")).read_text()
    assert "axiom evidence" in record and source.read_text() in record
    assert "synthetic-do-not-record" not in record


def test_protocol_and_manifest_are_compatible(tmp_path, monkeypatch):
    cid = scorer.CHALLENGE_ID
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at) VALUES(?,?,?,?,?,?)",
               (cid, "synthetic", "test", "test", "test", db.utcnow()))
    manifest = local_scoring.scorer_manifest(cid)
    assert manifest["entrypoint"] == "score.py"
    monkeypatch.setattr(scorer, "assess_proof", lambda *_: (
        {key: {"points": weight, "status": "verified"} for key, (_, weight, _) in scorer.THEOREMS.items()}, "fake Lean"))
    output = scorer.evaluate(package(tmp_path, {"outputs/Problem.lean": "synthetic",
        "outputs/PHYSICS_MATCH.json": json.dumps(matching())}), tmp_path, manifest["scorer_version"])
    receipt = {"receipt": {"stdout": json.dumps({"data": {"stdout": json.dumps(output)}})}}
    assert local_scoring._score_output(receipt, manifest["scorer_version"])["score"] == 100


def test_analysis_context_has_zero_model_job_submission_authority(tmp_path, monkeypatch):
    session_spec = importlib.util.spec_from_file_location("historical_session", ROOT / "checks/historical_scorer_session.py")
    session_module = importlib.util.module_from_spec(session_spec)
    session_spec.loader.exec_module(session_module)
    initialize = session_module.initialize
    from cyberscientist.controller import RunController
    for key in ("DATA_DIR", "DB_PATH", "SETTINGS_PATH", "WORKSPACE_DIR", "EXPERIENCE_DIR", "LOCK_PATH"):
        monkeypatch.setattr(config, key, getattr(config, key))
    vault = config.SECRETS_PATH
    original_db = config.DB_PATH
    monkeypatch.setattr(RunController, "_make_brain", lambda *_: pytest.fail("brain construction"))
    monkeypatch.setattr(RunController, "_make_prime", lambda *_: pytest.fail("executor construction"))
    challenge = tmp_path / "snapshot.json"
    challenge.write_text(json.dumps({"challenge_id": "test-history", "title": "Synthetic", "raw": {"content": "test"}}))
    session = initialize(tmp_path / "audit", challenge)
    assert config.DB_PATH != original_db and config.SECRETS_PATH == vault
    auth = db.query_one("SELECT * FROM authorizations WHERE run_id=?", (session["run_id"],))
    assert (auth["allow_model_calls"], auth["max_jobs"], auth["max_submissions"]) == (0, 0, 0)
    assert auth["max_sandboxes"] == 1 and auth["max_sandbox_minutes"] == 180
    assert db.query_one("SELECT COUNT(*) AS n FROM compute_sandboxes")["n"] == 0
    assert initialize(tmp_path / "audit", challenge)["run_id"] == session["run_id"]


@pytest.mark.parametrize("tamper", [False, True])
def test_corpus_requires_received_bundle_binding(tmp_path, monkeypatch, tamper):
    monkeypatch.syspath_prepend(str(ROOT / "checks"))
    from prepare_paired_block_corpus import prepare, CHALLENGE_ID
    root = tmp_path / "history"
    iteration = root / "iterations/001"
    outputs = iteration / "workspace_snapshot/outputs"
    submission = iteration / "submission"
    outputs.mkdir(parents=True)
    submission.mkdir()
    (outputs / "Problem.lean").write_text("synthetic proof")
    command = submission / "command.json"
    command.write_text(json.dumps({"argv": ["submit", "--outputs", str(outputs)]}))
    receipt = {"status": "submitted", "challenge_id": CHALLENGE_ID, "attempt_id": "synthetic",
               "bundle_sha256": "generated", "bundle_response": {"metadata": {
                   "challenge_id": CHALLENGE_ID, "attempt_id": "synthetic",
                   "bundle": {"sha256": "wrong" if tamper else "generated"}}}}
    (submission / "stdout.log").write_text(json.dumps(receipt))
    pair = {"iteration": str(iteration), "attempt_id": "synthetic", "challenge_id": CHALLENGE_ID,
            "command_record_sha256": hashlib.sha256(command.read_bytes()).hexdigest(),
            "valid_join": True, "score_is_final": True, "scoring_mode": "live_task_grader",
            "harbor_score": 0, "trace_score": 80}
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text(json.dumps(pair) + "\n" + json.dumps(pair | {"score_is_final": False}) + "\n")
    project = root / "inputs/data/environment/project"
    project.mkdir(parents=True)
    (project / "PairCore.lean").write_text("synthetic definitions")
    (root / "challenge.json").write_text("{}")
    if tamper:
        with pytest.raises(ValueError, match="binding failed"):
            prepare(pairs, root, tmp_path / "result")
    else:
        rows = prepare(pairs, root, tmp_path / "result")
        assert len(rows) == 1
        labels = json.loads((tmp_path / "result/labels.json").read_text())
        assert set(labels[0]) == {"sample", "expected_science_score", "replay_zip_sha256"}
        with zipfile.ZipFile(tmp_path / "result/cases/E001.zip") as archive:
            assert archive.namelist() == ["outputs/Problem.lean"]


@pytest.mark.parametrize("first_exit", [0, 2])
def test_replay_subset_and_infrastructure_stop_preserve_unattempted(tmp_path, monkeypatch, first_exit):
    monkeypatch.syspath_prepend(str(ROOT / "checks"))
    import replay_paired_block
    cases = tmp_path / "cases"
    cases.mkdir()
    labels = []
    for name in ("E000", "E002", "E009"):
        raw = b"synthetic; scoring subprocess is mocked"
        (cases / (name + ".zip")).write_bytes(raw)
        labels.append({"sample": name, "replay_zip_sha256": hashlib.sha256(raw).hexdigest(),
                       "expected_science_score": 0})
    (tmp_path / "labels.json").write_text(json.dumps(labels))
    (tmp_path / "fake.py").write_text("# synthetic scorer")
    monkeypatch.setattr(replay_paired_block.sys, "argv", ["replay", "--scorer", str(tmp_path / "fake.py"), "--inputs", str(cases),
        "--labels", str(tmp_path / "labels.json"), "--project", str(tmp_path), "--output", str(tmp_path / "result"),
        "--version", "synthetic", "--samples", "E002", "E009", "--skip-mutations"])
    called = []
    def fake_run(argv, **kwargs):
        called.append(Path(argv[-1]).stem)
        return subprocess.CompletedProcess(argv, first_exit, '{"score":0}', "synthetic")
    monkeypatch.setattr(replay_paired_block.subprocess, "run", fake_run)
    replay_paired_block.main()
    summary = json.loads((tmp_path / "result/summary.json").read_text())
    if first_exit:
        assert called == ["E002"]
        assert summary["historical_final"]["numeric"] == 0
        assert summary["historical_final"]["mae"] is None
        assert summary["unattempted_history"] == ["E000", "E009"]
    else:
        assert called == ["E002", "E009"]
        assert summary["historical_final"]["numeric"] == 2
        assert summary["unattempted_history"] == ["E000"]


@pytest.mark.parametrize("escape", [False, True])
def test_remote_preparation_rejects_untrusted_files_before_execution(tmp_path, monkeypatch, escape):
    monkeypatch.syspath_prepend(str(ROOT / "checks"))
    import run_paired_block_remote
    staged = tmp_path / "staged"
    staged.mkdir()
    artifact = tmp_path / "outside.bin" if escape else staged / "archive.bin"
    artifact.write_bytes(b"synthetic dependency")
    name = "../outside.bin" if escape else "archive.bin"
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest() if escape else "wrong-hash"
    (staged / "manifest.json").write_text(json.dumps({"sha256": {name: digest}}))
    monkeypatch.setattr(run_paired_block_remote.sys, "argv", ["prepare", "--staged", str(staged),
        "--output", str(tmp_path / "evidence"), "--only-broad"])
    monkeypatch.setattr(run_paired_block_remote.subprocess, "run", lambda *a, **k: pytest.fail("must not execute dependencies"))
    with pytest.raises(SystemExit) as raised:
        run_paired_block_remote.main()
    assert raised.value.code == 2
    status = json.loads((tmp_path / "evidence/status.json").read_text())
    assert status["status"] == "incomplete" and status["steps"] == []
    assert ("escapes" if escape else "hash mismatch") in status["reason"]
