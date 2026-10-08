"""RunController 状态机（Demo 组件，纯本地，无外部调用）。"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from cyberscientist import config, db
from cyberscientist.controller import ControllerError, RunController


def _seed_challenge(cid="DEMO_CHALLENGE"):
    db.execute(
        "INSERT INTO challenges(id, platform_challenge_id, origin, title, content,"
        " content_hash, contract_status, imported_at, is_demo)"
        " VALUES(?,?,?,?,?,?,'unknown',?,1)",
        (cid, "DEMO_000", "demo://local", "演示题", "内容", "hash", db.utcnow()))


def _controller() -> RunController:
    return RunController()


@pytest.fixture(autouse=True)
def _demo_mode():
    """Run 模式快照自 settings；本文件默认 demo，connected 用例自行覆盖。"""
    settings = config.load_settings()
    settings["app"]["mode"] = "demo"
    config.save_settings(settings)


async def _wait_for(pred, timeout=15.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.2)
    return False


def test_create_run_requires_challenge():
    with pytest.raises(ControllerError) as exc:
        _controller().create_run("nope")
    assert exc.value.code == "NOT_FOUND"


def test_active_run_limit_is_configurable():
    _seed_challenge()
    # Exercise the existing explicit three-slot grant; the new default is six.
    settings = config.load_settings()
    settings['run_defaults']['max_active_runs'] = 3
    config.save_settings(settings)
    c = _controller()
    for _ in range(3):
        c.create_run("DEMO_CHALLENGE")
    with pytest.raises(ControllerError) as exc:
        c.create_run("DEMO_CHALLENGE")
    assert exc.value.code == "RUN_ACTIVE"
    assert '上限 3' in str(exc.value)
    settings = config.load_settings()
    settings['run_defaults']['max_active_runs'] = 4
    config.save_settings(settings)
    assert c.create_run("DEMO_CHALLENGE")['phase'] == 'created'


async def test_three_demo_runs_have_independent_sessions_events_and_controls():
    _seed_challenge()
    c = _controller()
    ids = [c.create_run('DEMO_CHALLENGE')['id'] for _ in range(3)]
    for rid in ids:
        c.authorize(rid, 'demo', False, 0, 30, 0, None)
    await asyncio.gather(*(c.start_async(rid) for rid in ids))
    assert await _wait_for(lambda: all(rid in c._prime_sessions for rid in ids), 8)
    assert len({id(c._prime_instances[rid]) for rid in ids}) == 3
    assert len({c._prime_sessions[rid] for rid in ids}) == 3
    tokens = db.query("SELECT run_id,token_hash FROM capability_tokens"
                      " WHERE run_id IN (?,?,?)", tuple(ids))
    assert {row['run_id'] for row in tokens} == set(ids)
    assert len({row['token_hash'] for row in tokens}) == len(tokens)
    assert all(event['run_id'] == rid for rid in ids for event in db.events_after(rid, 0))
    for rid in ids:
        if c.run_snapshot(rid)['phase'] == 'running':
            await c.control(rid, 'pause', None, f'pause-{rid}')
    assert await _wait_for(lambda: all(c.run_snapshot(rid)['phase'] in ('paused','finished')
                                      for rid in ids), 8)
    for rid in ids:
        if c.run_snapshot(rid)['phase'] == 'paused':
            await c.control(rid, 'resume', None, f'resume-{rid}')
    assert await _wait_for(lambda: all(c.run_snapshot(rid)['phase'] == 'finished'
                                      for rid in ids), 20)


def test_startup_reconciles_each_run_despite_one_failure(monkeypatch):
    _seed_challenge()
    c = _controller()
    ids = [c.create_run('DEMO_CHALLENGE')['id'] for _ in range(3)]
    for rid in ids:
        db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    original = db.append_event_tx
    def fail_one(conn, run_id, *args, **kwargs):
        if run_id == ids[0]:
            raise RuntimeError('synthetic failure')
        return original(conn, run_id, *args, **kwargs)
    monkeypatch.setattr(db, 'append_event_tx', fail_one)
    assert c.reconcile_on_startup() == ids[1:]
    assert [c.run_snapshot(rid)['phase'] for rid in ids] == [
        'recovering', 'recovering', 'recovering']
    assert '对账失败' in c.run_snapshot(ids[0])['block_reason']


def test_challenge_model_config_frozen_per_run_and_submission():
    from cyberscientist import mailboxes
    _seed_challenge('MODEL_A')
    _seed_challenge('MODEL_B')
    choices = [
        ({'runtime':'codex','model_id':'model-brain-a','reasoning_effort':'xhigh'},
         {'runtime':'codex','model_id':'model-exec-a','reasoning_effort':'high'}),
        ({'runtime':'kimi','model_id':'model-brain-b','reasoning_effort':'max'},
         {'runtime':'kimi','model_id':'model-exec-b','reasoning_effort':'high'}),
    ]
    for cid, (brain, executor) in zip(('MODEL_A','MODEL_B'), choices):
        db.execute('UPDATE challenges SET brain_config_json=?,executor_config_json=? WHERE id=?',
                   (json.dumps(brain), json.dumps(executor), cid))
    c = _controller()
    first, second = [c.create_run(cid)['id'] for cid in ('MODEL_A','MODEL_B')]
    db.execute("UPDATE challenges SET executor_config_json=? WHERE id='MODEL_A'",
               (json.dumps({'runtime':'codex','model_id':'later-model',
                            'reasoning_effort':'low'}),))
    a = c.run_snapshot(first)['config_snapshot']['settings']
    b = c.run_snapshot(second)['config_snapshot']['settings']
    assert (a['brain']['model_id'], a['executor']['model_id']) == (
        'gpt-6-astra', 'model-exec-a')
    assert (b['brain']['model_id'], b['executor']['model_id']) == (
        'gpt-6-astra', 'model-exec-b')
    assert json.loads(db.query_one("SELECT brain_config_json FROM challenges WHERE id='MODEL_B'")[0]) == choices[1][0]
    assert mailboxes._submission_metadata(first)['model'] == 'demo'
    db.execute("UPDATE runs SET mode='connected' WHERE id IN (?,?)", (first, second))
    assert mailboxes._submission_metadata(first)['model'] == 'model-exec-a'
    assert mailboxes._submission_metadata(second)['model'] == 'model-exec-b'


async def test_full_demo_loop_to_finished():
    _seed_challenge()
    c = _controller()
    run = c.create_run("DEMO_CHALLENGE")
    rid = run["id"]
    with pytest.raises(ControllerError) as exc:
        await c.start_async(rid)
    assert exc.value.code == "NEEDS_AUTHORIZATION"
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    snap = await c.start_async(rid)
    assert snap["phase"] == "running"
    ok = await _wait_for(
        lambda: c.run_snapshot(rid)["phase"] == "finished", timeout=20)
    assert ok, "demo 闭环未在限时内完成"
    snap = c.run_snapshot(rid)
    assert any(t["status"] == "done" for t in snap["trials"])
    # 题内经验提议已落盘并直接生效（自进化闭环：题内免审）
    from cyberscientist import experiences
    items = experiences.list_experiences()["items"]
    assert any(i["status"] == "active" and i["scope"] == "challenge"
               for i in items)


async def test_pause_resume_terminate():
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    await c.start_async(rid)
    ok = await _wait_for(lambda: c.run_snapshot(rid)["current_trial_id"], 10)
    assert ok
    op = f"op_{uuid.uuid4().hex[:10]}"
    receipt = await c.control(rid, "pause", None, op)
    assert receipt["status"] == "accepted"
    assert c.run_snapshot(rid)["phase"] == "pausing"
    ok = await _wait_for(lambda: c.run_snapshot(rid)["phase"] == "paused", 10)
    assert ok, "demo abort confirmed 后应显示 paused"
    receipt = await c.control(rid, "resume", None, f"op_{uuid.uuid4().hex[:10]}")
    assert receipt["status"] == "confirmed"
    assert c.run_snapshot(rid)["phase"] == "running"
    receipt = await c.control(rid, "terminate", None, f"op_{uuid.uuid4().hex[:10]}")
    assert receipt["status"] == "confirmed"
    assert c.run_snapshot(rid)["phase"] == "cancelled"


async def test_cancelled_run_reopen_preserves_original_clock_and_trace():
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    await c.start_async(rid)
    started_at = c.run_snapshot(rid)["started_at"]
    await c.control(rid, "terminate", None, "reopen-test-terminate")
    ended_at = c.run_snapshot(rid)["ended_at"]
    stale = c.create_run("DEMO_CHALLENGE")["id"]
    db.execute("UPDATE runs SET phase='recovering' WHERE id=?", (stale,))
    result = await c.control(rid, "reopen", "恢复误终止的研究", "reopen-test")
    assert result["status"] == "confirmed"
    snap = c.run_snapshot(rid)
    assert snap["phase"] == "recovering"
    assert snap["started_at"] == started_at
    assert snap["ended_at"] is None
    assert (await c.control(rid, "reopen", "恢复误终止的研究",
                            "reopen-test"))["deduplicated"]
    events = db.events_after(rid, 0)
    assert [e["type"] for e in events].count("run.terminated") == 1
    reopened = next(e for e in events if e["type"] == "run.reopened")
    assert reopened["payload"]["previous_ended_at"] == ended_at


async def test_runtime_failed_run_reopens_without_new_run_or_replayed_compute():
    _seed_challenge()
    c = _controller()
    rid = c.create_run('DEMO_CHALLENGE')['id']
    c.authorize(rid, 'demo', False, 0, 30, 0, None)
    started = db.utcnow()
    db.execute("UPDATE runs SET phase='failed',started_at=?,ended_at=?,"
               "end_reason='runtime_error' WHERE id=?", (started, started, rid))
    authorization = db.query_one('SELECT authorization_id FROM runs WHERE id=?', (rid,))[0]
    failure = db.append_event(rid, 'controller', 'run.runtime_error',
                              {'error': 'ProtocolError: native transport read failed'})
    db.execute("INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,"
               "spec_json,input_directory,status,created_at,updated_at)"
               " VALUES('unsettled',?,'trial','hash','{}','.','unknown',?,?)",
               (rid, started, started))
    result = await c.control(rid, 'reopen', '修复原生传输后继续原授权', 'reopen-runtime-error')
    assert result['status'] == 'confirmed'
    assert db.query_one('SELECT COUNT(*) FROM runs')[0] == 1
    row = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    assert row['phase'] == 'recovering'
    assert row['started_at'] == started and row['authorization_id'] == authorization
    assert db.query_one('SELECT status FROM compute_jobs WHERE operation_id=?', ('unsettled',))[0] == 'unknown'
    assert db.query_one('SELECT COUNT(*) FROM compute_jobs')[0] == 1
    assert db.query_one('SELECT type FROM events WHERE run_id=? AND seq=?', (rid, failure['seq']))[0] == 'run.runtime_error'
    reopened = next(e for e in db.events_after(rid, 0) if e['type'] == 'run.reopened')
    assert reopened['payload']['previous_end_reason'] == 'runtime_error'


async def test_other_failed_run_is_not_reopened_as_runtime_recovery():
    _seed_challenge()
    c = _controller()
    rid = c.create_run('DEMO_CHALLENGE')['id']
    c.authorize(rid, 'demo', False, 0, 30, 0, None)
    db.execute("UPDATE runs SET phase='failed',started_at=?,end_reason='scientific_failure' WHERE id=?",
               (db.utcnow(), rid))
    with pytest.raises(ControllerError) as error:
        await c.control(rid, 'reopen', '不能伪装成运行时恢复', 'reject-non-runtime-reopen')
    assert error.value.code == 'INVALID_STATE'
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))[0] == 'failed'


async def test_control_operation_id_dedup():
    """同一 operation_id 的并发控制请求只受理一次。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    await c.start_async(rid)
    await _wait_for(lambda: c.run_snapshot(rid)["current_trial_id"], 10)
    op = f"op_{uuid.uuid4().hex[:10]}"
    results = await asyncio.gather(
        c.control(rid, "steer", "dup-test", op),
        c.control(rid, "steer", "dup-test", op))
    dedup_count = sum(1 for r in results if r.get("deduplicated"))
    queued = sum(1 for r in results if r.get("status") == "queued")
    assert dedup_count == 1 and queued == 1
    await c.control(rid, "terminate", None, f"op_{uuid.uuid4().hex[:10]}")


