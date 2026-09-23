"""技能目录扫描、题目绑定与生效合并测试（src/cyberscientist/skills.py）。"""
from __future__ import annotations

from pathlib import Path

from cyberscientist import db, skills


def _make_skill(root: Path, dirname: str, content: str | None) -> Path:
    d = root / dirname
    d.mkdir(parents=True, exist_ok=True)
    if content is not None:
        (d / "SKILL.md").write_text(content, encoding="utf-8")
    return d


def test_scan_catalog_basic(tmp_path):
    root = tmp_path / "kimi" / "skills"
    _make_skill(root, "tdd",
                "---\nname: tdd\ndescription: 测试驱动开发\n---\n\n正文")
    _make_skill(root, "grill", "---\nname: 烧烤\n---\n\n正文")  # 缺 description
    _make_skill(root, "plain", "没有 frontmatter 的正文")  # 缺 frontmatter
    _make_skill(root, "not-a-skill", None)  # 无 SKILL.md，跳过
    (root / "stray-file.md").write_text("x", encoding="utf-8")  # 非目录，跳过

    catalog = skills.scan_catalog(skill_dirs=[root])
    assert [s["id"] for s in catalog] == ["grill", "plain", "tdd"]
    by_id = {s["id"]: s for s in catalog}
    assert by_id["tdd"]["name"] == "tdd"
    assert by_id["tdd"]["description"] == "测试驱动开发"
    assert by_id["tdd"]["source"] == str(root)
    assert by_id["grill"]["name"] == "烧烤"
    assert by_id["grill"]["description"] == ""
    assert by_id["plain"]["name"] == "plain"  # 缺省用目录名
    assert by_id["plain"]["description"] == ""


