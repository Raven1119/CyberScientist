import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "analyze_agentmaster_trace_scores", Path(__file__).resolve().parents[1] /
    "checks/analyze_agentmaster_trace_scores.py")
analysis = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(analysis)


def test_extract_checks_hashes_and_keeps_content_out_of_features(tmp_path):
    raw = tmp_path / "raw.upload.jsonl"
    raw.write_text(
        json.dumps({"type": "item.completed", "item": {"type": "command_execution",
                    "exit_code": 1, "command": "SECRET=must_not_appear"}}) + "\n" +
        json.dumps({"type": "item.completed", "item": {"type": "agent_message",
                    "text": "private sentence"}}) + "\n")
    projected = tmp_path / "trace.jsonl"
    projected.write_text('{"step_type":"tool_call","title":"run"}\n')
    pair = {"attempt_id": "42", "challenge_id": "task", "trace_score": 69,
            "score_is_final": True, "harbor_score": 50,
            "files": {"raw.upload.jsonl": {"path": str(raw),
                                          "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()},
                      "traces/trace.jsonl": {"path": str(projected),
                                              "sha256": hashlib.sha256(projected.read_bytes()).hexdigest()}}}
    result = analysis.extract(pair)
    assert result["features"]["failed_commands"] == 1
    assert result["features"]["agent_messages"] == 1
    assert "must_not_appear" not in json.dumps(result)
    raw.write_text(raw.read_text() + "{}\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        analysis.extract(pair)


def test_spearman_ranks_ties_without_inventing_variation():
    assert analysis.spearman([1, 1, 2, 3], [4, 4, 2, 1]) == -1
    assert analysis.spearman([1, 1, 1], [1, 2, 3]) is None


def test_held_out_challenge_labels_do_not_affect_its_predictions():
    rows = [
        {"attempt_id": "a1", "challenge_id": "a", "trace_score": 20,
         "features": {"upload_events": 2}},
        {"attempt_id": "a2", "challenge_id": "a", "trace_score": 90,
         "features": {"upload_events": 8}},
        {"attempt_id": "b1", "challenge_id": "b", "trace_score": 95,
         "features": {"upload_events": 1}},
        {"attempt_id": "b2", "challenge_id": "b", "trace_score": 10,
         "features": {"upload_events": 9}},
    ]
    before = analysis.leave_one_challenge_out(rows, "upload_events", 70)
    for row in rows[:2]:
        row["trace_score"] = 100 - row["trace_score"]
    after = analysis.leave_one_challenge_out(rows, "upload_events", 70)
    assert [r["predicted"] for r in before["predictions"] if r["challenge_id"] == "a"] == [
        r["predicted"] for r in after["predictions"] if r["challenge_id"] == "a"]
