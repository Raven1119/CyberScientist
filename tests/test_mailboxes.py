"""邮箱管理双轨：实验邮箱提交主体 + 收割邮箱手动确认最高分包。"""
from __future__ import annotations

import json

import pytest

from cyberscientist import config, db, mailboxes
from cyberscientist.controller import RunController


def _seed_challenge():
    db.execute(
        "INSERT OR IGNORE INTO challenges(id, platform_challenge_id, origin,"
        " title, content, content_hash, contract_status, imported_at, is_demo)"
        " VALUES('MB_CH','MB','demo://local','邮箱测试题','内容','h',"
        "'unknown',?,1)", (db.utcnow(),))


def _make_run(max_submissions=5):
    c = RunController()
    rid = c.create_run("MB_CH", shadow_enabled=False)["id"]
    c.authorize(rid, "demo", True, 10, 30, max_submissions, None)
    return rid


def _make_package(rid: str, tid: str = "trial_mb1",
                  content: str = '{"result": 1}') -> str:
    """在 Trial 目录放一个提交包，返回工作区相对路径。"""
    d = config.WORKSPACE_DIR / "runs" / rid / "trials" / tid
    d.mkdir(parents=True, exist_ok=True)
    (d / "result_package.json").write_text(content, encoding="utf-8")
    return f"runs/{rid}/trials/{tid}/result_package.json"


def _set_scored(sub_id: str, score: float) -> None:
    """模拟平台已出分（真实拉回属平台适配器，测试直接落定）。"""
    db.execute("UPDATE submissions SET score=?, score_status='scored',"
               " scored_at=? WHERE id=?", (score, db.utcnow(), sub_id))


def test_harvest_unique_and_replaceable():
    h = mailboxes.add_harvest("me@example.com", "s3cret")
    assert h["role"] == "harvest" and h["secret_configured"]
    assert "secret_ref" not in h  # 凭据引用不出服务层
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.add_harvest("other@example.com", "x")
    assert exc.value.code == "CONFLICT"
    mailboxes.disable_mailbox(h["id"])
    h2 = mailboxes.add_harvest("new@example.com", "y")
    assert h2["status"] == "active"


def test_register_experiment_demo_and_real_missing():
    res = mailboxes.register_experiment(3)
    assert res["is_demo"] and len(res["items"]) == 3
    assert all(m["role"] == "experiment" and m["is_demo"] == 1
               and m["secret_configured"] for m in res["items"])
    s = config.load_settings()
    s["mailbox"]["platform"] = "bohrium_playground"
    config.save_settings(s)
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.register_experiment(1)
    assert exc.value.code == "MISSING_CREDENTIAL"
    assert "未配置" in str(exc.value)


def test_submit_experiment_quota_budget_dedup():
    _seed_challenge()
    rid = _make_run(max_submissions=1)
    pkg = _make_package(rid)
    mailboxes.register_experiment(1)

    # 未找到提交包 → 准确缺项
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.submit_experiment(rid, "trial_none", None, "op-0")
    assert exc.value.code == "NOT_FOUND"

    r = mailboxes.submit_experiment(rid, "trial_mb1", None, "op-1")
    assert r["status"] == "submitted" and not r["deduplicated"]
    assert r["package_path"] == pkg
    mb = db.query_one("SELECT * FROM mailboxes WHERE role='experiment'")
    assert mb["submissions_used"] == 1

    dup = mailboxes.submit_experiment(rid, "trial_mb1", None, "op-1")
    assert dup["deduplicated"] and dup["id"] == r["id"]

    # 授权上限（max_submissions=1）强制
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.submit_experiment(rid, "trial_mb1", None, "op-2")
    assert exc.value.code == "NEEDS_AUTHORIZATION"