def test_scan_catalog_dedupe_first_wins_and_missing_dir(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    _make_skill(first, "tdd", "---\ndescription: 第一来源\n---\n")
    _make_skill(second, "tdd", "---\ndescription: 第二来源\n---\n")
    _make_skill(second, "only-b", "---\ndescription: 仅 b\n---\n")

    catalog = skills.scan_catalog(
        skill_dirs=[first, tmp_path / "不存在", second])
    by_id = {s["id"]: s for s in catalog}
    assert by_id["tdd"]["description"] == "第一来源"
    assert by_id["tdd"]["source"] == str(first)
    assert "only-b" in by_id


def test_scan_catalog_multiline_description_collapsed(tmp_path):
    root = tmp_path / "skills"
    _make_skill(root, "folded",
                "---\nname: folded\ndescription: >\n  第一行\n  第二行\n---\n")
    (catalog,) = skills.scan_catalog(skill_dirs=[root])
    assert catalog["description"] == "第一行 第二行"


def test_challenge_skill_bind_unbind_list():
    conn = db.get_db()
    with db.transaction() as tx:
        db.bind_challenge_skill(tx, "CH1", "tdd")
        db.bind_challenge_skill(tx, "CH1", "tdd")  # INSERT OR IGNORE 幂等
        db.bind_challenge_skill(tx, "CH1", "grill")
        db.bind_challenge_skill(tx, "CH2", "tdd")
    assert db.list_challenge_skills(conn, "CH1") == ["grill", "tdd"]
    assert db.list_challenge_skills(conn, "CH2") == ["tdd"]
    with db.transaction() as tx:
        db.unbind_challenge_skill(tx, "CH1", "tdd")
    assert db.list_challenge_skills(conn, "CH1") == ["grill"]


def test_effective_for_merge_dedupe_and_skip_missing(tmp_path):
    root = tmp_path / "skills"
    _make_skill(root, "tdd", "---\ndescription: 测试驱动\n---\n")
    _make_skill(root, "grill", "---\ndescription: 拷问\n---\n")
    catalog = skills.scan_catalog(skill_dirs=[root])

    conn = db.get_db()
    with db.transaction() as tx:
        db.bind_challenge_skill(tx, "CH1", "grill")
        db.bind_challenge_skill(tx, "CH1", "已被删除的技能")
    settings = {"skills": {"always_on": ["tdd", "grill", "不存在的"]}}

    eff = skills.effective_for(conn, settings, "CH1", catalog=catalog)
    assert [s["id"] for s in eff] == ["tdd", "grill"]  # 去重 + 跳过失效引用

    # 无 challenge_id 时只有常驻
    eff_none = skills.effective_for(conn, settings, None, catalog=catalog)
    assert [s["id"] for s in eff_none] == ["tdd", "grill"]
    # 无常驻时只有本题绑定
    assert skills.effective_for(conn, {}, "CH1", catalog=catalog) == \
        [catalog_by_id(catalog, "grill")]


def catalog_by_id(catalog, sid):
    return next(s for s in catalog if s["id"] == sid)


def test_prompt_segment():
    seg = skills.prompt_segment([
        {"id": "tdd", "name": "tdd", "description": "测试驱动", "source": "/x"}])
    assert seg.startswith("\n\n本 Trial 启用技能")
    assert "- tdd: 测试驱动" in seg
    assert "SKILL.md: /x/tdd/SKILL.md" in seg
    assert "使用前必须阅读对应的 SKILL.md" in seg
    assert skills.prompt_segment([]) == ""


def test_prompt_segment_resolves_installed_file_not_display_name(tmp_path, monkeypatch):
    """CLI 会话工作目录不同；路径必须绝对定位到实际安装文件。"""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "installed skills"
    installed = _make_skill(root, "bohrium-job",
                            "---\nname: Bohrium Jobs\ndescription: 远程任务\n---\n")
    alias = tmp_path / "skills-alias"
    alias.symlink_to(root, target_is_directory=True)
    catalog = skills.scan_catalog(skill_dirs=[Path("skills-alias")])

    segment = skills.prompt_segment(catalog)

    assert "- Bohrium Jobs: 远程任务" in segment
    assert f"SKILL.md: {installed / 'SKILL.md'}" in segment
    assert "相对路径以该文件所在目录为准" in segment
    # source 仍是传入的目录根，不改变已有 API 消费方的字段约定。
    assert catalog[0]["source"] == "skills-alias"


def test_mcp_bridge_post_retries_transient_hang(monkeypatch):
    """M 桥对后端瞬时挂起重试一次；HTTP 协议错误不重试。"""
    import urllib.error

    from cyberscientist import mcp_bridge

    calls = {"n": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def flaky(req, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("timed out")
        return _Resp()

    monkeypatch.setattr(mcp_bridge.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(mcp_bridge.time, "sleep", lambda s: None)
    out = mcp_bridge._post("/api/v1/tools/checkpoint", {"x": 1})
    assert out == {"ok": True} and calls["n"] == 2

    def always_http(req, timeout=0):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 401, "x", {}, None)

    calls["n"] = 0
    monkeypatch.setattr(mcp_bridge.urllib.request, "urlopen", always_http)
    out = mcp_bridge._post("/api/v1/tools/checkpoint", {"x": 1})
    assert "HTTP 401" in out["error"] and calls["n"] == 1


def test_mcp_bridge_survives_lone_surrogate_payload(monkeypatch):
    """执行器报告含孤代理字符（读二进制日志带入的 U+DCA2 一类）时：
    桥进程不得崩溃，POST body 用 U+FFFD 替换非法字符。回归：
    UnicodeEncodeError 曾让桥每次调用都崩溃 → 执行器侧 -32000 Connection closed。"""
    import io
    import json
    from cyberscientist import mcp_bridge

    sent = {}
    surrogates = chr(0xDCA2) + chr(0xDC8C)  # 孤代理，非法 UTF-8

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"checkpoint_id": "cp_x"}'

    def capture(req, timeout=0):
        sent["body"] = req.data
        return _Resp()

    monkeypatch.setattr(mcp_bridge.urllib.request, "urlopen", capture)
    out = mcp_bridge._post("/api/v1/tools/checkpoint",
                           {"report_md": "日志摘录: " + surrogates + " 乱码"})
    assert out == {"checkpoint_id": "cp_x"}  # 没抛异常、拿到了响应
    decoded = sent["body"].decode("utf-8")
    json.loads(decoded)  # body 是合法 UTF-8 JSON
    assert surrogates not in decoded and "" in decoded

    # main() 层兜底：_handle 抛任何异常都返回 JSON-RPC 错误而不是崩溃
    monkeypatch.setattr(mcp_bridge, "_handle",
                        lambda m: (_ for _ in ()).throw(ValueError("boom")))
    inp = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/call"}\n')
    out_buf = io.StringIO()
    monkeypatch.setattr(mcp_bridge.sys, "stdin", inp)
    monkeypatch.setattr(mcp_bridge.sys, "stdout", out_buf)
    mcp_bridge.main()
    resp = json.loads(out_buf.getvalue().strip())
    assert resp["id"] == 1 and resp["error"]["code"] == -32603
    assert "boom" in resp["error"]["message"]
