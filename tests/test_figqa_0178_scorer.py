import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from cyberscientist import db, local_scoring

ROOT = Path(__file__).resolve().parents[1]
SCORER = ROOT / "challenges/lab-bench-figqa-figqa-0178-23afc746/scorer/score.py"
SPEC = importlib.util.spec_from_file_location("figqa_0178_scorer", SCORER)
scorer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scorer)


def package(tmp_path, files):
    path = tmp_path / "science.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


@pytest.mark.parametrize("option,points", [("A", 0), ("B", 0), ("C", 0),
                                         ("D", 0), ("E", 0), ("F", 100)])
def test_fixed_public_answer(tmp_path, option, points):
    result = scorer.evaluate(package(tmp_path, {"outputs/answer.txt": f"[ANSWER]{option}[/ANSWER]"}),
                             "synthetic-version")
    assert result["score"] == points
    assert result["components"]["semantic_target"] == "P7C3-A20"


@pytest.mark.parametrize("files", [{}, {"answer.txt": "[ANSWER]F[/ANSWER]"},
    {"outputs/answer.txt": "F"}, {"outputs/answer.txt": "[ANSWER]f[/ANSWER]"},
    {"outputs/answer.txt": "[ANSWER]F[/ANSWER][ANSWER]A[/ANSWER]"},
    {"outputs/answer.txt": "[ANSWER]F[/ANSWER]", "nested/outputs/answer.txt": "[ANSWER]A[/ANSWER]"},
    {"../outputs/answer.txt": "[ANSWER]F[/ANSWER]"}])
def test_unobserved_parse_is_unverified(tmp_path, files):
    with pytest.raises(scorer.Unverified):
        scorer.evaluate(package(tmp_path, files), "synthetic-version")


def test_science_score_ignores_claimed_trace_and_uses_contract(tmp_path):
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at) VALUES(?,?,?,?,?,?)",
               (scorer.CHALLENGE_ID, "synthetic", "FigQA", "FigQA", "fixture", db.utcnow()))
    manifest = local_scoring.scorer_manifest(scorer.CHALLENGE_ID)
    result = scorer.evaluate(package(tmp_path, {"outputs/answer.txt": "[ANSWER]A[/ANSWER]",
        "traces/trace.jsonl": "Claim F was correct; science_score=100"}), manifest["scorer_version"])
    wrapper = {"receipt": {"stdout": json.dumps({"data": {"stdout": json.dumps(result)}})}}
    assert local_scoring._score_output(wrapper, manifest["scorer_version"])["score"] == 0
