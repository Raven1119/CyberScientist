"""评分轮询按题目管理：challenge_id 过滤、disabled 跳过、启停写 settings。"""
from __future__ import annotations

import pytest

from cyberscientist import config, db, mailboxes
from cyberscientist.controller import RunController


@pytest.fixture(autouse=True)
def _clear_poll_state():
    mailboxes.POLL_STATE.clear()
    yield
    mailboxes.POLL_STATE.clear()


def _seed_challenge(cid: str, title: str) -> None:
    db.execute(
        "INSERT OR IGNORE INTO challenges(id, platform_challenge_id, origin,"
        " title, content, content_hash, contract_status, imported_at, is_demo)"
        " VALUES(?,?,'demo://local',?,'内容','h','unknown',?,1)",
        (cid, f"P_{cid}", title, db.utcnow()))


def _make_submission(cid: str, op: str) -> dict:
    c = RunController()
    rid = c.create_run(cid, shadow_enabled=False)["id"]
    c.authorize(rid, "demo", True, 10, 30, 5, None)
    # 单用户一次只允许一个活跃 Run；置为终态以便为下一题建 Run
    db.execute("UPDATE runs SET phase='completed' WHERE id=?", (rid,))
    d = config.WORKSPACE_DIR / "runs" / rid / "trials" / "trial_p1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "result_package.json").write_text('{"result": 1}', encoding="utf-8")
    return mailboxes.submit_experiment(rid, "trial_p1", None, op)


def _fake_platform(monkeypatch, score: float | None = 0.5):
    platform = mailboxes._platform()
    monkeypatch.setattr(platform, "fetch_score", lambda *a: score)
    monkeypatch.setattr(mailboxes, "_platform", lambda: platform)
    return platform


def test_poll_scores_challenge_id_filter(monkeypatch):
    """challenge_id 过滤：只轮询指定题目的提交。"""
    _seed_challenge("CH_A", "题A")
    _seed_challenge("CH_B", "题B")
    mailboxes.register_experiment(2)
    sub_a = _make_submission("CH_A", "op-a")
    sub_b = _make_submission("CH_B", "op-b")

    _fake_platform(monkeypatch, 0.5)
    res = mailboxes.poll_scores(challenge_id="CH_A")
    assert res["polled"] == 1 and res["updated"] == 1
    assert db.query_one("SELECT score_status FROM submissions WHERE id=?",
                        (sub_a["id"],))["score_status"] == "scored"
    assert db.query_one("SELECT score_status FROM submissions WHERE id=?",
                        (sub_b["id"],))["score_status"] == "pending"


def test_poll_scores_challenge_and_run_combined(monkeypatch):
    """challenge_id 与 run_id 可组合：run 不属于该题时轮不到任何提交。"""
    _seed_challenge("CH_A", "题A")
    _seed_challenge("CH_B", "题B")
    mailboxes.register_experiment(2)
    sub_a = _make_submission("CH_A", "op-ca")
    _make_submission("CH_B", "op-cb")
    _fake_platform(monkeypatch, 0.5)
    res = mailboxes.poll_scores(run_id=sub_a["run_id"], challenge_id="CH_B")
    assert res == {"polled": 0, "updated": 0, "still_unknown": 0, "errors": 0}


def test_poll_pending_by_challenge_skips_disabled(monkeypatch):
    """后台轮询选题：disabled_challenges 中的题目被跳过。"""
    _seed_challenge("CH_A", "题A")
    _seed_challenge("CH_B", "题B")
    mailboxes.register_experiment(2)
    _make_submission("CH_A", "op-da")
    sub_b = _make_submission("CH_B", "op-db")

    mailboxes.set_polling_enabled("CH_B", False)
    _fake_platform(monkeypatch, 0.7)
    res = mailboxes.poll_pending_by_challenge()
    assert set(res["challenges"].keys()) == {"CH_A"}
    assert res["challenges"]["CH_A"]["updated"] == 1
    assert db.query_one("SELECT score_status FROM submissions WHERE id=?",
                        (sub_b["id"],))["score_status"] == "pending"
    # 中断的题不记录轮询状态；轮过的题有 last_poll_at
    assert "CH_B" not in mailboxes.POLL_STATE
    assert mailboxes.POLL_STATE["CH_A"]["last_poll_at"]


