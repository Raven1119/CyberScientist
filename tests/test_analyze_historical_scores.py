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
