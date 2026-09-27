import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "build_scorer_dataset", Path(__file__).resolve().parents[1] /
    "checks/build_scorer_dataset.py")
dataset = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dataset)


def _write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _fixture(tmp_path):
    challenge_id = "topic"
    challenge = {"roundStartAt": "2026-01-01T00:00:00Z",
                 "roundEndAt": "2026-01-02T00:00:00Z",
                 "scoring": {"strategy": "arm_v1_1_generic"}}
    challenge_sha, _ = _write(tmp_path, f"raw/challenges/{challenge_id}/detail.json", challenge)
    _write(tmp_path, "challenge_snapshots_manifest.json", {challenge_id: {"sha256": challenge_sha}})
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("arm_manifest.json", json.dumps({"trace": "trace/steps.jsonl"}))
        archive.writestr("trace/steps.jsonl", json.dumps({"step_type": "error", "body": "test failed"}) + "\n" +
                         json.dumps({"step_type": "decision", "body": "fix and validate"}) + "\n")
        archive.writestr("results/score.json", '{"score": 1}')
    raw_files = {}
    attempts = []
    for aid, created, card, status in (
        ("live", "2026-01-01T12:00:00Z", {"harbor_score": 80, "trace_score": 75}, "scored"),
        ("late", "2026-01-03T12:00:00Z", {"packaging": 90}, "late_scored"),
    ):
        prefix = f"raw/accounts/owner/attempts/{aid}/"
        detail = {"createdAt": created, "updatedAt": created,
                  "status": status, "scorecard": card,
                  "scoringState": {"displayScore": 80}}
        for name, value in (("detail.json", detail), ("score.json", {"status": status})):
            sha, _ = _write(tmp_path, prefix + name, value)
            raw_files[prefix + name] = {"sha256": sha}
        files = {}
        if aid == "live":
            sha, _ = _write(tmp_path, prefix + "bundle.zip", bundle.getvalue())
            raw_files[prefix + "bundle.zip"] = {"sha256": sha}
            files["bundle.zip"] = sha
        attempts.append({"id": aid, "challenge_id": challenge_id,
                         "content": "available" if files else "unavailable", "files": files})
    _write(tmp_path, "inventory.json", {
        "accounts": [{"alias": "owner", "role": "experiment", "credential_available": True,
                      "attempts": attempts}], "raw_files": raw_files})
    page = {"page": 1, "platform_total": 2,
            "rows": [{"status": "scored", "display_score": 72,
                      "harbor_score": 80, "trace_score": 70},
                     {"status": "scoring", "display_score": None,
                      "harbor_score": None, "trace_score": None}]}
    relative = f"raw/background/{challenge_id}/page-001.json"
    sha, size = _write(tmp_path, relative, page)
    _write(tmp_path, "background_pages_manifest.json", {
        challenge_id: {"platform_total": 2,
                       "pages": [{"page": 1, "relative_path": relative,
                                  "bytes": size, "sha256": sha}]}})
    return tmp_path


def test_rebuild_is_deterministic_and_separates_background(tmp_path):
    root = _fixture(tmp_path)
    first = dataset.build(root)
    assert first["scoring_modes"] == {"live_task_grader": 1, "late_generic_arm": 1}
    assert first["live_with_bundle"] == 1
    assert first["background"]["row_count"] == 2
    rows = [json.loads(line) for line in (root / "dataset.jsonl").read_text().splitlines()]
    live = next(row for row in rows if row["attempt_id"] == "live")
    assert live["trace_selection"]["rule"] == "manifest_pointer"
    assert live["trace_features"]["error_repair_pairs"] == 1
    assert "results/score.json" in live["science_files"]
    background = [json.loads(line) for line in (root / "background.jsonl").read_text().splitlines()]
    assert all(set(row) == {"challenge_id", "status", "display_score",
                                "harbor_score", "trace_score"} for row in background)
    assert dataset.build(root) == first


def test_rebuild_refuses_changed_raw_receipt(tmp_path):
    root = _fixture(tmp_path)
    detail = root / "raw/accounts/owner/attempts/live/detail.json"
    detail.write_bytes(detail.read_bytes() + b" ")
    with pytest.raises(ValueError, match="raw hash mismatch"):
        dataset.build(root)


def test_rebuild_refuses_incomplete_background(tmp_path):
    root = _fixture(tmp_path)
    manifest = root / "background_pages_manifest.json"
    data = json.loads(manifest.read_text())
    data["topic"]["platform_total"] = 3
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="background page metadata mismatch"):
        dataset.build(root)


def test_scoring_mode_keeps_outside_round_legacy_separate():
    challenge = {"roundStartAt": "2026-01-01T00:00:00Z",
                 "roundEndAt": "2026-01-02T00:00:00Z"}
    detail = {"createdAt": "2026-01-03T00:00:00Z", "status": "scored",
              "scorecard": {"harbor_score": 50}}
    assert dataset.classify(detail, challenge) == ("legacy_components_outside_round", "after")
    detail["status"] = "needs_review"
    assert dataset.classify(detail, challenge) == ("unscored_or_needs_review", "after")
