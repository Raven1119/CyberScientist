import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location(
    "analyze_historical_scores", Path(__file__).resolve().parents[1] /
    "checks/analyze_historical_scores.py")
analysis = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(analysis)


def test_formula_classification_keeps_regimes_and_missing_separate():
    row = {"harbor_score": 60.0, "trace_score": 69.0, "display_score": 58.5}
    assert analysis.classify_formula(row)["class"] == "formula_a"
    row["display_score"] = 41.4
    assert analysis.classify_formula(row)["class"] == "formula_b"
    row["display_score"] = 17.0
    assert analysis.classify_formula(row)["class"] == "neither"
    row["display_score"] = None
    assert analysis.classify_formula(row)["class"] == "missing"
    row.update({"harbor_score": 0.0, "display_score": 0.0})
    assert analysis.classify_formula(row)["class"] == "both"


def test_analysis_only_uses_live_rows_and_preserves_anomalies():
    rows = [
        {"scoring_mode": "live_task_grader", "challenge_id": "topic",
         "attempt_id": "a", "harbor_score": 60, "trace_score": 69,
         "display_score": 41.4, "science_files": None,
         "override_in_effect": False, "score_is_final": True},
        {"scoring_mode": "late_generic_arm", "challenge_id": "topic",
         "attempt_id": "b", "harbor_score": 60, "trace_score": 69,
         "display_score": 58.5, "science_files": {"results/x": {}},
         "override_in_effect": False, "score_is_final": True},
    ]
    result = analysis.analyze(rows)
    assert result["live_count"] == 1
    assert result["formula_classes"] == {"formula_b": 1}
    assert result["by_challenge"]["topic"]["science_artifact_count"] == 0
    assert result["anomalies"][0]["attempt_id"] == "a"


def test_reward_scaling_is_checked_without_inferring_science_inputs():
    rows = [
        {"scoring_mode": "live_task_grader", "challenge_id": "topic",
         "attempt_id": "a", "harbor_score": 60, "trace_score": 69,
         "display_score": 41.4, "scorecard": {
             "harbor_reward": 0.6, "harbor_replay_executed": 1}},
        {"scoring_mode": "live_task_grader", "challenge_id": "topic",
         "attempt_id": "b", "harbor_score": 70, "trace_score": 80,
         "display_score": 70, "scorecard": {
             "harbor_reward": 0.5, "harbor_replay_executed": 1}},
    ]
    result = analysis.analyze(rows)["harbor_reward_x100"]
    assert result == {"paired_count": 2, "max_abs_error": 20.0,
                      "mismatch_count_at_1e_6": 1, "replay_executed_count": 2}


def test_gate70_hypothesis_counts_held_boundary_as_unobserved():
    rows = [
        {"scoring_mode": "live_task_grader", "challenge_id": "topic",
         "attempt_id": "below", "harbor_score": 60, "trace_score": 69,
         "display_score": 41.4},
        {"scoring_mode": "live_task_grader", "challenge_id": "topic",
         "attempt_id": "above", "harbor_score": 60, "trace_score": 76,
         "display_score": 60},
        {"scoring_mode": "live_task_grader", "challenge_id": "topic",
         "attempt_id": "missing", "harbor_score": 60, "trace_score": 70,
         "display_score": None},
    ]
    assert analysis.analyze(rows)["gate70_hypothesis"] == {
        "complete_count": 2, "max_abs_error": 0.0,
        "mismatch_count_at_0_001": 0,
        "max_distinguishable_below": 69.0,
        "min_distinguishable_above": 76.0,
    }
