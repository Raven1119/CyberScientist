"""本地 HTTP API（/api/v1）与 SSE。只绑定 127.0.0.1。

写请求要求本地会话 cookie + CSRF 双提交；首次启动生成配对码（仅后端控制台输出）。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets as pysecrets
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from . import config, db, experiences
from .brains.codex import CodexBrain
from .brains.demo import DemoBrain
from .brains.kimi import KimiBrain
from .controller import ControllerError, RunController
from .prime import DemoPrime, PrimeRpc

controller = RunController()

# ---------------- 会话与 CSRF ----------------

SESSION_COOKIE = "cs_session"
CSRF_HEADER = "x-csrf-token"


def _session_secret() -> str:
    path = config.DATA_DIR / "session.secret"
    config.ensure_dirs()
    if not path.exists():
        path.write_text(pysecrets.token_hex(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def _pairing_code() -> str:
    path = config.DATA_DIR / "pairing.code"
    config.ensure_dirs()
    if not path.exists():
        path.write_text("-".join(pysecrets.token_hex(2) for _ in range(3)),
                        encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def _sign(value: str) -> str:
    return hmac.new(_session_secret().encode(), value.encode(), hashlib.sha256).hexdigest()


def make_session_token() -> str:
    raw = f"{pysecrets.token_hex(16)}.{int(time.time())}"
    return f"{raw}.{_sign(raw)}"


def verify_session_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        raw, sig = token.rsplit(".", 1)
        _, ts_str = raw.rsplit(".", 1)
    except ValueError:
        return False
    if not hmac.compare_digest(_sign(raw), sig):
        return False
    try:
        age = time.time() - int(ts_str)
    except ValueError:
        return False
    return 0 <= age <= 30 * 86400


async def require_write(request: Request,
                        x_csrf_token: str | None = Header(default=None)) -> None:
    """写请求依赖：会话 cookie + CSRF 双提交。"""
    token = request.cookies.get(SESSION_COOKIE)
    if not verify_session_token(token):
        raise HTTPException(401, detail={"code": "PAIRING_REQUIRED",
                                         "message": "需要本地配对码建立会话"})
    raw = token.rsplit(".", 1)[0]
    if not x_csrf_token or not hmac.compare_digest(
            _sign("csrf:" + raw), x_csrf_token):
        raise HTTPException(403, detail={"code": "CSRF_FAILED",
                                         "message": "CSRF 校验失败，请刷新页面"})


class PairRequest(BaseModel):
    code: str


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


class AuthorizeBody(BaseModel):
    scope: str = "demo"
    allow_model_calls: bool = False
    max_model_turns: int = 0
    max_run_minutes: int = 30
    max_submissions: int = 0
    note: str | None = None


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
    experiences.check_pending_writes()
    app = FastAPI(title="CyberScientist", docs_url=None, openapi_url=None)
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

    # ---------------- 健康与配对 ----------------

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "mode": config.load_settings()["app"]["mode"],
                "time": db.utcnow()}

    @app.get("/api/v1/session")
    async def session_state(request: Request) -> dict[str, Any]:
        return {"paired": verify_session_token(request.cookies.get(SESSION_COOKIE))}

    @app.post("/api/v1/pair")
    async def pair(req: PairRequest) -> Response:
        if not hmac.compare_digest(req.code.strip(), _pairing_code()):
            raise HTTPException(403, detail={"code": "PAIRING_FAILED",
                                             "message": "配对码不正确"})
        token = make_session_token()
        raw = token.rsplit(".", 1)[0]
        resp = Response(content=json.dumps({"ok": True}), media_type="application/json")
        resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict",
                        max_age=30 * 86400, path="/")
        resp.headers["X-CSRF-Token"] = _sign("csrf:" + raw)
        return resp

    # ---------------- 设置与秘密 ----------------

    @app.get("/api/v1/settings")
    async def get_settings() -> dict[str, Any]:
        s = config.load_settings()
        return s


    @app.put("/api/v1/settings", dependencies=[Depends(require_write)])
    async def put_settings(body: SettingsPut) -> dict[str, Any]:
        current = config.load_settings()
        if body.base_revision != current["revision"]:
            raise HTTPException(409, detail={
                "code": "REVISION_CONFLICT",
                "message": "设置已被其他修改更新，请刷新后重试",
                "current_revision": current["revision"]})
        merged = json.loads(json.dumps(config.DEFAULT_SETTINGS))
        merged.update(body.settings)
        merged["revision"] = current["revision"] + 1
        config.save_settings(merged)
        return merged


    @app.post("/api/v1/secrets", dependencies=[Depends(require_write)])
    async def put_secret(body: SecretPut) -> dict[str, Any]:
        if not body.secret_id or any(c in body.secret_id for c in "/\\: \t"):
            raise HTTPException(422, detail={"code": "INVALID_SECRET_ID",
                                             "message": "secret_id 含非法字符"})
        secrets_store = config.load_secrets()
        secrets_store[body.secret_id] = body.value
        config.save_secrets(secrets_store)
        return {"secret_ref": f"local:{body.secret_id}", "configured": True}

    @app.delete("/api/v1/secrets/{secret_id}", dependencies=[Depends(require_write)])
    async def delete_secret(secret_id: str) -> dict[str, Any]:
        secrets_store = config.load_secrets()
        secrets_store.pop(secret_id, None)
        config.save_secrets(secrets_store)
        return {"secret_ref": f"local:{secret_id}", "configured": False}

    # ---------------- 连接测试 ----------------


    @app.post("/api/v1/connections/{conn_id}/test",
              dependencies=[Depends(require_write)])
    async def test_connection(conn_id: str, body: ConnectionTest) -> dict[str, Any]:
        settings = config.load_settings()
        if conn_id == "brain":
            runtime = settings["brain"]["runtime"] if settings["app"]["mode"] != "demo" else "demo"
            brain = {"demo": DemoBrain(),
                     "codex": CodexBrain(settings["brain"].get("executable") or None,
                                         settings["brain"].get("model_id")),
                     "kimi": KimiBrain()}[runtime]
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
        if conn_id == "prime":
            prime = DemoPrime() if settings["app"]["mode"] == "demo" \
                else PrimeRpc(settings["prime"].get("executable", ""))
            health = await prime.inspect()
            return {"status": "ok" if health.installed else "unavailable",
                    "health": health.__dict__}
        if conn_id == "playground":
            configured = config.secret_configured(
                settings["playground"]["token_secret_ref"])
            return {"status": "configured" if configured else "missing",
                    "detail": "Playground Token " + ("已配置" if configured
                                                     else "未配置；题目 URL 导入不可用")}
        if conn_id == "bohrium":
            import os
            exe = settings["bohrium"]["executable"]
            if not exe or not os.path.exists(exe):
                return {"status": "unavailable",
                        "detail": "bohr CLI 未安装或未配置；科学计算不可用"}
            return {"status": "ok", "detail": "bohr 可执行文件存在；版本探针属阶段 2"}
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "未知连接"})

    # ---------------- 题目 ----------------


    @app.post("/api/v1/challenges/import", dependencies=[Depends(require_write)])
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
            raise HTTPException(502, detail={
                "code": "MISSING_CREDENTIAL",
                "message": "URL 导入需要已配置的 Playground Token；当前未配置，"
                           "或平台契约未核实。请使用手动导入。",
                "recoverable": True})
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

    # ---------------- Run ----------------


    @app.post("/api/v1/runs", dependencies=[Depends(require_write)])
    async def create_run(body: RunCreate) -> dict[str, Any]:
        return controller.create_run(body.challenge_id, body.mode)

    @app.get("/api/v1/runs")
    async def list_runs() -> dict[str, Any]:
        return {"items": controller.list_runs()}

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        return controller.run_snapshot(run_id)


    @app.post("/api/v1/runs/{run_id}/authorize", dependencies=[Depends(require_write)])
    async def authorize(run_id: str, body: AuthorizeBody) -> dict[str, Any]:
        return controller.authorize(run_id, body.scope, body.allow_model_calls,
                                    body.max_model_turns, body.max_run_minutes,
                                    body.max_submissions, body.note)

    @app.post("/api/v1/runs/{run_id}/start", dependencies=[Depends(require_write)])
    async def start_run(run_id: str) -> dict[str, Any]:
        return await controller.start_async(run_id)


    @app.post("/api/v1/runs/{run_id}/control", dependencies=[Depends(require_write)])
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


    @app.post("/api/v1/runs/{run_id}/checkpoints", dependencies=[Depends(require_write)])
    async def save_checkpoint(run_id: str, body: CheckpointBody) -> dict[str, Any]:
        import uuid
        controller.run_snapshot(run_id)
        cp_id = f"cp_{uuid.uuid4().hex[:10]}"
        db.execute(
            "INSERT INTO checkpoints(id, run_id, trial_id, report, evidence_refs,"
            " created_at) VALUES(?,?,?,?,?,?)",
            (cp_id, run_id, body.trial_id, body.report,
             json.dumps(body.evidence_refs, ensure_ascii=False), db.utcnow()))
        db.append_event(run_id, "controller", "checkpoint.created",
                        {"checkpoint_id": cp_id, "trial_id": body.trial_id})
        return {"checkpoint_id": cp_id}

    @app.get("/api/v1/runs/{run_id}/checkpoints")
    async def list_checkpoints(run_id: str) -> dict[str, Any]:
        rows = db.query("SELECT * FROM checkpoints WHERE run_id=? ORDER BY created_at",
                        (run_id,))
        return {"items": [dict(r) | {"evidence_refs": json.loads(r["evidence_refs"])}
                          for r in rows]}

    # ---------------- 经验 ----------------

    @app.get("/api/v1/experiences")
    async def list_exp(scope: str | None = None,
                       challenge_id: str | None = None) -> dict[str, Any]:
        return experiences.list_experiences(scope, challenge_id)


    @app.post("/api/v1/experiences", dependencies=[Depends(require_write)])
    async def create_exp(body: ExperienceCreate) -> dict[str, Any]:
        import uuid
        exp_id = body.id or f"exp_{uuid.uuid4().hex[:8]}"
        return experiences.save_experience(exp_id, body.frontmatter, body.body_md,
                                           operator="user", reason=body.reason,
                                           base_hash=None)

    @app.get("/api/v1/experiences/{exp_id}")
    async def get_exp(exp_id: str) -> dict[str, Any]:
        return experiences.get_experience(exp_id)


    @app.put("/api/v1/experiences/{exp_id}", dependencies=[Depends(require_write)])
    async def put_exp(exp_id: str, body: ExperiencePut) -> dict[str, Any]:
        return experiences.save_experience(exp_id, body.frontmatter, body.body_md,
                                           operator="user", reason=body.reason,
                                           base_hash=body.base_hash)

    @app.get("/api/v1/experiences/{exp_id}/revisions")
    async def exp_revisions(exp_id: str) -> dict[str, Any]:
        return {"items": experiences.get_revisions(exp_id)}


    @app.post("/api/v1/experiences/{exp_id}/restore",
              dependencies=[Depends(require_write)])
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
