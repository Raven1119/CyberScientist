import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "audit_agentmaster_grader_diagnostics", Path(__file__).resolve().parents[1] /
    "checks/audit_agentmaster_grader_diagnostics.py")
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


def make_receipt(tmp_path, decision="review", trace_score=69, factor=0.69):
    iteration = tmp_path / "iteration"
    (iteration / "submission").mkdir(parents=True)
    (iteration / "grader").mkdir()
    trace = iteration / "raw.upload.jsonl"
    trace.write_text(json.dumps({"type": "item.completed", "item": {
        "type": "command_execution", "exit_code": 0, "command": "secret text"}}) + "\n")
    outputs = tmp_path / "live/outputs"
    sealed = iteration / "workspace_snapshot/outputs"
    outputs.mkdir(parents=True)
    sealed.mkdir(parents=True)
    (outputs / "answer.txt").write_text("private answer")
    (sealed / "answer.txt").write_text("private answer")
    (iteration / "submission/submission.json").write_text(
        json.dumps({"attempt_id": 12, "status": "submitted"}))
    (iteration / "submission/stdout.log").write_text(
        json.dumps({"attempt_id": "12", "bundle_sha256": "bundle-digest",
                    "bundle_response": {"native_trace_sha256":
                        hashlib.sha256(trace.read_bytes()).hexdigest()}}))
    (iteration / "submission/command.json").write_text(json.dumps({"argv": [
        "playground", "submit", "--challenge-id", "task", "--trace", str(trace),
        "--outputs", str(outputs)]}))
    score = 80 * factor
    (iteration / "grader/grader.json").write_text(json.dumps({
        "attempt_id": 12, "status": "scored", "score": score}))
    raw = iteration / "grader/grader.raw.json"
    raw.write_text(json.dumps({"attempt_id": 12, "detail": {
        "challengeId": "task", "scoringDetails": {"trace_factor": factor},
        "resultsJson": {"trace_decision": decision, "trace_score": trace_score,
                        "trace_score_engine": "engine", "harbor_score": 80,
                        "score_percent": score,
                        "trace_low_score_reasons": [{"code": "N09_NO_EXECUTION_EVIDENCE",
                                                     "score_effect": -30}],
                        "trace_missing_evidence": ["secret reason"]}}}))
    return raw


def test_receipt_verifies_join_factor_and_content_free_features(tmp_path):
    path = make_receipt(tmp_path)
    row = audit.audit_receipt(path)
    assert row["factor_error"] == 0
    assert row["display_error"] == 0
    assert row["trace_receipt_match"]
    assert row["trace_features"]["successful_commands"] == 1
    assert row["output_file_count"] == 1
    assert row["output_snapshot_verified"]
    assert "secret" not in json.dumps(row)
    assert "private answer" not in json.dumps(row)
    summary = audit.summarize([row])
    assert summary["no_execution_reason_with_successful_commands"] == 1


def test_mismatched_submission_and_missing_trace_are_not_silently_paired(tmp_path):
    path = make_receipt(tmp_path)
    trace = path.parent.parent / "raw.upload.jsonl"
    trace.unlink()
    assert audit.audit_receipt(path)["trace_receipt_match"] is False
    submission = path.parent.parent / "submission/submission.json"
    submission.write_text(json.dumps({"attempt_id": 13, "status": "submitted"}))
    with pytest.raises(ValueError, match="mismatch"):
        audit.audit_receipt(path)


def test_changed_live_output_is_not_accepted_as_sealed_submission(tmp_path):
    path = make_receipt(tmp_path)
    (tmp_path / "live/outputs/answer.txt").write_text("changed")
    with pytest.raises(ValueError, match="differ"):
        audit.audit_receipt(path)


def test_harvest_without_snapshot_is_explicitly_unverified(tmp_path):
    path = make_receipt(tmp_path)
    (path.parent.parent / "workspace_snapshot/outputs/answer.txt").unlink()
    (path.parent.parent / "workspace_snapshot/outputs").rmdir()
    row = audit.audit_receipt(path)
    assert not row["output_snapshot_verified"]
    assert row["output_file_count"] == 1


def test_trace_path_is_not_treated_as_upload_when_receipt_hash_differs(tmp_path):
    path = make_receipt(tmp_path)
    trace = path.parent.parent / "raw.upload.jsonl"
    saved = tmp_path / "saved-raw.jsonl"
    saved.write_bytes(trace.read_bytes())
    original_sha = hashlib.sha256(saved.read_bytes()).hexdigest()
    trace.write_text(trace.read_text() + '{}\n')
    row = audit.audit_receipt(path)
    assert row["command_trace_path_available"]
    assert not row["trace_receipt_match"]
    assert not row["native_trace_content_available"]
    assert row["trace_features"] is None
    recovered = audit.audit_receipt(path, {original_sha: [saved]})
    assert recovered["native_trace_content_available"]
    assert recovered["native_trace_source_kind"] == "other_iteration"
    assert recovered["trace_features"]["successful_commands"] == 1


def test_older_pair_requires_receipt_digest_and_unchanged_file(tmp_path):
    path = make_receipt(tmp_path)
    iteration = path.parent.parent
    trace = iteration / "raw.upload.jsonl"
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text(json.dumps({"valid_join": True, "iteration": str(iteration),
                                 "files": {"raw.upload.jsonl": {"path": str(trace),
                                     "sha256": hashlib.sha256(trace.read_bytes()).hexdigest()}}}) + "\n")
    assert audit.verify_older_pairs(pairs)["native_trace_receipt_matches"] == 1
    trace.write_text("{}\n")
    assert audit.verify_older_pairs(pairs)["native_trace_receipt_matches"] == 0
