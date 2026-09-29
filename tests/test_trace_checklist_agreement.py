import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location(
    "analyze_trace_checklist_agreement",
    Path(__file__).resolve().parents[1] / "checks/analyze_trace_checklist_agreement.py")
agreement = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(agreement)


def test_unlisted_v8_code_and_unobservable_v6_input_are_kept_distinct():
    rows = [
        {"sample": "S01", "items": [{"code": "N09", "status": "triggered"}],
         "codes": ["N09"], "cap": 49},
        {"sample": "S02", "items": [{"code": "N09", "status": "triggered"}],
         "codes": ["N09"], "cap": 49},
        {"sample": "S03", "items": [{"code": "N09", "status": "clear"}],
         "codes": [], "cap": 100},
        {"sample": "S04", "items": [{"code": "N09", "status": "not_observable"}],
         "codes": [], "cap": 100},
    ]
    labels = {
        "S01": {"reasons": ["N09"], "score": 45},
        "S02": {"reasons": [], "score": 30},
        "S03": {"reasons": ["N09"], "score": 70},
        "S04": {"reasons": ["N09"], "score": 80},
    }
    result = agreement.compare(rows, labels, "fix")
    item = result["items"][0]
    assert (item["tp"], item["fp"], item["fn"], item["tn"],
            item["not_observable"]) == (1, 1, 1, 0, 1)
    assert item["v8_listed_positives"] == 3
    assert item["eligible_positives"] == 2
    assert item["open_world_precision_bounds"] == [.5, 1]
    assert item["open_world_recall_bounds"] == [.5, 2 / 3]
    assert result["cap_violations"] == []


def test_predeclared_reliability_gates_require_positive_support():
    assert agreement.classification(2, 1, 1) == "unavailable_or_unknown"
    assert agreement.classification(3, .7, .7) == "indicative"
    assert agreement.classification(5, .9, .9) == "reliable"
    assert agreement.classification(5, None, 1) == "unavailable_or_unknown"
