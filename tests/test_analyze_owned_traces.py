import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "analyze_owned_traces", Path(__file__).resolve().parents[1] /
    "checks/analyze_owned_traces.py")
analysis = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(analysis)


def test_trace_features_are_descriptive_not_a_score():
    result = analysis.trace_features([
        {"type": "error", "title": "test failed"},
        {"type": "decision", "title": "fix and verify"},
        {"type": "tool_call", "title": "run validation"},
    ])
    assert result["step_count"] == 3
    assert result["type_counts"] == {"decision": 1, "error": 1, "tool_call": 1}
    assert result["stage_mentions_heuristic"]["validation"] == 3
    assert result["error_followed_by_action_within_3_steps_heuristic"] == 1


def test_bundle_selection_does_not_count_unselected_event_logs():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("arm_manifest.json", json.dumps({"trace": "traces/main.jsonl"}))
        archive.writestr("traces/main.jsonl", json.dumps({"step_type": "tool_call", "title": "run"}) + "\n")
        archive.writestr("traces/event_index.jsonl", json.dumps({"type": "event", "seq": 1}) + "\n")
    result = analysis.bundle_features(stream.getvalue(), [{"type": "tool_call", "title": "run"}])
    assert result["selected_members"] == ["traces/main.jsonl"]
    assert result["selected_rows"] == result["schema_shaped_rows"] == 1
    assert result["api_title_type_overlap"] == 1


def test_direct_credential_trace_overrides_empty_operator_view(tmp_path):
    def save(relative, value):
        raw = json.dumps(value).encode()
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    author, aid = "owned_agent", "attempt_1"
    listed = {"attempts": [{"id": aid, "authorId": author, "traceCount": 1,
                            "scorecard": {"trace_score": 82}}]}
    list_sha = save(f"attempt-lists/{author}.json", listed)
    empty_sha = save(f"raw/{author}/{aid}/trace.json", [])
    direct_sha = save(f"raw/{author}/{aid}/direct-trace.json",
                      [{"type": "observation", "title": "observed"}])
    save("owned_lists_summary.json", [{"author_id": author, "visible_attempts": 1,
                                       "list_sha256": list_sha}])
    save("trace_inventory.json", [{"author_id": author, "attempt_id": aid,
                                   "files": {"trace.json": empty_sha}, "errors": []}])
    save("direct_mailbox_inventory.json", [{"author_id": author, "attempt_id": aid,
                                             "files": {"direct-trace.json": direct_sha},
                                             "errors": []}])
    save("export_mismatch_summary.json", [])
    result = analysis.analyze(tmp_path)
    assert result["retrieved_positive"] == result["legacy_paired_count"] == 1
    assert result["attempts"][0]["operator_trace_count"] == 0
    assert result["attempts"][0]["trace_source"] == "direct_agent"


def test_verified_file_stays_inside_audit_root(tmp_path):
    with pytest.raises(ValueError, match="escapes root"):
        analysis._verified(tmp_path / "audit", Path("../other.json"), "unused")