def test_submit_experiment_no_mailbox_available():
    _seed_challenge()
    rid = _make_run()
    _make_package(rid)
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.submit_experiment(rid, "trial_mb1", None, "op-x")
    assert exc.value.code == "NO_MAILBOX"

    s = config.load_settings()
    s["mailbox"]["submission_limit"] = 1
    config.save_settings(s)
    mailboxes.register_experiment(1)
    mailboxes.submit_experiment(rid, "trial_mb1", None, "op-y")
    mb = db.query_one("SELECT * FROM mailboxes WHERE role='experiment'")
    assert mb["status"] == "exhausted"
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.submit_experiment(rid, "trial_mb1", None, "op-z")
    assert exc.value.code == "NO_MAILBOX"


def test_poll_scores_unknown_then_scored(monkeypatch):
    _seed_challenge()
    rid = _make_run()
    _make_package(rid)
    mailboxes.register_experiment(1)
    sub = mailboxes.submit_experiment(rid, "trial_mb1", None, "op-p1")

    # demo 平台无评分能力：保持 unknown
    res = mailboxes.poll_scores()
    assert res["updated"] == 0 and res["still_unknown"] == 1
    assert db.query_one("SELECT score_status FROM submissions WHERE id=?",
                        (sub["id"],))["score_status"] == "pending"

    # 平台出分后拉回
    platform = mailboxes._platform()
    monkeypatch.setattr(platform, "fetch_score", lambda *a: 0.91)
    monkeypatch.setattr(mailboxes, "_platform", lambda: platform)
    res = mailboxes.poll_scores()
    assert res["updated"] == 1
    row = db.query_one("SELECT * FROM submissions WHERE id=?", (sub["id"],))
    assert row["score"] == 0.91 and row["score_status"] == "scored"


def test_harvest_eligibility_and_happy_path():
    _seed_challenge()
    rid = _make_run(max_submissions=5)
    _make_package(rid)
    mailboxes.register_experiment(2)
    s1 = mailboxes.submit_experiment(rid, "trial_mb1", None, "op-h1")
    _set_scored(s1["id"], 0.80)
    _make_package(rid, "trial_mb2", '{"result": 2}')
    s2 = mailboxes.submit_experiment(rid, "trial_mb2", None, "op-h2")
    _set_scored(s2["id"], 0.88)

    # 未确认拒绝
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.harvest_submit(s2["id"], "op-hv0", False)
    assert exc.value.code == "NEEDS_CONFIRM"
    # 未配置收割邮箱
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.harvest_submit(s2["id"], "op-hv1", True)
    assert exc.value.code == "NO_MAILBOX"
    mailboxes.add_harvest("me@example.com", "s3cret")
    # 非最高分拒绝
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.harvest_submit(s1["id"], "op-hv2", True)
    assert exc.value.code == "INVALID_STATE"
    # 最高分通过
    r = mailboxes.harvest_submit(s2["id"], "op-hv3", True)
    assert r["status"] == "submitted" and r["is_harvest"] == 1
    assert r["source_submission_id"] == s2["id"]
    assert r["package_sha256"] == s2["package_sha256"]
    # 幂等
    dup = mailboxes.harvest_submit(s2["id"], "op-hv3", True)
    assert dup["deduplicated"] and dup["id"] == r["id"]
    # 包被篡改后拒绝（篡改最高分 s2 的包）
    import pathlib
    pathlib.Path(config.WORKSPACE_DIR / s2["package_path"]).write_text(
        '{"result": 999}', encoding="utf-8")
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.harvest_submit(s2["id"], "op-hv4", True)
    assert exc.value.code == "CONFLICT"


def test_harvest_rejects_unknown_score_source():
    _seed_challenge()
    rid = _make_run()
    _make_package(rid)
    mailboxes.register_experiment(1)
    sub = mailboxes.submit_experiment(rid, "trial_mb1", None, "op-u1")
    mailboxes.add_harvest("me@example.com", "s3cret")
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.harvest_submit(sub["id"], "op-u2", True)
    assert exc.value.code == "INVALID_STATE"
    assert "未知" in str(exc.value) or "score_status" in str(exc.value)


