"""本地 HTTP API（/api/v1）与 SSE。只绑定 127.0.0.1。

单用户本地工具：无配对码、无会话、无 CSRF（用户已确认此边界，
见 docs/DECISIONS.md）。不要绑定到非回环地址。
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import collab, config, db, experiences, mailboxes, skills
from .brains.codex import CodexBrain
from .brains.demo import DemoBrain
from .brains.kimi import KimiBrain
from .controller import ControllerError, RunController
from .prime import CodexExecutor, DemoPrime, KimiExecutor, PrimeRpc

controller = RunController()

PRIME_MODELS_PATH = Path.home() / ".prime" / "agent" / "models.json"


def _sync_prime_models(settings: dict[str, Any]) -> bool:
    """从 llm_profiles + secrets.json 渲染 Prime 原生 models.json。

    单一事实源是 secrets.json；models.json 是 Prime 的官方凭据/模型配置面，
    由后端托管重建（见 docs/DECISIONS.md）。无可用 profile 时不动现有文件。
    """
    providers: dict[str, Any] = {}
    for p in settings.get("llm_profiles", []):
        if p.get("protocol") != "openai_chat_completions":
            continue
        key = config.resolve_secret(p.get("secret_ref", ""))
        if not key:
            continue
        pname = p.get("prime_provider") or "openrouter"
        prov = providers.setdefault(pname, {
            "baseUrl": p.get("base_url", ""),
            "apiKey": key,
            "api": "openai-completions",
            "compat": {"supportsDeveloperRole": False},
            "models": []})
        prov["apiKey"] = key
        prov["models"].append({
            "id": p.get("model_id", ""),
            "name": p.get("id", ""),
            "reasoning": True,
            "input": ["text"],
            "contextWindow": p.get("context_window", 1048576),
            "maxTokens": p.get("max_tokens", 16384),
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}})
    if not providers:
        return False
    PRIME_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PRIME_MODELS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"providers": providers}, ensure_ascii=False,
                              indent=2), encoding="utf-8")
    tmp.replace(PRIME_MODELS_PATH)
    return True


def _prime_models_synced(settings: dict[str, Any]) -> bool:
    """真实回读 models.json：每个已配置 profile 的模型都在且 provider 有 key。"""
    if not PRIME_MODELS_PATH.exists():
        return False
    try:
        data = json.loads(PRIME_MODELS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    providers = data.get("providers", {})
    expected = [p for p in settings.get("llm_profiles", [])
                if p.get("protocol") == "openai_chat_completions"
                and config.resolve_secret(p.get("secret_ref", ""))]
    if not expected:
        return False
    for p in expected:
        pname = p.get("prime_provider") or "openrouter"
        prov = providers.get(pname)
        if not prov or not prov.get("apiKey"):
            return False
        if not any(m.get("id") == p.get("model_id")
                   for m in prov.get("models", [])):
            return False
    return True


class SettingsPut(BaseModel):
    settings: dict[str, Any]
    base_revision: int


class SecretPut(BaseModel):
    secret_id: str
    value: str


class ConnectionTest(BaseModel):
    kind: str = "inspect"
    confirm_spend: bool = False


class ChallengeImport(BaseModel):
    mode: str                     # demo | manual | url
    title: str | None = None
    content: str | None = None
    url: str | None = None
    platform_challenge_id: str | None = None


class RunCreate(BaseModel):
    challenge_id: str
    mode: str | None = None
    shadow_enabled: bool | None = None


class ReviewRequestCreate(BaseModel):
    blocking: bool = False


class ShadowToggle(BaseModel):
    enabled: bool


class PollingToggle(BaseModel):
    enabled: bool


class AlwaysOnPut(BaseModel):
    skill_ids: list[str]


class SkillBind(BaseModel):
    skill_id: str


class AuthorizeBody(BaseModel):
    scope: str = "demo"
    allow_model_calls: bool = False
    max_model_turns: int = 0
    max_run_minutes: int = 30
    max_submissions: int = 0
    max_jobs: int = 0
    note: str | None = None


class BudgetBody(BaseModel):
    max_brain_reviews: int | None = None
    max_trials: int | None = None
    max_model_turns: int | None = None
    max_run_minutes: int | None = None
    max_submissions: int | None = None
    max_jobs: int | None = None


class ControlBody(BaseModel):
    action: str
    text: str | None = None
    operation_id: str


class CheckpointBody(BaseModel):
    trial_id: str | None = None
    report: str
    evidence_refs: list[str] = []


class ExperienceCreate(BaseModel):
    id: str | None = None
    frontmatter: dict[str, Any]
    body_md: str
    reason: str | None = None


class ExperiencePut(BaseModel):
    frontmatter: dict[str, Any]
    body_md: str
    base_hash: str
    reason: str | None = None


class RestoreBody(BaseModel):
    revision_hash: str
    reason: str | None = None


def create_app(web_dist: Path | None = None) -> FastAPI:
    config.ensure_dirs()
    db.init_db()
    problems = experiences.check_pending_writes()
    if problems:
        # 启动对账发现不一致不再静默丢弃：如实告警（不写日志文件防密钥混入）
        print(f"[cyberscientist] 经验修订对账异常 {len(problems)} 项: "
              + "; ".join(str(p)[:120] for p in problems[:5]))
    _sync_prime_models(config.load_settings())  # 启动即对齐 Prime 模型配置

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # 重启对账：无事件循环的非终态 Run 如实标记 recovering（AGENTS 进程可靠性）
        controller.reconcile_on_startup()
        # 后台评分轮询：提交后进入评分等待，由这里异步拿回分数。
        # 评分器可能长时间排队或抽风（409 scoringInProgress / 5xx），
        # 全部吞掉下一轮再试；轮询失败绝不影响服务本身。
        stop = asyncio.Event()

        async def _poll_loop() -> None:
            while not stop.is_set():
                try:
                    # 按题目分组轮询，跳过用户在 settings 中中断的题目
                    await asyncio.to_thread(
                        mailboxes.poll_pending_by_challenge)
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(stop.wait(), 45)
                except asyncio.TimeoutError:
                    pass

        task = asyncio.create_task(_poll_loop())
        try:
            yield
        finally:
            stop.set()
            task.cancel()

    app = FastAPI(title="CyberScientist", docs_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.web_dist = web_dist

    @app.exception_handler(ControllerError)
    async def controller_error(_: Request, exc: ControllerError):
        status = {"NOT_FOUND": 404, "NEEDS_AUTHORIZATION": 403,
                  "MISSING_CREDENTIAL": 400, "RUN_ACTIVE": 409,
                  "INVALID_STATE": 409, "INVALID_ACTION": 400}.get(exc.code, 400)
        return JSONResponse(status_code=status, content={
            "detail": {"code": exc.code, "message": str(exc),
                       "recoverable": exc.recoverable, "details_ref": None}})

    @app.exception_handler(experiences.ExperienceError)
    async def exp_error(_: Request, exc: experiences.ExperienceError):
        status = 409 if exc.code == "REVISION_CONFLICT" else \
            404 if exc.code == "NOT_FOUND" else 422
        body: dict[str, Any] = {"code": exc.code, "message": str(exc),
                                "recoverable": True, "details_ref": None}
        if exc.details:
            body["details"] = exc.details
        return JSONResponse(status_code=status, content={"detail": body})

    @app.exception_handler(collab.CollabError)
    async def collab_error(_: Request, exc: collab.CollabError):
        status = {"NOT_FOUND": 404, "CONFLICT": 409, "RUN_ENDED": 409,
                  "NOT_DELIVERED": 409}.get(exc.code, 422)
        return JSONResponse(status_code=status, content={
            "detail": {"code": exc.code, "message": str(exc),
                       "recoverable": True, "details_ref": None}})

    @app.exception_handler(mailboxes.MailboxError)
    async def mailbox_error(_: Request, exc: mailboxes.MailboxError):
        status = {"NOT_FOUND": 404, "CONFLICT": 409, "INVALID_STATE": 409,
                  "NEEDS_AUTHORIZATION": 403, "NEEDS_CONFIRM": 400,
                  "MISSING_CREDENTIAL": 400, "NO_MAILBOX": 400,
                  "INVALID_MESSAGE": 422}.get(exc.code, 400)
        return JSONResponse(status_code=status, content={
            "detail": {"code": exc.code, "message": str(exc),
                       "recoverable": True, "details_ref": None}})

    # ---------------- 健康 ----------------

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "mode": config.load_settings()["app"]["mode"],
                "time": db.utcnow()}

    # ---------------- 设置与秘密 ----------------

    @app.get("/api/v1/settings")
    async def get_settings() -> dict[str, Any]:
        s = config.load_settings()
        # 真实文件状态同步：secrets.json 与 Prime models.json 回读，不回显值
        secrets_store = config.load_secrets()
        s["_status"] = {
            "secrets": {sid: True for sid in secrets_store},
            "prime_models_synced": _prime_models_synced(s),
        }
        return s


    @app.put("/api/v1/settings")
    async def put_settings(body: SettingsPut) -> dict[str, Any]:
        current = config.load_settings()
        if body.base_revision != current["revision"]:
            raise HTTPException(409, detail={
                "code": "REVISION_CONFLICT",
                "message": "设置已被其他修改更新，请刷新后重试",
                "current_revision": current["revision"]})
        merged = json.loads(json.dumps(config.DEFAULT_SETTINGS))
        incoming = {k: v for k, v in body.settings.items()
                    if k != "_status"}  # _status 是 GET 响应的瞬态字段，不落盘
        merged.update(incoming)
        merged["revision"] = current["revision"] + 1
        config.save_settings(merged)
        _sync_prime_models(merged)  # llm_profiles 可能变化，保持 models.json 同步
        return merged


    @app.post("/api/v1/secrets")
    async def put_secret(body: SecretPut) -> dict[str, Any]:
        if not body.secret_id or any(c in body.secret_id for c in "/\\: \t"):
            raise HTTPException(422, detail={"code": "INVALID_SECRET_ID",
                                             "message": "secret_id 含非法字符"})
        secrets_store = config.load_secrets()
        secrets_store[body.secret_id] = body.value
        config.save_secrets(secrets_store)
        synced = _sync_prime_models(config.load_settings())
        return {"secret_ref": f"local:{body.secret_id}", "configured": True,
                "prime_models_synced": synced}

    @app.delete("/api/v1/secrets/{secret_id}")
    async def delete_secret(secret_id: str) -> dict[str, Any]:
        secrets_store = config.load_secrets()
        secrets_store.pop(secret_id, None)
        config.save_secrets(secrets_store)
        synced = _sync_prime_models(config.load_settings())
        return {"secret_ref": f"local:{secret_id}", "configured": False,
                "prime_models_synced": synced}

    # ---------------- 连接测试 ----------------


    @app.post("/api/v1/connections/{conn_id}/test",
              )
    async def test_connection(conn_id: str, body: ConnectionTest) -> dict[str, Any]:
        settings = config.load_settings()
        if conn_id != "brain" and body.kind == "model_roundtrip":
            raise HTTPException(501, detail={
                "code": "NOT_IMPLEMENTED",
                "message": "模型工具调用往返只对大脑开放；执行器/平台请用"
                           "“检查安装/认证”（零费用）"})
        if conn_id == "brain":
            runtime = settings["brain"]["runtime"] if settings["app"]["mode"] != "demo" else "demo"
            brain = {"demo": DemoBrain(),
                     "codex": CodexBrain(settings["brain"].get("executable") or None,
                                         settings["brain"].get("model_id"),
                                         settings["brain"].get("reasoning_effort")),
                     "kimi": KimiBrain(settings["brain"].get("executable") or None,
                                       settings["brain"].get("model_id"),
                                       settings["brain"].get("reasoning_effort"))}[runtime]
            health = await brain.inspect()
            if body.kind == "model_roundtrip":
                if not body.confirm_spend:
                    raise HTTPException(403, detail={
                        "code": "NEEDS_AUTHORIZATION",
                        "message": "真实模型往返消耗额度；需显式确认（confirm_spend=true）"})
                if settings["app"]["mode"] == "demo":
                    return {"status": "synthetic", "detail": "Demo 模式往返为合成数据，"
                            "不作为真实联调证据", "health": health.__dict__}
                raise HTTPException(501, detail={
                    "code": "NOT_IMPLEMENTED",
                    "message": "真实模型往返需 Run 级授权上下文；阶段 1 仅开放握手探针"})
            return {"status": "ok" if health.installed else "unavailable",
                    "health": health.__dict__}
        if conn_id == "executor":
            # 当前配置的执行系统（默认 kimi）：与 Run 实际路径一致
            if settings["app"]["mode"] == "demo":
                health = await DemoPrime().inspect()
            else:
                health = await controller._make_prime(settings).inspect()
            return {"status": "ok" if health.installed else "unavailable",
                    "health": health.__dict__}
        if conn_id == "prime":
            import shutil
            exe = settings["prime"].get("executable") or shutil.which("prime-agent") or ""
            prime = DemoPrime() if settings["app"]["mode"] == "demo" else PrimeRpc(exe)
            health = await prime.inspect()
            return {"status": "ok" if health.installed else "unavailable",
                    "health": health.__dict__}
        if conn_id == "playground":
            configured = config.secret_configured(
                settings["playground"]["token_secret_ref"])
            detail = "Playground Token " + ("已配置" if configured
                                            else "未配置；题目 URL 导入不可用")
            return {"status": "configured" if configured else "missing",
                    "detail": detail,
                    "health": {"installed": None, "authenticated": configured,
                               "detail": detail, "version": None,
                               "capabilities": {}}}
        if conn_id == "bohrium":
            import os
            import shutil
            exe = settings["bohrium"]["executable"] or shutil.which("bohr") or ""
            if not exe or not os.path.exists(exe):
                return {"status": "unavailable",
                        "detail": "bohr CLI 未安装或未配置；科学计算不可用",
                        "health": {"installed": False, "authenticated": None,
                                   "detail": "bohr CLI 未安装或未配置；科学计算不可用",
                                   "version": None, "capabilities": {}}}
            # 零算力只读探针：--version（本地）+ auth whoami（只读 API）
            import subprocess
            def _bohr(args: list[str]) -> subprocess.CompletedProcess:
                cmd = (["cmd", "/c", exe, *args]
                       if exe.lower().endswith((".cmd", ".bat"))
                       else [exe, *args])
                return subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=30, shell=False)
            version: str | None = None
            authenticated: bool | None = None
            detail_parts: list[str] = []
            try:
                vp = _bohr(["--version"])
                version = (vp.stdout or vp.stderr).strip() or None
            except (OSError, subprocess.TimeoutExpired):
                pass
            try:
                wp = _bohr(["auth", "whoami"])
                if wp.returncode == 0 and '"ok": true' in wp.stdout:
                    authenticated = True
                    detail_parts.append("AccessKey 已认证")
                else:
                    authenticated = False
                    detail_parts.append("未认证；请在密钥区保存 Bohrium AccessKey "
                                        "后执行 bohr auth login --ak")
            except (OSError, subprocess.TimeoutExpired):
                detail_parts.append("认证探针超时")
            detail = "；".join(detail_parts) or "bohr 可用"
            ok = authenticated is True
            return {"status": "ok" if ok else "unavailable",
                    "detail": detail,
                    "health": {"installed": True, "authenticated": authenticated,
                               "detail": detail, "version": version,
                               "capabilities": {}}}
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "未知连接"})
    # ---------------- 题目 ----------------


    @app.post("/api/v1/challenges/import")
    async def import_challenge(body: ChallengeImport) -> dict[str, Any]:
        import hashlib
        import uuid
        if body.mode == "demo":
            cid = "DEMO_CHALLENGE"
            existing = db.query_one("SELECT id FROM challenges WHERE id=?", (cid,))
            if existing:
                return {"challenge": _challenge_dict(cid)}
            content = ("# 演示题目：远程环境与结果包自检\n\n"
                       "这是虚构的演示题目，用于验证 导入→研究→经验→重启可见 的"
                       "完整交互。不消耗任何模型额度或算力。\n\n"
                       "## 目标\n验证执行器、产物登记与经验闭环。\n")
            db.execute(
                "INSERT INTO challenges(id, platform_challenge_id, origin, title,"
                " content, content_hash, contract_status, imported_at, is_demo)"
                " VALUES(?,?,?,?,?,?,'unknown',?,1)",
                (cid, "DEMO_000", "demo://local", content.splitlines()[0].lstrip("# "),
                 content, hashlib.sha256(content.encode()).hexdigest(), db.utcnow()))
            return {"challenge": _challenge_dict(cid)}
        if body.mode == "manual":
            if not body.title or not body.content:
                raise HTTPException(422, detail={
                    "code": "INVALID_IMPORT",
                    "message": "手动导入需要 title 与 content"})
            cid = f"local_{uuid.uuid4().hex[:8]}"
            db.execute(
                "INSERT INTO challenges(id, platform_challenge_id, origin, title,"
                " content, content_hash, contract_status, imported_at, is_demo)"
                " VALUES(?,?,?,?,?,?,'unknown',?,0)",
                (cid, body.platform_challenge_id, "manual://local", body.title,
                 body.content,
                 hashlib.sha256(body.content.encode()).hexdigest(), db.utcnow()))
            return {"challenge": _challenge_dict(cid)}
        if body.mode == "url":
            from . import mailbox_platform
            slug = mailbox_platform.parse_challenge_slug(body.url or "")
            if not slug:
                raise HTTPException(422, detail={
                    "code": "INVALID_IMPORT",
                    "message": "无法从输入解析题目 id；请粘贴平台题目 URL 或题目 slug"})
            existing = db.query_one(
                "SELECT id FROM challenges WHERE platform_challenge_id=?"
                " AND is_demo=0", (slug,))
            if existing:
                return {"challenge": _challenge_dict(existing["id"])}
            settings = config.load_settings()
            pg = settings.get("playground") or {}
            token_ref = pg.get("token_secret_ref") or ""
            token = config.resolve_secret(token_ref) if token_ref else None
            try:
                data = await asyncio.to_thread(
                    mailbox_platform.fetch_platform_challenge,
                    pg.get("base_url") or "https://play.bohrium.com/api",
                    slug, token)
            except mailbox_platform.PlatformError as exc:
                status = 404 if "HTTP 404" in str(exc) else 502
                raise HTTPException(status, detail={
                    "code": "PLATFORM_UNREACHABLE",
                    "message": f"平台题目拉取失败：{exc}",
                    "recoverable": True}) from exc
            content = (data.get("content") or "").strip()
            if not content:
                raise HTTPException(502, detail={
                    "code": "PLATFORM_CONTRACT_UNKNOWN",
                    "message": f"平台题目 {slug} 无题面内容（content 为空），"
                               "请使用手动导入。",
                    "recoverable": True})
            title = (data.get("title_zh") or data.get("title")
                     or slug).strip()
            cid = f"local_{uuid.uuid4().hex[:8]}"
            resources = data.get("resources")
            db.execute(
                "INSERT INTO challenges(id, platform_challenge_id, origin, title,"
                " content, content_hash, contract_status, imported_at, is_demo,"
                " resources_json)"
                " VALUES(?,?,?,?,?,?,'unknown',?,0,?)",
                (cid, slug, body.url, title, content,
                 hashlib.sha256(content.encode()).hexdigest(), db.utcnow(),
                 json.dumps(resources, ensure_ascii=False)
                 if isinstance(resources, list) else None))
            return {"challenge": _challenge_dict(cid)}
        raise HTTPException(422, detail={"code": "INVALID_IMPORT",
                                         "message": f"未知导入模式: {body.mode}"})

    def _challenge_dict(cid: str) -> dict[str, Any]:
        row = db.query_one("SELECT * FROM challenges WHERE id=?", (cid,))
        if not row:
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "题目不存在"})
        return dict(row)

    @app.get("/api/v1/challenges")
    async def list_challenges() -> dict[str, Any]:
        rows = db.query("SELECT id, platform_challenge_id, origin, title,"
                        " contract_status, imported_at, is_demo"
                        " FROM challenges ORDER BY imported_at DESC")
        return {"items": [dict(r) for r in rows]}

    @app.get("/api/v1/challenges/{cid}")
    async def get_challenge(cid: str) -> dict[str, Any]:
        return _challenge_dict(cid)

    # ---------------- 技能 ----------------

    def _require_challenge(cid: str) -> None:
        if not db.query_one("SELECT id FROM challenges WHERE id=?", (cid,)):
            raise HTTPException(404, detail={"code": "NOT_FOUND",
                                             "message": "题目不存在"})

    def _require_catalog_skill(skill_id: str,
                               catalog: list[dict[str, Any]]) -> None:
        if not any(s["id"] == skill_id for s in catalog):
            raise HTTPException(404, detail={"code": "NOT_FOUND",
                                             "message": f"技能不存在于目录: {skill_id}"})

    @app.get("/api/v1/skills")
    async def list_skills(challenge_id: str | None = None) -> dict[str, Any]:
        catalog = skills.scan_catalog()
        settings = config.load_settings()
        catalog_ids = {s["id"] for s in catalog}
        always_on = [sid for sid in
                     (settings.get("skills") or {}).get("always_on", [])
                     if sid in catalog_ids]
        bound = db.list_challenge_skills(db.get_db(), challenge_id) \
            if challenge_id else []
        bound_set = set(bound)
        always_set = set(always_on)
        return {"skills": [s | {"always_on": s["id"] in always_set,
                                "bound": s["id"] in bound_set}
                           for s in catalog],
                "always_on": always_on, "bound": bound}

    @app.put("/api/v1/skills/always_on")
    async def put_always_on(body: AlwaysOnPut) -> dict[str, Any]:
        catalog_ids = {s["id"] for s in skills.scan_catalog()}
        ids: list[str] = []
        for sid in body.skill_ids:
            if sid in catalog_ids and sid not in ids:
                ids.append(sid)
        settings = config.load_settings()
        settings.setdefault("skills", {})["always_on"] = ids
        settings["revision"] = settings["revision"] + 1
        config.save_settings(settings)
        return {"always_on": ids, "revision": settings["revision"]}

    @app.post("/api/v1/challenges/{cid}/skills")
    async def bind_skill(cid: str, body: SkillBind) -> dict[str, Any]:
        _require_challenge(cid)
        _require_catalog_skill(body.skill_id, skills.scan_catalog())
        with db.transaction() as conn:
            db.bind_challenge_skill(conn, cid, body.skill_id)
            bound = db.list_challenge_skills(conn, cid)
        return {"challenge_id": cid, "bound": bound}

    @app.delete("/api/v1/challenges/{cid}/skills/{skill_id}")
    async def unbind_skill(cid: str, skill_id: str) -> dict[str, Any]:
        _require_challenge(cid)
        with db.transaction() as conn:
            db.unbind_challenge_skill(conn, cid, skill_id)
            bound = db.list_challenge_skills(conn, cid)
        return {"challenge_id": cid, "bound": bound}

    # ---------------- Run ----------------


    @app.post("/api/v1/runs")
    async def create_run(body: RunCreate) -> dict[str, Any]:
        return controller.create_run(body.challenge_id, body.mode,
                                     body.shadow_enabled)

    @app.get("/api/v1/runs")
    async def list_runs() -> dict[str, Any]:
        return {"items": controller.list_runs()}

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        return controller.run_snapshot(run_id)


    @app.post("/api/v1/runs/{run_id}/authorize")
    async def authorize(run_id: str, body: AuthorizeBody) -> dict[str, Any]:
        return controller.authorize(run_id, body.scope, body.allow_model_calls,
                                    body.max_model_turns, body.max_run_minutes,
                                    body.max_submissions, body.note,
                                    max_jobs=body.max_jobs)

    @app.put("/api/v1/runs/{run_id}/budget")
    async def update_budget(run_id: str, body: BudgetBody) -> dict[str, Any]:
        return controller.update_budget(
            run_id, max_brain_reviews=body.max_brain_reviews,
            max_trials=body.max_trials, max_model_turns=body.max_model_turns,
            max_run_minutes=body.max_run_minutes,
            max_submissions=body.max_submissions, max_jobs=body.max_jobs)

    @app.post("/api/v1/runs/{run_id}/start")
    async def start_run(run_id: str) -> dict[str, Any]:
        return await controller.start_async(run_id)


    @app.post("/api/v1/runs/{run_id}/control")
    async def control_run(run_id: str, body: ControlBody) -> dict[str, Any]:
        return await controller.control(run_id, body.action, body.text,
                                        body.operation_id)

    @app.get("/api/v1/runs/{run_id}/events")
    async def run_events(run_id: str, after: int = 0) -> StreamingResponse:
        controller.run_snapshot(run_id)  # 404 校验

        async def stream() -> Any:
            last = after
            while True:
                events = db.events_after(run_id, last, limit=200)
                for ev in events:
                    last = ev["seq"]
                    yield f"id: {ev['event_id']}\n" \
                          f"event: {ev['type']}\n" \
                          f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if not events:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1.0)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})


    @app.post("/api/v1/runs/{run_id}/checkpoints")
    async def save_checkpoint(run_id: str, body: CheckpointBody) -> dict[str, Any]:
        """UI 手动检查点：与 MCP 工具共用 collab 服务（去重/原子/唤醒）。"""
        import uuid
        msg = {"schema_version": 1, "message_type": "checkpoint",
               "checkpoint_key": f"ui-{uuid.uuid4().hex[:8]}",
               "review": "none", "stage": "progress",
               "report_md": body.report, "evidence_refs": body.evidence_refs}
        result = collab.submit_checkpoint(
            run_id, msg, source="user",
            notify=controller.notify_run_change)
        return {"checkpoint_id": result["checkpoint_id"]}

    # ---------------- 协作：静默监督 / 审阅请求 / 指导 ----------------

    @app.get("/api/v1/runs/{run_id}/supervision")
    async def get_supervision(run_id: str) -> dict[str, Any]:
        return controller.supervision_status(run_id)

    @app.post("/api/v1/runs/{run_id}/supervision")
    async def set_supervision(run_id: str, body: ShadowToggle) -> dict[str, Any]:
        return controller.set_shadow(run_id, body.enabled)

    @app.post("/api/v1/runs/{run_id}/review_requests")
    async def request_review(run_id: str,
                             body: ReviewRequestCreate) -> dict[str, Any]:
        return controller.request_review(run_id, body.blocking)

    # ---------------- 协作工具桥（能力令牌鉴权）----------------

    def _tool_auth(request: Request) -> dict[str, Any]:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        row = collab.validate_token(token)
        if not row:
            raise HTTPException(status_code=401, detail={
                "code": "INVALID_TOKEN",
                "message": "能力令牌无效/过期/已撤销"})
        return row

    @app.post("/api/v1/tools/checkpoint")
    async def tool_checkpoint(request: Request) -> dict[str, Any]:
        identity = _tool_auth(request)
        body = await request.json()
        body["schema_version"] = 1
        body["message_type"] = "checkpoint"
        return collab.submit_checkpoint(
            identity["run_id"], body, source="executor",
            notify=controller.notify_run_change)

    @app.post("/api/v1/tools/ack")
    async def tool_ack(request: Request) -> dict[str, Any]:
        identity = _tool_auth(request)
        body = await request.json()
        body["schema_version"] = 1
        body["message_type"] = "guidance_ack"
        return collab.ack_guidance(identity["run_id"], body)

    @app.get("/api/v1/runs/{run_id}/checkpoints")
    async def list_checkpoints(run_id: str) -> dict[str, Any]:
        rows = db.query("SELECT * FROM checkpoints WHERE run_id=? ORDER BY created_at",
                        (run_id,))
        return {"items": [dict(r) | {"evidence_refs": json.loads(r["evidence_refs"])}
                          for r in rows]}

    # ---------------- 邮箱与提交 ----------------

    @app.get("/api/v1/mailboxes")
    async def list_mailboxes() -> dict[str, Any]:
        return mailboxes.list_mailboxes()

    @app.post("/api/v1/mailboxes/harvest")
    async def add_harvest(request: Request) -> dict[str, Any]:
        body = await request.json()
        return mailboxes.add_harvest(body.get("email", ""),
                                     body.get("secret", ""))

    @app.post("/api/v1/mailboxes/experiment/register")
    async def register_experiment(request: Request) -> dict[str, Any]:
        body = await request.json()
        return mailboxes.register_experiment(int(body.get("count", 1)))

    @app.delete("/api/v1/mailboxes/{mailbox_id}")
    async def disable_mailbox(mailbox_id: str) -> dict[str, Any]:
        return mailboxes.disable_mailbox(mailbox_id)

    @app.get("/api/v1/runs/{run_id}/submissions")
    async def list_run_submissions(run_id: str) -> dict[str, Any]:
        return mailboxes.list_submissions(run_id)

    @app.get("/api/v1/challenges/{challenge_id}/submissions")
    async def list_challenge_submissions(challenge_id: str) -> dict[str, Any]:
        """题目级提交聚合（前端「提交与评分」tab）：item 形状与
        /runs/{run_id}/submissions 一致，聚合该题所有 Run，新的在前。"""
        return mailboxes.list_challenge_submissions(challenge_id)

    @app.post("/api/v1/runs/{run_id}/submissions")
    async def submit_experiment(run_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        return mailboxes.submit_experiment(
            run_id, body.get("trial_id"), body.get("package_path"),
            body.get("operation_id", ""))

    @app.post("/api/v1/submissions/poll")
    async def poll_scores(request: Request) -> dict[str, Any]:
        body = await request.json() if request.headers.get(
            "content-type", "").startswith("application/json") else {}
        # 评分平台 HTTP 是同步调用：卸载到线程，不阻塞事件循环
        return await asyncio.to_thread(mailboxes.poll_scores, body.get("run_id"))

    # ---------------- 评分轮询任务（按题目中断/启用） ----------------

    @app.get("/api/v1/polling")
    async def polling_tasks() -> dict[str, Any]:
        return mailboxes.polling_tasks()

    @app.post("/api/v1/polling/{challenge_id}")
    async def polling_toggle(challenge_id: str,
                             body: PollingToggle) -> dict[str, Any]:
        return mailboxes.set_polling_enabled(challenge_id, body.enabled)

    @app.post("/api/v1/polling/{challenge_id}/run")
    async def polling_run(challenge_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            mailboxes.poll_scores_now, challenge_id)

    @app.get("/api/v1/harvest/candidates")
    async def harvest_candidates(challenge_id: str) -> dict[str, Any]:
        return mailboxes.harvest_candidates(challenge_id)

    @app.post("/api/v1/harvest/submit")
    async def harvest_submit(request: Request) -> dict[str, Any]:
        body = await request.json()
        return mailboxes.harvest_submit(
            body.get("submission_id", ""), body.get("operation_id", ""),
            bool(body.get("confirm")))

    # ---------------- 经验 ----------------

    @app.get("/api/v1/experiences")
    async def list_exp(scope: str | None = None,
                       challenge_id: str | None = None) -> dict[str, Any]:
        return experiences.list_experiences(scope, challenge_id)

    # 具体路径必须先于 {exp_id} 注册，否则被路径参数吞掉
    @app.post("/api/v1/experiences/curate_global")
    async def curate_global(request: Request) -> dict[str, Any]:
        """手动触发全局经验整理（一次性大脑会话，消耗模型调用）。"""
        body = await request.json()
        return await controller.curate_global_experience(
            body.get("challenge_ids") or [])

    @app.get("/api/v1/experiences/curate_global")
    async def curate_global_status() -> dict[str, Any]:
        return controller.global_curation_status()

    @app.post("/api/v1/experiences/{exp_id}/approve")
    async def approve_exp(exp_id: str) -> dict[str, Any]:
        """用户审批：全局 candidate → active（全局经验唯一晋升通道）。"""
        return experiences.approve_experience(exp_id)

    @app.post("/api/v1/experiences/{exp_id}/reject")
    async def reject_exp(exp_id: str, request: Request) -> dict[str, Any]:
        """用户驳回：保持 candidate 并附批注，大脑下轮整理参考批注。"""
        body = await request.json()
        return experiences.reject_experience(exp_id, body.get("note", ""))


    @app.post("/api/v1/experiences")
    async def create_exp(body: ExperienceCreate) -> dict[str, Any]:
        import uuid
        exp_id = body.id or f"exp_{uuid.uuid4().hex[:8]}"
        return experiences.save_experience(exp_id, body.frontmatter, body.body_md,
                                           operator="user", reason=body.reason,
                                           base_hash=None)

    @app.get("/api/v1/experiences/{exp_id}")
    async def get_exp(exp_id: str) -> dict[str, Any]:
        return experiences.get_experience(exp_id)


    @app.put("/api/v1/experiences/{exp_id}")
    async def put_exp(exp_id: str, body: ExperiencePut) -> dict[str, Any]:
        return experiences.save_experience(exp_id, body.frontmatter, body.body_md,
                                           operator="user", reason=body.reason,
                                           base_hash=body.base_hash)

    @app.get("/api/v1/experiences/{exp_id}/revisions")
    async def exp_revisions(exp_id: str) -> dict[str, Any]:
        return {"items": experiences.get_revisions(exp_id)}


    @app.post("/api/v1/experiences/{exp_id}/restore",
              )
    async def restore_exp(exp_id: str, body: RestoreBody) -> dict[str, Any]:
        return experiences.restore_revision(exp_id, body.revision_hash, "user",
                                            body.reason)

    # ---------------- 产物 ----------------

    @app.get("/api/v1/runs/{run_id}/artifacts/{relpath:path}")
    async def get_artifact(run_id: str, relpath: str) -> FileResponse:
        base = (config.WORKSPACE_DIR / "runs" / run_id).resolve()
        target = (base / relpath).resolve()
        if not target.is_relative_to(base):
            raise HTTPException(403, detail={"code": "PATH_FORBIDDEN",
                                             "message": "路径越界被拒绝"})
        if not target.is_file():
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "产物不存在"})
        return FileResponse(target)

    # ---------------- 前端静态资源 ----------------

    if web_dist and (web_dist / "index.html").exists():
        @app.get("/{full_path:path}")
        async def spa(full_path: str) -> Any:
            candidate = (web_dist / full_path).resolve()
            if full_path and candidate.is_file() and str(candidate).startswith(
                    str(web_dist.resolve())):
                return FileResponse(candidate)
            return FileResponse(web_dist / "index.html")

    return app
