"""BohriumPlaygroundPlatform 适配器单测：全部 mock HTTP，不打真实平台。

端点形状依据官方文档快照 checks/results/AGENT_API.md（2026-09 抓取）。
"""
from __future__ import annotations

import io
import hashlib
import json
import urllib.error
import urllib.request
import zipfile

import pytest

from cyberscientist.mailbox_platform import (
    BohriumPlaygroundPlatform, PlatformError, _encode_multipart, get_platform)


class FakeHTTP:
    """记录调用并按 (method, path 前缀) 返回预置响应。"""

    def __init__(self, routes: dict[tuple[str, str], object]):
        self.routes = routes
        self.calls: list[dict] = []

    def __call__(self, method, path, token=None, json_body=None,
                 form=None):
        self.calls.append({"method": method, "path": path, "token": token,
                           "json_body": json_body,
                           "form_fields": form[0] if form else None,
                           "form_files": [(f, n) for f, n, _ in
                                          (form[1] if form else [])]})
        for (m, prefix), resp in self.routes.items():
            if method == m and path.startswith(prefix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"未预置的调用: {method} {path}")


def _platform(routes, operator_token="op-tok"):
    p = BohriumPlaygroundPlatform("https://play.bohrium.com/api",
                                  operator_token=operator_token)
    fake = FakeHTTP(routes)
    p._http = fake  # type: ignore[method-assign]
    return p, fake


def test_register_requires_operator_token():
    p = BohriumPlaygroundPlatform("https://play.bohrium.com/api",
                                  operator_token=None)
    with pytest.raises(PlatformError, match="token_secret_ref"):
        p.register_account()


def test_register_account_option_a_shape():
    p, fake = _platform({
        ("POST", "/agent/register"): {
            "token": "asp_new",
            "agentUser": {"id": "agent-x", "name": "cyberscientist-exp-abc"}},
    })
    acc = p.register_account()
    call = fake.calls[0]
    assert call["token"] == "op-tok"
    assert call["json_body"]["framework"] == "CyberScientist"
    assert call["json_body"]["name"].startswith("cyberscientist-exp-")
    assert acc["password"] == "asp_new"
    assert acc["platform_account_id"] == "agent-x"


def test_register_account_bad_response():
    p, _ = _platform({("POST", "/agent/register"): {"unexpected": True}})
    with pytest.raises(PlatformError, match="token/agentUser"):
        p.register_account()


def test_submit_requires_secret_and_challenge(tmp_path):
    pkg = tmp_path / "result_package.json"
    pkg.write_text("{}", encoding="utf-8")
    p, _ = _platform({})
    with pytest.raises(PlatformError, match="无平台凭据"):
        p.submit_package("a@b.c", None, str(pkg), "ch-1")
    with pytest.raises(PlatformError, match="challenge_id"):
        p.submit_package("a@b.c", "asp_x", str(pkg), "")
    with pytest.raises(PlatformError, match="不存在"):
        p.submit_package("a@b.c", "asp_x", str(tmp_path / "none.zip"),
                         "ch-1")


def test_submit_zip_happy_path(tmp_path):
    pkg = tmp_path / "bundle.zip"
    with zipfile.ZipFile(pkg, "w") as z:
        z.writestr("results/x.csv", "a,b\n1,2\n")
    p, fake = _platform({
        ("POST", "/challenges/ch-1/attempts"): {"id": 42},
        ("POST", "/attempts/42/bundle"): {"ok": True},
        ("POST", "/attempts/42/submit"): {"ok": True},
    })
    r = p.submit_package("agent-x", "asp_x", str(pkg), "ch-1",
                         meta={"outcome": "success", "model": "Kimi K3"})
    assert r == {"accepted": True, "receipt": "42", "bundle_uploaded": True}
    create = fake.calls[0]
    assert create["method"] == "POST"
    assert create["path"] == "/challenges/ch-1/attempts"
    f = create["form_fields"]
    assert f["status"] == "draft" and f["type"] == "agent"
    assert f["outcome"] == "success" and f["model"] == "Kimi K3"
    trace = json.loads(f["trace"])
    assert trace == [{"step_type": "observation", "title": "Sealed package",
                      "body": "提交封存包 " + hashlib.sha256(pkg.read_bytes()).hexdigest()}]
    assert fake.calls[1]["path"] == "/attempts/42/bundle"
    assert fake.calls[1]["form_files"][0][0] == "bundle"
    assert fake.calls[2]["path"] == "/attempts/42/submit"
    assert all(c["token"] == "asp_x" for c in fake.calls)


def test_submit_non_zip_skips_bundle(tmp_path):
    pkg = tmp_path / "result_package.json"
    pkg.write_text('{"result": 1}', encoding="utf-8")
    p, fake = _platform({
        ("POST", "/challenges/ch-1/attempts"): {"id": 77},
        ("POST", "/attempts/77/submit"): {"ok": True},
    })
    r = p.submit_package("agent-x", "asp_x", str(pkg), "ch-1")
    assert r["bundle_uploaded"] is False
    assert len(fake.calls) == 2