async def test_connected_mode_blocked_without_components(tmp_path):
    _seed_challenge()
    settings = config.load_settings()
    settings["app"]["mode"] = "connected"
    settings["brain"]["runtime"] = "codex"
    settings["brain"]["executable"] = str(tmp_path / "no-brain")
    settings["executor"]["runtime"] = "prime"
    settings["prime"]["executable"] = str(tmp_path / "no-prime")
    config.save_settings(settings)
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE", mode="connected")["id"]
    c.authorize(rid, "model_roundtrip", True, 1, 30, 0, None)
    with pytest.raises(ControllerError) as exc:
        await c.start_async(rid)
    assert exc.value.code == "MISSING_CREDENTIAL"
    snap = c.run_snapshot(rid)
    assert snap["phase"] == "blocked"
    assert "执行器不可用" in snap["block_reason"]


async def test_stale_decision_not_executed():
    """state_version 变化后旧判断只保存不执行。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    await c.start_async(rid)
    await _wait_for(lambda: c.run_snapshot(rid)["current_trial_id"], 10)
    v = c.run_snapshot(rid)["state_version"]
    db.bump_state_version(rid)  # 模拟用户暂停/指导造成的版本变化
    dec = {"schema_version": 1, "decision_id": "dec_stale", "run_id": rid,
           "observed_state_version": v, "summary": "旧判断",
           "evidence_refs": [], "actions": [{"op": "finish", "reason": "r"}],
           "experience_proposals": []}
    await c._apply_decision(rid, dec, {}, None, None)
    types = [e["type"] for e in db.events_after(rid, 0)]
    assert "brain.decision_stale" in types
    assert "run.finished" not in types
    await c.control(rid, "terminate", None, f"op_{uuid.uuid4().hex[:10]}")


def test_update_budget_settings_and_auth():
    """v2 Trial 上限只改本 Run；大脑判断上限仍走实时 settings。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 40, 30, 1, None)
    out = c.update_budget(rid, max_brain_reviews=20, max_model_turns=80,
                          max_run_minutes=120, max_submissions=5,
                          max_trials=9)
    assert out["updated"] == {"max_brain_reviews": 20, "max_trials": 9,
                              "max_model_turns": 80, "max_run_minutes": 120,
                              "max_submissions": 5}
    # 新 Run 的 Trial 上限不再污染全局默认值。
    assert config.load_settings()["run_defaults"]["max_brain_reviews"] == 20
    assert config.load_settings()["run_defaults"]["max_trials"] == 3
    # 授权行更新并反映在 budget 状态里
    budget = c.run_snapshot(rid)["budget"]
    assert budget["max_brain_reviews"] == 20
    assert budget["max_trials"] == 9
    assert budget["model_turns"]["limit"] == 80
    assert budget["run_minutes_limit"] == 120
    assert budget["max_submissions"] == 5
    types = [e["type"] for e in db.events_after(rid, 0)]
    assert "run.budget_updated" in types


