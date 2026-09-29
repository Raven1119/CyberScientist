"""Submission-time diagnostics are advisory and preserve tool evidence."""
from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

import pytest

from cyberscientist import config, db, mailboxes, observation, trace_diagnostics, trace_selection
from test_trace_narrative import _fixture


def _zip(rows: list[dict]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("arm_manifest.json", json.dumps({
            "arm_version": "1.1", "trace": "traces/trace.jsonl",
            "execution": {"artifacts": [{"path": "result.txt"}]}}))
        archive.writestr("traces/trace.jsonl", "".join(json.dumps(row) + "\n" for row in rows))
        archive.writestr("result.txt", "42\n")
    return stream.getvalue()


def test_advice_only_requests_real_work():
    assert set(trace_diagnostics.GRADES) == set(trace_diagnostics.ADVICE)
    forbidden = ("关键词", "触发检测", "改写措辞", "凑检测", "add keyword",
                 "trigger detection", "rewrite wording")
    for advice in trace_diagnostics.ADVICE.values():
        assert not any(phrase in advice.lower() for phrase in forbidden)
    narrowed = trace_diagnostics.executor_view({"status": "ready", "checklist_cap": 20,
        "advisory_cap": None, "details": [{"code": "N04_TRACE_SCHEMA_INVALID"}],
        "advisories": [{"code": "N04_TRACE_SCHEMA_INVALID", "action": "不要显示"},
                       {"code": "N09_NO_EXECUTION_EVIDENCE", "action": "执行真实计算"}]})
    assert "details" not in narrowed and "checklist_cap" not in narrowed
    assert narrowed["advisory_cap"] is None
    assert all(item["code"] != "N04_TRACE_SCHEMA_INVALID" for item in narrowed["advisories"])


def test_legacy_projected_pairs_survive_conversion_and_public_parser():
    rows = [
        {"step_type": "tool_call", "tool_call_id": "a", "cs_ref": "run#1",
         "title": "real command", "timestamp": "2026-09-30T00:00:00Z"},
        {"step_type": "tool_result", "tool_call_id": "a", "cs_ref": "run#2",
         "tool_output": "42", "timestamp": "2026-09-30T00:00:01Z"},
    ]
    selected = trace_selection.select({"arm_manifest.json": json.dumps({
        "trace": "traces/trace.jsonl"}).encode(),
        "traces/trace.jsonl": ("".join(json.dumps(row) + "\n" for row in rows)).encode()})
    result = trace_diagnostics.diagnose_sealed_package(_zip(rows))
    assert result["status"] == "ready", result.get("reason")
    assert result["selected_rows"] == len(selected.rows) == 2
    assert result["paired_tool_calls"] == 1
    assert result["adapter_labels_added"] == 2


def test_diagnostic_failure_does_not_change_submission_gate(monkeypatch):
    run_id, trial_id, *_ = _fixture()
    monkeypatch.setattr(mailboxes.arm_admission, "check",
                        lambda *_: {"verdict": "admitted", "signals": {}})
    original = mailboxes.preflight_submission(run_id, trial_id, None)
    with zipfile.ZipFile(io.BytesIO(original["sealed_bytes"])) as archive:
        selected = trace_selection.select({name: archive.read(name) for name in archive.namelist()})
    assert original["trace_diagnostics"]["status"] == "ready"
    assert original["trace_diagnostics"]["paired_tool_calls"] == \
        trace_diagnostics._tool_counts(list(selected.rows))[2]
    def fail(*_args):
        raise RuntimeError("fixture failure")
    monkeypatch.setattr(trace_diagnostics, "diagnose_sealed_package", fail)
    failed = mailboxes.preflight_submission(run_id, trial_id, None)
    assert failed["trace_diagnostics"]["status"] == "unavailable"
    assert failed["error_code"] == original["error_code"]
    assert failed["sealed_package_sha256"] == original["sealed_package_sha256"]


def test_submission_review_frame_uses_durable_diagnostic_summary(monkeypatch):
    run_id, trial_id, *_ = _fixture()
    mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, "check",
                        lambda *_: {"verdict": "admitted", "signals": {}})
    monkeypatch.setattr(trace_diagnostics, "diagnose_sealed_package", lambda *_: {
        "status": "ready", "checklist_cap": 49, "advisory_cap": 49,
        "advisories": [{"code": "N09_NO_EXECUTION_EVIDENCE", "grade": "reliable",
                        "reason": "缺执行证据", "action": "执行真实计算"}], "details": []})
    submission = mailboxes.submit_experiment(run_id, trial_id, None,
        "trace-diagnostic-fixture", prediction_md="真实证据补齐后，预计轨迹分增加")
    through = db.query_one("SELECT MAX(seq) AS n FROM events WHERE run_id=?", (run_id,))["n"]
    frame = observation.build_frame(run_id, mode="lifecycle", frame_id="diagnostic-frame",
                                    from_seq=1, through_seq=through,
                                    shadow_cfg=config.load_settings()["shadow"], sparse=True)
    summary = frame["submission_summary"]
    assert summary["submission_id"] == submission["id"]
    assert summary["trace_diagnostics"]["checklist_cap"] == 49
    assert summary["trace_diagnostics"]["advisories"][0]["code"] == "N09_NO_EXECUTION_EVIDENCE"
    db.append_event(run_id, "controller", "submission.created", {
        "submission_id": "different-trial", "trace_diagnostics": {
            "status": "ready", "checklist_cap": 20, "advisories": []}}, trial_id="other-trial")
    later = db.query_one("SELECT MAX(seq) AS n FROM events WHERE run_id=?", (run_id,))["n"]
    frame = observation.build_frame(run_id, mode="lifecycle", frame_id="diagnostic-frame-later",
                                    from_seq=1, through_seq=later,
                                    shadow_cfg=config.load_settings()["shadow"], sparse=True)
    assert frame["submission_summary"]["submission_id"] == submission["id"]