def test_fetch_score_only_final():
    p, _ = _platform({
        ("GET", "/attempts/1/score"): {
            "score": 0.0,
            "scoringState": {"scoreIsFinal": False, "state": "evaluating"}},
    })
    assert p.fetch_score("a", "asp_x", "1") is None  # 评分中：如实 unknown

    p2, _ = _platform({
        ("GET", "/attempts/2/score"): {
            "score": 88.0,
            "scoringState": {"scoreIsFinal": True, "displayScore": 88.0}},
    })
    assert p2.fetch_score("a", "asp_x", "2") == 88.0

    p3, _ = _platform({
        ("GET", "/attempts/3/score"): {
            "score": 42.5, "scoringState": {"scoreIsFinal": True}},
    })
    assert p3.fetch_score("a", None, "3") == 42.5  # displayScore 缺省回退

    assert p3.fetch_score("a", None, "demo-receipt:x") is None
    assert p3.fetch_score("a", None, "") is None


def test_score_details_retain_failure_and_eligibility_without_credentials():
    body = {"status": "scoring_failed", "score": None,
            "scoringState": {"scoreIsFinal": False, "workerStatus": "error",
                             "zeroReason": "worker_timeout", "zeroEvidence": {"job": "j1"}},
            "competitionEligibility": {"eligible": False, "reason": "after_deadline"},
            "token": "asp_should_not_escape", "error": "request asp_x was rejected"}
    p, _ = _platform({("GET", "/attempts/9/score"): body})
    feedback = p.fetch_score_details("a", "asp_x", "9")
    assert feedback["scoringState"] == body["scoringState"]
    assert feedback["competitionEligibility"] == body["competitionEligibility"]
    assert "asp_" not in json.dumps(feedback)
    assert "token" not in feedback
    assert p.fetch_score("a", "asp_x", "9") is None


@pytest.mark.parametrize("state,score", [("false", 1), (True, "NaN"), (True, True)])
def test_score_requires_boolean_finality_and_finite_number(state, score):
    p, _ = _platform({("GET", "/attempts/9/score"): {
        "score": score, "scoringState": {"scoreIsFinal": state}}})
    assert p.fetch_score("a", None, "9") is None


def test_multipart_encoding():
    body, ctype = _encode_multipart({"a": "1"}, [("f", "x.zip", b"PK")])
    assert ctype.startswith("multipart/form-data; boundary=")
    boundary = ctype.split("boundary=", 1)[1]
    assert b'name="a"' in body and b"name=\"f\"; filename=\"x.zip\"" in body
    assert body.endswith(f"--{boundary}--\r\n".encode())  # 闭合 boundary


def test_submit_rejects_demo_challenge(tmp_path):
    pkg = tmp_path / "p.json"
    pkg.write_text("{}", encoding="utf-8")
    p, _ = _platform({})
    with pytest.raises(PlatformError, match="未关联真实平台"):
        p.submit_package("a", "asp_x", str(pkg), "demo://local")


def test_submit_json_package_becomes_results_json(tmp_path):
    """JSON 提交包的内容必须作为 results_json 表单字段进入 attempt 创建。"""
    pkg = tmp_path / "result_package.json"
    payload = {"r_values": {"(0.2, 0.3, 1)": 4.1},
               "saving_rate_values": {"(0.2, 0.3, 1)": 23.7}}
    pkg.write_text(json.dumps(payload), encoding="utf-8")
    p, fake = _platform({
        ("POST", "/challenges/ch-1/attempts"): {"id": 88},
        ("POST", "/attempts/88/submit"): {"ok": True},
    })
    p.submit_package("agent-x", "asp_x", str(pkg), "ch-1")
    f = fake.calls[0]["form_fields"]
    assert json.loads(f["results_json"]) == payload

    # meta 显式给出时优先于包内容
    p2, fake2 = _platform({
        ("POST", "/challenges/ch-1/attempts"): {"id": 89},
        ("POST", "/attempts/89/submit"): {"ok": True},
    })
    override = {"r_values": {"(0.2, 0.3, 1)": 4.2}}
    p2.submit_package("agent-x", "asp_x", str(pkg), "ch-1",
                      meta={"results_json": override})
    assert json.loads(fake2.calls[0]["form_fields"]["results_json"]) == override

    # 坏 JSON 报准确缺项，不发请求
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(PlatformError, match="无法解析"):
        p.submit_package("agent-x", "asp_x", str(bad), "ch-1")


def test_http_layer_url_headers_and_body(monkeypatch):
    """mock urlopen 走真实 _http：URL 拼接、Authorization 头、JSON body。"""
    captured: dict = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["ctype"] = req.get_header("Content-type")
        captured["method"] = req.get_method()
        captured["data"] = req.data
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    p = BohriumPlaygroundPlatform("https://play.bohrium.com/api/")
    out = p._http("POST", "/agent/register", token="op-tok",
                  json_body={"name": "x"})
    assert out == {"ok": True}
    assert captured["url"] == "https://play.bohrium.com/api/agent/register"
    assert captured["auth"] == "Bearer op-tok"
    assert captured["ctype"] == "application/json"
    assert json.loads(captured["data"]) == {"name": "x"}

    # multipart 接线：Content-Type 带 boundary，body 含字段
    p._http("POST", "/attempts/1/bundle", token="t",
            form=({"k": "v"}, [("bundle", "b.zip", b"PK")]))
    assert captured["ctype"].startswith("multipart/form-data; boundary=")
    assert b'name="bundle"; filename="b.zip"' in captured["data"]


