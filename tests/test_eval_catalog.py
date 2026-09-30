import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_schema_and_evidence_links():
    schema = json.loads((ROOT / "evals/catalog.schema.json").read_text())
    catalog = json.loads((ROOT / "evals/catalog.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(catalog, schema)
    ids = [item["challenge_id"] for item in catalog["challenges"]]
    assert len(ids) == len(set(ids))
    assert {item["tier"] for item in catalog["challenges"] if item["included"]} == {"fast", "hard"}
    for item in catalog["challenges"]:
        scorer = item["science_scorer"]
        assert all((ROOT / ref).is_file() for ref in scorer["evidence_refs"])
        if item["included"]:
            assert scorer["status"] != "unavailable"
            assert (ROOT / scorer["directory"] / "scorer.json").is_file()
        lower, upper = item["expected_run_cost"]["wall_minutes_range"]
        assert lower <= upper
        if item["public_score_distribution"]["status"] == "unavailable":
            assert item["public_score_distribution"]["sample_count"] is None


def test_two_new_candidates_have_distinct_evidence_levels():
    items = {item["challenge_id"]: item for item in
             json.loads((ROOT / "evals/catalog.json").read_text())["challenges"]}
    figqa = items["lab-bench-figqa-figqa-0178-23afc746"]
    matchgate = items["flowforge-matchgate-swap-inverse-synthesis-v2-4019e745"]
    assert figqa["included"] and figqa["science_scorer"]["status"] == "receipt_validated"
    assert matchgate["included"] and matchgate["science_scorer"]["status"] == "spec_validated"
    assert matchgate["evaluation_difficulty"]["estimated_minutes"] is None