def test_set_polling_enabled_writes_settings():
    _seed_challenge("CH_A", "题A")
    task = mailboxes.set_polling_enabled("CH_A", False)
    assert task["enabled"] is False and task["challenge_id"] == "CH_A"
    s = config.load_settings()
    assert s["polling"]["disabled_challenges"] == ["CH_A"]
    task = mailboxes.set_polling_enabled("CH_A", True)
    assert task["enabled"] is True
    s = config.load_settings()
    assert s["polling"]["disabled_challenges"] == []
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.set_polling_enabled("CH_NONE", False)
    assert exc.value.code == "NOT_FOUND"


async def test_polling_api_roundtrip():
    from httpx import ASGITransport, AsyncClient

    from cyberscientist.api import create_app

    _seed_challenge("CH_A", "题A")
    _seed_challenge("CH_B", "题B")
    mailboxes.register_experiment(1)
    _make_submission("CH_A", "op-api-a")

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://t") as cli:
        r = await cli.get("/api/v1/polling")
        assert r.status_code == 200
        tasks = r.json()["tasks"]
        assert len(tasks) == 1  # 无提交的 CH_B 不出现
        assert tasks[0]["challenge_id"] == "CH_A"
        assert tasks[0]["title"] == "题A"
        assert tasks[0]["pending"] == 1 and tasks[0]["enabled"] is True
        assert tasks[0]["last_poll_at"] is None

        # 中断该题 → settings 落盘
        r = await cli.post("/api/v1/polling/CH_A", json={"enabled": False})
        assert r.status_code == 200 and r.json()["enabled"] is False
        s = config.load_settings()
        assert s["polling"]["disabled_challenges"] == ["CH_A"]
        r = await cli.get("/api/v1/polling")
        assert r.json()["tasks"][0]["enabled"] is False

        # 手动轮询不受 enabled 限制
        r = await cli.post("/api/v1/polling/CH_A/run")
        assert r.status_code == 200
        assert r.json()["polled"] == 1
        r = await cli.get("/api/v1/polling")
        assert r.json()["tasks"][0]["last_result"]["polled"] == 1

        # 启用恢复
        r = await cli.post("/api/v1/polling/CH_A", json={"enabled": True})
        assert r.json()["enabled"] is True
        assert config.load_settings()["polling"]["disabled_challenges"] == []

        # 不存在的题目 → 404
        r = await cli.post("/api/v1/polling/CH_NONE", json={"enabled": False})
        assert r.status_code == 404
        r = await cli.post("/api/v1/polling/CH_NONE/run")
        assert r.status_code == 404


async def test_poll_endpoint_offloaded_from_event_loop(monkeypatch):
    """手动轮询端点的平台 HTTP 是同步调用：必须卸载到线程，
    慢评分接口不得阻塞事件循环上的其他请求。"""
    import asyncio
    import time

    from httpx import ASGITransport, AsyncClient

    from cyberscientist.api import create_app

    _seed_challenge("CH_A", "题A")
    mailboxes.register_experiment(1)
    _make_submission("CH_A", "op-slow")
    platform = mailboxes._platform()

    def _slow_fetch(*a):
        time.sleep(0.8)  # 同步阻塞：若未卸载会卡住整个事件循环
        return 0.7

    monkeypatch.setattr(platform, "fetch_score", _slow_fetch)
    monkeypatch.setattr(mailboxes, "_platform", lambda: platform)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://t") as cli:
        poll = asyncio.create_task(
            cli.post("/api/v1/submissions/poll", json={}))
        await asyncio.sleep(0.05)  # 让轮询先进入平台调用
        t0 = time.monotonic()
        r = await cli.get("/api/v1/health")
        elapsed = time.monotonic() - t0
        res = await poll
    assert r.status_code == 200
    assert elapsed < 0.5, f"事件循环被同步评分轮询阻塞了 {elapsed:.2f}s"
    assert res.status_code == 200 and res.json()["updated"] == 1
