"""Legacy manifest references never become new submissions or automatic retries."""
import json
from pathlib import Path

import pytest

from cyberscientist import config, db, decision, mailboxes
from cyberscientist.brains.codex import CodexBrain
from cyberscientist.brains.kimi import KimiBrain
from cyberscientist.controller import RunController
from test_decision import valid_decision
from test_mailboxes import _make_package, _seed_challenge


@pytest.mark.parametrize("allow_formal", [False, True])
@pytest.mark.parametrize("manifest_exists", [False, True])
async def test_legacy_ref_rejected_without_submission_or_fallback(
        monkeypatch, allow_formal, manifest_exists):
    settings = config.load_settings()
    settings["policy"]["allow_formal_submission"] = allow_formal
    config.save_settings(settings)
    _seed_challenge()
    controller = RunController()
    rid = controller.create_run("MB_CH", mode="demo")["id"]
    controller.authorize(rid, "demo", True, 10, 30, 1, None)
    tid = "trial_mb1"
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at)"
               " VALUES(?,?,?,?,'active',?)", (tid, rid, "goal", "check", db.utcnow()))
    db.execute("UPDATE runs SET phase='running',current_trial_id=? WHERE id=?", (tid, rid))
    package = Path(_make_package(rid))
    (config.WORKSPACE_DIR / package.with_suffix(".zip")).write_bytes(b"fixture only")
    ref = package.with_name("bundle_manifest.json").as_posix()
    if manifest_exists:
        (config.WORKSPACE_DIR / ref).write_text(json.dumps({"package_path": str(package)}))

    def forbidden(*args, **kwargs):
        pytest.fail("A rejected legacy ref must not resolve, submit or queue another review")

    monkeypatch.setattr(mailboxes, "_resolve_package", forbidden)
    monkeypatch.setattr(mailboxes, "submit_experiment", forbidden)
    monkeypatch.setattr(controller, "_execute_submit", forbidden)
    monkeypatch.setattr(controller, "request_review", forbidden)
    dec = valid_decision(run_id=rid, actions=[{
        "op": "request_submission", "trial_id": tid, "bundle_manifest_ref": ref}])
    assert decision.validate_structure(dec) == []
    await controller._apply_decision(rid, dec, {}, None, None)
    await controller._apply_decision(rid, dec, {}, None, None)
    events = db.events_after(rid, 0)
    rejected = [e["payload"] for e in events if e["type"] == "brain.action_rejected"]
    assert len(rejected) == 2
    assert not any(e["type"] == "brain.action_deferred" for e in events)
    for payload in rejected:
        assert payload["op"] == "request_submission"
        reasons = " ".join(payload["reasons"])
        if allow_formal:
            assert payload["bundle_manifest_ref"] == ref and payload["trial_id"] == tid
            assert "未执行提交" in reasons and "ReviewResult" in reasons
            assert "guidance.kind=submit" in reasons
        else:
            assert "policy.allow_formal_submission=false" in reasons
    for table in ("submissions", "guidance", "review_requests"):
        assert db.query_one(f"SELECT count(*) AS n FROM {table} WHERE run_id=?", (rid,))["n"] == 0
    assert controller.run_snapshot(rid)["phase"] == "running"


async def test_rejected_legacy_ref_is_bounded_and_secret_redacted():
    settings = config.load_settings()
    settings["policy"]["allow_formal_submission"] = True
    config.save_settings(settings)
    config.save_secrets({"test": "test-known-secret"})
    _seed_challenge()
    controller = RunController()
    rid = controller.create_run("MB_CH", mode="demo")["id"]
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    ref = "https://example.invalid/test-known-secret?accessKey=query-secret&ref=" + "x" * 5000
    await controller._apply_decision(rid, valid_decision(run_id=rid, actions=[{
        "op": "request_submission", "trial_id": "trial_missing", "bundle_manifest_ref": ref}]), {}, None, None)
    events = db.events_after(rid, 0)
    assert "test-known-secret" not in json.dumps(events)
    assert "query-secret" not in json.dumps(events)
    payload = next(e["payload"] for e in events if e["type"] == "brain.action_rejected")
    assert len(payload["bundle_manifest_ref"]) <= 4000
    assert db.query_one("SELECT count(*) AS n FROM submissions")["n"] == 0


@pytest.mark.parametrize("brain", [CodexBrain, KimiBrain])
def test_brain_prompt_names_supported_submit_route_and_legacy_rejection(brain):
    prompt = brain._render_prompt({"trigger": "trial.completed"})
    assert '- {"op":"request_submission"' not in prompt
    assert "request_submission 会被明确拒绝" in prompt
    assert "guidance.kind=submit" in prompt
    assert "不要在当前 Decision 中混入 ReviewResult" in prompt
    review_prompt = brain._render_prompt({"protocol": "review_result", "frame_id": "frame_test"})
    assert '"kind":"nudge|steer|stop|submit"' in review_prompt
    assert "已有 Run 授权、提交预算" in review_prompt and "去重检查" in review_prompt