def test_http_error_becomes_platform_error(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 403, "Forbidden", {},
            io.BytesIO(b'{"error":"nope"}'))

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    p = BohriumPlaygroundPlatform("https://x.test/api")
    with pytest.raises(PlatformError, match="HTTP 403"):
        p._http("GET", "/auth/me", token="t")

    def net_boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", net_boom)
    with pytest.raises(PlatformError, match="网络失败"):
        p._http("GET", "/auth/me")


def test_get_platform_unknown():
    with pytest.raises(PlatformError, match="未知邮箱平台"):
        get_platform("nonexistent")



def test_parse_challenge_slug():
    from cyberscientist.mailbox_platform import parse_challenge_slug

    assert parse_challenge_slug(
        "https://play.bohrium.com/challenges/aiyagari-1994-qje"
    ) == "aiyagari-1994-qje"
    assert parse_challenge_slug(
        "https://play.bohrium.com/api/challenges/aiyagari-1994-qje?x=1#f"
    ) == "aiyagari-1994-qje"
    assert parse_challenge_slug("aiyagari-1994-qje") == "aiyagari-1994-qje"
    assert parse_challenge_slug("  aiyagari-1994-qje  ") == "aiyagari-1994-qje"
    assert parse_challenge_slug("") is None
    assert parse_challenge_slug("https://play.bohrium.com/about") is None
    assert parse_challenge_slug("not a slug") is None
    assert parse_challenge_slug("../etc/passwd") is None


def test_fetch_platform_challenge_mocked(monkeypatch):
    from cyberscientist.mailbox_platform import fetch_platform_challenge

    captured: dict = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"id": "ch-1", "title": "T",
                               "title_zh": "题", "content": "# 题面"}).encode()

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    data = fetch_platform_challenge("https://x.test/api/", "ch 1")
    assert data["title_zh"] == "题"
    assert captured["url"] == "https://x.test/api/challenges/ch%201"
    assert captured["auth"] is None  # 公开端点，无 token 不带认证头

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {},
                                     io.BytesIO(b'{"error":"no"}'))

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(PlatformError, match="HTTP 404"):
        fetch_platform_challenge("https://x.test/api", "nope")


@pytest.mark.asyncio
async def test_import_challenge_url_api(monkeypatch):
    """URL 导入端点：真实路由 + mock 平台 HTTP，验证落库与幂等。"""
    from httpx import ASGITransport, AsyncClient

    from cyberscientist import db
    from cyberscientist.api import create_app

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                "id": "aiyagari-1994-qje",
                "title": "Uninsured Idiosyncratic Risk",
                "title_zh": "Aiyagari 复现",
                "content": "# 题面正文",
                "resources": [{"kind": "data", "name": "public-training-data",
                               "description": "训练数据"}],
            }).encode()

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResp())
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://t") as cli:
        r = await cli.post("/api/v1/challenges/import", json={
            "mode": "url",
            "url": "https://play.bohrium.com/challenges/aiyagari-1994-qje"})
        assert r.status_code == 200, r.text
        ch = r.json()["challenge"]
        assert ch["platform_challenge_id"] == "aiyagari-1994-qje"
        assert ch["title"] == "Aiyagari 复现"  # 优先中文标题
        assert ch["content"] == "# 题面正文"
        assert ch["is_demo"] == 0
        # 幂等：同 slug 再导入返回同一题
        r2 = await cli.post("/api/v1/challenges/import",
                            json={"mode": "url", "url": "aiyagari-1994-qje"})
        assert r2.json()["challenge"]["id"] == ch["id"]
        # 无法解析的输入
        r3 = await cli.post("/api/v1/challenges/import",
                            json={"mode": "url", "url": "https://x.test/about"})
        assert r3.status_code == 422
        assert r3.json()["detail"]["code"] == "INVALID_IMPORT"
    row = db.query_one("SELECT contract_status FROM challenges WHERE id=?",
                       (ch["id"],))
    assert row["contract_status"] == "unknown"  # 评分契约如实 unknown
    res = db.query_one("SELECT resources_json FROM challenges WHERE id=?",
                       (ch["id"],))
    stored = json.loads(res["resources_json"])
    assert stored[0]["name"] == "public-training-data", \
        "平台资源清单必须随导入落库，供大脑 run_start 探查"


@pytest.mark.asyncio
async def test_import_challenge_url_platform_404(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from cyberscientist.api import create_app

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {},
                                     io.BytesIO(b"{}"))

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://t") as cli:
        r = await cli.post("/api/v1/challenges/import",
                           json={"mode": "url", "url": "no-such-challenge"})
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "PLATFORM_UNREACHABLE"
