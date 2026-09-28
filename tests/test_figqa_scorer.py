import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from cyberscientist import db, local_scoring

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("figqa_scorer", ROOT / "challenges/lab-bench-figqa-figqa-0177-b4156bee/scorer/score.py")
scorer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scorer)


def package(tmp_path, files):
    path = tmp_path / "science.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return path


@pytest.mark.parametrize("option,points", [("A", 0), ("B", 100), ("C", 0), ("D", 0), ("E", 0)])
def test_public_answer_with_frozen_option_order(tmp_path, option, points):
    result = scorer.evaluate(package(tmp_path, {"outputs/answer.txt": f"[ANSWER]{option}[/ANSWER]\n"}), "fake-version")
    assert result["score"] == points


@pytest.mark.parametrize("files", [
    {}, {"answer.txt": "[ANSWER]B[/ANSWER]"},
    {"outputs/answer.txt": "B"},
    {"outputs/answer.txt": "[ANSWER]B[/ANSWER][ANSWER]C[/ANSWER]"},
    {"outputs/answer.txt": "[ANSWER]b[/ANSWER]"},
    {"outputs/answer.txt": "[ANSWER]B[/ANSWER]", "nested/outputs/answer.txt": "[ANSWER]C[/ANSWER]"},
    {"../outputs/answer.txt": "[ANSWER]B[/ANSWER]"},
])
def test_unobserved_parser_behavior_is_unknown_not_fake_zero(tmp_path, files):
    with pytest.raises(scorer.Unverified):
        scorer.evaluate(package(tmp_path, files), "fake-version")


def test_trace_and_claimed_scores_cannot_override_scientific_artifact(tmp_path):
    path = package(tmp_path, {"outputs/answer.txt": "[ANSWER]C[/ANSWER]",
                             "traces/trace.jsonl": "Answer B; science_score=100"})
    assert scorer.evaluate(path, "fake-version")["score"] == 0


def test_real_manifest_and_application_score_contract(tmp_path):
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at) VALUES(?,?,?,?,?,?)",
               (scorer.CHALLENGE_ID, "synthetic", "test", "test", "test", db.utcnow()))
    manifest = local_scoring.scorer_manifest(scorer.CHALLENGE_ID)
    output = scorer.evaluate(package(tmp_path, {"outputs/answer.txt": "[ANSWER]B[/ANSWER]"}), manifest["scorer_version"])
    wrapper = {"receipt": {"stdout": json.dumps({"data": {"stdout": json.dumps(output)}})}}
    assert local_scoring._score_output(wrapper, manifest["scorer_version"])["score"] == 100


@pytest.mark.parametrize("wrong_bundle", [False, True])
def test_historical_input_binding_excludes_wrong_received_bundle(tmp_path, monkeypatch, wrong_bundle):
    monkeypatch.syspath_prepend(str(ROOT / "checks"))
    import replay_figqa
    import audit_agentmaster_grader_diagnostics
    history = tmp_path / "history"
    iteration = history / "iterations/001"
    (iteration / "submission").mkdir(parents=True)
    (iteration / "workspace_snapshot/outputs").mkdir(parents=True)
    (iteration / "workspace_snapshot/outputs/answer.txt").write_text("[ANSWER]B[/ANSWER]")
    receipt = {"bundle_sha256": "generated", "challenge_id": scorer.CHALLENGE_ID,
               "bundle_response": {"metadata": {"bundle": {"sha256": "wrong" if wrong_bundle else "generated"},
                   "challenge_id": scorer.CHALLENGE_ID, "attempt_id": "synthetic"}}}
    (iteration / "submission/stdout.log").write_text(json.dumps(receipt))
    monkeypatch.setattr(audit_agentmaster_grader_diagnostics, "audit_receipt", lambda *_: {
        "challenge_id": scorer.CHALLENGE_ID, "output_snapshot_verified": True,
        "attempt_id": "synthetic", "science_score": 100, "receipt_sha256": "synthetic",
        "output_tree_sha256": "synthetic", "trace_score": 25, "display_score": 0})
    report = replay_figqa.prepare(history, tmp_path / "corpus")
    assert len(report["excluded"]) == int(wrong_bundle)
    assert len(report["samples"]) == int(not wrong_bundle)
    if not wrong_bundle:
        with zipfile.ZipFile(tmp_path / "corpus/cases/F001.zip") as archive:
            assert archive.namelist() == ["outputs/answer.txt"]
