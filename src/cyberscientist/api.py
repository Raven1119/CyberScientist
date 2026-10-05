"""本地 HTTP API（/api/v1）与 SSE。只绑定 127.0.0.1。

单用户本地工具：无配对码、无会话、无 CSRF（用户已确认此边界，
见 docs/DECISIONS.md）。不要绑定到非回环地址。
"""
from __future__ import annotations

import asyncio
import json
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import collab, config, db, datasets, experiences, mailboxes, skills, compute, observation, sandboxes, local_scoring, trace_diagnostics, evaluations, job_recovery
from .brains.codex import CodexBrain
from .brains.demo import DemoBrain
from .brains.kimi import KimiBrain
from .controller import ControllerError, RunController
from .resource_coordinator import ResourceWait
from .prime import CodexExecutor, DemoPrime, KimiExecutor, PrimeRpc

controller = RunController()

CLOCK_HEARTBEAT_SECONDS = 15

class SettingsPut(BaseModel):
    settings: dict[str, Any]
    base_revision: int
    replace_paths: list[str] = []


class SecretPut(BaseModel):
    secret_id: str
    value: str


class ConnectionTest(BaseModel):
    kind: str = "inspect"
    confirm_spend: bool = False
    model_choice: dict[str, Any] | None = None


class ChallengeImport(BaseModel):
    mode: str                     # demo | manual | url
    title: str | None = None
    content: str | None = None
    url: str | None = None
    platform_challenge_id: str | None = None
    models: dict[str, Any] | None = Field(default=None, alias="model_config")


class ChallengeModelsPut(BaseModel):
    models: dict[str, Any] = Field(alias="model_config")


class RunCreate(BaseModel):
    challenge_id: str
    mode: str | None = None
    shadow_enabled: bool | None = None


class EvaluationCreate(BaseModel):
    suite: str
    repeats: int = 2
    label: str = ''


class RoundImport(BaseModel):
    challenge_ids: list[str] | None = None
    season: str = ''
    round_seq: int | None = None
    label: str = ''
    mode: str = 'connected'


class RoundConfirm(BaseModel):
    template: dict[str, Any]
    overrides: dict[str, Any] | None = None


class RoundAppend(BaseModel):
    challenge_id: str
    template: dict[str, Any] | None = None


class RoundItemPut(BaseModel):
    priority: int | None = None
    paused: bool | None = None


class RoundTriage(BaseModel):
    allow_model_calls: bool = False


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
    max_environment_saves: int = 0
    unlimited_resources: bool = False
    max_sandboxes: int = 0
    max_sandbox_minutes: int = 0
    allow_sandbox_gpu: bool = False
    max_compute_cost_cny: float | None = None
    job_limits: dict | None = None
    allow_data_download: bool = False
    objective: str | None = None
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
    research_summary_md: str | None = None
    evidence_refs: list[str] = []
    experience_uses: list[dict[str, str]] = []


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
    operation_id: str | None = None


class ExperienceReview(BaseModel):
    expected_revision: str
    note: str = ""


