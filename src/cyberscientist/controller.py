"""RunController：进程内单活跃 Run 的研究闭环与状态机。

事件流是权威记录；控制器只追加。暂停/终止语义按 ARCHITECTURE：
只有代理确认停下才显示 paused；steer 接受不等于生效。

协作模型（docs/collaboration/SPEC.md）：
- 主循环只做短事务与调度；大脑审阅在独立单飞 worker 中执行，
  审阅期间执行器事件继续落库、控制门禁不等待大脑。
- 生命周期 Decision（run_start / 明确交付 trial_complete / 用户指导）
  与静默/请求的 ReviewResult 共用同一个大脑会话和同一个排队入口。
- 指导经持久化 outbox（guidance 表）在自然边界投递：检查点工具返回
  或已确认空闲的回合边界；一次指导只选一个渠道。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import jsonschema

from . import collab, config, db, decision as decision_mod, experiences, mailboxes, observation
from . import skills as skills_mod
from .brains.base import BrainRuntime
from .brains.codex import CodexBrain
from .brains.demo import DemoBrain
from .brains.kimi import KimiBrain
from .prime import (CodexExecutor, DemoPrime, KimiExecutor, PrimeRpc,
                    PrimeRuntime)

log = logging.getLogger("cyberscientist.controller")

PHASES = ("created", "running", "pausing", "paused", "blocked",
          "recovering", "finished", "failed", "cancelled")

# 值得触发静默观察的科学变化（心跳/进度/大脑自身输出不在内）
_SHADOW_TRIGGERS = ("checkpoint.created", "trial.reported_complete",
                    "trial.stalled", "trial.done", "prime.error")

_REVIEW_RESULT_SCHEMA: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "docs" / "collaboration" / "contract.schema.json").read_text(
         encoding="utf-8"))


def _salvage_review_result(result: Any) -> tuple[Any, list[str]]:
    """大脑输出的容错修复：格式问题就地规整/降级，返回 (result, 修复说明)。

    原则：注释性内容（watchlist）尽量修复保留；驱动动作的 guidance 格式非法时
    丢弃并把审阅降级为 silent——坏指导比没指导危险，但整张审阅不该陪葬。
    """
    if not isinstance(result, dict):
        return result, []
    fixed = dict(result)
    notes: list[str] = []
    wl = fixed.get("watchlist")
    if isinstance(wl, list):
        items: list[dict[str, Any]] = []
        for i, item in enumerate(wl):
            if len(items) >= 3:
                notes.append("watchlist 超过 3 项，多余项已截断")
                break
            if isinstance(item, str) and item.strip():
                items.append({"id": f"w{i + 1}", "hypothesis_md": item.strip()[:1000],
                              "evidence_needed_md": "（大脑未说明）",
                              "intervene_when_md": "出现反证或新证据时",
                              "evidence_refs": []})
                notes.append(f"watchlist[{i}] 字符串已包装为 Watch 对象")
            elif isinstance(item, dict):
                hypothesis = str(item.get("hypothesis_md")
                                 or item.get("hypothesis") or "").strip()
                if not hypothesis:
                    notes.append(f"watchlist[{i}] 缺 hypothesis_md，已丢弃")
                    continue
                refs = item.get("evidence_refs")
                items.append({
                    "id": (str(item.get("id") or f"w{i + 1}").strip()
                           or f"w{i + 1}")[:96],
                    "hypothesis_md": hypothesis[:1000],
                    "evidence_needed_md": str(
                        item.get("evidence_needed_md") or "（大脑未说明）")[:1000],
                    "intervene_when_md": str(
                        item.get("intervene_when_md") or "出现反证或新证据时")[:1000],
                    "evidence_refs": ([str(r)[:256] for r in refs if r][:32]
                                      if isinstance(refs, list) else []),
                })
                notes.append(f"watchlist[{i}] 字段已规整")
            else:
                notes.append(f"watchlist[{i}] 非法类型，已丢弃")
        fixed["watchlist"] = items
    return fixed, notes


class ControllerError(Exception):
    def __init__(self, code: str, message: str, recoverable: bool = True):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


def _rid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _redact(text: str | None, limit: int = 2000) -> str:
    """指导文本入库前截断并遮蔽明显密钥形态（事件库等同日志）。"""
    if not text:
        return ""
    return observation.strip_secrets(text[:limit])


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _validate_question_answer(question: dict[str, Any],
                              answers: dict[str, Any]) -> tuple[bool, str]:
    """大脑回答必须覆盖必答题且取值来自选项 const（不通过则拒收）。"""
    for q in question.get("questions", []):
        qid = q.get("id")
        if q.get("required") and qid not in answers:
            return False, f"缺必答题 {qid}"
        opts = q.get("options") or []
        consts = {str(o.get("const")) for o in opts if o.get("const") is not None}
        if consts and qid in answers and str(answers[qid]) not in consts:
            return False, f"{qid} 的值不在选项内"
    return True, ""


class RunController:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._signals: dict[str, asyncio.Queue] = {}
        self._prime_sessions: dict[str, str] = {}
        self._pumps: dict[str, asyncio.Task] = {}
        self._start_pump: dict[str, Any] = {}
        self._prime_instances: dict[str, Any] = {}
        self._demo_prime = DemoPrime()
        self._brain_sessions: dict[str, Any] = {}
        # 协作调度：审阅唤醒（内存提示，DB 为权威）与执行器忙闲镜像
        self._review_wake: dict[str, asyncio.Event] = {}
        self._review_tasks: dict[str, asyncio.Task] = {}
        self._executor_busy: dict[str, bool] = {}
        # 执行器提问（AskUserQuestion）→ 大脑回答的等待句柄：request_id → Future
        self._question_waiters: dict[str, asyncio.Future] = {}
        # 全局经验整理（手动触发、无 Run 的一次性大脑会话）状态
        self._global_curation: dict[str, Any] = {}

    # ---------- 组件工厂 ----------
    def _make_brain(self, settings: dict[str, Any]) -> BrainRuntime:
        if settings["app"]["mode"] == "demo":
            return DemoBrain()
        brain_cfg = settings["brain"]
        runtime = brain_cfg["runtime"]
        if runtime == "codex":
            return CodexBrain(executable=brain_cfg.get("executable") or None,
                              model=brain_cfg.get("model_id"),
                              effort=brain_cfg.get("reasoning_effort"))
        return KimiBrain(executable=brain_cfg.get("executable") or None,
                         model=brain_cfg.get("model_id"),
                         effort=brain_cfg.get("reasoning_effort"))

    def _make_prime(self, settings: dict[str, Any]) -> PrimeRuntime:
        """执行系统三选一：kimi（默认）/ prime / codex；demo 模式仍 DemoPrime。"""
        if settings["app"]["mode"] == "demo":
            return self._demo_prime
        exec_cfg = settings.get("executor") or {}
        runtime = exec_cfg.get("runtime", "kimi")
        if runtime == "prime":
            import shutil
            exe = settings["prime"].get("executable") \
                or shutil.which("prime-agent") or ""
            return PrimeRpc(exe)
        if runtime == "codex":
            return CodexExecutor(
                executable=exec_cfg.get("executable") or None,
                model=exec_cfg.get("model_id"),
                effort=exec_cfg.get("reasoning_effort"))
        return KimiExecutor(executable=exec_cfg.get("executable") or None,
                            model=exec_cfg.get("model_id"),
                            effort=exec_cfg.get("reasoning_effort"))

    def _prime_spec(self, run_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        """执行器启动参数：工作目录 + 运行时专有配置。"""
        import os
        run = self._require_run(run_id)
        challenge_dir = config.WORKSPACE_DIR / "challenges" / run["challenge_id"]
        challenge_dir.mkdir(parents=True, exist_ok=True)
        runtime = (settings.get("executor") or {}).get("runtime", "kimi")
        spec: dict[str, Any] = {
            "run_id": run_id,
            "working_directory": str(challenge_dir),
        }
        if runtime == "prime":
            # Prime 专有：项目隔离 session 目录 + 环境 allowlist + 模型选择
            profile = next((p for p in settings.get("llm_profiles", [])
                            if p.get("id") == settings["prime"].get("llm_profile_id")),
                           None)
            env = {k: os.environ[k] for k in
                   ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
                    "HOME", "APPDATA") if k in os.environ}
            if profile:
                value = config.resolve_secret(profile.get("secret_ref", ""))
                if value:
                    env[profile.get("env_var") or "PRIME_LLM_API_KEY"] = value
            run_dir = config.WORKSPACE_DIR / "runs" / run_id / "prime"
            run_dir.mkdir(parents=True, exist_ok=True)
            spec.update({
                "session_dir": run_dir,
                "env": env,
                "provider": (profile or {}).get("prime_provider"),
                "model": (profile or {}).get("model_id"),
            })
        if runtime == "kimi":
            # 协作工具桥：项目/会话级 MCP 注入 + 短时能力令牌（不修改全局配置）
            import sys as _sys
            with db.transaction() as conn:
                # 新会话签发前撤销本 Run 旧令牌：旧会话身份随之失效，
                #  ACK/检查点的会话绑定在令牌鉴权层成立
                collab.revoke_run_tokens(conn, run_id)
                gen = conn.execute(
                    "SELECT COUNT(*) AS n FROM capability_tokens"
                    " WHERE run_id=?", (run_id,)).fetchone()["n"] + 1
                token = collab.issue_token(conn, run_id, "executor",
                                           "executor-session", gen)
            app_cfg = settings["app"]
            spec["mcp_servers"] = [{
                "name": "cyberscientist",
                "command": _sys.executable,
                "args": ["-m", "cyberscientist.mcp_bridge"],
                "env": [
                    {"name": "CS_TOOL_TOKEN", "value": token},
                    {"name": "CS_API_URL",
                     "value": f"http://{app_cfg['host']}:{app_cfg['port']}"},
                ],
            }]
        # codex 运行时的 per-thread MCP 注入能力未经本机核实：暂缺，
        # 该运行时依靠空闲边界 prompt 投递指导（能力矩阵如实标注）
        return spec

    # ---------- Run 生命周期 ----------
    def create_run(self, challenge_id: str, mode: str | None = None,
                   shadow_enabled: bool | None = None) -> dict[str, Any]:
        settings = config.load_settings()
        mode = mode or settings["app"]["mode"]
        challenge = db.query_one("SELECT id FROM challenges WHERE id=?", (challenge_id,))
        if not challenge:
            raise ControllerError("NOT_FOUND", f"题目不存在: {challenge_id}")
        active = db.query_one(
            "SELECT id FROM runs WHERE phase IN ('created','running','pausing','paused')")
        if active:
            raise ControllerError("RUN_ACTIVE",
                                  f"已有活跃 Run {active['id']}；单工作区一次只允许一个")
        run_id = _rid("run")
        # 协作配置在创建时快照化（settings.shadow + 本次开关）
        shadow_cfg = dict(settings.get("shadow") or {})
        if shadow_enabled is not None:
            shadow_cfg["enabled"] = bool(shadow_enabled)
        snapshot = {"settings": self._redacted_settings(settings),
                    "shadow": shadow_cfg,
                    "challenge_id": challenge_id, "mode": mode}
        db.execute(
            "INSERT INTO runs(id, challenge_id, mode, phase, state_version, intention,"
            " config_snapshot, created_at) VALUES(?,?,?,?,0,NULL,?,?)",
            (run_id, challenge_id, mode, "created", json.dumps(snapshot, ensure_ascii=False),
             db.utcnow()))
        return self.run_snapshot(run_id)

    @staticmethod
    def _redacted_settings(settings: dict[str, Any]) -> dict[str, Any]:
        snap = json.loads(json.dumps(settings))
        for profile in snap.get("llm_profiles", []):
            profile.pop("secret_value", None)
        return snap

    def _shadow_cfg(self, run: Any) -> dict[str, Any]:
        snap = json.loads(run["config_snapshot"])
        cfg = dict((snap.get("shadow") or {}))
        defaults = config.DEFAULT_SETTINGS["shadow"]
        for k, v in defaults.items():
            cfg.setdefault(k, v)
        return cfg

    def authorize(self, run_id: str, scope: str, allow_model_calls: bool,
                  max_model_turns: int, max_run_minutes: int,
                  max_submissions: int, note: str | None,
                  max_jobs: int = 0) -> dict[str, Any]:
        run = self._require_run(run_id)
        if run["phase"] not in ("created", "blocked"):
            raise ControllerError("INVALID_STATE", f"当前阶段 {run['phase']} 不能授权")
        auth_id = _rid("auth")
        db.execute(
            "INSERT INTO authorizations(id, run_id, scope, allow_model_calls,"
            " max_model_turns, max_run_minutes, max_submissions, max_jobs,"
            " granted_at, note)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (auth_id, run_id, scope, int(allow_model_calls), max_model_turns,
             max_run_minutes, max_submissions, max_jobs, db.utcnow(), note))
        db.execute("UPDATE runs SET authorization_id=?, block_reason=NULL WHERE id=?",
                   (auth_id, run_id))
        if run["phase"] == "blocked":
            db.execute("UPDATE runs SET phase='created' WHERE id=?", (run_id,))
        db.append_event(run_id, "controller", "run.authorized",
                        {"scope": scope, "allow_model_calls": allow_model_calls})
        return {"authorization_id": auth_id}

    def update_budget(self, run_id: str, *, max_brain_reviews: int | None = None,
                      max_trials: int | None = None,
                      max_model_turns: int | None = None,
                      max_run_minutes: int | None = None,
                      max_submissions: int | None = None,
                      max_jobs: int | None = None) -> dict[str, Any]:
        """运行中提高预算：大脑/Trial 上限走实时 settings，模型/时长/提交走授权行。"""
        run = self._require_run(run_id)
        if run["phase"] in ("finished", "failed", "cancelled"):
            raise ControllerError("INVALID_STATE",
                                  f"Run 已终态 {run['phase']}，不能调整预算")
        changes: dict[str, int] = {}
        settings_keys = {"max_brain_reviews": max_brain_reviews,
                         "max_trials": max_trials}
        if any(v is not None for v in settings_keys.values()):
            settings = config.load_settings()
            for key, value in settings_keys.items():
                if value is None:
                    continue
                if value <= 0:
                    raise ControllerError("INVALID_ARGUMENT",
                                          f"{key} 必须为正整数")
                settings["run_defaults"][key] = value
                changes[key] = value
            config.save_settings(settings)
        auth_keys = {"max_model_turns": max_model_turns,
                     "max_run_minutes": max_run_minutes,
                     "max_submissions": max_submissions,
                     "max_jobs": max_jobs}
        if any(v is not None for v in auth_keys.values()):
            if not run["authorization_id"]:
                raise ControllerError("NEEDS_AUTHORIZATION",
                                      "该 Run 无授权记录，不能调整授权预算")
            for key, value in auth_keys.items():
                if value is None:
                    continue
                if value <= 0:
                    raise ControllerError("INVALID_ARGUMENT",
                                          f"{key} 必须为正整数")
                db.execute(f"UPDATE authorizations SET {key}=? WHERE id=?",
                           (value, run["authorization_id"]))
                changes[key] = value
        if not changes:
            raise ControllerError("INVALID_ARGUMENT", "未提供任何预算字段")
        db.append_event(run_id, "controller", "run.budget_updated", changes)
        return {"run_id": run_id, "updated": changes,
                "budget": self._budget_status(self._require_run(run_id))}

    async def start_async(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        if run["phase"] != "created":
            raise ControllerError("INVALID_STATE", f"当前阶段 {run['phase']} 不能启动")
        if not run["authorization_id"]:
            raise ControllerError("NEEDS_AUTHORIZATION",
                                  "先保存本轮有界授权（POST /runs/{id}/authorize）")
        settings = config.load_settings()
        prime = self._make_prime(settings)
        p_health = await prime.inspect()
        brain = self._make_brain(settings)
        b_health = await brain.inspect()

        if run["mode"] == "connected":
            problems = []
            if not b_health.installed:
                problems.append(f"大脑不可用：{b_health.detail}")
            if run["mode"] == "connected" and not p_health.installed:
                problems.append(f"执行器不可用：{p_health.detail}")
            auth = db.query_one("SELECT * FROM authorizations WHERE id=?",
                                (run["authorization_id"],))
            if auth and not auth["allow_model_calls"]:
                problems.append("授权未包含模型调用（allow_model_calls=false）")
            if problems:
                db.execute("UPDATE runs SET phase='blocked', block_reason=? WHERE id=?",
                           ("；".join(problems), run_id))
                db.append_event(run_id, "controller", "run.blocked",
                                {"reasons": problems})
                raise ControllerError("MISSING_CREDENTIAL", "；".join(problems))

        # 原子抢占：并发 start（双击）只有一个能完成 created→running 转换
        with db._db_lock:
            conn = db.get_db()
            cur = conn.execute(
                "UPDATE runs SET phase='running', started_at=? WHERE id=? AND phase='created'",
                (db.utcnow(), run_id))
            conn.commit()
            if cur.rowcount != 1:
                raise ControllerError("INVALID_STATE",
                                      f"当前阶段不能启动（并发或状态已变化）")
            other = conn.execute(
                "SELECT id FROM runs WHERE phase IN ('running','pausing','paused')"
                " AND id<>?", (run_id,)).fetchone()
            if other:
                conn.execute("UPDATE runs SET phase='created', started_at=NULL"
                             " WHERE id=?", (run_id,))
                conn.commit()
                raise ControllerError("RUN_ACTIVE", f"已有活跃 Run {other['id']}")
        db.append_event(run_id, "controller", "run.started", {
            "brain": b_health.version or brain.kind,
            "prime": p_health.version or prime.kind,
            "mode": run["mode"]})
        self._record_experience_snapshot(run_id, "at_start")
        # 监督状态行（幂等）；配置来自 Run 快照
        shadow_cfg = self._shadow_cfg(self._require_run(run_id))
        db.execute(
            "INSERT OR IGNORE INTO supervision(run_id, enabled, updated_at)"
            " VALUES(?,?,?)",
            (run_id, int(bool(shadow_cfg.get("enabled"))), db.utcnow()))
        q: asyncio.Queue = asyncio.Queue()
        self._signals[run_id] = q
        self._tasks[run_id] = asyncio.create_task(self._run_loop(run_id, q))
        return self.run_snapshot(run_id)

    async def control(self, run_id: str, action: str, text: str | None,
                      operation_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        q = self._signals.get(run_id)
        # 先完成全部校验，再落 operation_id；失败路径不消耗去重名额
        if action == "steer":
            if run["phase"] != "running":
                raise ControllerError("INVALID_STATE",
                                      f"当前阶段 {run['phase']} 不能发送指导")
            if q is None:
                raise ControllerError("RECOVERABLE",
                                      "Run 事件循环不可用；请刷新状态或重启后端恢复")
            if not db.record_operation(operation_id, run_id, f"control.{action}",
                                       "accepted",
                                       request_summary=_redact(text or action)):
                existing = db.query_one(
                    "SELECT status FROM operations WHERE operation_id=?", (operation_id,))
                return {"status": existing["status"], "deduplicated": True}
            db.append_event(run_id, "user", "user.steer.queued",
                            {"text": _redact(text), "status": "queued"})
            db.bump_state_version(run_id)
            await q.put({"type": "steer", "text": text})
            return {"status": "queued",
                    "detail": "指导已排队；以审阅与投递事件确认生效"}
        if action == "pause":
            if run["phase"] != "running":
                raise ControllerError("INVALID_STATE", f"当前阶段 {run['phase']} 不能暂停")
            if q is None:
                raise ControllerError("RECOVERABLE",
                                      "Run 事件循环不可用；请刷新状态或重启后端恢复")
            if not db.record_operation(operation_id, run_id, f"control.{action}",
                                       "accepted", request_summary=action):
                existing = db.query_one(
                    "SELECT status FROM operations WHERE operation_id=?", (operation_id,))
                return {"status": existing["status"], "deduplicated": True}
            # 暂停与已发出/排队指导交错：排队中的 shadow 指导立即失效，
            # 已 sent 的不谎报撤回
            with db.transaction() as conn:
                conn.execute("UPDATE runs SET phase='pausing' WHERE id=?", (run_id,))
                self._invalidate_shadow_guidance_tx(conn, run_id,
                                                    reason="用户暂停")
                db.append_event_tx(conn, run_id, "controller", "run.pausing", {
                    "notice": "正在暂停；已有远程任务可能继续运行/计费"})
            await q.put({"type": "pause"})
            return {"status": "accepted", "detail": "暂停中，等待代理确认"}
        if action == "resume":
            if run["phase"] == "recovering":
                # 后端重启后的恢复：重建事件循环与大脑/执行器会话，
                # 以 recovery 生命周期审阅让大脑裁决下一步，不盲目续跑
                other = db.query_one(
                    "SELECT id FROM runs WHERE phase IN"
                    " ('running','pausing','paused') AND id<>?", (run_id,))
                if other:
                    raise ControllerError("RUN_ACTIVE",
                                          f"已有活跃 Run {other['id']}")
                if not db.record_operation(operation_id, run_id, f"control.{action}",
                                           "accepted", request_summary=action):
                    existing = db.query_one(
                        "SELECT status FROM operations WHERE operation_id=?",
                        (operation_id,))
                    return {"status": existing["status"], "deduplicated": True}
                db.execute("UPDATE runs SET phase='running', block_reason=NULL"
                           " WHERE id=?", (run_id,))
                db.append_event(run_id, "controller", "run.resumed",
                                {"via": "recovery"})
                nq: asyncio.Queue = asyncio.Queue()
                self._signals[run_id] = nq
                self._tasks[run_id] = asyncio.create_task(
                    self._run_loop(run_id, nq, trigger="recovery"))
                return {"status": "confirmed",
                        "detail": "已重建会话；大脑将以 recovery 审阅裁决下一步"}
            if run["phase"] != "paused":
                raise ControllerError("INVALID_STATE", f"当前阶段 {run['phase']} 不能恢复")
            if q is None:
                raise ControllerError("RECOVERABLE",
                                      "Run 事件循环不可用；请刷新状态或重启后端恢复")
            if not db.record_operation(operation_id, run_id, f"control.{action}",
                                       "accepted", request_summary=action):
                existing = db.query_one(
                    "SELECT status FROM operations WHERE operation_id=?", (operation_id,))
                return {"status": existing["status"], "deduplicated": True}
            db.execute("UPDATE runs SET phase='running' WHERE id=?", (run_id,))
            db.append_event(run_id, "controller", "run.resumed", {})
            await q.put({"type": "resume"})
            return {"status": "confirmed"}
        if action == "terminate":
            if run["phase"] in ("finished", "failed", "cancelled"):
                raise ControllerError("INVALID_STATE",
                                      f"Run 已终态 {run['phase']}，不能改写")
            if not db.record_operation(operation_id, run_id, f"control.{action}",
                                       "accepted", request_summary=action):
                existing = db.query_one(
                    "SELECT status FROM operations WHERE operation_id=?", (operation_id,))
                return {"status": existing["status"], "deduplicated": True}
            with db.transaction() as conn:
                conn.execute("UPDATE runs SET phase='cancelled', ended_at=?"
                             " WHERE id=?", (db.utcnow(), run_id))
                conn.execute("UPDATE trials SET status='interrupted'"
                             " WHERE run_id=?"
                             " AND status IN ('active','reported_complete','stalled')",
                             (run_id,))
                conn.execute("UPDATE review_requests SET status='obsolete',"
                             " updated_at=? WHERE run_id=?"
                             " AND status IN ('pending','running')",
                             (db.utcnow(), run_id))
                collab.revoke_run_tokens(conn, run_id)
                db.append_event_tx(conn, run_id, "controller", "run.terminated", {
                    "notice": "证据与历史 Attempt 保留；远程 Job 取消属阶段 2 范围"})
            # 执行器会话 best-effort 终止：不留孤儿 CLI 进程
            prime = self._prime_instances.get(run_id)
            sid = self._prime_sessions.get(run_id)
            if prime and sid:
                try:
                    receipt = await prime.abort(sid)
                    db.append_event(run_id, "prime", "prime.session_aborted",
                                    {"status": receipt.status})
                except Exception as exc:  # noqa: BLE001
                    db.append_event(run_id, "prime", "prime.session_abort_failed",
                                    {"detail": str(exc)[:200]})
            if q:
                await q.put({"type": "terminate"})
            task = self._tasks.pop(run_id, None)
            if task:
                task.cancel()
            rtask = self._review_tasks.pop(run_id, None)
            if rtask:
                rtask.cancel()
            return {"status": "confirmed"}
        raise ControllerError("INVALID_ACTION", f"未知控制动作: {action}")

    def reconcile_on_startup(self) -> list[str]:
        """后端重启对账：无事件循环的非终态 Run 是僵尸——标记 recovering 等用户裁决。

        进程内的会话/队列/任务都随旧进程消失，phase 停在 running/pausing/paused
        的 Run 不能假装还在跑：如实标记、切断悬空审阅，由用户选择恢复或终止。
        """
        zombies = db.query(
            "SELECT id, phase FROM runs"
            " WHERE phase IN ('running','pausing','paused')")
        recovered = []
        for z in zombies:
            inflight = [r["id"] for r in db.query(
                "SELECT id FROM review_requests WHERE run_id=?"
                " AND status IN ('pending','running')", (z["id"],))]
            with db.transaction() as conn:
                conn.execute(
                    "UPDATE runs SET phase='recovering', block_reason=?"
                    " WHERE id=?",
                    ("后端重启；大脑/执行器会话已随旧进程断开。"
                     "可恢复（重建会话，大脑重新裁决）或终止", z["id"]))
                conn.execute(
                    "UPDATE review_requests SET status='obsolete', updated_at=?"
                    " WHERE run_id=? AND status IN ('pending','running')",
                    (db.utcnow(), z["id"]))
                db.append_event_tx(conn, z["id"], "controller",
                                   "run.needs_recovery",
                                   {"from_phase": z["phase"]})
            for request_id in inflight:
                # 被重启作废的收尾整理若承载着 finish：直接收尾，不软锁
                self._maybe_finalize_after_curation(request_id)
            recovered.append(z["id"])
        return recovered

    # ---------- 静默监督开关 ----------
    def set_shadow(self, run_id: str, enabled: bool) -> dict[str, Any]:
        run = self._require_run(run_id)
        with db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO supervision(run_id, enabled, updated_at)"
                " VALUES(?,0,?)", (run_id, db.utcnow()))
            if not enabled:
                # 关闭只停被动观察：shadow_epoch+1 使在途 shadow 审阅与
                # 未投递 shadow 指导失效；用户/显式请求保留
                conn.execute(
                    "UPDATE supervision SET enabled=0,"
                    " shadow_epoch=shadow_epoch+1, updated_at=? WHERE run_id=?",
                    (db.utcnow(), run_id))
                conn.execute(
                    "UPDATE review_requests SET status='obsolete', updated_at=?"
                    " WHERE run_id=? AND source='shadow' AND status='pending'",
                    (db.utcnow(), run_id))
                self._invalidate_shadow_guidance_tx(conn, run_id,
                                                    reason="静默监督已关闭")
            else:
                conn.execute(
                    "UPDATE supervision SET enabled=1, degraded=0,"
                    " degrade_reason=NULL, updated_at=? WHERE run_id=?",
                    (db.utcnow(), run_id))
            db.append_event_tx(run_id=run_id, conn=conn, source="controller",
                               type_="shadow.toggled",
                               payload={"enabled": bool(enabled),
                                        "note": "已发布指导仍可能有效；"
                                                "执行器不受影响"})
        self._wake(run_id)
        return self.supervision_status(run_id)

    @staticmethod
    def _invalidate_shadow_guidance_tx(conn: Any, run_id: str,
                                       reason: str) -> None:
        rows = conn.execute(
            "SELECT id, target_trial_id FROM guidance WHERE run_id=?"
            " AND source='shadow' AND status='queued'", (run_id,)).fetchall()
        for g in rows:
            conn.execute(
                "UPDATE guidance SET status='invalidated', updated_at=?"
                " WHERE id=?", (db.utcnow(), g["id"]))
            db.append_event_tx(conn, run_id, "controller",
                               "guidance.invalidated",
                               {"guidance_id": g["id"], "reason": reason},
                               trial_id=g["target_trial_id"])

    def request_review(self, run_id: str, blocking: bool = False) -> dict[str, Any]:
        """用户显式请求大脑现在审阅；返回 request ID，不重启执行器。"""
        run = self._require_run(run_id)
        if run["phase"] not in ("running", "paused"):
            raise ControllerError("INVALID_STATE",
                                  f"当前阶段 {run['phase']} 不能请求审阅")
        with db.transaction() as conn:
            rid = collab._enqueue_request_tx(conn, run_id, source="user",
                                             blocking=blocking,
                                             trigger="user_request")
        self._wake(run_id)
        return {"review_id": rid, "status": "pending"}

    def _wake(self, run_id: str) -> None:
        wake = self._review_wake.get(run_id)
        if wake:
            wake.set()

    # ---------- 执行器提问 → 大脑回答 ----------
    async def _answer_executor_question(
            self, run_id: str, question: dict[str, Any]) -> dict | None:
        """AskUserQuestion 的大脑回答：入队 executor_question 审阅并等待结果。

        返回 {"answers": {...}, "reason_md": ...}；失败/超时/额度用尽返回
        None（适配层如实 decline，不伪造答案）。Run 非 running 时直接 None。
        """
        run = db.query_one("SELECT phase FROM runs WHERE id=?", (run_id,))
        if not run or run["phase"] != "running":
            return None
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        with db.transaction() as conn:
            rid = collab._enqueue_request_tx(
                conn, run_id, source="executor", blocking=False,
                trigger="executor_question")
            conn.execute(
                "UPDATE review_requests SET frame_json=? WHERE id=?",
                (json.dumps({"question": question}, ensure_ascii=False), rid))
        self._question_waiters[rid] = fut
        self._wake(run_id)
        try:
            await asyncio.wait_for(fut, timeout=140)
        except asyncio.TimeoutError:
            return None
        finally:
            self._question_waiters.pop(rid, None)
        row = db.query_one(
            "SELECT status, result_json FROM review_requests WHERE id=?",
            (rid,))
        if row and row["status"] == "done" and row["result_json"]:
            try:
                return json.loads(row["result_json"])
            except json.JSONDecodeError:
                return None
        return None

    async def _run_question_review(self, run_id: str, req: Any,
                                   brain: BrainRuntime, b_session: Any) -> None:
        """执行器提问的审阅：小上下文 + 结构化回答。消耗大脑判断额度；
        失败如实标记，不影响 Run 相位。"""
        run = self._require_run(run_id)
        defaults = config.load_settings()["run_defaults"]
        db.execute("UPDATE review_requests SET status='running', updated_at=?"
                   " WHERE id=? AND status='pending'", (db.utcnow(), req["id"]))
        if run["brain_reviews_used"] >= defaults["max_brain_reviews"]:
            self._finish_request(
                req["id"], "error",
                error=f"大脑判断额度用尽 {defaults['max_brain_reviews']} 次")
            return
        db.execute("UPDATE runs SET brain_reviews_used=? WHERE id=?",
                   (run["brain_reviews_used"] + 1, run_id))
        try:
            question = json.loads(req["frame_json"]).get("question", {}) \
                if req["frame_json"] else {}
        except json.JSONDecodeError:
            question = {}
        trial = None
        if run["current_trial_id"]:
            trial = db.query_one(
                "SELECT id, goal, status FROM trials WHERE id=?",
                (run["current_trial_id"],))
        packet = {
            "protocol": "executor_question",
            "run_id": run_id,
            "current_intention": run["intention"],
            "trial_summary": {"trial_id": trial["id"], "goal": trial["goal"],
                              "status": trial["status"]} if trial else None,
            "budget_remaining": {
                "brain_reviews": defaults["max_brain_reviews"]
                - run["brain_reviews_used"] - 1},
            "question": question,
        }
        db.append_event(run_id, "brain", "brain.question_started", {
            "review_id": req["id"],
            "message": str(question.get("message", ""))[:200]})
        answer: dict[str, Any] | None = None
        error_msg: str | None = None
        try:
            async for ev in brain.review(b_session, packet):
                if ev.type == "question_answer":
                    answer = ev.payload
                elif ev.type == "error":
                    error_msg = ev.payload.get("message", "")
        except Exception as exc:  # noqa: BLE001
            error_msg = f"{exc.__class__.__name__}: {str(exc)[:300]}"
        if answer:
            valid, why = _validate_question_answer(question, answer["answers"])
            if valid:
                self._finish_request(req["id"], "done", result=answer)
                db.append_event(run_id, "brain", "brain.question_answered", {
                    "review_id": req["id"],
                    "answers": {k: str(v)[:80]
                                for k, v in answer["answers"].items()},
                    "reason_md": answer.get("reason_md", "")[:300]})
                return
            error_msg = f"大脑回答未通过选项校验: {why}"
        self._finish_request(req["id"], "error",
                             error=(error_msg or "大脑未给出有效回答")[:300])

    def notify_run_change(self, run_id: str) -> None:
        """collab 服务的内存唤醒提示（DB 已先行提交，丢失可由扫描恢复）。"""
        self._maybe_shadow(run_id)
        self._wake(run_id)

    # ---------- 主循环 ----------
    async def _run_loop(self, run_id: str, q: asyncio.Queue,
                        trigger: str = "run_start") -> None:
        settings = config.load_settings()
        brain = self._make_brain(settings)
        prime = self._make_prime(settings)
        if isinstance(prime, KimiExecutor):
            # 执行器 AskUserQuestion 路由给大脑回答（全自动，不问人类）
            prime.ask_handler = lambda _sid, q: self._answer_executor_question(
                run_id, q)
        self._prime_instances[run_id] = prime
        run = self._require_run(run_id)
        try:
            # 大脑视图：独立工作目录，不继承施工仓库指令
            brain_dir = config.WORKSPACE_DIR / "runs" / run_id / "brain_view"
            brain_dir.mkdir(parents=True, exist_ok=True)
            b_session = await brain.open(
                {"working_directory": str(brain_dir)})
            self._brain_sessions[run_id] = b_session
        except Exception as exc:  # noqa: BLE001
            db.execute("UPDATE runs SET phase='failed' WHERE id=?", (run_id,))
            db.append_event(run_id, "brain", "brain.session_error",
                            {"message": str(exc)[:300]})
            return

        prime_sid = await prime.start(self._prime_spec(run_id, settings))
        self._prime_sessions[run_id] = prime_sid

        async def prime_event_pump(sid: str) -> None:
            """每个原生会话常驻且唯一的事件消费者；回合结束不退出。"""
            try:
                async for ev in prime.events(sid):
                    await q.put({"type": "prime_event", "event": ev})
                    if ev.get("type") == "session.ended":
                        break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                await q.put({"type": "prime_error", "message": str(exc)[:300]})

        def start_pump() -> asyncio.Task:
            old = self._pumps.get(run_id)
            if old and not old.done():
                return old  # 同会话只允许一个消费者（A6）
            task = asyncio.create_task(
                prime_event_pump(self._prime_sessions[run_id]))
            self._pumps[run_id] = task
            return task

        self._start_pump[run_id] = start_pump
        start_pump()

        wake = asyncio.Event()
        self._review_wake[run_id] = wake
        worker = asyncio.create_task(
            self._review_worker(run_id, brain, b_session))
        self._review_tasks[run_id] = worker
        # 重启恢复：把中断时悬空的 running 请求如实标记，不盲目重放
        self._recover_review_requests(run_id)
        # 重启对账可能作废了承载 waiting_brain 的 blocking 审阅：
        # 兜底放行，否则恢复后大脑所有 start_trial 都会被门禁拒绝
        self._release_orphaned_gate(run_id)
        self._enqueue_lifecycle(run_id, trigger=trigger)
        try:
            while True:
                run = self._require_run(run_id)
                phase = run["phase"]
                if phase in ("finished", "failed", "cancelled"):
                    break
                # 有界授权：运行时长上限（只在 running 时触发一次；
                # 不设守卫会每轮重复置 paused + continue 空转，永不 await，
                # 同步 DB 写把事件循环彻底堵死——2026-09-19 实测 seq 爆炸到 9 万+）
                if phase == "running" and self._run_minutes_exceeded(run):
                    db.execute("UPDATE runs SET phase='paused', block_reason=? WHERE id=?",
                               ("达到本轮授权运行时长上限", run_id))
                    db.append_event(run_id, "controller", "run.time_limit",
                                    {"notice": "达到授权时长上限；已暂停新增受控操作"})
                    continue
                if phase == "pausing":
                    receipt = await prime.abort(self._prime_sessions[run_id])
                    if receipt.status == "confirmed":
                        db.execute("UPDATE runs SET phase='paused' WHERE id=?",
                                   (run_id,))
                        db.append_event(run_id, "prime", "run.paused",
                                        {"detail": receipt.detail})
                    else:
                        db.append_event(run_id, "prime", "run.pause_unknown", {
                            "detail": f"abort 收据={receipt.status}；保持 pausing，"
                                      f"不伪造已暂停"})
                    phase = self._require_run(run_id)["phase"]
                    if phase == "pausing":
                        signal = await q.get()
                        await self._handle_signal(signal, run_id, q)
                        continue
                try:
                    signal = await asyncio.wait_for(q.get(), timeout=3600)
                except asyncio.TimeoutError:
                    # 无事件不代表结束：记账后继续等待，绝不静默杀死 Run
                    db.append_event(run_id, "controller", "run.idle_notice",
                                    {"detail": "长时间无事件；Run 保持运行，等待新信号"})
                    continue
                await self._handle_signal(signal, run_id, q,
                                          prime=prime,
                                          prime_sid=self._prime_sessions[run_id])
        except asyncio.CancelledError:
            pass
        finally:
            worker.cancel()
            pump = self._pumps.pop(run_id, None)
            if pump:
                pump.cancel()
            try:
                await brain.close(b_session)
            except Exception:  # noqa: BLE001
                pass
            self._signals.pop(run_id, None)
            self._tasks.pop(run_id, None)
            self._prime_sessions.pop(run_id, None)
            self._prime_instances.pop(run_id, None)
            self._brain_sessions.pop(run_id, None)
            self._start_pump.pop(run_id, None)
            self._review_wake.pop(run_id, None)
            self._review_tasks.pop(run_id, None)
            self._executor_busy.pop(run_id, None)

    def _recover_review_requests(self, run_id: str) -> None:
        """重启对账：running→error（中断）；sending 指导→unknown（无法确认在途）。"""
        with db.transaction() as conn:
            stale = conn.execute(
                "SELECT id, blocking FROM review_requests WHERE run_id=?"
                " AND status='running'", (run_id,)).fetchall()
            for r in stale:
                conn.execute(
                    "UPDATE review_requests SET status='error',"
                    " error='interrupted by restart', updated_at=? WHERE id=?",
                    (db.utcnow(), r["id"]))
            inflight = conn.execute(
                "SELECT id FROM guidance WHERE run_id=? AND status='sending'",
                (run_id,)).fetchall()
            for g in inflight:
                conn.execute(
                    "UPDATE guidance SET status='unknown', updated_at=?"
                    " WHERE id=?", (db.utcnow(), g["id"]))
        for r in stale:
            # 中断的 curation 若承载着 finish，标 error 后直接收尾
            self._maybe_finalize_after_curation(r["id"])
            if r["blocking"]:
                self._blocking_dead_end(run_id, r["id"],
                                        "阻塞审阅被重启中断，无有效答复")

    def _handle_signal_guarded_pause(self, run_id: str) -> bool:
        """暂停/正在暂停期间：只记账，不驱动 Trial 完成与大脑判断。"""
        phase = self._require_run(run_id)["phase"]
        return phase in ("pausing", "paused")

    async def _handle_signal(self, signal: dict[str, Any], run_id: str,
                             q: asyncio.Queue, **ctx: Any) -> None:
        stype = signal["type"]
        if stype == "prime_event":
            ev = signal["event"]
            run = self._require_run(run_id)
            trial_id = run["current_trial_id"]
            etype = ev.get("type", "prime.event")
            db.append_event(run_id, "prime", f"prime.{etype}",
                            {"detail": ev.get("detail", "")}, trial_id=trial_id)
            if self._handle_signal_guarded_pause(run_id):
                if etype in ("trial.completed", "run.aborted",
                             "executor.turn_completed"):
                    db.append_event(run_id, "controller", "prime.late_event_ignored", {
                        "type": etype,
                        "notice": "暂停期间不驱动状态推进；恢复后由代理状态核对"})
                return
            if etype == "executor.turn_completed":
                # 原生回合结束 ≠ 实验交付：只更新忙闲与等待门禁（A4/A7）
                self._executor_busy[run_id] = False
                await self._on_turn_boundary(run_id, ev)
            elif etype == "trial.completed":
                # 仅 demo 执行器仍用此词汇；真实执行器走
                # research_checkpoint(stage=trial_complete)
                self._executor_busy[run_id] = False
                db.execute("UPDATE trials SET status='done' WHERE id=?",
                           (trial_id,))
                db.append_event(run_id, "controller", "trial.done",
                                {"trial_id": trial_id})
                self._enqueue_lifecycle(run_id, trigger="trial_done")
            elif etype == "trial.stalled":
                # A9：无事件只代表需要活性核对，不判失败、不 abort、不换会话；
                # Trial 标记 stalled 保留现场，由大脑生命周期审阅裁决
                self._executor_busy[run_id] = False
                db.execute("UPDATE trials SET status='stalled' WHERE id=?"
                           " AND status='active'", (trial_id,))
                db.append_event(run_id, "controller", "trial.stalled", {
                    "trial_id": trial_id,
                    "notice": "事件流超时；保留会话与现场，等大脑裁决。"
                              "可能的远程任务状态独立核对"}, trial_id=trial_id)
                self._enqueue_lifecycle(run_id, trigger="trial_stalled")
            elif etype == "run.aborted":
                db.append_event(run_id, "prime", "prime.aborted",
                                {"detail": ev.get("detail", "")})
                run = self._require_run(run_id)
                if run["gate"] == "stopped":
                    db.execute("UPDATE trials SET status='interrupted'"
                               " WHERE id=? AND status='active'", (trial_id,))
                    db.append_event(run_id, "controller", "run.stop_confirmed", {
                        "trial_id": trial_id,
                        "notice": "收到原生取消终态；远程 Job 状态独立核对"})
                elif run["phase"] == "running":
                    # 非预期中断（如通信失败）：唤醒大脑裁决，不干等
                    self._executor_busy[run_id] = False
                    self._enqueue_lifecycle(run_id, trigger="executor_aborted")
            if etype in _SHADOW_TRIGGERS or \
                    f"prime.{etype}" in ("prime.checkpoint.created",):
                self._maybe_shadow(run_id)
        elif stype == "steer":
            # 用户指导 → 生命周期审阅（同一个大脑排队入口）
            self._enqueue_lifecycle(run_id, trigger="user_steer",
                                    user_guidance=signal.get("text"))
        elif stype == "resume":
            # 恢复：重新挂接执行器。若仍有活跃 Trial 且执行器空闲，
            # 重新下发任务让其继续（远程 Job 的实际状态核对属阶段 2）。
            run = self._require_run(run_id)
            trial_id = run["current_trial_id"]
            if trial_id and run["gate"] == "open":
                trial = db.query_one("SELECT * FROM trials WHERE id=?", (trial_id,))
                if trial and trial["status"] == "active":
                    state = await ctx["prime"].state(ctx["prime_sid"])
                    if state.get("status") == "idle":
                        receipt = await ctx["prime"].prompt(
                            ctx["prime_sid"],
                            f"继续目标：{trial['goal']}\n成功判据：{trial['success_check']}")
                        self._executor_busy[run_id] = receipt.status == "accepted"
                        db.append_event(run_id, "prime", "prime.task_resumed",
                                        {"status": receipt.status,
                                         "detail": receipt.detail},
                                        trial_id=trial_id)
                        if receipt.status == "accepted":
                            starter = self._start_pump.get(run_id)
                            if starter:
                                starter()
        elif stype in ("pause", "terminate"):
            pass  # 状态转换已在 control()/主循环处理
        elif stype == "prime_error":
            db.append_event(run_id, "prime", "prime.error",
                            {"message": signal.get("message", "")})
            self._maybe_shadow(run_id)

    def _blocking_inflight(self, run_id: str) -> Any:
        return db.query_one(
            "SELECT id FROM review_requests WHERE run_id=?"
            " AND blocking=1 AND status IN ('pending','running')",
            (run_id,))

    def _release_orphaned_gate(self, run_id: str) -> bool:
        """门禁兜底：等待门禁所承载的 blocking 审阅已不存在（被重启对账、
        额度用尽等作废）时放行并留痕——否则没有任何东西能再开门，
        大脑的所有 start_trial 都会被门禁永远拒绝。"""
        run = self._require_run(run_id)
        if run["gate"] not in ("yielding", "waiting_brain"):
            return False
        if self._blocking_inflight(run_id):
            return False
        db.execute("UPDATE runs SET gate='open' WHERE id=?"
                   " AND gate IN ('yielding','waiting_brain')", (run_id,))
        db.append_event(run_id, "controller", "run.gate_opened", {
            "by": "no_blocking_inflight",
            "notice": "承载等待的 blocking 审阅已不存在；放行并留痕"})
        return True

    async def _on_turn_boundary(self, run_id: str, ev: dict[str, Any]) -> None:
        """已确认空闲的回合边界：等待门禁转换 + 指导的边界投递。"""
        run = self._require_run(run_id)
        gate = run["gate"]
        if gate in ("yielding", "waiting_brain"):
            blocking = self._blocking_inflight(run_id)
            if blocking:
                if gate == "yielding":
                    db.execute("UPDATE runs SET gate='waiting_brain' WHERE id=?",
                               (run_id,))
                    db.append_event(run_id, "controller", "run.waiting_brain", {
                        "review_id": blocking["id"],
                        "notice": "执行器已交棒；等待大脑有效答复，不暗中放行"})
                self._wake(run_id)
                return
            if gate == "waiting_brain":
                # 等待中的 blocking 审阅已被作废：兜底放行并留痕
                self._release_orphaned_gate(run_id)
            else:
                db.execute("UPDATE runs SET gate='open' WHERE id=?", (run_id,))
        # 空闲边界投递：queued 指导经 prompt 下发（与检查点工具返回互斥，
        # 状态机保证一次指导只走一个渠道）
        if self._require_run(run_id)["gate"] == "open":
            await self._deliver_queued_guidance(run_id)

    async def _deliver_queued_guidance(self, run_id: str) -> None:
        prime = self._prime_instances.get(run_id)
        sid = self._prime_sessions.get(run_id)
        if not prime or not sid or self._executor_busy.get(run_id):
            return
        # 只有运行中且门禁开放才投递：暂停/等待大脑期间不准唤醒执行器
        run = self._require_run(run_id)
        if run["phase"] != "running" or run["gate"] != "open":
            return
        with db.transaction() as conn:
            rows = collab.pending_guidance(conn, run_id)
            if not rows:
                return
            g = rows[0]
            claimed = conn.execute(
                "UPDATE guidance SET status='sending', updated_at=?"
                " WHERE id=? AND status='queued'",
                (db.utcnow(), g["id"])).rowcount == 1
            if not claimed:
                return
        text = (f"【大脑指导 {g['id']}】kind={g['kind']} intent={g['intent']}\n"
                f"{g['text_md']}\n依据：{g['reason_md'] or ''}\n"
                f"预期：{g['expected_change_md'] or ''}\n"
                f"重新讨论条件：{g['revisit_when_md'] or ''}\n"
                f"请用 ack_guidance 确认 accepted 或 challenged。")
        receipt = await prime.prompt(sid, text)
        with db.transaction() as conn:
            if receipt.status == "accepted":
                self._executor_busy[run_id] = True
                conn.execute(
                    "UPDATE guidance SET status='sent', delivery_channel=?,"
                    " operation_id=?, updated_at=? WHERE id=?",
                    ("idle_prompt", receipt.operation_id or "", db.utcnow(),
                     g["id"]))
                db.append_event_tx(conn, run_id, "controller", "guidance.sent",
                                   {"guidance_id": g["id"], "kind": g["kind"],
                                    "channel": "idle_prompt",
                                    "operation_id": receipt.operation_id},
                                   trial_id=g["target_trial_id"])
            else:
                # 发送失败不谎报：回滚到 queued 等下一边界
                conn.execute(
                    "UPDATE guidance SET status='queued', updated_at=?"
                    " WHERE id=?", (db.utcnow(), g["id"]))
                db.append_event_tx(conn, run_id, "controller",
                                   "guidance.send_deferred",
                                   {"guidance_id": g["id"],
                                    "detail": receipt.detail[:200]},
                                   trial_id=g["target_trial_id"])

    # ---------- 审阅调度（单飞 worker）----------
    def _enqueue_lifecycle(self, run_id: str, trigger: str,
                           user_guidance: str | None = None) -> str:
        with db.transaction() as conn:
            rid = collab._enqueue_request_tx(
                conn, run_id, source="lifecycle", blocking=False,
                trigger=trigger)
            if user_guidance:
                conn.execute(
                    "UPDATE review_requests SET frame_json=? WHERE id=?",
                    (json.dumps({"user_guidance": _redact(user_guidance)},
                                ensure_ascii=False), rid))
        self._wake(run_id)
        return rid

    def _maybe_shadow(self, run_id: str) -> None:
        """有新的有效科学变化且额度允许时，排队一次被动观察（合并语义）。"""
        run = self._require_run(run_id)
        if run["phase"] != "running":
            return
        sup = db.query_one("SELECT * FROM supervision WHERE run_id=?",
                           (run_id,))
        if not sup or not sup["enabled"] or sup["degraded"]:
            return
        cfg = self._shadow_cfg(run)
        if sup["reviews_used"] >= cfg["max_reviews"]:
            return
        pending = db.query_one(
            "SELECT id FROM review_requests WHERE run_id=?"
            " AND source='shadow' AND status IN ('pending','running')",
            (run_id,))
        if pending:
            return  # 合并：大脑忙/已有待处理范围时不另起请求
        notable = db.query_one(
            f"SELECT MAX(seq) AS s FROM events WHERE run_id=?"
            f" AND type IN ({','.join('?' * len(_SHADOW_TRIGGERS))})",
            (run_id, *_SHADOW_TRIGGERS))
        latest = (notable["s"] or 0) if notable else 0
        if latest <= sup["covered_seq"]:
            return  # 无新有效变化，不调用模型
        with db.transaction() as conn:
            collab._enqueue_request_tx(conn, run_id, source="shadow",
                                       blocking=False, trigger="passive",
                                       )
        self._wake(run_id)

    def _maybe_periodic_shadow(self, run_id: str) -> None:
        """时间兜底：执行器持续运转但没交检查点时，到点唤起大脑看一眼。

        触发词表只覆盖"科学变化"事件；心跳/进度刻意不算。没有这条兜底，
        沉默干活的执行器会让大脑永远旁观。仍受 shadow 额度、合并语义与
        真实新事件约束（covered_seq 之后无新事件则不调用模型）。
        """
        import time as _time
        run = self._require_run(run_id)
        if run["phase"] != "running":
            return
        sup = db.query_one("SELECT * FROM supervision WHERE run_id=?",
                           (run_id,))
        if not sup or not sup["enabled"] or sup["degraded"]:
            return
        cfg = self._shadow_cfg(run)
        if sup["reviews_used"] >= cfg["max_reviews"]:
            return
        pending = db.query_one(
            "SELECT id FROM review_requests WHERE run_id=?"
            " AND source='shadow' AND status IN ('pending','running')",
            (run_id,))
        if pending:
            return  # 合并：已有待处理 shadow 审阅
        last = _parse_ts(sup["last_review_at"]) or _parse_ts(run["started_at"])
        if last is None or _time.time() - last < cfg["max_interval_seconds"]:
            return
        latest = db.query_one(
            "SELECT MAX(seq) AS s FROM events WHERE run_id=?"
            " AND source IN ('prime','executor','user')", (run_id,))
        if (latest["s"] or 0) <= sup["covered_seq"]:
            return  # 执行器/用户无新动作（大脑自身记账不算），不调用模型
        with db.transaction() as conn:
            collab._enqueue_request_tx(conn, run_id, source="shadow",
                                       blocking=False, trigger="periodic")
        self._wake(run_id)

    async def _review_worker(self, run_id: str, brain: BrainRuntime,
                             b_session: Any) -> None:
        """每个 Run 唯一的大脑审阅 worker：所有模式共用，单飞。"""
        wake = self._review_wake[run_id]
        while True:
            run = self._require_run(run_id)
            if run["phase"] in ("finished", "failed", "cancelled"):
                return
            req = self._next_request(run_id)
            if req is None:
                # 稀疏兜底：有待观察变化时按 max_interval 再检查；
                # 检查本身不调用模型
                cfg = self._shadow_cfg(run)
                timeout = min(cfg["max_interval_seconds"], 60.0)
                wake.clear()
                # clear 后再查一次：擦掉刚到唤醒的窗口由此关闭
                if self._next_request(run_id) is not None:
                    continue
                try:
                    await asyncio.wait_for(wake.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    self._maybe_shadow(run_id)
                    self._maybe_periodic_shadow(run_id)
                continue
            if req["source"] == "shadow":
                wait = self._shadow_throttle(run_id, req)
                if wait is None:
                    continue  # 已失效/降级，循环取下一个
                if wait > 0:
                    wake.clear()
                    # 若节流等待期间到达更高优先级请求，立即改处理它
                    nxt = self._next_request(run_id)
                    if nxt is not None and nxt["id"] != req["id"]:
                        continue
                    try:
                        await asyncio.wait_for(wake.wait(), timeout=wait)
                    except asyncio.TimeoutError:
                        pass
                    continue  # 重新按优先级取（可能有更紧急请求到达）
            await self._run_one_review(run_id, req, brain, b_session)

    def _next_request(self, run_id: str) -> Any | None:
        """优先级：显式 blocking → 生命周期 → 用户 → 执行器 async → shadow。"""
        return db.query_one(
            "SELECT * FROM review_requests WHERE run_id=? AND status='pending'"
            " ORDER BY blocking DESC,"
            " CASE source WHEN 'lifecycle' THEN 0 WHEN 'user' THEN 1"
            " WHEN 'executor' THEN 2 ELSE 3 END, created_at LIMIT 1",
            (run_id,))

    def _shadow_throttle(self, run_id: str, req: Any) -> float | None:
        """返回还需等待秒数；None 表示该请求已失效（标 obsolete）。"""
        run = self._require_run(run_id)
        sup = db.query_one("SELECT * FROM supervision WHERE run_id=?",
                           (run_id,))
        cfg = self._shadow_cfg(run)
        if not sup or not sup["enabled"] or sup["degraded"]:
            self._obsolete_request(req["id"], "静默监督不可用")
            return None
        if sup["reviews_used"] >= cfg["max_reviews"]:
            self._obsolete_request(req["id"], "shadow 观察额度用尽")
            with db.transaction() as conn:
                conn.execute(
                    "UPDATE supervision SET degraded=1, degrade_reason=?,"
                    " updated_at=? WHERE run_id=?",
                    ("shadow 观察额度用尽；执行器在原授权内继续",
                     db.utcnow(), run_id))
                db.append_event_tx(conn, run_id, "controller",
                                   "shadow.degraded",
                                   {"reason": "观察额度用尽",
                                    "notice": "只降级静默监督，Run 不暂停"})
            return None
        last = _parse_ts(sup["last_review_at"])
        if last is not None:
            import time as _time
            elapsed = _time.time() - last
            if elapsed < cfg["min_interval_seconds"]:
                return cfg["min_interval_seconds"] - elapsed
        return 0.0

    def _obsolete_request(self, request_id: str, reason: str) -> None:
        db.execute("UPDATE review_requests SET status='obsolete', error=?,"
                   " updated_at=? WHERE id=?",
                   (reason, db.utcnow(), request_id))
        fut = self._question_waiters.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(None)
        # 被作废的请求可能是承载 finish 的收尾整理：作废不阻塞 Run 收尾
        self._maybe_finalize_after_curation(request_id)

    def _blocking_dead_end(self, run_id: str, review_id: str,
                           reason: str) -> None:
        """blocking 请求终态化且无有效答复：不暗中放行；若无其他在途 blocking
        请求，暂停 Run 并如实说明，等用户处理（否则 gate 永远不会再开）。"""
        other = db.query_one(
            "SELECT id FROM review_requests WHERE run_id=? AND blocking=1"
            " AND status IN ('pending','running') AND id<>?",
            (run_id, review_id))
        if other:
            return
        with db.transaction() as conn:
            cur = conn.execute("SELECT gate, phase FROM runs WHERE id=?",
                               (run_id,)).fetchone()
            if not cur or cur["gate"] not in ("yielding", "waiting_brain") \
                    or cur["phase"] not in ("running", "pausing"):
                return
            conn.execute("UPDATE runs SET phase='paused', block_reason=?"
                         " WHERE id=?", (reason, run_id))
            db.append_event_tx(conn, run_id, "controller", "run.paused", {
                "review_id": review_id, "reason": reason,
                "notice": "阻塞审阅无有效答复；已暂停等待用户处理，未自动放行"})

    async def _run_one_review(self, run_id: str, req: Any,
                              brain: BrainRuntime, b_session: Any) -> None:
        """worker 唯一的大脑调用点；结果由控制器短事务单点接受。"""
        if req["trigger"] == "executor_question":
            # 执行器提问：独立小协议，不走 ObservationFrame/Decision
            await self._run_question_review(run_id, req, brain, b_session)
            return
        run = self._require_run(run_id)
        cfg = self._shadow_cfg(run)
        # 大脑判断上限读实时 settings：运行中可通过预算接口调大，无需重启
        defaults = config.load_settings()["run_defaults"]
        mode = "lifecycle" if req["source"] == "lifecycle" else (
            "shadow" if req["source"] == "shadow" else "requested")

        # 额度：lifecycle/显式消耗大脑判断上限；shadow 消耗观察子额度
        if mode == "lifecycle" or req["blocking"]:
            if run["brain_reviews_used"] >= defaults["max_brain_reviews"]:
                if mode == "lifecycle":
                    db.execute(
                        "UPDATE runs SET phase='paused', block_reason=?"
                        " WHERE id=?",
                        (f"达到大脑判断上限 {defaults['max_brain_reviews']} 次",
                         run_id))
                    db.append_event(run_id, "controller", "run.review_limit",
                                    {"limit": defaults["max_brain_reviews"]})
                self._obsolete_request(req["id"], "大脑判断额度用尽")
                if req["blocking"]:
                    self._blocking_dead_end(
                        run_id, req["id"],
                        f"阻塞审阅超出大脑判断上限 "
                        f"{defaults['max_brain_reviews']} 次，无有效答复")
                return

        sup = db.query_one("SELECT * FROM supervision WHERE run_id=?",
                           (run_id,))
        from_seq = (sup["covered_seq"] + 1) if sup else 1
        through_seq = self._last_seq(run_id)
        frame_id = _rid("frame")

        try:
            if mode == "lifecycle":
                extra = json.loads(req["frame_json"]) if req["frame_json"] else {}
                packet = self._lifecycle_packet(
                    run, req["trigger"] or "lifecycle",
                    user_guidance=extra.get("user_guidance"))
            else:
                packet = observation.build_frame(
                    run_id, mode=mode, frame_id=frame_id,
                    from_seq=from_seq, through_seq=through_seq,
                    shadow_cfg=cfg, run_defaults=defaults,
                    request={"review_id": req["id"],
                             "checkpoint_id": req["checkpoint_id"],
                             "blocking": bool(req["blocking"])})
                packet["protocol"] = "review_result"
        except Exception as exc:  # noqa: BLE001
            self._finish_request(req["id"], "error",
                                 error=f"frame 构建失败: {exc}"[:300])
            return

        now = db.utcnow()
        with db.transaction() as conn:
            conn.execute(
                "UPDATE review_requests SET status='running', frame_id=?,"
                " frame_json=?, from_seq=?, through_seq=?, state_version=?,"
                " evidence_revision=?, shadow_epoch=?, updated_at=?"
                " WHERE id=? AND status='pending'",
                (frame_id,
                 json.dumps(packet, ensure_ascii=False) if mode != "lifecycle"
                 else req["frame_json"],
                 from_seq, through_seq, run["state_version"],
                 (sup["evidence_revision"] if sup else 0),
                 (sup["shadow_epoch"] if sup else 0), now, req["id"]))
        db.append_event(run_id, "brain", "brain.review_started", {
            "trigger": req["trigger"], "mode": mode,
            "review_id": req["id"], "frame_id": frame_id,
            "from_seq": from_seq, "through_seq": through_seq})

        if mode != "shadow":
            db.execute("UPDATE runs SET brain_reviews_used=?"
                       " WHERE id=?",
                       (run["brain_reviews_used"] + 1, run_id))
        else:
            db.execute("UPDATE supervision SET reviews_used=reviews_used+1,"
                       " last_review_at=? WHERE run_id=?", (now, run_id))

        raw_parts: list[str] = []
        result: dict[str, Any] | None = None
        error_msg: str | None = None
        try:
            async for ev in brain.review(b_session, packet):
                if ev.type == "decision" and mode == "lifecycle":
                    result = {"kind": "decision", "decision": ev.payload["decision"]}
                elif ev.type == "review_result" and mode != "lifecycle":
                    result = {"kind": "review_result",
                              "result": ev.payload["result"]}
                elif ev.type == "error":
                    error_msg = ev.payload.get("message", "")
                elif ev.type == "approval_request":
                    db.append_event(run_id, "brain", "brain.approval_request",
                                    ev.payload)
                elif ev.type in ("token", "message", "raw"):
                    raw_parts.append(str(ev.payload.get("text", "")))
        except Exception as exc:  # noqa: BLE001
            error_msg = f"{exc.__class__.__name__}: {str(exc)[:300]}"
        if raw_parts:
            db.append_event(run_id, "brain", "brain.raw_output",
                            {"text": "".join(raw_parts)[:2000]})

        if error_msg or result is None:
            self._review_failed(run_id, req, mode,
                                error_msg or "大脑未产出有效结果")
            return

        if result["kind"] == "decision":
            if req["blocking"]:
                # Decision 是 blocking 请求的有效答复（lifecycle 协议的答复形态）：
                # 先开门再应用——否则答复里的 start_trial 会被自己正在解除的
                # 门禁拒绝（2026-09-19 seq 868 实测循环死锁）
                with db.transaction() as conn:
                    opened = conn.execute(
                        "UPDATE runs SET gate='open' WHERE id=?"
                        " AND gate IN ('yielding','waiting_brain')",
                        (run_id,)).rowcount == 1
                    if opened:
                        db.append_event_tx(conn, run_id, "controller",
                                           "run.gate_opened",
                                           {"review_id": req["id"],
                                            "by": "blocking_decision"})
            await self._apply_decision(run_id, result["decision"],
                                       packet, brain, b_session)
            self._finish_request(req["id"], "done",
                                 result={"summary": result["decision"].get(
                                     "summary", "")[:500]})
        else:
            self._apply_review_result(run_id, req, mode, packet,
                                      result["result"])

    def _review_failed(self, run_id: str, req: Any, mode: str,
                       error_msg: str) -> None:
        """失败隔离：shadow 失败只降级监督；blocking 保持等待不暗中放行。"""
        db.append_event(run_id, "brain", "brain.error",
                        {"message": error_msg, "review_id": req["id"],
                         "mode": mode})
        self._finish_request(req["id"], "error", error=error_msg)
        if mode == "shadow":
            with db.transaction() as conn:
                conn.execute(
                    "UPDATE supervision SET degraded=1, degrade_reason=?,"
                    " updated_at=? WHERE run_id=?",
                    (f"静默审阅失败: {error_msg[:150]}", db.utcnow(), run_id))
                db.append_event_tx(conn, run_id, "controller",
                                   "shadow.degraded",
                                   {"reason": error_msg[:200],
                                    "notice": "只降级静默监督，执行器继续；"
                                              "重新开启监督可恢复"})
        elif req["blocking"]:
            db.append_event(run_id, "controller",
                            "brain.blocking_unanswered",
                            {"review_id": req["id"], "error": error_msg[:200],
                             "notice": "无有效阻塞答复；保持等待，不自动放行"})
            self._blocking_dead_end(run_id, req["id"],
                                    f"阻塞审阅失败: {error_msg[:120]}")

    def _apply_review_result(self, run_id: str, req: Any, mode: str,
                             frame: dict[str, Any],
                             result: dict[str, Any]) -> None:
        """ReviewResult 唯一接受点：契约校验、过期判断、原子落库。"""
        schema = {"$ref": "#/$defs/ReviewResult",
                  "$defs": _REVIEW_RESULT_SCHEMA["$defs"]}
        salvaged: list[str] = []
        try:
            jsonschema.validate(result, schema)
        except jsonschema.ValidationError:
            # 第一刀：注释性字段容错（watchlist 字符串→Watch 对象等）
            result, salvaged = _salvage_review_result(result)
            try:
                jsonschema.validate(result, schema)
            except jsonschema.ValidationError:
                # 第二刀：guidance 非法只丢 guidance，审阅降级 silent，不整单拒收
                if isinstance(result, dict) and result.get("guidance") is not None:
                    result = dict(result, guidance=None)
                    if result.get("disposition") == "intervene":
                        result["disposition"] = "silent"
                    salvaged.append("guidance 格式非法已丢弃，审阅降级为 silent")
                try:
                    jsonschema.validate(result, schema)
                except jsonschema.ValidationError as exc:
                    self._review_failed(run_id, req, mode,
                                        f"ReviewResult 契约校验失败: "
                                        f"{exc.message[:200]}")
                    return
        if salvaged:
            db.append_event(run_id, "brain", "brain.review_salvaged",
                            {"review_id": req["id"], "mode": mode,
                             "fixes": salvaged[:6]})
        if result["frame_id"] != frame.get("frame_id"):
            self._review_failed(run_id, req, mode,
                                "frame_id 不匹配；按审阅失败处理")
            return

        run = self._require_run(run_id)
        with db.transaction() as conn:
            sup = conn.execute("SELECT * FROM supervision WHERE run_id=?",
                               (run_id,)).fetchone()
            # shadow 来源结果按 shadow_epoch 失效（用户关闭监督后到达的旧结果）。
            # 必须在事务内重查：req 快照取自 pending 时刻，shadow_epoch 列在
            # 标 running 时才写入，直接用快照等于不做失效检查。
            cur = conn.execute(
                "SELECT source, shadow_epoch FROM review_requests WHERE id=?",
                (req["id"],)).fetchone()
            if cur and cur["source"] == "shadow" and sup and \
                    cur["shadow_epoch"] is not None and \
                    cur["shadow_epoch"] != sup["shadow_epoch"]:
                conn.execute(
                    "UPDATE review_requests SET status='obsolete',"
                    " error='shadow_epoch 已变化', updated_at=? WHERE id=?",
                    (db.utcnow(), req["id"]))
                db.append_event_tx(conn, run_id, "brain",
                                   "brain.review_obsolete",
                                   {"review_id": req["id"]})
                return
            # SILENT / INTERVENE 都原子保存笔记、观察项与已审阅范围
            conn.execute(
                "UPDATE supervision SET private_note_md=?, watchlist=?,"
                " covered_seq=MAX(covered_seq, ?), updated_at=? WHERE run_id=?",
                (result["private_note_md"],
                 json.dumps(result["watchlist"], ensure_ascii=False),
                 frame.get("through_seq") or 0, db.utcnow(), run_id))
            db.append_event_tx(conn, run_id, "brain", "brain.review_done", {
                "review_id": req["id"], "mode": mode,
                "disposition": result["disposition"],
                "frame_id": result["frame_id"],
                "note_excerpt": result["private_note_md"][:200]})

            guidance_id: str | None = None
            if result["disposition"] == "intervene":
                g = result["guidance"]
                guidance_id = collab.create_guidance(
                    conn, run_id,
                    source="shadow" if req["source"] == "shadow"
                    else "requested",
                    g=g, target_trial_id=frame.get("trial_id"),
                    review_request_id=req["id"], frame_id=result["frame_id"],
                    state_version=run["state_version"],
                    evidence_revision=frame.get("evidence_revision") or 0,
                    shadow_epoch=frame.get("shadow_epoch") or 0)
                db.append_event_tx(conn, run_id, "brain",
                                   "guidance.queued",
                                   {"guidance_id": guidance_id,
                                    "kind": g["kind"], "intent": g["intent"],
                                    "text_excerpt": g["text_md"][:200]},
                                   trial_id=frame.get("trial_id"))
                if g["kind"] == "stop":
                    # STOP 先关门；原生取消在主事务外请求
                    conn.execute("UPDATE runs SET gate='stopped' WHERE id=?",
                                 (run_id,))
                    db.append_event_tx(conn, run_id, "controller",
                                       "run.stop_requested",
                                       {"guidance_id": guidance_id,
                                        "notice": "已关闭新增受控动作入口；"
                                                  "收到原生终态才确认已停"})
                elif g["kind"] == "submit":
                    # submit 是系统级动作：不投递给执行器、不改门禁。
                    # 标 sent/system_action 使投递循环永远跳过它；
                    # 真实提交在事务外执行（见 _execute_submit）。
                    conn.execute(
                        "UPDATE guidance SET status='sent',"
                        " delivery_channel='system_action', updated_at=?"
                        " WHERE id=?", (db.utcnow(), guidance_id))
                    db.append_event_tx(conn, run_id, "controller",
                                       "submission.auto_requested",
                                       {"guidance_id": guidance_id},
                                       trial_id=frame.get("trial_id"))
            if req["blocking"] and result["disposition"] == "intervene":
                # 有效阻塞答复：解除等待（SILENT 不解除）
                conn.execute("UPDATE runs SET gate='open' WHERE id=?"
                             " AND gate IN ('yielding','waiting_brain')",
                             (run_id,))
                db.append_event_tx(conn, run_id, "controller",
                                   "run.gate_opened",
                                   {"review_id": req["id"],
                                    "by": "blocking_review_answer"})
            conn.execute(
                "UPDATE review_requests SET status='done', result_json=?,"
                " updated_at=? WHERE id=?",
                (json.dumps(result, ensure_ascii=False), db.utcnow(),
                 req["id"]))

        # 事务外：stop 的原生取消 + submit 自动提交 + 空闲边界投递
        if result["disposition"] == "intervene":
            g = result["guidance"]
            if g["kind"] == "stop":
                asyncio.create_task(self._request_abort(run_id))
            elif g["kind"] == "submit":
                asyncio.create_task(self._execute_submit(
                    run_id, guidance_id, frame.get("trial_id")))
            elif not self._executor_busy.get(run_id):
                asyncio.create_task(self._deliver_queued_guidance(run_id))
        elif req["blocking"]:
            db.append_event(run_id, "controller", "brain.blocking_unanswered",
                            {"review_id": req["id"],
                             "notice": "阻塞请求收到 SILENT，不是有效答复；"
                                       "保持等待"})

    async def _request_abort(self, run_id: str) -> None:
        prime = self._prime_instances.get(run_id)
        sid = self._prime_sessions.get(run_id)
        if not prime or not sid:
            return
        receipt = await prime.abort(sid)
        db.append_event(run_id, "controller", "run.abort_requested",
                        {"status": receipt.status, "detail": receipt.detail})

    async def _execute_submit(self, run_id: str, guidance_id: str,
                              trial_id: str | None) -> None:
        """大脑 submit 指导的执行体：实验邮箱自动提交（无需用户确认）。

        幂等键绑定 guidance_id，重放不产生重复提交；失败只记事件并标
        guidance failed，是否重试由大脑下一轮审阅决定——不自动重复
        消耗配额的付费动作。提交成功后分数由服务端评分轮询异步拿回。
        """
        try:
            res = await asyncio.to_thread(
                mailboxes.submit_experiment, run_id, trial_id, None,
                f"auto-{guidance_id}")
        except Exception as exc:
            code = getattr(exc, "code", None) or type(exc).__name__
            with db.transaction() as conn:
                conn.execute(
                    "UPDATE guidance SET status='failed', updated_at=?"
                    " WHERE id=?", (db.utcnow(), guidance_id))
                db.append_event_tx(
                    conn, run_id, "controller", "submission.auto_failed",
                    {"guidance_id": guidance_id, "code": code,
                     "error": str(exc)[:400]},
                    trial_id=trial_id)
            return
        ok = res.get("status") == "submitted"
        with db.transaction() as conn:
            conn.execute(
                "UPDATE guidance SET status=?, applied_evidence=?,"
                " updated_at=? WHERE id=?",
                ("applied" if ok else "failed",
                 json.dumps([f"submission:{res.get('id')}",
                             f"platform_ref:{res.get('platform_ref')}"],
                            ensure_ascii=False),
                 db.utcnow(), guidance_id))
            db.append_event_tx(
                conn, run_id, "controller",
                "submission.auto_done" if ok else "submission.auto_failed",
                {"guidance_id": guidance_id,
                 "submission_id": res.get("id"),
                 "platform_ref": res.get("platform_ref"),
                 "error": res.get("error")}, trial_id=trial_id)

    def _maybe_finalize_after_curation(self, request_id: str) -> None:
        """curation 审阅进入任何终态（done/error/obsolete）后，若它承载着被
        推迟的 finish 且 Run 未到终态，则执行收尾：整理失败/作废/被重启中断
        都不阻塞 Run 到达终态（防软锁）。"""
        req = db.query_one(
            "SELECT run_id, trigger, frame_json FROM review_requests"
            " WHERE id=?", (request_id,))
        if not req or req["trigger"] != "curation" or not req["frame_json"]:
            return
        try:
            meta = json.loads(req["frame_json"])
        except (json.JSONDecodeError, TypeError):
            return
        if not meta.get("finish_after"):
            return
        run = db.query_one("SELECT phase FROM runs WHERE id=?",
                           (req["run_id"],))
        if not run or run["phase"] in ("finished", "failed", "cancelled"):
            return
        self._finalize_run(req["run_id"],
                           meta.get("finish_reason") or "研究完成")

    def _finish_request(self, request_id: str, status: str,
                        result: dict[str, Any] | None = None,
                        error: str | None = None) -> None:
        db.execute(
            "UPDATE review_requests SET status=?, result_json=?, error=?,"
            " updated_at=? WHERE id=?",
            (status, json.dumps(result, ensure_ascii=False) if result else None,
             error, db.utcnow(), request_id))
        fut = self._question_waiters.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(None)  # 唤醒 executor_question 等待者去读结果
        # 收尾整理审阅完结（无论成败，含暂停中完结）→ 执行被推迟的 finish，防死锁
        self._maybe_finalize_after_curation(request_id)

    # ---------- 生命周期 Decision（旧协议，同一 worker 入口）----------
    def _lifecycle_packet(self, run: Any, trigger: str,
                          user_guidance: str | None = None) -> dict[str, Any]:
        run_id = run["id"]
        settings = config.load_settings()
        auth = db.query_one("SELECT * FROM authorizations WHERE id=?",
                            (run["authorization_id"],)) \
            if run["authorization_id"] else None
        defaults = settings["run_defaults"]
        active_tid = self._active_trial_id(run)
        if active_tid:
            trial = db.query_one("SELECT * FROM trials WHERE id=?", (active_tid,))
        else:
            trial = db.query_one("SELECT * FROM trials WHERE run_id=?"
                                 " ORDER BY rowid DESC LIMIT 1", (run_id,))
        recent = db.events_after(run_id, max(0, self._last_seq(run_id) - 20))
        packet = {
            "run_id": run_id,
            "state_version": run["state_version"],
            "trigger": trigger,
            "current_intention": run["intention"],
            "trial_summary": {"trial_id": trial["id"], "status": trial["status"],
                              "goal": trial["goal"]} if trial else None,
            "current_trial_id": trial["id"] if trial else None,
            "latest_trial_status": trial["status"] if trial else None,
            "trial_count": len(db.query("SELECT id FROM trials WHERE run_id=?",
                                        (run_id,))),
            "challenge_id": run["challenge_id"],
            "user_guidance": user_guidance,
            "new_events_since_last_review": [
                {"seq": e["seq"], "source": e["source"], "type": e["type"],
                 **observation.event_excerpt(e)}
                for e in recent][-20:],
            "budget_remaining": {
                "brain_reviews": defaults["max_brain_reviews"]
                - run["brain_reviews_used"],
                "model_turns": (auth["max_model_turns"] if auth else 0),
            },
            "experience_manifest": self._memory_manifest(run, settings),
        }
        # 题目信息进帧：大脑开局必须亲自核实任务要素（数据/工具链/评分契约），
        # 不再只能依赖执行器转述（2026-09-19：大脑因帧内无题面，
        # 把执行器「PyPI/bohr 查无」误当「资源不可得」）
        challenge = db.query_one("SELECT * FROM challenges WHERE id=?",
                                 (run["challenge_id"],))
        if challenge:
            slug = challenge["platform_challenge_id"]
            try:
                resources = (json.loads(challenge["resources_json"])
                             if challenge["resources_json"] else None)
            except (json.JSONDecodeError, TypeError):
                resources = None
            packet["challenge"] = {
                "id": challenge["id"],
                "title": challenge["title"],
                "platform_url": (f"https://play.bohrium.com/challenge/{slug}"
                                 if slug else None),
                "resources": resources,
            }
            if trigger in ("run_start", "recovery"):
                # 开局/恢复帧带完整题面（含工具链 quickstart 与评分契约）
                packet["challenge"]["content"] = challenge["content"]
        if trigger == "curation":
            # 收尾整理：给大脑本题全部经验正文与效果回联（只在此时给，
            # 平时的帧不带——A12）
            packet["curation"] = self._curation_payload(run)
        return packet

    def _last_seq(self, run_id: str) -> int:
        row = db.query_one("SELECT COALESCE(MAX(seq),0) AS s FROM events WHERE run_id=?",
                           (run_id,))
        return row["s"]

    def _memory_manifest(self, run: Any, settings: dict[str, Any]) -> list[dict[str, Any]]:
        listing = experiences.list_experiences(
            scope=None, challenge_id=run["challenge_id"])
        manifest = []
        for item in listing["items"]:
            if item["status"] != "active":
                continue
            manifest.append({"id": item["id"], "revision_hash": item["revision_hash"],
                             "scope": item["scope"],
                             "evidence_status": item["evidence_status"],
                             "title": item["title"]})
        return manifest[:settings["memory"]["max_global_entries"]
                        + settings["memory"]["max_challenge_entries"]]

    @staticmethod
    def _active_trial_id(run: Any) -> str | None:
        tid = run["current_trial_id"]
        if not tid:
            return None
        t = db.query_one("SELECT status FROM trials WHERE id=?", (tid,))
        return tid if (t and t["status"] == "active") else None

    def _has_active_trial(self, run: Any) -> bool:
        return self._active_trial_id(run) is not None

    async def _apply_decision(self, run_id: str, dec: dict[str, Any],
                              packet: dict[str, Any], brain: BrainRuntime,
                              b_session: Any) -> None:
        run = self._require_run(run_id)
        settings = config.load_settings()
        defaults = settings["run_defaults"]
        structural = decision_mod.validate_structure(dec)
        db.append_event(run_id, "brain", "brain.decision",
                        {"decision_id": dec.get("decision_id"),
                         "summary": dec.get("summary", "")[:500],
                         "actions": [a.get("op") for a in dec.get("actions", [])]})
        if structural:
            # 容错（与 ReviewResult salvage 同一原则）：经验提议是注释性内容，
            # 剔除非法提议后重验——一个坏 kind 不该陪葬 finish 等主决定。
            # 被剔除的提议全文进事件流，大脑下一帧可见并可用合法 kind 重提。
            proposals = dec.get("experience_proposals")
            if isinstance(proposals, list) and proposals:
                kept = [p for p in proposals if not decision_mod.validate_structure(
                    {**dec, "experience_proposals": [p]})]
                if len(kept) < len(proposals):
                    dropped = [p for p in proposals if p not in kept]
                    dec = {**dec, "experience_proposals": kept}
                    db.append_event(run_id, "brain", "brain.decision_salvaged", {
                        "decision_id": dec.get("decision_id"),
                        "dropped_proposals": dropped,
                        "notice": "非法经验提议已剔除（原文保留于此事件）；"
                                  "Decision 其余部分继续执行"})
                    structural = decision_mod.validate_structure(dec)
        if structural:
            db.append_event(run_id, "brain", "brain.decision_rejected",
                            {"reasons": structural})
            return
        if dec["observed_state_version"] < run["state_version"]:
            db.append_event(run_id, "brain", "brain.decision_stale", {
                "detail": f"判断基于 state_version={dec['observed_state_version']}，"
                          f"当前 {run['state_version']}；保存但不执行"})
            return
        current_tid = run["current_trial_id"]
        stalled_tid = None
        reported_tid = None
        if current_tid:
            t = db.query_one("SELECT status FROM trials WHERE id=?", (current_tid,))
            if t and t["status"] == "stalled":
                stalled_tid = current_tid
            elif t and t["status"] == "reported_complete":
                reported_tid = current_tid
        # 逐动作放行：语义问题只拒单个动作（原因进事件流，大脑下一帧可见并自我纠正），
        # 不再整单拒收
        sem_ctx = dict(has_active_trial=self._has_active_trial(run),
                       current_trial_id=self._active_trial_id(run),
                       allow_formal_submission=settings["policy"]["allow_formal_submission"],
                       stalled_trial_id=stalled_tid,
                       reported_trial_id=reported_tid)

        for proposal in dec.get("experience_proposals", [])[:3]:
            self._apply_experience_proposal(run_id, dec["decision_id"], proposal)

        prime_sid = self._prime_sessions.get(run_id)
        prime = self._prime_instances.get(run_id) or self._make_prime(settings)
        direction_used = False
        for action in dec["actions"]:
            op = action["op"]
            errs = decision_mod.validate_semantics(
                {**dec, "actions": [action]}, **sem_ctx)
            if errs:
                db.append_event(run_id, "brain", "brain.action_rejected",
                                {"op": op, "reasons": errs})
                continue
            if op in decision_mod.DIRECTION_OPS:
                if direction_used:
                    db.append_event(run_id, "brain", "brain.action_rejected", {
                        "op": op,
                        "reason": "同一 Decision 最多一个改变运行方向的主动作"})
                    continue
                direction_used = True
            if op == "start_trial":
                if run["gate"] != "open":
                    db.append_event(run_id, "brain", "brain.action_rejected", {
                        "op": op,
                        "reason": f"研究门禁为 {run['gate']}；等待解除"})
                    continue
                # 有界授权：Trial 数上限
                trial_count = len(db.query("SELECT id FROM trials WHERE run_id=?",
                                           (run_id,)))
                if trial_count >= defaults["max_trials"]:
                    db.append_event(run_id, "brain", "brain.action_rejected", {
                        "op": op,
                        "reason": f"达到 Trial 上限 {defaults['max_trials']}；"
                                  f"需要新 Trial 请结束当前 Run 重新授权"})
                    continue
                trial_id = _rid("trial")
                parent = run["current_trial_id"]
                with db.transaction() as conn:
                    conn.execute(
                        "INSERT INTO trials(id, run_id, parent_trial_id, goal,"
                        " success_check, status, created_at)"
                        " VALUES(?,?,?,?,?,'active',?)",
                        (trial_id, run_id, parent, action["goal"],
                         action["success_check"], db.utcnow()))
                    conn.execute(
                        "UPDATE runs SET current_trial_id=?, intention=?,"
                        " gate='open' WHERE id=?",
                        (trial_id, action["goal"], run_id))
                    db.append_event_tx(conn, run_id, "controller",
                                       "trial.created",
                                       {"trial_id": trial_id,
                                        "goal": action["goal"]},
                                       trial_id=trial_id)
                self._snapshot_memory(run_id, trial_id, settings)
                enabled_skills = skills_mod.effective_for(
                    db.get_db(), settings, run["challenge_id"])
                task_text = (f"目标：{action['goal']}\n"
                             f"成功判据：{action['success_check']}\n"
                             f"经验库目录：{config.EXPERIENCE_DIR}"
                             f"（global/ 与 challenges/{run['challenge_id']}/ 下"
                             f" status=active 的经验，开工前必读）"
                             f"{executor_instruction_suffix()}"
                             f"{skills_mod.prompt_segment(enabled_skills)}")
                if enabled_skills:
                    db.append_event(run_id, "controller",
                                    "trial.skills_enabled",
                                    {"skills": [s["id"] for s in enabled_skills],
                                     "trial_id": trial_id},
                                    trial_id=trial_id)
                receipt = await prime.prompt(prime_sid, task_text)
                self._executor_busy[run_id] = receipt.status == "accepted"
                db.append_event(run_id, "prime", "prime.task_accepted",
                                {"status": receipt.status, "detail": receipt.detail},
                                trial_id=trial_id)
                if receipt.status == "accepted":
                    starter = self._start_pump.get(run_id)
                    if starter:
                        starter()
            elif op == "steer":
                # A5：不再依赖回合内 steer；进入可靠指导 outbox
                with db.transaction() as conn:
                    # 大脑裁决 stalled Trial 继续：恢复原位（会话与现场未丢）
                    conn.execute(
                        "UPDATE trials SET status='active' WHERE id=?"
                        " AND status='stalled'", (action["trial_id"],))
                    gid = collab.create_guidance(
                        conn, run_id, source="requested",
                        g={"kind": "steer", "intent": "continue",
                           "text_md": action["message"],
                           "reason_md": "大脑生命周期判断",
                           "evidence_refs": [],
                           "expected_change_md": "按指导调整当前研究动作",
                           "revisit_when_md": "指导不适用或有反证"},
                        target_trial_id=action["trial_id"],
                        review_request_id=None, frame_id=None,
                        state_version=run["state_version"],
                        evidence_revision=0, shadow_epoch=0)
                    db.append_event_tx(conn, run_id, "brain",
                                       "guidance.queued",
                                       {"guidance_id": gid, "kind": "steer",
                                        "via": "lifecycle_decision"},
                                       trial_id=action["trial_id"])
                if not self._executor_busy.get(run_id):
                    await self._deliver_queued_guidance(run_id)
            elif op == "wait":
                db.append_event(run_id, "brain", "brain.wait",
                                {"reason": action["reason"]})
            elif op == "pause":
                db.execute("UPDATE runs SET phase='pausing' WHERE id=?", (run_id,))
                db.append_event(run_id, "controller", "run.pausing",
                                {"reason": action["reason"],
                                 "notice": "正在暂停；已有远程任务可能继续运行/计费"})
                q = self._signals.get(run_id)
                if q:
                    await q.put({"type": "pause"})
            elif op == "finish":
                # Run 终态前先自动整理本题经验（一轮 curation 生命周期审阅），
                # 审阅完结（done/error/obsolete）后由 _finish_request 钩子收尾；
                # 额度用尽或已在整理则直接收尾，防死锁
                if self._defer_finish_for_curation(run_id, action["reason"]):
                    db.append_event(run_id, "controller", "run.finish_deferred",
                                    {"notice": "先进行本题经验整理审阅，"
                                               "随后自动收尾"})
                    continue
                self._finalize_run(run_id, action["reason"])
            elif op == "promote_experience":
                self._promote(run_id, action)
            elif op in ("refresh_platform", "request_submission"):
                db.append_event(run_id, "brain", "brain.action_deferred", {
                    "op": op, "detail": "阶段 2 能力：真实平台核对/提交尚未接入"})

    def _apply_experience_proposal(self, run_id: str | None, decision_id: str,
                                   proposal: dict[str, Any]) -> None:
        """经验落库（自进化闭环的唯一写入点，Run 内与全局整理共用）。

        题内提议直接落 active（无审查门槛）；全局落 candidate 待用户审批。
        带 target_id = 更新已有条目：追加新修订（冲突即更新，不拒绝）；
        更新全局 active 条目时内容落修订但状态回 candidate，待用户复核。
        """
        target_id = proposal.get("target_id")
        prior: dict[str, Any] | None = None
        try:
            if target_id:
                try:
                    prior = experiences.get_experience(target_id)
                except experiences.ExperienceError:
                    if run_id:
                        db.append_event(run_id, "brain", "brain.action_rejected", {
                            "op": "experience_proposal",
                            "reason": f"target_id {target_id} 不存在；"
                                      f"如需新建请去掉 target_id"})
                    return
                exp_id = target_id
                scope = prior["frontmatter"]["scope"]  # 范围以既有条目为准
                challenge_id = prior["frontmatter"].get("challenge_id")
                kind = proposal.get("kind") or prior["frontmatter"].get(
                    "kind") or "heuristic"
                evidence_refs = sorted(set(
                    prior["frontmatter"].get("evidence_refs", [])
                    + proposal.get("evidence_refs", [])))
                base_hash: str | None = prior["current_hash"]
            else:
                exp_id = _rid("exp")
                scope = proposal["scope"]
                if run_id and scope == "challenge":
                    # 题内提议不信任模型自报的 challenge_id：
                    # 强制绑定当前 Run 的题目，写错题时如实记事件
                    challenge_id = self._require_run(run_id)["challenge_id"]
                    declared = proposal.get("challenge_id")
                    if declared not in (None, challenge_id):
                        db.append_event(
                            run_id, "brain", "experience.proposal_rebound", {
                                "declared_challenge_id": declared,
                                "bound_challenge_id": challenge_id,
                                "notice": "题内提议的 challenge_id 已强制绑定"
                                          "当前 Run 题目，不信任模型自报值"})
                else:
                    challenge_id = proposal.get("challenge_id")
                kind = proposal.get("kind") or "heuristic"
                evidence_refs = proposal.get("evidence_refs", [])
                base_hash = None
            is_global = scope == "global"
            fm = {"title": proposal["title"], "scope": scope,
                  "challenge_id": None if is_global else challenge_id,
                  "status": "candidate" if is_global else "active",
                  "evidence_status": "hypothesis" if is_global else "observed",
                  "kind": kind,
                  "applicability": proposal["applicability"],
                  "evidence_refs": evidence_refs}
            experiences.save_experience(
                exp_id, fm, proposal["body_md"], operator="brain",
                reason=f"Decision {decision_id} "
                       f"{'更新' if target_id else '提议'}",
                base_hash=base_hash)
            if run_id:
                db.append_event(
                    run_id, "brain",
                    "experience.updated" if target_id else "experience.proposed",
                    {"experience_id": exp_id, "title": proposal["title"],
                     "scope": scope, "status": fm["status"],
                     "notice": ("全局经验待用户在经验页审批后生效"
                                if is_global else "题内经验即时生效")})
        except experiences.ExperienceError as exc:
            if run_id:
                db.append_event(run_id, "brain", "experience.proposal_rejected",
                                {"reason": str(exc)[:200]})

    def _promote(self, run_id: str, action: dict[str, Any]) -> None:
        try:
            exp = experiences.get_experience(action["experience_id"])
            scope = exp["frontmatter"]["scope"]
            if scope == "global":
                db.append_event(run_id, "brain", "brain.action_rejected", {
                    "op": "promote_experience",
                    "reason": "全局经验由用户在前端经验页审批；大脑无需晋升"})
                return
            # 陈旧视图保护：大脑看到的是旧修订时不覆盖别人/自己的新改动
            if action.get("revision_hash") and \
                    action["revision_hash"] != exp["current_hash"]:
                db.append_event(run_id, "brain", "brain.action_rejected", {
                    "op": "promote_experience",
                    "reason": "revision_hash 与当前修订不一致；请重新读取后再操作"})
                return
            fm = dict(exp["frontmatter"])
            fm["status"] = "active"
            fm["evidence_status"] = "observed"
            fm["evidence_refs"] = sorted(set(
                fm.get("evidence_refs", []) + action["evidence_refs"]))
            experiences.save_experience(action["experience_id"], fm, exp["body_md"],
                                        operator="brain",
                                        reason=f"晋升: {action['reason']}",
                                        base_hash=exp["current_hash"])
            db.append_event(run_id, "brain", "experience.activated",
                            {"experience_id": action["experience_id"]})
        except experiences.ExperienceError as exc:
            db.append_event(run_id, "brain", "brain.action_rejected",
                            {"op": "promote_experience", "reason": str(exc)[:200]})

    # ---------- 经验闭环：收尾整理 / 效果回联 / 全局整理 ----------
    def _finalize_run(self, run_id: str, reason: str) -> None:
        self._record_experience_snapshot(run_id, "at_end")
        with db.transaction() as conn:
            conn.execute("UPDATE runs SET phase='finished', ended_at=?"
                         " WHERE id=?", (db.utcnow(), run_id))
            collab.revoke_run_tokens(conn, run_id)
            db.append_event_tx(conn, run_id, "controller",
                               "run.finished", {"reason": reason})
        q = self._signals.get(run_id)
        if q:
            q.put_nowait({"type": "terminate"})

    def _defer_finish_for_curation(self, run_id: str, reason: str) -> bool:
        """Run 终态前先整理本题经验：需要且能整理则排 curation 审阅并推迟
        finish（返回 True）；审阅完结后由 _finish_request 钩子收尾。"""
        done = db.query_one(
            "SELECT id FROM review_requests WHERE run_id=?"
            " AND trigger='curation' AND status IN ('done','error','obsolete')",
            (run_id,))
        if done:
            return False
        pending = db.query_one(
            "SELECT id FROM review_requests WHERE run_id=?"
            " AND trigger='curation' AND status IN ('pending','running')",
            (run_id,))
        if pending:
            return True
        run = self._require_run(run_id)
        defaults = config.load_settings()["run_defaults"]
        if run["brain_reviews_used"] >= defaults["max_brain_reviews"]:
            db.append_event(run_id, "controller", "run.curation_skipped",
                            {"reason": "大脑判断额度用尽，直接收尾"})
            return False
        review_id = self._enqueue_lifecycle(run_id, trigger="curation")
        db.execute("UPDATE review_requests SET frame_json=? WHERE id=?",
                   (json.dumps({"finish_after": True, "finish_reason": reason},
                               ensure_ascii=False), review_id))
        return True

    def _record_experience_snapshot(self, run_id: str, key: str) -> None:
        """效果回联原料：Run 起止时各记一份 active 经验版本清单。"""
        run = self._require_run(run_id)
        settings = config.load_settings()
        manifest = self._memory_manifest(run, settings)
        try:
            snap = json.loads(run["experience_snapshot"]) \
                if run["experience_snapshot"] else {}
        except (json.JSONDecodeError, TypeError):
            snap = {}
        snap[key] = {"recorded_at": db.utcnow(), "items": manifest}
        db.execute("UPDATE runs SET experience_snapshot=? WHERE id=?",
                   (json.dumps(snap, ensure_ascii=False), run_id))

    def _experience_usage(self, challenge_id: str) -> dict[str, Any]:
        """题目粒度效果回联：经验 id → 使用过它的 Run 与已知最好分数。
        只如实记录，不做任何自动评分规则——判断归大脑。"""
        usage: dict[str, list[dict[str, Any]]] = {}
        runs = db.query(
            "SELECT id, phase, experience_snapshot FROM runs"
            " WHERE challenge_id=?", (challenge_id,))
        for r in runs:
            if not r["experience_snapshot"]:
                continue
            try:
                snap = json.loads(r["experience_snapshot"])
            except (json.JSONDecodeError, TypeError):
                continue
            best = db.query_one(
                "SELECT MAX(score) AS s FROM submissions"
                " WHERE run_id=? AND score_status='scored'", (r["id"],))
            seen = {it.get("id") for part in ("at_start", "at_end")
                    for it in ((snap.get(part) or {}).get("items") or [])}
            for exp_id in seen:
                if exp_id:
                    usage.setdefault(exp_id, []).append(
                        {"run_id": r["id"], "phase": r["phase"],
                         "best_score": best["s"] if best else None})
        return usage

    @staticmethod
    def _experience_entries_with_bodies(items: list[dict[str, Any]],
                                        limit: int = 1500) -> list[dict[str, Any]]:
        entries = []
        for item in items:
            try:
                full = experiences.get_experience(item["id"])
                body = full["body_md"][:limit]
                note = full["frontmatter"].get("review_note")
            except experiences.ExperienceError:
                body, note = "", None
            entries.append({"id": item["id"], "title": item["title"],
                            "status": item["status"],
                            "evidence_status": item["evidence_status"],
                            "kind": item["kind"], "body_md": body,
                            "review_note": note})
        return entries

    def _curation_payload(self, run: Any) -> dict[str, Any]:
        """Run 收尾整理素材：本题全部经验（含正文节选与驳回批注）+ 效果回联。"""
        challenge_id = run["challenge_id"]
        listing = experiences.list_experiences(scope="challenge",
                                               challenge_id=challenge_id)
        return {"scope": "challenge", "challenge_id": challenge_id,
                "experiences": self._experience_entries_with_bodies(
                    listing["items"]),
                "usage": self._experience_usage(challenge_id)}

    async def curate_global_experience(self, challenge_ids: list[str]) -> dict:
        """手动触发全局经验整理：无 Run 的一次性大脑会话。素材=全局条目
        （含待审批与驳回批注）+ 入选题目的题内经验与使用回联。
        产出仍走 proposal 规则：全局落 candidate 待用户审批。"""
        if self.global_curation_status().get("state") == "running":
            raise ControllerError("CURATION_RUNNING",
                                  "全局经验整理正在进行", False)
        self._global_curation = {"state": "running",
                                 "started_at": db.utcnow(),
                                 "challenge_ids": challenge_ids}
        self._persist_global_curation()
        asyncio.get_event_loop().create_task(
            self._run_global_curation(list(challenge_ids)))
        return dict(self._global_curation)

    @staticmethod
    def _curation_state_path() -> Path:
        return config.DATA_DIR / "global_curation.json"

    def _persist_global_curation(self) -> None:
        """状态落盘：重启后前端能对账到真实状态，而不是永远停在「整理中」。"""
        path = self._curation_state_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._global_curation, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(path)

    def _load_global_curation(self) -> dict[str, Any]:
        """读持久化状态。running 只可能是旧进程残留（任务随进程消失），
        如实转为 failed/interrupted 并回写，不伪造仍在进行。"""
        try:
            data = json.loads(
                self._curation_state_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        if data.get("state") == "running":
            data = {**data, "state": "failed", "finished_at": db.utcnow(),
                    "interrupted": True,
                    "error": "后端重启，全局整理被中断"}
            self._global_curation = data
            try:
                self._persist_global_curation()
            except OSError:
                pass
        return data

    def global_curation_status(self) -> dict[str, Any]:
        if self._global_curation:
            return dict(self._global_curation)
        return self._load_global_curation()

    async def _run_global_curation(self, challenge_ids: list[str]) -> None:
        # 整个函数体纳入兜底：load_settings/_make_brain/会话建立任何一步
        # 失败都必须终态化，否则状态永远停在 running，前端永远「整理中」
        session = None
        brain: BrainRuntime | None = None
        try:
            settings = config.load_settings()
            brain = self._make_brain(settings)
            work = (config.WORKSPACE_DIR / "curation"
                    / db.utcnow().replace(":", "-").replace("+", "Z"))
            work.mkdir(parents=True, exist_ok=True)
            session = await brain.open({"working_directory": str(work)})
            listing = experiences.list_experiences(scope="global")
            packet = {
                "trigger": "global_curation",
                "instruction": "整理全局经验库：阅读下列全局条目（含待审批与驳回"
                               "批注）与入选题目的题内经验及使用结果，决定新建/"
                               "更新(target_id)/不变。全局产出落 candidate，由用户"
                               "审批；被驳回的条目参考 review_note 重写或放弃。",
                "global_experiences":
                    self._experience_entries_with_bodies(listing["items"]),
                "challenges": [
                    {"challenge_id": cid,
                     "experiences": self._experience_entries_with_bodies(
                         experiences.list_experiences(
                             scope="challenge", challenge_id=cid)["items"]),
                     "usage": self._experience_usage(cid)}
                    for cid in challenge_ids],
            }
            decision: dict[str, Any] | None = None
            error_msg: str | None = None
            async for ev in brain.review(session, packet):
                if ev.type == "decision":
                    decision = ev.payload["decision"]
                elif ev.type == "error":
                    error_msg = ev.payload.get("message", "")
            if decision is None:
                raise ControllerError(
                    "BRAIN_ERROR",
                    f"大脑未产出整理决策: {error_msg or '无结果'}", False)
            errs = decision_mod.validate_structure(decision)
            if errs:
                raise ControllerError("INVALID_DECISION",
                                      "; ".join(errs)[:300], False)
            applied = 0
            for proposal in decision.get("experience_proposals", [])[:3]:
                self._apply_experience_proposal(
                    None, decision["decision_id"], proposal)
                applied += 1
            self._global_curation = {
                "state": "done", "finished_at": db.utcnow(),
                "challenge_ids": challenge_ids,
                "summary": decision.get("summary", "")[:500],
                "proposals_applied": applied}
        except Exception as exc:  # noqa: BLE001
            log.exception("全局经验整理失败")
            self._global_curation = {"state": "failed",
                                     "finished_at": db.utcnow(),
                                     "error": str(exc)[:300]}
        finally:
            try:
                self._persist_global_curation()
            except OSError:
                pass
            if session is not None and brain is not None:
                try:
                    await brain.close(session)
                except Exception:  # noqa: BLE001
                    pass

    def _snapshot_memory(self, run_id: str, trial_id: str,
                         settings: dict[str, Any]) -> None:
        run_dir = config.WORKSPACE_DIR / "runs" / run_id
        trial_dir = run_dir / "trials" / trial_id
        trial_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._memory_manifest(self._require_run(run_id), settings)
        (trial_dir / "memory_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 查询 ----------
    def _require_run(self, run_id: str) -> Any:
        run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if not run:
            raise ControllerError("NOT_FOUND", f"Run 不存在: {run_id}", False)
        return run

    def supervision_status(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        sup = db.query_one("SELECT * FROM supervision WHERE run_id=?", (run_id,))
        cfg = self._shadow_cfg(run)
        pending_reqs = db.query(
            "SELECT id, source, blocking, status, trigger, created_at"
            " FROM review_requests WHERE run_id=?"
            " AND status IN ('pending','running') ORDER BY created_at",
            (run_id,))
        guidance_rows = db.query(
            "SELECT id, kind, intent, status, text_md, target_trial_id,"
            " ack_disposition, created_at FROM guidance WHERE run_id=?"
            " ORDER BY created_at DESC LIMIT 20", (run_id,))
        brain_running = db.query_one(
            "SELECT id FROM review_requests WHERE run_id=?"
            " AND status='running'", (run_id,)) is not None
        d = dict(sup) if sup else {"enabled": 0, "shadow_epoch": 0,
                                   "covered_seq": 0, "reviews_used": 0,
                                   "private_note_md": "", "watchlist": "[]",
                                   "degraded": 0, "degrade_reason": None,
                                   "last_review_at": None,
                                   "evidence_revision": 0}
        d["watchlist"] = json.loads(d.get("watchlist") or "[]")
        d["max_reviews"] = cfg["max_reviews"]
        d["brain_busy"] = brain_running
        d["gate"] = run["gate"]
        d["executor_busy"] = self._executor_busy.get(run_id, False)
        d["pending_requests"] = [dict(r) for r in pending_reqs]
        d["guidance"] = [dict(g) for g in guidance_rows]
        d["latest_seq"] = self._last_seq(run_id)
        return d

    def run_snapshot(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        trials = [dict(t) for t in db.query(
            "SELECT * FROM trials WHERE run_id=? ORDER BY created_at", (run_id,))]
        d = dict(run)
        d["config_snapshot"] = json.loads(d["config_snapshot"])
        d["trials"] = trials
        d["budget"] = self._budget_status(run)
        return d

    def _run_minutes_exceeded(self, run: Any) -> bool:
        settings = config.load_settings()
        auth = db.query_one("SELECT * FROM authorizations WHERE id=?",
                            (run["authorization_id"],)) if run["authorization_id"] else None
        minutes = auth["max_run_minutes"] if auth else 0
        if not minutes or not run["started_at"]:
            return False
        started = _parse_ts(run["started_at"])
        if started is None:
            return False
        import time as _time
        return (_time.time() - started) > minutes * 60

    def _budget_status(self, run: Any) -> dict[str, Any]:
        settings = config.load_settings()
        defaults = settings["run_defaults"]
        auth = db.query_one("SELECT * FROM authorizations WHERE id=?",
                            (run["authorization_id"],)) if run["authorization_id"] else None
        return {
            "brain_reviews_used": run["brain_reviews_used"],
            "max_brain_reviews": defaults["max_brain_reviews"],
            "trials_used": len(db.query("SELECT id FROM trials WHERE run_id=?",
                                        (run["id"],))),
            "max_trials": defaults["max_trials"],
            "run_minutes_limit": auth["max_run_minutes"] if auth else 0,
            "run_minutes_exceeded": self._run_minutes_exceeded(run),
            "model_turns": {"limit": auth["max_model_turns"] if auth else 0,
                            "used": 0,
                            "known_cost": None, "unknown_cost": True,
                            "enforced": False,
                            "note": "阶段 1 无真实模型调用路径；真实往返接入后强制"},
            "max_submissions": auth["max_submissions"] if auth else 0,
            "max_jobs": auth["max_jobs"] if auth else 0,
        }

    def list_runs(self) -> list[dict[str, Any]]:
        rows = db.query("SELECT * FROM runs ORDER BY created_at DESC")
        out = []
        for r in rows:
            d = dict(r)
            d.pop("config_snapshot", None)
            out.append(d)
        return out


def executor_instruction_suffix() -> str:
    """执行器协作指令片段（prompts/collaboration/executor.md）。"""
    path = (Path(__file__).resolve().parent.parent.parent
            / "prompts" / "collaboration" / "executor.md")
    try:
        return "\n\n" + path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