def test_historical_e008_e010_e011_only_when_local_evidence_available():
    path = Path(".package-checks/cs-up-04/conversions.jsonl")
    if not path.is_file():
        pytest.skip("private historical conversion evidence is not installed")
    records = {item["sample"]: item for item in map(json.loads, path.read_text().splitlines())}
    def diagnostic(sample: str, variant: str) -> dict:
        rows = [json.loads(line) for line in Path(records[sample][variant]["path"]).read_text().splitlines()]
        result = trace_diagnostics.diagnose_normalized_trace(rows)
        assert result["status"] == "ready"
        return result
    def codes(result: dict) -> set[str]:
        return {item["code"] for item in result["details"]}
    original = diagnostic("S30", "cli")
    assert "N04_TRACE_SCHEMA_INVALID" in codes(original)
    assert original["checklist_cap"] == 20 and original["advisory_cap"] is None
    assert next(item for item in original["details"] if item["code"] == "N04_TRACE_SCHEMA_INVALID")["implied_cap"] == 20
    assert "N04_TRACE_SCHEMA_INVALID" not in {item["code"] for item in original["advisories"]}
    assert "N04_TRACE_SCHEMA_INVALID" not in codes(diagnostic("S30", "fix"))
    e010 = diagnostic("S32", "fix")
    assert "N09_NO_EXECUTION_EVIDENCE" in codes(e010)
    assert e010["advisory_cap"] == 49
    assert "N09_NO_EXECUTION_EVIDENCE" not in codes(diagnostic("S33", "fix"))


def test_h7_abc_sealed_trace_pairs_when_local_evidence_available():
    path = Path("workspace/submissions/sub_2d30d5b21d/package.zip")
    if not path.is_file():
        pytest.skip("private H7 ARM bundle is not installed")
    with zipfile.ZipFile(path) as archive:
        selection = trace_selection.select({name: archive.read(name) for name in archive.namelist()})
    expected = trace_diagnostics._tool_counts(list(selection.rows))[2]
    result = trace_diagnostics.diagnose_sealed_package(path.read_bytes())
    assert result["status"] == "ready", result.get("reason")
    assert result["paired_tool_calls"] == expected == 43
    assert result["selected_rows"] == len(selection.rows)