def test_submit_demo_challenge_rejected_and_quota_released(monkeypatch):
    """platform_challenge_id 是 demo:// 时真实平台拒绝，且预占配额必须释放。"""
    from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform

    db.execute(
        "INSERT OR IGNORE INTO challenges(id, platform_challenge_id, origin,"
        " title, content, content_hash, contract_status, imported_at, is_demo)"
        " VALUES('MB_DEMO','demo://local','demo://local','t','c','h',"
        "'unknown',?,1)", (db.utcnow(),))
    c = RunController()
    rid = c.create_run("MB_DEMO", shadow_enabled=False)["id"]
    c.authorize(rid, "demo", True, 10, 30, 5, None)
    _make_package(rid)
    secrets = config.load_secrets()
    secrets["mbox_test_tok"] = "asp_x"
    config.save_secrets(secrets)
    db.execute(
        "INSERT INTO mailboxes(id, role, email, platform, secret_ref, status,"
        " submission_limit, is_demo, created_at) VALUES('mbox_t1',"
        "'experiment','agent-x','bohrium_playground','local:mbox_test_tok',"
        "'active',10,0,?)", (db.utcnow(),))
    monkeypatch.setattr(
        mailboxes, "_platform",
        lambda: BohriumPlaygroundPlatform("https://x.test/api"))
    r = mailboxes.submit_experiment(rid, "trial_mb1", None, "op-demo-guard")
    assert r["status"] == "failed"
    assert "未关联真实平台" in r["error"]
    mb = db.query_one(
        "SELECT submissions_used, status FROM mailboxes WHERE id='mbox_t1'")
    assert mb["submissions_used"] == 0 and mb["status"] == "active"


def test_submit_unexpected_exception_still_releases_quota(monkeypatch):
    """适配器抛出非 PlatformError 时补偿事务也必须执行。"""
    _seed_challenge()
    rid = _make_run(max_submissions=5)
    _make_package(rid)
    mailboxes.register_experiment(1)

    class Boom:
        name = "demo"
        is_demo = True

        def submit_package(self, *a, **k):
            raise OSError("disk vanished")

        def fetch_score(self, *a):
            return None

    monkeypatch.setattr(mailboxes, "_platform", lambda: Boom())
    r = mailboxes.submit_experiment(rid, "trial_mb1", None, "op-boom")
    assert r["status"] == "failed"
    assert "OSError" in r["error"]
    mb = db.query_one("SELECT submissions_used, status FROM mailboxes"
                      " WHERE role='experiment'")
    assert mb["submissions_used"] == 0 and mb["status"] == "active"


def test_real_platform_skips_demo_mailboxes():
    """真实平台下提交不得落到 demo 合成账号（实测 401 教训）。"""
    _seed_challenge()
    rid = _make_run()
    _make_package(rid)
    mailboxes.register_experiment(1)  # demo 平台下注册 → demo 邮箱
    s = config.load_settings()
    s["mailbox"]["platform"] = "bohrium_playground"
    config.save_settings(s)
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.submit_experiment(rid, "trial_mb1", None, "op-mix")
    assert exc.value.code == "NO_MAILBOX"
    assert "bohrium_playground" in str(exc.value)


def test_poll_scores_skips_missing_platform_ref():
    """无平台回执引用的提交直接保持 unknown，不拿内部 id 去查平台。"""
    _seed_challenge()
    rid = _make_run()
    _make_package(rid)
    mailboxes.register_experiment(1)
    sub = mailboxes.submit_experiment(rid, "trial_mb1", None, "op-noref")
    db.execute("UPDATE submissions SET platform_ref=NULL WHERE id=?",
               (sub["id"],))
    res = mailboxes.poll_scores()
    assert res["still_unknown"] == 1 and res["errors"] == 0


