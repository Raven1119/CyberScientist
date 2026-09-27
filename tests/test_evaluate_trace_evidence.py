import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location(
    "evaluate_trace_evidence", Path(__file__).resolve().parents[1] /
    "checks/evaluate_trace_evidence.py")
evaluation = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(evaluation)


def test_score_only_rows_cannot_validate_predictor():
    own = [{"scoring_mode": "live_task_grader", "trace_score": 69,
            "trace_features": None, "bundle_sha256": None, "model": "m",
            "harness": "h"}]
    background = [{"trace_score": 69}, {"trace_score": 81}, {"trace_score": None}]
    result = evaluation.summarize(own, background)
    assert result["paired_live_count"] == 0
    assert result["model_status"] == "unavailable_no_paired_live_trace"
    assert result["noise_status"] == "unknown"
    assert result["validated_ge70_accuracy"] is None
    assert result["background_distribution"] == {
        "with_trace_score": 2, "below_70": 1, "below_80": 1, "median": 75.0}


def test_paired_rows_are_counted_only_from_live_mode():
    own = [
        {"scoring_mode": "late_generic_arm", "trace_score": 80,
         "trace_features": {"steps": 5}, "bundle_sha256": "same"},
        {"scoring_mode": "live_task_grader", "trace_score": 75,
         "trace_features": {"steps": 7}, "bundle_sha256": "same"},
    ]
    result = evaluation.summarize(own, [])
    assert result["paired_live_count"] == 1
    assert result["repeated_paired_bundle_count"] == 0
    assert result["model_status"] == "requires_validation"