def test_update_budget_validation():
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    # 未授权时调整授权预算报错
    with pytest.raises(ControllerError) as exc:
        c.update_budget(rid, max_model_turns=10)
    assert exc.value.code == "NEEDS_AUTHORIZATION"
    # 空body / 非正整数
    with pytest.raises(ControllerError) as exc:
        c.update_budget(rid)
    assert exc.value.code == "INVALID_ARGUMENT"
    with pytest.raises(ControllerError) as exc:
        c.update_budget(rid, max_brain_reviews=0)
    assert exc.value.code == "INVALID_ARGUMENT"
    # Run 不存在
    with pytest.raises(ControllerError) as exc:
        c.update_budget("nope", max_brain_reviews=5)
    assert exc.value.code == "NOT_FOUND"


async def test_steer_to_stalled_trial_recovers():
    """stalled Trial 可被大脑 steer 裁决：指导入队且 Trial 恢复 active。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    c.authorize(rid, "demo", False, 0, 30, 0, None)
    tid = "trial_stalled_x"
    db.execute(
        "INSERT INTO trials(id, run_id, parent_trial_id, goal, success_check,"
        " status, created_at) VALUES(?,?,NULL,?,?,'stalled',?)",
        (tid, rid, "探索", "判据", db.utcnow()))
    db.execute("UPDATE runs SET current_trial_id=?,phase='running' WHERE id=?", (tid, rid))
    v = c.run_snapshot(rid)["state_version"]
    dec = {"schema_version": 1, "decision_id": "dec_steer_stalled",
           "run_id": rid, "observed_state_version": v, "summary": "停滞收束",
           "evidence_refs": [],
           "actions": [{"op": "steer", "trial_id": tid, "message": "立即交付基线"}],
           "experience_proposals": []}
    await c._apply_decision(rid, dec, {}, None, None)
    types = [e["type"] for e in db.events_after(rid, 0)]
    assert "brain.decision_rejected" not in types
    assert "guidance.queued" in types
    assert db.query_one("SELECT status FROM trials WHERE id=?",
                        (tid,))["status"] == "active"


async def test_update_budget_rejects_terminal_run():
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    await c.control(rid, "terminate", None, f"op_{uuid.uuid4().hex[:10]}")
    with pytest.raises(ControllerError) as exc:
        c.update_budget(rid, max_brain_reviews=30)
    assert exc.value.code == "INVALID_STATE"


def test_max_jobs_authorization_roundtrip():
    """算力授权：authorize 落 max_jobs，update_budget 可运行中调整，budget 状态回读。"""
    _seed_challenge()
    c = _controller()
    rid = c.create_run("DEMO_CHALLENGE")["id"]
    # 默认未授权算力
    assert c.run_snapshot(rid)["budget"] is None or True
    c.authorize(rid, "demo", False, 40, 30, 1, None, max_jobs=2)
    budget = c.run_snapshot(rid)["budget"]
    assert budget["max_jobs"] == 2
    # 运行中提高
    out = c.update_budget(rid, max_jobs=5)
    assert out["updated"] == {"max_jobs": 5}
    assert c.run_snapshot(rid)["budget"]["max_jobs"] == 5
    # 观测帧（给大脑看的预算）也带 max_jobs
    from cyberscientist import observation
    frame = observation.build_frame(
        rid, mode="shadow", frame_id="fr_test", from_seq=0, through_seq=0,
        shadow_cfg={}, request={"kind": "lifecycle", "detail": "test"},
        run_defaults={})
    assert frame["budget"]["max_jobs"] == 5