def create_app(web_dist: Path | None = None) -> FastAPI:
    from . import backend_identity
    backend_identity.record_startup()
    config.ensure_dirs()
    db.init_db()
    for challenge in db.query("SELECT id,resources_json FROM challenges WHERE resources_json IS NOT NULL"):
        try:
            resources = json.loads(challenge["resources_json"])
        except (TypeError, ValueError):
            resources = []
        if isinstance(resources, list):
            datasets.register_resources(challenge["id"], resources)
    problems = experiences.check_pending_writes()
    if problems:
        # 启动对账发现不一致不再静默丢弃：如实告警（不写日志文件防密钥混入）
        print(f"[cyberscientist] 经验修订对账异常 {len(problems)} 项: "
              + "; ".join(str(p)[:120] for p in problems[:5]))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # 重启对账：无事件循环的非终态 Run 如实标记 recovering（AGENTS 进程可靠性）
        controller.reconcile_on_startup()
        compute.recover_pending()
        bohrium_cfg = config.load_settings()['bohrium']
        if config.resolve_secret(bohrium_cfg.get('access_key_secret_ref','')):
            from . import machine_catalog
            await asyncio.to_thread(machine_catalog.refresh)
            try:
                await asyncio.to_thread(sandboxes.reconcile_startup)
            except Exception:
                import logging
                logging.getLogger('cyberscientist.api').exception('Sandbox startup reconciliation failed')
        from . import maintenance
        maintenance.reconcile_interrupted()
        from . import package_reviews
        package_reviews.reconcile_interrupted()
        from . import auto_harvest
        for run_id in compute.reconciliation_runs(startup=True):
            try:
                await job_recovery.reconcile(run_id, controller)
            except Exception:
                # Other Runs still need their independent startup recovery.
                import logging
                logging.getLogger('cyberscientist.api').exception(
                    'Job reconciliation failed for Run %s', run_id)
        # Attempts are reconciled before native sessions can recover. An
        # unavailable receipt remains visible to the recovery PI as unknown.
        try:
            _notify_scores(await asyncio.to_thread(mailboxes.poll_pending_by_challenge))
        except Exception as exc:
            for run in db.query("SELECT id FROM runs WHERE phase='recovering'"):
                db.append_event(run['id'], 'controller', 'run.submission_reconciliation_unknown',
                                {'error': type(exc).__name__})
        auto_harvest.reconcile_interrupted()
        mailboxes.reconcile_draft_continuations()
        from . import power
        await power.recover(controller)
        controller.scan_score_waits()
        # 后台评分轮询：提交后进入评分等待，由这里异步拿回分数。
        # 评分器可能长时间排队或抽风（409 scoringInProgress / 5xx），
        # 全部吞掉下一轮再试；轮询失败绝不影响服务本身。
        stop = asyncio.Event()

        async def _poll_loop() -> None:
            while not stop.is_set():
                try:
                    # 按题目分组轮询，跳过用户在 settings 中中断的题目
                    result = await asyncio.to_thread(mailboxes.poll_pending_by_challenge)
                    _notify_scores(result)
                    await asyncio.to_thread(sandboxes.reconcile_deletions)
                    for run_id in compute.reconciliation_runs():
                        try:
                            await job_recovery.reconcile(run_id, controller)
                            controller.notify_run_change(run_id)
                        except Exception:
                            import logging
                            logging.getLogger('cyberscientist.api').exception(
                                'Job polling failed for Run %s', run_id)
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(stop.wait(), 45)
                except asyncio.TimeoutError:
                    pass

        async def _watch_loop() -> None:
            import logging
            logger = logging.getLogger('cyberscientist.api')
            while not stop.is_set():
                controller.scan_score_waits()
                try:
                    await asyncio.to_thread(sandboxes.expire_due)
                    compute.release_unknown_slots()
                except Exception:
                    logger.exception('Sandbox expiry cleanup failed')
                from . import maintenance
                try:
                    await maintenance.advance(controller)
                except Exception:
                    logger.exception('End-of-Run maintenance scheduling failed')
                for row in db.query("SELECT id FROM runs WHERE phase='running'"):
                    try:
                        controller.check_liveness(row['id'])
                        await controller.retry_limited_executor(row['id'])
                    except Exception:
                        logger.exception('Liveness check failed for Run %s', row['id'])
                from . import auto_harvest, alerts
                try:
                    await auto_harvest.advance()
                    await asyncio.to_thread(alerts.synchronize)
                except Exception:
                    logger.exception('Harvest and alert scheduling failed')
                try:
                    await asyncio.wait_for(stop.wait(), 15)
                except asyncio.TimeoutError:
                    pass

        async def _evaluation_loop() -> None:
            import logging
            logger = logging.getLogger('cyberscientist.api')
            while not stop.is_set():
                try:
                    await evaluations.advance(controller)
                except Exception:
                    logger.exception('Evaluation scheduling pass failed')
                try:
                    await asyncio.wait_for(stop.wait(), 10)
                except asyncio.TimeoutError:
                    pass

        async def _clock_loop() -> None:
            from . import run_clock
            import logging
            while not stop.is_set():
                try:
                    run_clock.heartbeat()
                except Exception:
                    logging.getLogger('cyberscientist.api').exception('Active-time heartbeat failed')
                try:
                    await asyncio.wait_for(stop.wait(), CLOCK_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    pass

        async def _job_recovery_loop() -> None:
            from . import job_recovery
            import logging
            while not stop.is_set():
                try:
                    await job_recovery.advance(controller)
                except Exception:
                    logging.getLogger('cyberscientist.api').exception('Job recovery scheduling failed')
                try:
                    await asyncio.wait_for(stop.wait(), 5)
                except asyncio.TimeoutError:
                    pass

        task = asyncio.create_task(_poll_loop())
        clock_task = asyncio.create_task(_clock_loop())
        watch_task = asyncio.create_task(_watch_loop())
        evaluation_task = asyncio.create_task(_evaluation_loop())
        job_recovery_task = asyncio.create_task(_job_recovery_loop())
        try:
            yield
        finally:
            stop.set()
            db.execute("INSERT OR REPLACE INTO system_state VALUES('shutdown_requested','1')")
            task.cancel()
            clock_task.cancel()
            watch_task.cancel()
            evaluation_task.cancel()
            job_recovery_task.cancel()
            await asyncio.gather(task, clock_task, watch_task, evaluation_task, job_recovery_task, return_exceptions=True)
            await job_recovery.drain()
            await auto_harvest.drain()

    app = FastAPI(title="CyberScientist", docs_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.web_dist = web_dist

    @app.post('/api/v1/system/safe-shutdown')
    async def safe_shutdown():
        from . import power
        return await power.safe_shutdown(controller)

    @app.get('/api/v1/alerts')
    async def pending_alerts():
        from . import alerts
        return {'items': await asyncio.to_thread(alerts.pending)}

    @app.post('/api/v1/alerts/{alert_id}/acknowledge')
    async def acknowledge_alert(alert_id: str):
        from . import alerts
        try:
            return alerts.acknowledge(alert_id)
        except ValueError as exc:
            raise HTTPException(404, detail={'message': str(exc)}) from exc


    @app.exception_handler(ResourceWait)
    async def resource_wait(_: Request, exc: ResourceWait):
        return JSONResponse(status_code=409, content={'detail': {
            'code': 'RESOURCE_WAIT', 'message': str(exc), 'recoverable': True}})

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
                  "INVALID_MESSAGE": 422, "PREDICTION_REQUIRED": 422,
                  "INVALID_TRACE_NARRATIVE": 422,
                  "SCIENCE_ARTIFACT_CHANGED": 409}.get(exc.code, 400)
        return JSONResponse(status_code=status, content={
            "detail": {"code": exc.code, "message": str(exc),
                       "recoverable": True, "details_ref": None,
                       "warnings": exc.warnings}})

    @app.exception_handler(local_scoring.LocalScoreError)
    async def local_score_error(request: Request, exc: local_scoring.LocalScoreError):
        from . import tool_feedback
        return JSONResponse(status_code=404 if exc.code == 'NOT_FOUND' else 409,
                            content={"detail": {"code": exc.code, "message": str(exc),
                                                "recoverable": True, "details": exc.details},
                                     'failure_feedback': tool_feedback.failure(
                                         request.url.path, str(exc), code=exc.code)})

    # ---------------- 健康 ----------------

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "mode": config.load_settings()["app"]["mode"],
                "time": db.utcnow(), 'backend': backend_identity.loaded()}

    @app.get('/api/v1/preflight')
    async def get_preflight():
        from . import preflight
        return preflight.cached()

    @app.post('/api/v1/preflight')
    async def run_preflight():
        from . import preflight
        async def connection(name):
            return await test_connection(name, ConnectionTest(kind='inspect'))
        try:
            return await preflight.run(connection, health)
        except resource_coordinator.ResourceWait as exc:
            raise HTTPException(409, detail={'code': exc.code, 'message': str(exc)}) from exc

    # ---------------- 设置与秘密 ----------------

    @app.get("/api/v1/settings")
    async def get_settings() -> dict[str, Any]:
        s = config.load_settings()
        # 仅报告项目后端配置状态；Prime 使用原生认证，绝不改写全局 CLI 配置。
        secrets_store = config.load_secrets()
        s["_status"] = {
            "secrets": {sid: True for sid in secrets_store},
            "prime_authentication": "native_unknown",
        }
        return s


    @app.put("/api/v1/settings")
    async def put_settings(body: SettingsPut) -> dict[str, Any]:
        with config.mutation_lock:
            current = config.load_settings()
            if body.base_revision != current["revision"]:
                raise HTTPException(409, detail={
                    "code": "REVISION_CONFLICT",
                    "message": "设置已被其他修改更新，请刷新后重试",
                    "current_revision": current["revision"]})
            incoming = {k: v for k, v in body.settings.items()
                        if k != "_status"}  # _status 是 GET 响应的瞬态字段，不落盘
            merged = config.merge_settings(current, incoming)
            for path in body.replace_paths:
                if path not in ('model_pricing', 'bohrium.host_overrides'):
                    raise HTTPException(422, detail={'message': '不支持替换此配置路径'})
                source, destination = incoming, merged
                parts = path.split('.')
                for part in parts[:-1]:
                    if not isinstance(source.get(part), dict):
                        raise HTTPException(422, detail={'message': '替换路径缺少完整配置'})
                    source, destination = source[part], destination[part]
                if not isinstance(source.get(parts[-1]), dict):
                    raise HTTPException(422, detail={'message': '替换配置必须是完整字典'})
                destination[parts[-1]] = json.loads(json.dumps(source[parts[-1]]))
            from . import challenge_models, model_usage
            try:
                for role in ('brain', 'executor', 'reviewer', 'post_review'):
                    challenge_models.choose(role, None, merged)
                merged['solver_roster'] = challenge_models.roster(merged)
                model_usage.validate(merged.get('model_pricing', {}))
                from . import auto_harvest
                merged['harvest'] = auto_harvest.validate(merged.get('harvest', {}))
                features = merged.get('features', {})
                if not isinstance(features, dict) or any(type(value) is not bool for value in features.values()):
                    raise ValueError('功能开关必须是布尔值')
                policy = merged.get('policy', {})
                if type(policy.get('require_ended_submission', False)) is not bool or not isinstance(policy.get('allowed_submission_targets', []), list) or any(not isinstance(target, str) or not target for target in policy.get('allowed_submission_targets', [])):
                    raise ValueError('提交目标授权策略无效')
                encoded = json.dumps(incoming, ensure_ascii=False)
                if any(value in encoded for value in config.sensitive_values() if len(value) > 7):
                    raise ValueError('设置不能包含密钥值')
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(422, detail={'message': str(exc)}) from exc
            resources = merged.get('resources', {})
            providers = resources.get('provider_sessions', {}) if isinstance(resources, dict) else None
            if not isinstance(providers, dict) or any(type(v) is not int or v < 1 for v in providers.values()):
                raise HTTPException(422, detail={'message': '提供方会话上限须为正整数'})
            for key in ('max_concurrent_jobs', 'max_concurrent_sandboxes'):
                value = resources.get(key)
                if value is not None and (type(value) is not int or value < 1):
                    raise HTTPException(422, detail={'message': '全局算力并发上限须为正整数或留空'})
            limit = (merged.get("run_defaults") or {}).get("max_active_runs")
            if type(limit) is not int or not 1 <= limit <= 20:
                raise HTTPException(422, detail={"code": "INVALID_SETTINGS",
                                                 "message": "max_active_runs 必须为 1–20 的整数"})
            for key, lower, upper in (("stall_seconds", 1, 86400),
                                      ("max_brain_wait_seconds", 1, 86400),
                                      ("brain_review_timeout_seconds", 1, 86400),
                                      ("rate_limit_max_seconds", 1, 86400)):
                value = (merged.get("run_defaults") or {}).get(key,
                    config.DEFAULT_SETTINGS["run_defaults"][key])
                if type(value) is not int or not lower <= value <= upper:
                    raise HTTPException(422, detail={"code": "INVALID_SETTINGS",
                                                     "message": f"{key} 必须为 {lower}–{upper} 的整数"})
            merged["revision"] = current["revision"] + 1
            config.save_settings(merged)
        return merged


    @app.post("/api/v1/secrets")
    async def put_secret(body: SecretPut) -> dict[str, Any]:
        if not body.secret_id or any(c in body.secret_id for c in "/\\: \t"):
            raise HTTPException(422, detail={"code": "INVALID_SECRET_ID",
                                             "message": "secret_id 含非法字符"})
        config.update_secret(body.secret_id, body.value)
        return {"secret_ref": f"local:{body.secret_id}", "configured": True,
                "prime_authentication": "native_unknown"}

    @app.delete("/api/v1/secrets/{secret_id}")
    async def delete_secret(secret_id: str) -> dict[str, Any]:
        config.update_secret(secret_id, None)
        return {"secret_ref": f"local:{secret_id}", "configured": False,
                "prime_authentication": "native_unknown"}

    # ---------------- 连接测试 ----------------


    @app.post("/api/v1/connections/{conn_id}/test",
              )
    async def test_connection(conn_id: str, body: ConnectionTest) -> dict[str, Any]:
        settings = config.load_settings()
        if body.kind in ("tool_call_probe", "connectivity_probe"):
            if conn_id not in ('brain', 'executor', 'reviewer', 'post_review'):
                raise HTTPException(422, detail={'message': '未知模型角色'})
            if not body.confirm_spend:
                raise HTTPException(403, detail={'message': '真实工具探针需显式一次模型调用授权'})
            from . import model_probe
            try:
                if body.kind == 'connectivity_probe' and conn_id not in ('brain', 'executor'):
                    raise ValueError('联网探针只适用于PI和求解者')
                return await model_probe.run(controller, conn_id, body.model_choice,
                    connectivity=body.kind == 'connectivity_probe')
            except Exception as exc:
                return {'status': 'unavailable', 'detail': observation.strip_secrets(str(exc))}
        if body.kind == "model_selection":
            if conn_id not in ("brain", "executor", "reviewer", "post_review"):
                raise HTTPException(422, detail={"code": "INVALID_CONNECTION",
                                                 "message": "只支持四个模型角色检查"})
            from tempfile import TemporaryDirectory
            from . import challenge_models
            try:
                selected = challenge_models.choose(conn_id, body.model_choice, settings)
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(422, detail={"code": "INVALID_MODEL_CONFIG",
                                                 "message": str(exc)}) from exc
            probe_settings = json.loads(json.dumps(settings))
            probe_settings["app"]["mode"] = "connected"
            if probe_settings[conn_id].get("runtime") != selected["runtime"]:
                probe_settings[conn_id]["executable"] = ""
            probe_settings[conn_id].update(selected)
            if conn_id in ('reviewer', 'post_review'):
                probe_settings['brain'] = probe_settings[conn_id]
            runtime = (controller._make_brain(probe_settings) if conn_id != "executor"
                       else controller._make_prime(probe_settings))
            health = await runtime.inspect()
            if not health.installed:
                return {"status": "unavailable", "detail": health.detail,
                        "model": selected["model_id"]}
            try:
                with TemporaryDirectory(prefix="model-check-", dir=config.DATA_DIR) as cwd:
                    if conn_id != "executor":
                        session = await runtime.open({"working_directory": cwd})
                        await runtime.close(session)
                    else:
                        session_id = await runtime.start({"working_directory": cwd})
                        await runtime.close(session_id)
            except Exception as exc:
                return {"status": "unavailable", "model": selected["model_id"],
                        "detail": "模型会话验证失败：" + observation.strip_secrets(
                            f"{type(exc).__name__}: {str(exc)[:180]}")}
            return {"status": "ok", "model": selected["model_id"],
                    "detail": "原生会话接受所选模型；未发起模型 turn"}
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
            import re
            import shutil
            import subprocess

            bohrium = settings["bohrium"]
            configured_exe = bohrium["executable"]
            exe = (shutil.which(configured_exe) if configured_exe
                   else shutil.which("bohr")) or configured_exe
            if not exe or not os.path.exists(exe):
                return {"status": "unavailable",
                        "detail": "bohr CLI 未安装或未配置；科学计算不可用",
                        "health": {"installed": False, "authenticated": None,
                                   "detail": "bohr CLI 未安装或未配置；科学计算不可用",
                                   "version": None, "capabilities": {}}}
            # bohr 1.1.0 使用 version / project list，无 auth whoami。
            # 密钥只传给后端子进程；兼容旧 CLI 的 ACCESS_KEY 名称。
            env = os.environ.copy()
            access_key = config.resolve_secret(bohrium.get("access_key_secret_ref", ""))
            access_key = access_key or env.get("BOHR_ACCESS_KEY") or env.get("ACCESS_KEY")
            if access_key:
                env["BOHR_ACCESS_KEY"] = env["ACCESS_KEY"] = access_key
            env.update(compute.client_host_overrides(bohrium, wenyon=False))

            def _bohr(args: list[str]) -> subprocess.CompletedProcess:
                cmd = (["cmd", "/c", exe, *args]
                       if exe.lower().endswith((".cmd", ".bat"))
                       else [exe, *args])
                return subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=30, shell=False, env=env)
            version: str | None = None
            authenticated: bool | None = None
            detail_parts: list[str] = []
            try:
                vp = await asyncio.to_thread(_bohr, ["version"])
                # CLI 联网错误可能带 accessKey URL；只返回版本号，不回显原文。
                for line in vp.stdout.splitlines():
                    if re.fullmatch(r"v?\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9._-]+)?",
                                    line.strip()):
                        version = line.strip()
                        break
            except (OSError, subprocess.TimeoutExpired):
                pass
            try:
                wp = await asyncio.to_thread(_bohr, ["project", "list", "--json"])
                projects = json.loads(wp.stdout) if wp.returncode == 0 else None
                if isinstance(projects, list) and all(
                    isinstance(project, dict) and "projectId" in project
                    for project in projects
                ):
                    authenticated = True
                    detail_parts.append("AccessKey 已认证（只读项目列表成功）")
                    project_id = bohrium.get("project_id")
                    if project_id is not None and not any(
                        str(project["projectId"]) == str(project_id) for project in projects
                    ):
                        detail_parts.append("配置的项目不在可访问列表中；请检查项目 ID")
                else:
                    detail_parts.append("项目列表读取失败；认证状态未知，请检查 AccessKey 与网络")
            except (ValueError, TypeError):
                detail_parts.append("项目列表响应格式未知；无法确认认证")
            except (OSError, subprocess.TimeoutExpired):
                detail_parts.append("认证探针不可用或超时；认证状态未知")
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
        from . import challenge_models
        try:
            supplied = body.models or {}
            if not isinstance(supplied, dict):
                raise ValueError("模型配置必须为对象")
            defaults = config.load_settings()
            models = {role: challenge_models.choose(role, supplied.get(role), defaults)
                      for role in ("brain", "executor")}
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, detail={"code": "INVALID_MODEL_CONFIG",
                                             "message": str(exc)}) from exc
        def save_models(cid: str) -> None:
            db.execute("UPDATE challenges SET brain_config_json=?,executor_config_json=?"
                       " WHERE id=?", (json.dumps(models["brain"]),
                                        json.dumps(models["executor"]), cid))
        if body.mode == "demo":
            cid = "DEMO_CHALLENGE"
            existing = db.query_one("SELECT id FROM challenges WHERE id=?", (cid,))
            if existing:
                if body.models is not None:
                    save_models(cid)
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
            save_models(cid)
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
            save_models(cid)
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
                if body.models is not None:
                    save_models(existing["id"])
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
            platform_snapshot = {key: data.get(key) for key in (
                "status", "roundStartAt", "roundEndAt", "scoring")}
            platform_snapshot["fetched_at"] = db.utcnow()
            db.execute(
                "INSERT INTO challenges(id, platform_challenge_id, origin, title,"
                " content, content_hash, contract_status, imported_at, is_demo,"
                " resources_json, platform_snapshot_json)"
                " VALUES(?,?,?,?,?,?,'unknown',?,0,?,?)",
                (cid, slug, body.url, title, content,
                 hashlib.sha256(content.encode()).hexdigest(), db.utcnow(),
                 json.dumps(resources, ensure_ascii=False)
                 if isinstance(resources, list) else None,
                 json.dumps(platform_snapshot, ensure_ascii=False)))
            save_models(cid)
            if isinstance(resources, list):
                from . import datasets
                datasets.register_resources(cid, resources)
            return {"challenge": _challenge_dict(cid)}
        raise HTTPException(422, detail={"code": "INVALID_IMPORT",
                                         "message": f"未知导入模式: {body.mode}"})

    def _challenge_dict(cid: str) -> dict[str, Any]:
        row = db.query_one("SELECT * FROM challenges WHERE id=?", (cid,))
        if not row:
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "题目不存在"})
        result = dict(row)
        result["platform_snapshot"] = json.loads(result.pop("platform_snapshot_json") or "null")
        from . import challenge_models
        result["model_config"] = challenge_models.from_challenge(row, config.load_settings())
        result.pop("brain_config_json", None)
        result.pop("executor_config_json", None)
        return result

    @app.get("/api/v1/challenges")
    async def list_challenges() -> dict[str, Any]:
        rows = db.query("SELECT id, platform_challenge_id, origin, title,"
                        " contract_status, imported_at, is_demo"
                        " FROM challenges ORDER BY imported_at DESC")
        return {"items": [dict(r) for r in rows]}

    @app.get("/api/v1/challenges/{cid}")
    async def get_challenge(cid: str) -> dict[str, Any]:
        return _challenge_dict(cid)

    @app.put("/api/v1/challenges/{cid}/models")
    async def put_challenge_models(cid: str, body: ChallengeModelsPut) -> dict[str, Any]:
        _require_challenge(cid)
        from . import challenge_models
        try:
            settings = config.load_settings()
            choices = {role: challenge_models.choose(role, body.models.get(role), settings)
                       for role in ("brain", "executor")}
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, detail={"code": "INVALID_MODEL_CONFIG",
                                             "message": str(exc)}) from exc
        db.execute("UPDATE challenges SET brain_config_json=?,executor_config_json=? WHERE id=?",
                   (json.dumps(choices["brain"]), json.dumps(choices["executor"]), cid))
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
        with config.mutation_lock:
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

    @app.post('/api/v1/rounds/import')
    async def import_round(body: RoundImport):
        from . import competition
        try:
            return await asyncio.to_thread(competition.import_round, **body.model_dump())
        except (ValueError, compute.ComputeError) as exc:
            raise HTTPException(422, detail={'message': str(exc)}) from exc

    @app.get('/api/v1/rounds')
    async def list_rounds():
        return {'items': [dict(r) for r in db.query("SELECT id,label,status,created_at FROM eval_runs"
                                                   " WHERE suite='competition' ORDER BY created_at DESC")]}

    @app.get('/api/v1/rounds/{round_id}')
    async def read_round(round_id: str):
        from . import competition
        try: return competition.get_round(round_id)
        except ValueError as exc: raise HTTPException(404, detail={'message': str(exc)}) from exc

    @app.post('/api/v1/rounds/{round_id}/triage')
    async def triage_round(round_id: str, body: RoundTriage):
        from . import competition
        try: return await competition.triage(round_id, controller, body.allow_model_calls)
        except ValueError as exc: raise HTTPException(422, detail={'message': str(exc)}) from exc

    @app.post('/api/v1/rounds/{round_id}/confirm')
    async def confirm_round(round_id: str, body: RoundConfirm):
        from . import competition
        try: return competition.confirm(round_id, **body.model_dump())
        except ValueError as exc: raise HTTPException(422, detail={'message': str(exc)}) from exc

    @app.post('/api/v1/rounds/{round_id}/runs')
    async def append_round_run(round_id: str, body: RoundAppend):
        from . import competition
        try: return competition.append_run(round_id, **body.model_dump())
        except ValueError as exc: raise HTTPException(422, detail={'message': str(exc)}) from exc

    @app.put('/api/v1/rounds/{round_id}/items/{item_id}')
    async def update_round_item(round_id: str, item_id: str, body: RoundItemPut):
        from . import competition
        try: return competition.update_item(round_id, item_id, **body.model_dump())
        except ValueError as exc: raise HTTPException(422, detail={'message': str(exc)}) from exc

    @app.post('/api/v1/evals')
    async def create_evaluation(body: EvaluationCreate) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(evaluations.create_evaluation,
                                           body.suite, body.repeats, body.label)
        except evaluations.EvaluationError as exc:
            raise HTTPException(422, detail={'code': 'INVALID_EVALUATION',
                                             'message': str(exc)}) from exc

    @app.get('/api/v1/evals')
    async def list_evaluations() -> dict[str, Any]:
        return {'items': evaluations.list_evaluations()}

    @app.get('/api/v1/evals/{eval_id}')
    async def get_evaluation(eval_id: str) -> dict[str, Any]:
        try:
            return evaluations.get_evaluation(eval_id)
        except evaluations.EvaluationError as exc:
            raise HTTPException(404, detail={'code': 'NOT_FOUND', 'message': str(exc)}) from exc

    @app.get('/api/v1/evals/{eval_id}/report')
    async def get_evaluation_report(eval_id: str) -> dict[str, Any]:
        try:
            return evaluations.report(eval_id)
        except evaluations.EvaluationError as exc:
            raise HTTPException(404, detail={'code': 'NOT_FOUND', 'message': str(exc)}) from exc


    @app.post("/api/v1/runs")
    async def create_run(body: RunCreate) -> dict[str, Any]:
        return controller.create_run(body.challenge_id, body.mode,
                                     body.shadow_enabled)

    @app.get("/api/v1/runs")
    async def list_runs() -> dict[str, Any]:
        return {"items": controller.list_runs()}

    @app.get("/api/v1/runs/overview")
    async def active_run_overview() -> dict[str, Any]:
        return {"items": controller.active_overview()}

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        return controller.run_snapshot(run_id)


    @app.post("/api/v1/runs/{run_id}/authorize")
    async def authorize(run_id: str, body: AuthorizeBody) -> dict[str, Any]:
        return controller.authorize(run_id, body.scope, body.allow_model_calls,
                                    body.max_model_turns, body.max_run_minutes,
                                    body.max_submissions, body.note,
                                    max_jobs=body.max_jobs, job_limits=body.job_limits,
                                    allow_data_download=body.allow_data_download,
                                    max_sandboxes=body.max_sandboxes,
                                    max_sandbox_minutes=body.max_sandbox_minutes,
                                    allow_sandbox_gpu=body.allow_sandbox_gpu,
                                    max_compute_cost_cny=body.max_compute_cost_cny,
                                    max_environment_saves=body.max_environment_saves,
                                    unlimited_resources=body.unlimited_resources,
                                    objective=body.objective)

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

    @app.post("/api/v1/runs/{run_id}/pending-intent/drop")
    async def drop_pending_intent(run_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        return controller.drop_pending_intent(run_id, body.get("reason", "用户放弃该意图"))


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
                    run = db.query_one("SELECT phase FROM runs WHERE id=?", (run_id,))
                    if not run or run['phase'] in ('finished', 'failed', 'cancelled'):
                        return  # All pages drained; completed Run history is finite.
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(1.0)
                else:
                    await asyncio.sleep(0)  # Drain large histories without a second per page.

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
               "report_md": body.report, "evidence_refs": body.evidence_refs,
               "experience_uses":body.experience_uses}
        if body.research_summary_md is not None:
            msg["research_summary_md"] = body.research_summary_md
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

    def _tool_auth(request: Request, role: str | None = "executor") -> dict[str, Any]:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        row = collab.validate_token(token)
        if not row:
            raise HTTPException(status_code=401, detail={
                "code": "INVALID_TOKEN",
                "message": "能力令牌无效/过期/已撤销"})
        if role is not None and row["role"] != role:
            raise HTTPException(status_code=403, detail={
                "code": "WRONG_ROLE", "message": "此能力令牌不能调用该工具"})
        return row

    @app.exception_handler(compute.ComputeError)
    async def compute_error(request: Request, exc: compute.ComputeError):
        from . import tool_feedback
        return JSONResponse(status_code=409, content={"detail": {"code": exc.code, "message": str(exc),
                                                         "details": exc.details},
            'failure_feedback': tool_feedback.failure(request.url.path, exc.details or str(exc),
                code=exc.code, remote_effect=exc.details.get('possible_remote_effect', 'none'),
                operation_id=getattr(request.state, 'operation_id', None))})

    @app.exception_handler(datasets.DataError)
    async def data_error(_: Request, exc: datasets.DataError):
        return JSONResponse(status_code=409, content={"detail": {"code": exc.code, "message": str(exc)}})

    @app.get("/api/v1/challenges/{challenge_id}/data")
    async def list_challenge_data(challenge_id: str) -> dict:
        return datasets.status(challenge_id)

    @app.post("/api/v1/runs/{run_id}/data/materialize")
    async def materialize_data(run_id: str, request: Request) -> dict:
        run = db.query_one("SELECT challenge_id FROM runs WHERE id=?", (run_id,))
        if not run:
            raise datasets.DataError("NOT_FOUND", "Run 不存在")
        body = await request.json()
        return await asyncio.to_thread(datasets.materialize,
            run["challenge_id"], body.get("resource_key", ""), body.get("operation_id", ""), run_id)

    @app.post("/api/v1/tools/data")
    async def tool_data(request: Request) -> dict:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        identity = collab.validate_token(token)
        if not identity:
            raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN"})
        run = db.query_one("SELECT challenge_id FROM runs WHERE id=?", (identity["run_id"],))
        body = await request.json()
        if body.get("action") in ("list", "status"):
            return datasets.status(run["challenge_id"])
        if body.get("action") == "request":
            return await asyncio.to_thread(datasets.materialize, run["challenge_id"],
                body.get("resource_key", ""), body.get("operation_id", ""), identity["run_id"])
        raise datasets.DataError("INVALID_ACTION", "支持 list/status/request")

    @app.post("/api/v1/tools/bohr")
    async def tool_bohr(request: Request) -> dict:
        identity = _tool_auth(request)
        body = await request.json()
        args = body.get('args') or []
        if isinstance(args, list) and '--cs-operation-id' in args:
            index = args.index('--cs-operation-id')
            request.state.operation_id = args[index + 1] if index + 1 < len(args) else None
        result = await asyncio.to_thread(compute.cli, identity["run_id"], body.get("args"), body.get("cwd", ""))
        controller.notify_run_change(identity["run_id"])
        from . import tool_feedback
        return tool_feedback.attach(identity['run_id'], 'bohr', result)

    @app.post('/api/v1/tools/sandbox')
    async def tool_sandbox(request: Request) -> dict:
        identity = _tool_auth(request)
        result = await asyncio.to_thread(sandboxes.dispatch, identity['run_id'], await request.json())
        controller.notify_run_change(identity['run_id'])
        from . import tool_feedback
        return tool_feedback.attach(identity['run_id'], 'sandbox', result)

    @app.get('/api/v1/runs/{run_id}/sandboxes')
    async def run_sandboxes(run_id: str) -> dict:
        return sandboxes.list_run(run_id)

    @app.post('/api/v1/runs/{run_id}/sandboxes/{sandbox_id}/delete')
    async def run_sandbox_delete(run_id: str, sandbox_id: str) -> dict:
        result = await asyncio.to_thread(sandboxes.delete, run_id, sandbox_id)
        controller.notify_run_change(run_id)
        return result

    @app.post('/api/v1/tools/environment')
    async def save_environment(request: Request):
        from . import environment_saves
        identity = _tool_auth(request)
        body = await request.json()
        request.state.operation_id = body.get('operation_id')
        from . import environment_catalog
        if environment_catalog.enabled():
            try:
                if body.get('action') == 'list': return {'items': environment_catalog.items(), 'choice': environment_catalog.current(identity['run_id'])}
                if body.get('action') == 'restore': return environment_catalog.prepare(identity['run_id'], body.get('entry_id'), body.get('reason_md', ''))
                if body.get('action') == 'observe_smoke': return environment_catalog.observe_smoke(identity['run_id'], body.get('operation_id'))
                if body.get('action') == 'from_zero': return environment_catalog.choose(identity['run_id'], {'mode': 'from_zero', 'reason_md': body.get('reason_md')}, source='prime')
            except ValueError as exc:
                raise HTTPException(422, detail={'message': str(exc)}) from exc
        if body.get('action') == 'record_smoke':
            from . import planning
            return await asyncio.to_thread(planning.register_smoke, identity['run_id'],
                                           body.get('operation_id'), body.get('recipe'))
        if body.get('action') == 'save':
            return await asyncio.to_thread(environment_saves.save, identity['run_id'], body.get('operation_id'), body.get('dockerfile'), body.get('recipe'), body.get('smoke_command'))
        if body.get('action') == 'reconcile':
            owned = db.query_one('SELECT run_id FROM environment_saves WHERE operation_id=?', (body.get('operation_id'),))
            if not owned or owned['run_id'] != identity['run_id']:
                raise compute.ComputeError('NOT_OWNED', '环境未登记在本 Run')
            return await asyncio.to_thread(environment_saves.reconcile, body['operation_id'])
        if body.get('action') == 'list':
            return {'items': environment_saves.saves()}
        raise compute.ComputeError('INVALID_ACTION', '支持 save/reconcile/list/record_smoke')

    @app.get('/api/v1/environment-catalog')
    async def environment_catalog_list():
        from . import environment_catalog
        return {'enabled': environment_catalog.enabled(), 'items': environment_catalog.items()}

    @app.post("/api/v1/tools/job")
    async def tool_job(request: Request) -> dict:
        identity = _tool_auth(request)
        body = await request.json()
        rid = identity["run_id"]
        action = body.get("action")
        request.state.operation_id = body.get('operation_id')
        if action == "submit":
            result = await asyncio.to_thread(compute.submit, rid, body.get("operation_id"),
                                             body.get("spec"), body.get("input_directory", ""),
                                             body.get("preflight"))
        elif action == "reconcile":
            result = await job_recovery.reconcile(rid, controller)
        elif action == "stop":
            result = await asyncio.to_thread(compute.stop, rid, body.get("operation_id"))
        elif action == "list":
            result = compute.list_jobs(rid)
        else:
            raise compute.ComputeError("INVALID_ACTION", "支持 submit/list/reconcile/stop")
        controller.notify_run_change(rid)
        from . import tool_feedback
        return tool_feedback.attach(rid, 'job.' + str(action), result)

    @app.post('/api/v1/tools/package_review')
    async def tool_package_review(request: Request):
        from . import package_reviews
        identity = _tool_auth(request, role='brain')
        body = await request.json()
        try:
            return await package_reviews.review(controller, identity['run_id'], body.get('trial_id'), body.get('operation_id'), body.get('package_path'))
        except ValueError as exc:
            raise HTTPException(409, detail={'message': observation.strip_secrets(str(exc)), 'advisory_only': True}) from exc

    @app.get('/api/v1/runs/{run_id}/package-reviews')
    async def run_package_reviews(run_id: str):
        from . import package_reviews
        controller._require_run(run_id)
        return {'items': [package_reviews.get(r['operation_id'], run_id) for r in db.query('SELECT operation_id FROM package_reviews WHERE run_id=? ORDER BY created_at', (run_id,))]}

    @app.post('/api/v1/tools/trace_variant')
    async def tool_trace_variant(request: Request):
        identity = _tool_auth(request, role='brain')
        body = await request.json()
        source = db.query_one('SELECT run_id FROM submissions WHERE id=?', (body.get('source_submission_id'),))
        if not source or source['run_id'] != identity['run_id']:
            raise HTTPException(403, detail={'message': '只能为本 Run 的提交发起变体'})
        result = await mailboxes.submit_async(mailboxes.submit_trace_variant,
            body.get('source_submission_id'), body.get('operation_id', ''), body.get('prediction_md'),
            projection_only=body.get('projection_only', False), narrative_jsonl=body.get('narrative_jsonl'),
            narrative_written_at=body.get('narrative_written_at'))
        controller.notify_run_change(identity['run_id'])
        return result

    @app.get('/api/v1/challenges/{challenge_id}/shared')
    async def challenge_shared(challenge_id: str):
        from . import shared_artifacts
        return await asyncio.to_thread(shared_artifacts.catalog, challenge_id)

    @app.get('/api/v1/platform-contracts')
    async def platform_contract_status():
        from . import platform_contracts
        return await asyncio.to_thread(platform_contracts.describe)

    @app.get('/api/v1/protocol-drift')
    async def get_protocol_drift():
        from . import protocol_drift
        return protocol_drift.facts()

    @app.post('/api/v1/protocol-drift/check')
    async def check_protocol_drift():
        from . import protocol_drift
        return await asyncio.to_thread(protocol_drift.check)

    @app.post('/api/v1/platform-contracts/refresh')
    async def platform_contract_refresh():
        from . import platform_contracts
        try:
            return await asyncio.to_thread(platform_contracts.refresh)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, detail={'message': observation.strip_secrets(str(exc))[:400]}) from exc

    @app.post('/api/v1/tools/shared')
    async def tool_shared(request: Request):
        from . import shared_artifacts
        identity = _tool_auth(request, role=None)
        body = await request.json(); action = body.get('action')
        run = controller._require_run(identity['run_id'])
        try:
            if action == 'list':
                if identity['role'] not in ('brain', 'executor'): raise ValueError('仅PI与执行器可查看共享区')
                return await asyncio.to_thread(shared_artifacts.catalog, run['challenge_id'])
            if identity['role'] != 'executor':
                raise HTTPException(403, detail={'message': '仅执行器可发布/导入，不能修改正式验证器'})
            if action == 'publish':
                return await asyncio.to_thread(shared_artifacts.publish, run['id'], body.get('trial_id'), body.get('name'), body.get('source_path'), body.get('source_event_seq'))
            if action == 'import':
                return await asyncio.to_thread(shared_artifacts.import_artifact, run['id'], body.get('trial_id'), body.get('artifact_id'))
            raise ValueError('支持list/publish/import')
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, detail={'message': observation.strip_secrets(str(exc))[:400]}) from exc

    @app.post("/api/v1/tools/package_check")
    async def tool_package_check(request: Request) -> dict:
        identity = _tool_auth(request)
        body = await request.json()
        result = await asyncio.to_thread(mailboxes.preflight_submission,
            identity["run_id"], body.get("trial_id"), body.get("package_path"))
        result.pop("sealed_bytes", None)
        result.pop("projected_steps", None)
        result["trace_diagnostics"] = trace_diagnostics.executor_view(result["trace_diagnostics"])
        return result

    @app.post("/api/v1/tools/trace_narrative_check")
    async def tool_trace_narrative_check(request: Request) -> dict:
        identity = _tool_auth(request, role=None)
        body = await request.json()
        return await asyncio.to_thread(mailboxes.inspect_trace_narrative,
            identity["run_id"], body.get("trial_id"), body.get("package_path"))

    @app.post('/api/v1/tools/experience')
    async def tool_experience(request: Request):
        from . import experience_context
        import uuid
        identity = _tool_auth(request, role=None)
        body = await request.json()
        run = db.query_one('SELECT challenge_id,current_trial_id FROM runs WHERE id=?', (identity['run_id'],))
        entries = experience_context.effective(run['challenge_id'])
        if body.get('action') == 'list':
            return {'index': experience_context.index(run['challenge_id'], entries=entries)}
        if body.get('action') != 'read':
            raise HTTPException(409, detail={'code': 'INVALID_ACTION'})
        entry = next((entry for entry in entries if entry['id'] == body.get('experience_id')), None)
        if not entry:
            raise HTTPException(404, detail={'code': 'EXPERIENCE_UNAVAILABLE'})
        context = experience_context.freeze(identity['run_id'], run['current_trial_id'], 'read:' + uuid.uuid4().hex, items=[entry])
        return {'entry': entry, 'context_id': context['id'], 'revision_id': entry['revision_id'], 'semantics': 'latest_registered_active'}

    @app.post('/api/v1/tools/operating_facts')
    async def tool_operating_facts(request: Request) -> dict:
        from . import runtime_facts
        identity = _tool_auth(request, role=None)
        return await asyncio.to_thread(runtime_facts.facts, identity['run_id'])

    @app.post("/api/v1/tools/local_score")
    async def tool_local_score(request: Request) -> dict:
        from . import local_scoring, executor_scoring
        identity = _tool_auth(request)
        body = await request.json()
        action = body.get('action', 'evaluate')
        if action == 'prepare_job':
            return await asyncio.to_thread(executor_scoring.prepare, identity['run_id'], body.get('trial_id'), body.get('operation_id'), 'job', body.get('package_path'), body.get('environment_paths'), channel='job')
        if action == 'register_job':
            return await asyncio.to_thread(executor_scoring.register_job, identity['run_id'], body.get('trial_id'), body.get('operation_id'), body.get('execution_operation_id'))
        if action == 'prepare':
            return await asyncio.to_thread(executor_scoring.prepare,
                identity['run_id'], body.get('trial_id'), body.get('operation_id'),
                body.get('sandbox_id'), body.get('package_path'), body.get('environment_paths'))
        if action == 'register':
            return await asyncio.to_thread(executor_scoring.register,
                identity['run_id'], body.get('trial_id'), body.get('operation_id'),
                body.get('execution_operation_id'))
        if action != 'evaluate':
            raise local_scoring.LocalScoreError('INVALID_ACTION', '支持 evaluate/prepare/register')
        return await asyncio.to_thread(local_scoring.evaluate,
            identity['run_id'], body.get('trial_id'), body.get('sandbox_id'),
            body.get('operation_id'), body.get('package_path'))

    @app.post('/api/v1/tools/public_research')
    async def tool_public_research(request: Request) -> dict:
        from . import public_research
        identity = _tool_auth(request, role=None)
        if identity['role'] not in ('brain', 'executor'):
            raise HTTPException(403, detail={'message': '仅PI与执行器可公开检索'})
        body = await request.json(); name = body.get('tool')
        if name not in public_research.FUNCTIONS:
            raise HTTPException(422, detail={'message': '不支持的公开检索工具'})
        try:
            result = await asyncio.to_thread(public_research.FUNCTIONS[name], body.get('url' if name == 'research_web_read' else 'query'))
        except (ValueError, OSError) as exc:
            raise HTTPException(422, detail={'message': observation.strip_secrets(str(exc))[:300]}) from exc
        db.append_event(identity['run_id'], identity['role'], 'research.public_read', {
            'tool': name, 'status': result['status'], 'source': result.get('source'), 'sha256': result.get('sha256'),
            'http_status': result.get('http_status'), 'business_code': result.get('business_code')})
        return result

    @app.get("/api/v1/challenges/{challenge_id}/local-scores")
    async def challenge_local_scores(challenge_id: str) -> dict:
        from . import local_scoring
        return await asyncio.to_thread(local_scoring.list_challenge, challenge_id)

    @app.post("/api/v1/runs/{run_id}/local-scores")
    async def run_local_score(run_id: str, request: Request) -> dict:
        from . import local_scoring
        body = await request.json()
        return await asyncio.to_thread(local_scoring.evaluate,
            run_id, body.get('trial_id'), body.get('sandbox_id'),
            body.get('operation_id'), body.get('package_path'))

    @app.get("/api/v1/runs/{run_id}/jobs")
    async def run_jobs(run_id: str) -> dict:
        return compute.list_jobs(run_id)

    @app.post("/api/v1/runs/{run_id}/jobs/reconcile")
    async def reconcile_jobs(run_id: str) -> dict:
        return await job_recovery.reconcile(run_id, controller)

    @app.post("/api/v1/runs/{run_id}/jobs/{operation_id}/resolve-local-parse")
    async def resolve_local_job_parse(run_id: str, operation_id: str) -> dict:
        return await asyncio.to_thread(
            compute.resolve_local_parse_failure, run_id, operation_id)

    @app.post("/api/v1/runs/{run_id}/jobs/{operation_id}/stop")
    async def stop_job(run_id: str, operation_id: str) -> dict:
        return await asyncio.to_thread(compute.stop, run_id, operation_id)

    @app.post("/api/v1/runs/{run_id}/curation")
    async def curate_run(run_id: str, request: Request) -> dict:
        body = await request.json()
        return await controller.curate_run_experience(run_id, body.get("operation_id", ""))

    @app.get("/api/v1/runs/{run_id}/curation")
    async def run_curation(run_id: str) -> dict:
        return controller.run_curation_status(run_id)

    @app.get('/api/v1/runs/{run_id}/post-review')
    async def run_post_review(run_id: str) -> dict:
        controller._require_run(run_id)
        row = db.query_one('SELECT status,reason,report_path,error,updated_at FROM run_post_reviews WHERE run_id=?', (run_id,))
        result = dict(row) if row else {'status': 'idle'}
        if row and row['report_path']:
            path = config.WORKSPACE_DIR / row['report_path']
            if path.is_file():
                result['report_md'] = path.read_text(encoding='utf-8')
        result['versions'] = []
        for item in db.query('SELECT id,version,status,reason,report_path,error,calls_used,native_call_limit,updated_at FROM run_post_review_versions WHERE run_id=? ORDER BY version', (run_id,)):
            version = dict(item)
            if item['report_path']:
                path = (config.WORKSPACE_DIR / item['report_path']).resolve()
                if path.is_relative_to(config.WORKSPACE_DIR.resolve()) and path.is_file(): version['report_md'] = path.read_text(encoding='utf-8')
            result['versions'].append(version)
        return result

    @app.post('/api/v1/runs/{run_id}/post-review')
    async def repeat_post_review(run_id: str, request: Request) -> dict:
        from . import maintenance
        body = await request.json()
        if not isinstance(body, dict): raise HTTPException(422, '复盘请求必须为对象')
        try:
            row = maintenance.grant_post_review(controller, run_id, body.get('operation_id', ''),
                allow_model_calls=body.get('allow_model_calls'), reason=body.get('reason', ''),
                max_format_rewrites=body.get('max_format_rewrites', 0))
        except ValueError as exc: raise HTTPException(400, str(exc)) from exc
        if row['status'] == 'pending': maintenance.schedule(maintenance.run_post_review(controller, run_id, review_id=row['id']))
        return {'id': row['id'], 'version': row['version'], 'status': row['status'], 'native_call_limit': row['native_call_limit']}

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

    @app.post("/api/v1/tools/trace")
    async def tool_trace(request: Request) -> dict[str, Any]:
        identity = _tool_auth(request, role="brain")
        from . import research_trace
        try:
            return research_trace.access(identity["run_id"], await request.json())
        except research_trace.TraceError as exc:
            raise HTTPException(status_code=409, detail={
                "code": "TRACE_UNAVAILABLE", "message": str(exc)}) from exc

    @app.post('/api/v1/tools/platform_scores')
    async def tool_platform_scores(request: Request) -> dict[str, Any]:
        identity=_tool_auth(request,role='brain')
        from . import platform_scores
        return await asyncio.to_thread(platform_scores.get,identity['run_id'])

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

    @app.get("/api/v1/mailboxes/usage")
    async def mailbox_usage() -> dict[str, Any]:
        return mailboxes.mailbox_usage()

    @app.post("/api/v1/mailboxes/harvest")
    async def add_harvest(request: Request) -> dict[str, Any]:
        body = await request.json()
        return mailboxes.add_harvest(body.get("email", ""),
                                     body.get("secret", ""))

    @app.post("/api/v1/mailboxes/experiment/register")
    async def register_experiment(request: Request) -> dict[str, Any]:
        body = await request.json()
        return await asyncio.to_thread(mailboxes.register_experiment, int(body.get("count", 1)))

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
        result = await mailboxes.submit_async(mailboxes.submit_experiment,
            run_id, body.get("trial_id"), body.get("package_path"),
            body.get("operation_id", ""),
            body.get("allow_proxy_evidence", False),
            body.get("allow_indeterminate_admission", False),
            body.get("prediction_md"))
        controller.notify_run_change(run_id)
        return result

    @app.post("/api/v1/submissions/{submission_id}/trace-variants")
    async def submit_trace_variant(submission_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        result = await mailboxes.submit_async(
            mailboxes.submit_trace_variant, submission_id,
            body.get('operation_id', ''), body.get('prediction_md'),
            allow_proxy_evidence=body.get('allow_proxy_evidence', False),
            allow_indeterminate_admission=body.get('allow_indeterminate_admission', False),
            projection_only=body.get('projection_only', False), narrative_jsonl=body.get('narrative_jsonl'),
            narrative_written_at=body.get('narrative_written_at'))
        controller.notify_run_change(result['run_id'])
        return result

    @app.post("/api/v1/submissions/{submission_id}/exact-replay")
    async def submit_exact_replay(submission_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        result = await mailboxes.submit_async(mailboxes.submit_exact_replay,
                                       submission_id, body.get('operation_id', ''),
                                       body.get('prediction_md', ''))
        controller.notify_run_change(result['run_id'])
        return result

    @app.post("/api/v1/runs/{run_id}/submissions/preflight")
    async def preflight_submission(run_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        result = await asyncio.to_thread(mailboxes.preflight_submission,
            run_id, body.get("trial_id"), body.get("package_path"),
            allow_proxy_evidence=body.get("allow_proxy_evidence", False),
            allow_indeterminate_admission=body.get("allow_indeterminate_admission", False))
        result.pop("sealed_bytes", None)
        result.pop("projected_steps", None)
        return result

    @app.post("/api/v1/submissions/poll")
    async def poll_scores(request: Request) -> dict[str, Any]:
        body = await request.json() if request.headers.get(
            "content-type", "").startswith("application/json") else {}
        # 评分平台 HTTP 是同步调用：卸载到线程，不阻塞事件循环
        result = await asyncio.to_thread(mailboxes.poll_scores, body.get("run_id"), manual=True)
        _notify_scores(result)
        return result

    # ---------------- 评分轮询任务（按题目中断/启用） ----------------

    def _notify_scores(result):
        from . import auto_harvest
        auto_harvest.reconcile_interrupted(include_running=False)
        for rid in result.get("changed_run_ids",[]):
            run = db.query_one("SELECT phase FROM runs WHERE id=?",(rid,))
            if run and run["phase"] in ('running', 'waiting_score'):
                controller.notify_run_change(rid)

    @app.get("/api/v1/polling")
    async def polling_tasks() -> dict[str, Any]:
        return mailboxes.polling_tasks()

    @app.post("/api/v1/polling/{challenge_id}")
    async def polling_toggle(challenge_id: str,
                             body: PollingToggle) -> dict[str, Any]:
        return mailboxes.set_polling_enabled(challenge_id, body.enabled)

    @app.post("/api/v1/polling/{challenge_id}/run")
    async def polling_run(challenge_id: str) -> dict[str, Any]:
        result = await asyncio.to_thread(mailboxes.poll_scores_now, challenge_id)
        _notify_scores(result)
        return result

    @app.get("/api/v1/harvest/candidates")
    async def harvest_candidates(challenge_id: str) -> dict[str, Any]:
        return mailboxes.harvest_candidates(challenge_id)

    @app.post("/api/v1/harvest/submit")
    async def harvest_submit(request: Request) -> dict[str, Any]:
        body = await request.json()
        return await mailboxes.submit_async(mailboxes.harvest_submit,
            body.get("submission_id", ""), body.get("operation_id", ""),
            body.get("confirm") is True, body.get("acknowledge_warnings") is True)

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
    async def approve_exp(exp_id: str, body: ExperienceReview) -> dict[str, Any]:
        """用户审批：全局 candidate → active（全局经验唯一晋升通道）。"""
        return experiences.approve_experience(exp_id, expected_revision=body.expected_revision)

    @app.post("/api/v1/experiences/{exp_id}/reject")
    async def reject_exp(exp_id: str, body: ExperienceReview) -> dict[str, Any]:
        """用户驳回：保持 candidate 并附批注，大脑下轮整理参考批注。"""
        return experiences.reject_experience(exp_id, body.note, expected_revision=body.expected_revision)


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
                                            body.reason, operation_id=body.operation_id)

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