async def test_mailbox_api_roundtrip():
    from httpx import ASGITransport, AsyncClient

    from cyberscientist.api import create_app

    _seed_challenge()
    rid = _make_run(max_submissions=3)
    _make_package(rid)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://t") as cli:
        r = await cli.post("/api/v1/mailboxes/experiment/register",
                           json={"count": 2})
        assert r.status_code == 200 and len(r.json()["items"]) == 2
        r = await cli.post("/api/v1/mailboxes/harvest",
                           json={"email": "me@example.com", "secret": "pw"})
        assert r.status_code == 200
        assert "secret" not in json.dumps(r.json()) or "pw" not in \
            json.dumps(r.json())  # 凭据不回显
        r = await cli.get("/api/v1/mailboxes")
        assert len(r.json()["items"]) == 3
        r = await cli.post(f"/api/v1/runs/{rid}/submissions",
                           json={"trial_id": "trial_mb1",
                                 "operation_id": "op-api-1"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "submitted"
        r = await cli.get(f"/api/v1/runs/{rid}/submissions")
        assert len(r.json()["items"]) == 1
        # 未出分时收割 → 409 准确缺项
        r = await cli.post("/api/v1/harvest/submit", json={
            "submission_id": r.json()["items"][0]["id"],
            "operation_id": "op-api-hv", "confirm": True})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "INVALID_STATE"
        r = await cli.post("/api/v1/submissions/poll", json={})
        assert r.status_code == 200


def test_poll_scores_concurrent_transition_idempotent(monkeypatch):
    """并发轮询（手动+后台）同时拿到分数时，只有 pending→scored 的真实状态
    迁移记 submission.scored 事件：不重复记、不覆盖先到的分数。"""
    _seed_challenge()
    rid = _make_run()
    _make_package(rid)
    mailboxes.register_experiment(1)
    sub = mailboxes.submit_experiment(rid, "trial_mb1", None, "op-conc")
    platform = mailboxes._platform()

    def _racy_fetch(*a):
        # 模拟并发轮询在本次落库前已把该提交迁移为 scored
        db.execute("UPDATE submissions SET score=0.5, score_status='scored',"
                   " scored_at=? WHERE id=?", (db.utcnow(), sub["id"]))
        db.append_event(rid, "controller", "submission.scored",
                        {"submission_id": sub["id"], "score": 0.5})
        return 0.9

    monkeypatch.setattr(platform, "fetch_score", _racy_fetch)
    monkeypatch.setattr(mailboxes, "_platform", lambda: platform)
    res = mailboxes.poll_scores()
    assert res["polled"] == 1 and res["updated"] == 0
    scored = [e for e in db.events_after(rid, 0)
              if e["type"] == "submission.scored"]
    assert len(scored) == 1  # 只有并发方记的一次
    row = db.query_one("SELECT score, score_status FROM submissions"
                       " WHERE id=?", (sub["id"],))
    assert row["score"] == 0.5 and row["score_status"] == "scored"


async def test_challenge_submissions_aggregation_api():
    """题目级提交聚合端点：跨 Run 聚合、新的在前、item 形状与 Run 级一致。"""
    from httpx import ASGITransport, AsyncClient

    from cyberscientist.api import create_app

    _seed_challenge()
    mailboxes.register_experiment(2)
    rid1 = _make_run()
    _make_package(rid1)
    s1 = mailboxes.submit_experiment(rid1, "trial_mb1", None, "op-agg-1")
    # 单工作区一次只允许一个活跃 Run：置为终态再建第二个
    db.execute("UPDATE runs SET phase='completed' WHERE id=?", (rid1,))
    rid2 = _make_run()
    _make_package(rid2)
    s2 = mailboxes.submit_experiment(rid2, "trial_mb1", None, "op-agg-2")

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://t") as cli:
        r = await cli.get("/api/v1/challenges/MB_CH/submissions")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert [i["id"] for i in items] == [s2["id"], s1["id"]]  # 新的在前
        run_item = mailboxes.list_submissions(rid1)["items"][0]
        assert set(items[1].keys()) == set(run_item.keys())  # 契约形状一致
        r = await cli.get("/api/v1/challenges/CH_NOPE/submissions")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "NOT_FOUND"
