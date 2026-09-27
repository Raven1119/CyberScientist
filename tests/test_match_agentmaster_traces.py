import importlib.util
import json
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "match_agentmaster_traces", Path(__file__).resolve().parents[1] /
    "checks/match_agentmaster_traces.py")
matcher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(matcher)


def _fixture(tmp_path, command_challenge="challenge-a"):
    agentmaster = tmp_path / "AgentMaster"
    iteration = agentmaster / "store/T0/challenge-a-ep001/iterations/000"
    (iteration / "submission").mkdir(parents=True)
    (iteration / "traces").mkdir()
    (iteration / "submission/submission.json").write_text(
        json.dumps({"attempt_id": 42, "status": "submitted"}))
    (iteration / "submission/command.json").write_text(json.dumps({
        "argv": ["playground", "submit", "--challenge-id", command_challenge,
                 "--trace", str(iteration / "raw.upload.jsonl")]}))
    for name in ("raw.jsonl", "raw.upload.jsonl"):
        (iteration / name).write_text('{"type":"item.completed","item":{"type":"agent_message"}}\n')
    (iteration / "traces/trace.jsonl").write_text(
        '{"step_type":"thought","title":"observed"}\n')
    (iteration / "grader").mkdir()
    (iteration / "grader/grader.json").write_text(
        json.dumps({"trace_score": 81.0, "status": "scored"}))
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(json.dumps({
        "attempt_id": "42", "challenge_id": "challenge-a", "scoring_mode": "live_task_grader",
        "score_is_final": True, "trace_score": 81.0}) + "\n")
    return dataset, agentmaster


def test_exact_attempt_and_submit_command_pair_trace_with_score(tmp_path):
    dataset, agentmaster = _fixture(tmp_path)
    pairs, summary = matcher.match(dataset, agentmaster)
    assert len(pairs) == summary["valid_joins"] == summary["paired_final_trace_scores"] == 1
    assert pairs[0]["files"]["raw.upload.jsonl"]["rows"] == 1
    assert pairs[0]["local_grade_matches_snapshot"] is True


def test_challenge_mismatch_does_not_validate_pair(tmp_path):
    dataset, agentmaster = _fixture(tmp_path, command_challenge="challenge-b")
    pairs, summary = matcher.match(dataset, agentmaster)
    assert len(pairs) == 1
    assert pairs[0]["valid_join"] is False
    assert summary["valid_joins"] == summary["paired_trace_scores"] == 0


def test_duplicate_scored_attempt_is_rejected(tmp_path):
    dataset, agentmaster = _fixture(tmp_path)
    dataset.write_text(dataset.read_text() * 2)
    with pytest.raises(ValueError, match="duplicate scored Attempt"):
        matcher.match(dataset, agentmaster)
