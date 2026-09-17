"""Decision schema 结构校验 + 后端语义校验。"""
from __future__ import annotations

from cyberscientist import decision as d


def valid_decision(**over):
    dec = {
        "schema_version": 1,
        "decision_id": "dec_t1",
        "run_id": "run_t1",
        "observed_state_version": 0,
        "summary": "测试判断",
        "evidence_refs": ["demo://x"],
        "actions": [{"op": "wait", "reason": "无新证据"}],
        "experience_proposals": [],
    }
    dec.update(over)
    return dec


def test_valid_wait_passes():
    assert d.validate_structure(valid_decision()) == []


def test_missing_required_fails():
    bad = valid_decision()
    del bad["summary"]
    errors = d.validate_structure(bad)
    assert errors and "summary" in errors[0]


def test_unknown_action_fails():
    bad = valid_decision(actions=[{"op": "hack_the_planet", "reason": "x"}])
    assert d.validate_structure(bad)


def test_too_many_actions_fails():
    bad = valid_decision(actions=[{"op": "wait", "reason": "a"}] * 4)
    assert d.validate_structure(bad)


def test_experience_proposal_scope_constraint():
    bad = valid_decision(experience_proposals=[{
        "scope": "global", "challenge_id": "CH1", "title": "t",
        "body_md": "b", "applicability": "a", "evidence_refs": []}])
    assert d.validate_structure(bad)
    ok = valid_decision(experience_proposals=[{
        "scope": "challenge", "challenge_id": "CH1", "title": "t",
        "body_md": "b", "applicability": "a", "evidence_refs": []}])
    assert d.validate_structure(ok) == []


def test_semantics_two_direction_ops():
    dec = valid_decision(actions=[
        {"op": "start_trial", "goal": "g", "success_check": "s"},
        {"op": "finish", "reason": "r"}])
    errors = d.validate_semantics(dec, has_active_trial=False,
                                  current_trial_id=None,
                                  allow_formal_submission=False)
    assert any("最多一个" in e for e in errors)


def test_semantics_steer_requires_active_trial():
    dec = valid_decision(actions=[
        {"op": "steer", "trial_id": "t1", "message": "m"}])
    errors = d.validate_semantics(dec, has_active_trial=False,
                                  current_trial_id=None,
                                  allow_formal_submission=False)
    assert any("活跃 Trial" in e for e in errors)
    errors = d.validate_semantics(dec, has_active_trial=True,
                                  current_trial_id="t2",
                                  allow_formal_submission=False)
    assert any("不符" in e for e in errors)


def test_semantics_submission_requires_policy():
    dec = valid_decision(actions=[
        {"op": "request_submission", "trial_id": "t1", "bundle_manifest_ref": "m"}])
    errors = d.validate_semantics(dec, has_active_trial=True,
                                  current_trial_id="t1",
                                  allow_formal_submission=False)
    assert any("正式提交" in e for e in errors)
    assert d.validate_semantics(dec, has_active_trial=True,
                                current_trial_id="t1",
                                allow_formal_submission=True) == []
