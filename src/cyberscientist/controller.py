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
import re
import uuid
from pathlib import Path
from typing import Any

import jsonschema

from . import collab, config, datasets, db, decision as decision_mod, experiences, mailboxes, observation, experience_context
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
_SHADOW_TRIGGERS = ("job.observed", "job.unknown", "submission.scored", "submission.score_corrected", "checkpoint.created", "trial.reported_complete",
                    "trial.stalled", "trial.done", "prime.error")

_SPARSE_SHADOW_EVENTS = (
    "trial.stalled", "trial.done", "trial.reported_complete",
    "submission.scored", "submission.score_corrected", "run.blocked",
    "prime.error", "job.unknown", "job.observed",
)
_RESEARCH_JOB_STATES = frozenset(("Failed", "Stopped", "Finished"))
_RESEARCH_TRIAL_EVENTS = frozenset((
    "trial.stalled", "trial.done", "trial.reported_complete"))


def _is_sparse_brain_trigger(event_type: str, payload: dict[str, Any],
                             previous_state: str | None = None) -> bool:
    """Only durable research transitions wake sparse shadow supervision."""
    if event_type == "job.observed":
        status = payload.get("status")
        return (bool(payload.get("operation_id")) and
                status in _RESEARCH_JOB_STATES and
                status != previous_state)
    if event_type == "job.unknown":
        return previous_state != "unknown"
    if event_type in _RESEARCH_TRIAL_EVENTS:
        return event_type != previous_state
    return event_type in _SPARSE_SHADOW_EVENTS


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


def _runtime_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Public runtime evidence only, bounded and scrubbed before persistence."""
    from .bohr_proxy import redact

    secrets = [value for value in config.load_secrets().values() if isinstance(value, str)]

    def safe_text(value: str) -> str:
        value = observation.strip_secrets(redact(value, secrets))
        return re.sub(
            r"([?&](?:access_?key|api_?key|access_?token|token|secret|authorization|key)=)[^&\s\"'<>]+",
            r"\1[REDACTED]", value, flags=re.IGNORECASE)

    def clean(value: Any, budget: list[int], depth: int = 0) -> Any:
        if budget[1] <= 0 or depth > 6:
            return "[truncated]"
        budget[1] -= 1
        if isinstance(value, str):
            text = safe_text(value)
            if len(text) > budget[0]:
                text = text[:max(0, budget[0] - 11)] + "[truncated]" if budget[0] >= 11 else ""
            budget[0] -= len(text)
            return text
        if isinstance(value, dict):
            result = {safe_text(str(key))[:128]: clean(item, budget, depth + 1)
                      for key, item in list(value.items())[:32]}
            if len(value) > 32:
                result["_truncated"] = True
            return result
        if isinstance(value, list):
            result = [clean(item, budget, depth + 1) for item in value[:32]]
            return result + (["[truncated]"] if len(value) > 32 else [])
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return "[unsupported]"

    limits = {"detail": 4000, "status": 128, "exit_code": 128, "item_id": 256,
              "output": 12000, "usage": 12000, "error": 4000,
              "text": 2000, "message": 2000}
    return {name: clean(payload[name], [limit, 64])
            for name, limit in limits.items() if name in payload}


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
    def _runtime_settings(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        snapshot = json.loads(run["config_snapshot"])
        settings = snapshot["settings"]
        settings["app"]["mode"] = run["mode"]
        settings["run_defaults"] = config.load_settings()["run_defaults"]
        return settings

    @staticmethod
    def _sparse_brain(run: Any) -> bool:
        return json.loads(run["config_snapshot"]).get("sparse_brain_version") == 1

    def _brain_spec(self, run_id: str, settings: dict[str, Any],
                    brain_dir: Path) -> dict[str, Any]:
        """New Runs get a brain-only read capability; old Runs keep their snapshot."""
        run = self._require_run(run_id)
        if not self._sparse_brain(run):
            enabled = skills_mod.effective_for(db.get_db(), settings, run["challenge_id"])
            return {"working_directory": str(brain_dir),
                    "instructions": skills_mod.prompt_segment(enabled)}
        import sys as _sys
        from .codex_protocol import native_brain_environment
        with db.transaction() as conn:
            collab.revoke_role_tokens(conn, run_id, "brain")
            gen = conn.execute("SELECT COUNT(*) AS n FROM capability_tokens"
                               " WHERE run_id=? AND role='brain'", (run_id,)).fetchone()["n"] + 1
            token = collab.issue_token(conn, run_id, "brain", "brain-session", gen)
        app_cfg = settings["app"]
        variables = {"CS_TOOL_TOKEN": token, "CS_TOOL_ROLE": "brain",
                     "CS_API_URL": f"http://{app_cfg['host']}:{app_cfg['port']}"}
        return {"working_directory": str(brain_dir),
                "env": native_brain_environment() | variables,
                "mcp_servers": [{"name": "cyberscientist", "command": _sys.executable,
                                 "args": ["-m", "cyberscientist.mcp_bridge"],
                                 "env": [{"name": k, "value": v}
                                         for k, v in variables.items()]}],
                "instructions": "长期研究会话。仅 research_trace 可按需读取已登记公开记录；"
                                "没有读取必要时直接判断。不要使用通用 Shell、写文件或网络工具。"}

    def _require_model_authorization(self, run_id: str) -> None:
        run = self._require_run(run_id)
        if run["mode"] not in ("demo","connected"):
            raise ControllerError("INVALID_ARGUMENT","未知 Run mode")
        if run["mode"] == "connected":
            auth = db.query_one("SELECT * FROM authorizations WHERE id=? AND run_id=?",
                                (run["authorization_id"],run_id))
            if not auth or not auth["allow_model_calls"]:
                raise ControllerError("NEEDS_AUTHORIZATION","本 Run 未授权真实模型调用")

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
        if runtime in ("kimi", "codex", "prime"):
            # 协作工具桥：项目/会话级 MCP 注入 + 短时能力令牌（不修改全局配置）
            import sys as _sys
            with db.transaction() as conn:
                # 新会话签发前撤销本 Run 旧令牌：旧会话身份随之失效，
                #  ACK/检查点的会话绑定在令牌鉴权层成立
                collab.revoke_role_tokens(conn, run_id, "executor")
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
                    {"name": "CS_TOOL_ROLE", "value": "executor"},
                    {"name": "CS_API_URL",
                     "value": f"http://{app_cfg['host']}:{app_cfg['port']}"},
                ],
            }]
        if runtime == "codex":
            # 会话专用环境；密钥不进入提示词、配置快照或进程参数。
            trial_root = config.WORKSPACE_DIR / "runs" / run_id / "trials"
            trial_root.mkdir(parents=True, exist_ok=True)
            spec["writable_roots"] = [str(trial_root)]
            env = {name: os.environ[name] for name in (
                "HOME", "USER", "LOGNAME", "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR",
                "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR",
                "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
                "OPENAPI_HOST", "TIEFBLUE_HOST",
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                "http_proxy", "https_proxy", "all_proxy", "no_proxy",
            ) if name in os.environ}
            # Account credentials stay in the backend; even a login shell that
            # bypasses PATH's shim cannot inherit our Bohrium key.
            from .bohr_proxy import install_proxy
            proxy = install_proxy(config.WORKSPACE_DIR / "runs" / run_id / "bin")
            env["PATH"] = str(proxy.parent) + os.pathsep + env.get("PATH", "")
            env["CS_API_URL"] = f"http://{settings['app']['host']}:{settings['app']['port']}"
            env["CS_TOOL_TOKEN"] = token
            env["CS_TOOL_ROLE"] = "executor"
            spec["instructions"] = (
                f"所有 Bohrium 操作必须使用受控入口 {proxy} 或 research_job 工具。"
                "不要调用全局 bohr 绕过准入；创建返回 unknown/submitting 时先对账，禁止重复创建。"
                "每个 Job 先准备有限步骤、超时与退出条件；新体系先做有界资源试算。")
            spec["env"] = env
            spec["network_access"] = True
        if runtime == "kimi":
            from .codex_protocol import NATIVE_BRAIN_SHELL_ENV_KEYS
            allowed = (*NATIVE_BRAIN_SHELL_ENV_KEYS, "KIMI_API_KEY", "MOONSHOT_API_KEY")
            spec["env"] = {k: os.environ[k] for k in allowed if k in os.environ}
        if runtime in ("kimi", "prime"):
            from .bohr_proxy import install_proxy
            proxy = install_proxy(config.WORKSPACE_DIR / "runs" / run_id / "bin")
            spec['env']['PATH'] = str(proxy.parent) + os.pathsep + spec['env'].get('PATH', '')
            spec['env']['CS_TOOL_TOKEN'] = token
            spec['env']['CS_TOOL_ROLE'] = "executor"
            spec['env']['CS_API_URL'] = f"http://{settings['app']['host']}:{settings['app']['port']}"
        return spec

    # ---------- Run 生命周期 ----------
    def create_run(self, challenge_id: str, mode: str | None = None,
                   shadow_enabled: bool | None = None) -> dict[str, Any]:
        settings = config.load_settings()
        mode = mode if mode is not None else settings["app"]["mode"]
        if mode not in ("demo", "connected"):
            raise ControllerError("INVALID_ARGUMENT", "mode 必须为 demo 或 connected")
        settings["app"]["mode"] = mode
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
                    "challenge_id": challenge_id, "mode": mode,
                    "compute_policy_version": 1, "sparse_brain_version": 1,
                    "lifecycle_version": 2}
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
                  max_jobs: int = 0, job_limits: dict | None = None,
                  allow_data_download: bool = False,
                  objective: str | None = None) -> dict[str, Any]:
        run = self._require_run(run_id)
        if run["phase"] not in ("created", "blocked"):
            raise ControllerError("INVALID_STATE", f"当前阶段 {run['phase']} 不能授权")
        from .compute import validate_limits
        limits = validate_limits(job_limits)
        if any(type(v) is not int or v < 0 for v in (max_jobs, max_run_minutes, max_submissions, max_model_turns)):
            raise ControllerError('INVALID_ARGUMENT', '预算必须为非负整数')
        auth_id = _rid("auth")
        db.execute(
            "INSERT INTO authorizations(id, run_id, scope, allow_model_calls,"
            " max_model_turns, max_run_minutes, max_submissions, max_jobs,"
            " granted_at, note, job_limits_json,allow_data_download,max_trials)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (auth_id, run_id, scope, int(allow_model_calls), max_model_turns,
             max_run_minutes, max_submissions, max_jobs, db.utcnow(), note, json.dumps(limits),
             int(allow_data_download), config.load_settings()["run_defaults"]["max_trials"]))
        db.execute("UPDATE runs SET authorization_id=?, block_reason=NULL,objective_md=? WHERE id=?",
                   (auth_id, (objective if objective is not None else note), run_id))
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
                         "max_trials": max_trials if not self._lifecycle_v2(run) else None}
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
        if self._lifecycle_v2(run):
            auth_keys["max_trials"] = max_trials
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
        if self._lifecycle_v2(run) and max_trials is not None and run["gate"] == "awaiting_budget":
            used = len(db.query("SELECT id FROM trials WHERE run_id=?", (run_id,)))
            if max_trials > used:
                with db.transaction() as conn:
                    conn.execute("UPDATE runs SET gate='open' WHERE id=? AND gate='awaiting_budget'", (run_id,))
                    db.append_event_tx(conn, run_id, "controller", "run.budget_granted",
                                       {"max_trials": max_trials, "pending_intent": True})
                self._enqueue_lifecycle(run_id, trigger="budget_granted")
        if run_id in self._signals:
            self._signals[run_id].put_nowait({"type": "budget_updated"})
        return {"run_id": run_id, "updated": changes,
                "budget": self._budget_status(self._require_run(run_id))}

    @staticmethod
    def _lifecycle_v2(run: Any) -> bool:
        return json.loads(run["config_snapshot"]).get("lifecycle_version") == 2

    def drop_pending_intent(self, run_id: str, reason: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        if not self._lifecycle_v2(run) or not run["pending_action_json"]:
            raise ControllerError("INVALID_STATE", "没有待处理的 Trial 意图")
        pending = json.loads(run["pending_action_json"])
        with db.transaction() as conn:
            conn.execute("UPDATE runs SET pending_action_json=NULL,gate='open' WHERE id=?", (run_id,))
            db.append_event_tx(conn, run_id, "user", "run.pending_intent_dropped",
                               {"reason": reason[:500], "pending_intent": pending})
        if run["phase"] == "running":
            self._enqueue_lifecycle(run_id, trigger="pending_intent_dropped",
                                    user_guidance=f"用户放弃意图 {json.dumps(pending, ensure_ascii=False)}；原因：{reason[:500]}")
        return self.run_snapshot(run_id)

    async def start_async(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        if run["phase"] != "created":
            raise ControllerError("INVALID_STATE", f"当前阶段 {run['phase']} 不能启动")
        if not run["authorization_id"]:
            raise ControllerError("NEEDS_AUTHORIZATION",
                                  "先保存本轮有界授权（POST /runs/{id}/authorize）")
        self._require_model_authorization(run_id)
        settings = self._runtime_settings(run_id)
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
        if action == "reopen":
            # Explicit recovery from a cancelled Run keeps its original clock,
            # authorization, events and Job ledger. It never dispatches work.
            if run["phase"] == "recovering":
                previous_op = db.query_one(
                    "SELECT run_id,kind FROM operations WHERE operation_id=?",
                    (operation_id,))
                if previous_op and previous_op["run_id"] == run_id \
                        and previous_op["kind"] == "control.reopen":
                    return {"status": "confirmed", "deduplicated": True}
            if run["phase"] != "cancelled" or not run["started_at"]:
                raise ControllerError("INVALID_STATE", "仅已取消且曾启动的 Run 可以重开")
            self._require_model_authorization(run_id)
            if self._run_minutes_exceeded(run):
                raise ControllerError("AUTH_EXPIRED", "原 Run 的时长授权已到期")
            if not text or not text.strip():
                raise ControllerError("INVALID_ARGUMENT", "重开需要记录原因")
            with db.transaction() as conn:
                other = conn.execute(
                    "SELECT id FROM runs WHERE phase IN"
                    " ('created','running','pausing','paused') AND id<>?",
                    (run_id,)).fetchone()
                if other:
                    raise ControllerError("RUN_ACTIVE", f"已有活跃 Run {other['id']}")
                previous = conn.execute(
                    "SELECT ended_at FROM runs WHERE id=? AND phase='cancelled'",
                    (run_id,)).fetchone()
                if not previous:
                    raise ControllerError("INVALID_STATE", "Run 状态已变化")
                inserted = conn.execute(
                    "INSERT OR IGNORE INTO operations(operation_id,run_id,kind,status,"
                    " request_summary,payload_hash,created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (operation_id, run_id, "control.reopen", "confirmed",
                     _redact(text), "", db.utcnow())).rowcount
                if not inserted:
                    existing = conn.execute(
                        "SELECT run_id,kind FROM operations WHERE operation_id=?",
                        (operation_id,)).fetchone()
                    if existing and existing["run_id"] == run_id \
                            and existing["kind"] == "control.reopen":
                        return {"status": "confirmed", "deduplicated": True}
                    raise ControllerError("CONFLICT", "操作 ID 已用于其他动作")
                conn.execute(
                    "UPDATE runs SET phase='recovering', ended_at=NULL,"
                    " block_reason=?, state_version=state_version+1 WHERE id=?",
                    ("已重开；等待原生 recovery 审阅", run_id))
                db.append_event_tx(conn, run_id, "controller", "run.reopened", {
                    "previous_phase": "cancelled", "previous_ended_at": previous["ended_at"],
                    "reason": _redact(text),
                    "notice": "保留原授权、运行时钟与 Job 账本；未自动重提或改写远端任务"})
            return {"status": "confirmed", "detail": "已进入 recovering；请恢复原 Run"}
        if action == "resume":
            self._require_model_authorization(run_id)
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
            self._wake(run_id)
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
                conn.execute("UPDATE runs SET phase='cancelled', ended_at=?,end_reason='user_terminate'"
                             " WHERE id=?", (db.utcnow(), run_id))
                conn.execute("UPDATE trials SET status='interrupted'"
                             " WHERE run_id=?"
                             " AND status IN ('active','stalled')",
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
            pending = [t for t in (task, rtask) if t]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
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
                (observation.strip_secrets(json.dumps(
                    {"question": question}, ensure_ascii=False)), rid))
        self._question_waiters[rid] = fut
        self._wake(run_id)
        try:
            await asyncio.wait_for(fut, timeout=140)
        except asyncio.TimeoutError:
            self._obsolete_request(rid, "原生问题等待超时；迟到答案不得投递")
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
        """One research judgment; full text is saved before native transport."""
        run = self._require_run(run_id)
        defaults = config.load_settings()["run_defaults"]
        if run["brain_reviews_used"] >= defaults["max_brain_reviews"]:
            self._finish_request(
                req["id"], "error",
                error=f"大脑判断额度用尽 {defaults['max_brain_reviews']} 次")
            if req["blocking"]:
                self._blocking_dead_end(run_id, req["id"], "研究问题超出大脑判断额度")
            return
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
        sparse = self._sparse_brain(run)
        cutoff = self._last_seq(run_id)
        sup = db.query_one("SELECT * FROM supervision WHERE run_id=?", (run_id,))
        overview = observation.build_frame(
            run_id, mode="requested", frame_id=_rid("frame"),
            from_seq=(sup["covered_seq"] + 1 if sup else 1),
            through_seq=cutoff, shadow_cfg=self._shadow_cfg(run),
            run_defaults=defaults, sparse=True) if sparse else None
        packet = {
            "protocol": "executor_question",
            "sparse_brain_version": 1 if sparse else 0,
            "request_id": req["id"],
            "run_id": run_id,
            "current_intention": run["intention"],
            "trial_summary": {"trial_id": trial["id"], "goal": trial["goal"],
                              "status": trial["status"]} if trial else None,
            "budget_remaining": {
                "brain_reviews": defaults["max_brain_reviews"]
                - run["brain_reviews_used"] - 1},
            "question": question,
        }
        if self._lifecycle_v2(run):
            packet.pop("current_intention", None)
            packet["run_objective"] = run["objective_md"]
            packet["current_trial_goal"] = trial["goal"] if trial else None
            packet["pending_intent"] = json.loads(run["pending_action_json"]) if run["pending_action_json"] else None
        if sparse:
            auth = db.query_one(
                "SELECT note,max_jobs,max_submissions,max_run_minutes"
                " FROM authorizations WHERE id=?", (run["authorization_id"],)) \
                if run["authorization_id"] else None
            packet["research_state"] = {
                "goal_md": overview["goal_md"],
                "checkpoints": overview["checkpoint_summaries"],
                "compute_jobs": overview["compute_jobs"],
                "data_status": overview["data_status"],
                "known_scores": overview["known_scores"],
                "research_note_md": overview["brain_private_note_md"],
                "watchlist": overview["watchlist"],
                "budget": overview["budget"],
                "authorization": dict(auth) if auth else None,
                "unknown_fields": overview["quality"]["unknown_fields"]}
            packet["trace_access"] = {"tool": "research_trace", "optional": True,
                                      "through_seq": cutoff}
        with db.transaction() as conn:
            conn.execute("UPDATE review_requests SET status='running',"
                         " frame_json=?, frame_id=?, from_seq=?, through_seq=?,"
                         " state_version=?, evidence_revision=?, shadow_epoch=?,"
                         " updated_at=? WHERE id=? AND status='pending'",
                         (json.dumps({"question": question, "packet": packet},
                                     ensure_ascii=False),
                          overview["frame_id"] if overview else _rid("frame"),
                          overview["from_seq"] if overview else 1, cutoff,
                          run["state_version"],
                          sup["evidence_revision"] if sup else 0,
                          sup["shadow_epoch"] if sup else 0,
                          db.utcnow(), req["id"]))
            conn.execute("UPDATE runs SET brain_reviews_used=brain_reviews_used+1"
                         " WHERE id=?", (run_id,))
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
            if ("answer_md" not in answer and isinstance(answer.get("answers"), dict)
                    and answer["answers"]):
                answer = {**answer,
                          "answer_md": answer.get("reason_md") or json.dumps(
                              answer["answers"], ensure_ascii=False),
                          "native_answers": answer["answers"]}
            if not sparse:
                old_answers = answer.get("answers") or answer.get("native_answers")
                valid, why = _validate_question_answer(question, old_answers or {})
                if valid and old_answers:
                    self._finish_request(req["id"], "done", result={
                        "answers": old_answers,
                        "reason_md": answer.get("reason_md", answer.get("answer_md", ""))})
                    db.append_event(run_id, "brain", "brain.question_answered", {
                        "review_id": req["id"], "answers": old_answers})
                    return
                error_msg = f"大脑回答未通过选项校验: {why}"
            else:
                from . import research_trace
                body = answer.get("answer_md")
                refs = answer.get("evidence_refs", [])
                native = answer.get("native_answers")
                if (not isinstance(body, str) or not body.strip() or
                        len(body) > 12000 or not isinstance(refs, list) or
                        len(refs) > 32 or any(not isinstance(x, str) or
                        not research_trace.ref_exists(run_id, x, cutoff) for x in refs) or
                        (answer.get("request_id") not in (None, req["id"]))):
                    error_msg = "研究回答正文、请求 ID 或证据引用无效"
                else:
                    if not isinstance(native, dict) or not _validate_question_answer(
                            question, native)[0]:
                        native = None  # 自由正文不能强行映射到选项。
                    normalized = {"schema_version": 1, "message_type": "research_answer",
                                  "request_id": req["id"],
                                  "answer_md": observation.strip_secrets(body),
                                  "evidence_refs": refs, "native_answers": native}
                    try:
                        collab._validate(normalized, "ResearchAnswer")
                    except collab.CollabError as exc:
                        self._finish_request(req["id"], "error", error=str(exc))
                        return
                    current = self._require_run(run_id)
                    request_now = db.query_one("SELECT status FROM review_requests WHERE id=?",
                                               (req["id"],))
                    if (not request_now or request_now["status"] != "running" or
                            current["phase"] != "running" or
                            current["current_trial_id"] != run["current_trial_id"] or
                            current["state_version"] != run["state_version"]):
                        self._obsolete_request(req["id"], "研究问题已过期；正文未投递")
                        return
                    with db.transaction() as conn:
                        locked_run = conn.execute(
                            "SELECT phase,current_trial_id,state_version FROM runs WHERE id=?",
                            (run_id,)).fetchone()
                        locked_req = conn.execute(
                            "SELECT status FROM review_requests WHERE id=?",
                            (req["id"],)).fetchone()
                        if (not locked_run or locked_run["phase"] != "running" or
                                locked_run["current_trial_id"] != run["current_trial_id"] or
                                locked_run["state_version"] != run["state_version"] or
                                not locked_req or locked_req["status"] != "running"):
                            conn.execute("UPDATE review_requests SET status='obsolete',"
                                         " error=?, updated_at=? WHERE id=?",
                                         ("研究问题已过期；正文未投递", db.utcnow(), req["id"]))
                            fut = self._question_waiters.get(req["id"])
                            if fut is not None and not fut.done():
                                fut.set_result(None)
                            return
                        g = {"kind": "nudge", "intent": "continue",
                             "text_md": f"【研究回答 {req['id']}】\n{normalized['answer_md']}",
                             "reason_md": "执行器研究问题的大脑独立判断",
                             "evidence_refs": refs,
                             "expected_change_md": "据此继续研究或说明异议",
                             "revisit_when_md": "出现新的研究证据时"}
                        gid = collab.create_guidance(
                            conn, run_id, source="requested", g=g,
                            target_trial_id=run["current_trial_id"],
                            review_request_id=req["id"], frame_id=None,
                            state_version=run["state_version"],
                            evidence_revision=sup["evidence_revision"] if sup else 0,
                            shadow_epoch=sup["shadow_epoch"] if sup else 0)
                        normalized["guidance_id"] = gid
                        conn.execute("UPDATE review_requests SET status='done',"
                                     " result_json=?, updated_at=? WHERE id=? AND status='running'",
                                     (json.dumps(normalized, ensure_ascii=False),
                                      db.utcnow(), req["id"]))
                        if req["blocking"]:
                            conn.execute("UPDATE runs SET gate='open' WHERE id=?"
                                         " AND gate IN ('yielding','waiting_brain')", (run_id,))
                            db.append_event_tx(conn, run_id, "controller",
                                               "run.gate_opened", {"review_id": req["id"],
                                                                  "by": "research_answer"})
                        db.append_event_tx(conn, run_id, "brain", "brain.question_answered",
                                           {"review_id": req["id"], "guidance_id": gid,
                                            "native_form": "mapped" if native else "decline",
                                            "answer_md": normalized["answer_md"],
                                            "evidence_refs": refs}, trial_id=run["current_trial_id"])
                        db.append_event_tx(conn, run_id, "brain", "guidance.queued",
                                           {"guidance_id": gid, "kind": "nudge",
                                            "request_id": req["id"]},
                                           trial_id=run["current_trial_id"])
                    fut = self._question_waiters.get(req["id"])
                    if fut is not None and not fut.done():
                        fut.set_result(None)
                    if not self._executor_busy.get(run_id):
                        await self._deliver_queued_guidance(run_id)
                    return
        self._finish_request(req["id"], "error",
                             error=(error_msg or "大脑未给出有效回答")[:300])
        if req["blocking"]:
            self._blocking_dead_end(run_id, req["id"], "研究问题无有效答复")

    def notify_run_change(self, run_id: str) -> None:
        """collab 服务的内存唤醒提示（DB 已先行提交，丢失可由扫描恢复）。"""
        self._maybe_shadow(run_id)
        self._wake(run_id)

    # ---------- 主循环 ----------
    async def _run_loop(self, run_id: str, q: asyncio.Queue,
                        trigger: str = "run_start") -> None:
        brain = prime = b_session = prime_sid = None
        try:
            settings = self._runtime_settings(run_id)
            self._require_model_authorization(run_id)
            brain = self._make_brain(settings)
            prime = self._make_prime(settings)
            if isinstance(prime, KimiExecutor):
                prime.ask_handler = lambda _sid, question: self._answer_executor_question(run_id,question)
            self._prime_instances[run_id] = prime
            brain_dir = config.WORKSPACE_DIR / "runs" / run_id / "brain_view"
            brain_dir.mkdir(parents=True,exist_ok=True)
            run = self._require_run(run_id)
            b_session = await brain.open(self._brain_spec(run_id, settings, brain_dir))
            if self._sparse_brain(run):
                db.append_event(run_id, "controller", "brain.research_session_opened",
                                {"trace": "optional", "skills_injected": False})
            else:
                db.append_event(run_id, "controller", "brain.skills_enabled", {
                    "skills": [s["id"] for s in skills_mod.effective_for(
                        db.get_db(), settings, run["challenge_id"])],
                })
            self._brain_sessions[run_id] = b_session
            prime_sid = await prime.start(self._prime_spec(run_id,settings))
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
            while True:
                run = self._require_run(run_id)
                phase = run["phase"]
                if phase in ("finished", "failed", "cancelled"):
                    break
                # 有界授权：运行时长上限（只在 running 时触发一次；
                # 不设守卫会每轮重复置 paused + continue 空转，永不 await，
                # 同步 DB 写把事件循环彻底堵死——2026-09-19 实测 seq 爆炸到 9 万+）
                if phase == "running" and self._run_minutes_exceeded(run):
                    db.execute("UPDATE runs SET phase='pausing', block_reason=? WHERE id=?",
                               ("达到本轮授权运行时长上限", run_id))
                    db.append_event(run_id, "controller", "run.time_limit",
                                    {"notice": "达到授权时长上限；已暂停新增受控操作"})
                    phase = "pausing"
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
                    timeout = min(3600, max(0.01,self._run_seconds_remaining(run))) if phase == "running" else 3600
                    signal = await asyncio.wait_for(q.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    if self._run_minutes_exceeded(self._require_run(run_id)):
                        continue
                    # 无事件不代表结束：记账后继续等待，绝不静默杀死 Run
                    db.append_event(run_id, "controller", "run.idle_notice",
                                    {"detail": "长时间无事件；Run 保持运行，等待新信号"})
                    continue
                await self._handle_signal(signal, run_id, q,
                                          prime=prime,
                                          prime_sid=self._prime_sessions[run_id])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            with db.transaction() as conn:
                conn.execute("UPDATE runs SET phase='failed',block_reason=? WHERE id=?"
                             " AND phase NOT IN ('finished','failed','cancelled')",(str(exc)[:300],run_id))
                db.append_event_tx(conn,run_id,"controller","run.runtime_error",
                                   {"error":f"{type(exc).__name__}: {str(exc)[:300]}"})
        finally:
            tasks = [t for t in (self._review_tasks.get(run_id),self._pumps.get(run_id))
                     if t and t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks,return_exceptions=True)
            for runtime, session in ((prime,prime_sid),(brain,b_session)):
                if runtime:
                    try:
                        await runtime.close(session)
                    except Exception as exc:
                        db.append_event(run_id,"controller","run.cleanup_error",{"error":str(exc)[:200]})
            with db.transaction() as conn:
                collab.revoke_run_tokens(conn,run_id)
            for mapping in (self._signals,self._tasks,self._prime_sessions,self._prime_instances,
                            self._brain_sessions,self._start_pump,self._review_wake,self._review_tasks,
                            self._executor_busy,self._pumps):
                mapping.pop(run_id,None)

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
            if (etype in ("reasoning", "token", "thinking")
                    or (etype == "execution.progress" and str(ev.get("detail", "")).lstrip().startswith(("思考:", "思考：")))):
                return
            if etype == "trial.stalled" and (
                run["phase"] != "running" or not self._has_active_trial(run)
                or not self._executor_busy.get(run_id, False)
            ):
                return  # 原生会话开局待命/回合间空闲不代表研究停滞。
            if etype == "trial.stalled" and self._sparse_brain(run) and db.query_one(
                    "SELECT 1 FROM compute_jobs WHERE run_id=?"
                    " AND status IN ('accepted','Running','Pending','Scheduling')"
                    " LIMIT 1", (run_id,)):
                return  # 有已知活跃远端计算时，事件流安静不等于研究停滞。
            public = _runtime_event_payload(ev)
            public.setdefault("detail", "")
            db.append_event(run_id, "prime", f"prime.{etype}",
                            public, trial_id=trial_id)
            if self._handle_signal_guarded_pause(run_id):
                if run["phase"] == "pausing" and etype in ("run.aborted","executor.turn_completed","trial.completed","session.ended"):
                    self._executor_busy[run_id] = False
                    db.execute("UPDATE runs SET phase='paused' WHERE id=? AND phase='pausing'",(run_id,))
                    db.append_event(run_id,"controller","run.paused",{"evidence":etype,"notice":"本地代理已停止；远程 Job 独立对账"})
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
                                public)
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
            if (etype in _SHADOW_TRIGGERS or
                    f"prime.{etype}" == "prime.checkpoint.created" or
                    (self._sparse_brain(run) and etype == "error")):
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
            if (run["phase"] == "running" and not self._has_active_trial(run)
                    and not self._executor_busy.get(run_id, False)):
                # 只有用户显式恢复时重排失败的开局判断；旧错误保留，不自动重试。
                latest = db.query_one(
                    "SELECT trigger, status FROM review_requests WHERE run_id=?"
                    " AND source='lifecycle' ORDER BY rowid DESC LIMIT 1", (run_id,))
                pending = db.query_one(
                    "SELECT id FROM review_requests WHERE run_id=? AND source='lifecycle'"
                    " AND status IN ('pending','running')", (run_id,))
                if (latest and latest["status"] == "error"
                        and latest["trigger"] in ("run_start", "recovery") and not pending):
                    db.execute("UPDATE runs SET block_reason=NULL WHERE id=?", (run_id,))
                    self._enqueue_lifecycle(run_id, trigger=latest["trigger"])
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
            rows = collab.eligible_guidance(conn, run_id)
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
        try:
            receipt = await prime.prompt(sid, text)
        except Exception as exc:
            from .prime import ActionReceipt
            receipt = ActionReceipt(status="unknown", detail=str(exc)[:200])
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
                    "UPDATE guidance SET status=?, updated_at=?"
                    " WHERE id=?", ("unknown" if receipt.status in ("unknown", "confirmed") else "queued", db.utcnow(), g["id"]))
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
        if run["phase"] != "running" or run["gate"] == "awaiting_budget":
            return
        sup = db.query_one("SELECT * FROM supervision WHERE run_id=?",
                           (run_id,))
        if not sup or not sup["enabled"] or sup["degraded"]:
            return
        cfg = self._shadow_cfg(run)
        if sup["reviews_used"] >= cfg["max_reviews"]:
            return
        if self._sparse_brain(run) and db.query_one(
                "SELECT 1 FROM review_requests WHERE run_id=?"
                " AND status IN ('pending','running') LIMIT 1", (run_id,)):
            return  # 研究变化由已排队的判断合并；审阅完再检查后续变化。
        pending = db.query_one(
            "SELECT id FROM review_requests WHERE run_id=?"
            " AND source='shadow' AND status IN ('pending','running')",
            (run_id,))
        if pending:
            return  # 合并：大脑忙/已有待处理范围时不另起请求
        if self._sparse_brain(run):
            candidates = db.query(
                f"SELECT seq,type,trial_id,payload FROM events WHERE run_id=? AND seq>?"
                f" AND type IN ({','.join('?' * len(_SPARSE_SHADOW_EVENTS))})"
                " ORDER BY seq",
                (run_id, sup["covered_seq"], *_SPARSE_SHADOW_EVENTS))
            wake = False
            for event in candidates:
                payload = json.loads(event["payload"])
                previous = None
                if event["type"].startswith("job.") and payload.get("operation_id"):
                    prior = db.query_one(
                        "SELECT type,payload FROM events WHERE run_id=? AND seq<?"
                        " AND type IN ('job.observed','job.unknown')"
                        " AND json_extract(payload,'$.operation_id')=?"
                        " ORDER BY seq DESC LIMIT 1",
                        (run_id, event["seq"], payload["operation_id"]))
                    if prior:
                        previous = ("unknown" if prior["type"] == "job.unknown"
                                    else json.loads(prior["payload"]).get("status"))
                elif event["type"] in _RESEARCH_TRIAL_EVENTS:
                    trial_id = payload.get("trial_id") or event["trial_id"]
                    if trial_id:
                        prior = db.query_one(
                            "SELECT type FROM events WHERE run_id=? AND seq<?"
                            " AND type IN ('trial.stalled','trial.done','trial.reported_complete')"
                            " AND trial_id=? ORDER BY seq DESC LIMIT 1",
                            (run_id, event["seq"], trial_id))
                        previous = prior["type"] if prior else None
                if _is_sparse_brain_trigger(event["type"], payload, previous):
                    wake = True
                    break
            if not wake:
                return
        else:
            notable = db.query_one(
                f"SELECT MAX(seq) AS s FROM events WHERE run_id=?"
                f" AND type IN ({','.join('?' * len(_SHADOW_TRIGGERS))})",
                (run_id, *_SHADOW_TRIGGERS))
            latest = (notable["s"] or 0) if notable else 0
            if latest <= sup["covered_seq"]:
                return  # 旧 Run 保持原触发语义
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
        if run["phase"] != "running" or run["gate"] == "awaiting_budget":
            return
        if self._sparse_brain(run):
            return  # 定时器只检查健康；新 Run 只由研究级变化唤醒。
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
            " AND source IN ('prime','executor','user')"
            " AND type NOT IN ('prime.usage.updated','prime.execution.heartbeat')"
            " AND (type != 'prime.execution.progress' OR ("
            " COALESCE(json_extract(payload,'$.detail'),'') NOT LIKE '思考:%'"
            " AND COALESCE(json_extract(payload,'$.detail'),'') != ''"
            " AND COALESCE(json_extract(payload,'$.detail'),'') NOT LIKE '%bohr job list%'))", (run_id,))
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
            if run["phase"] != "running":
                wake.clear()
                await wake.wait()
                continue
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
            if self._sparse_brain(self._require_run(run_id)):
                completed = db.query_one(
                    "SELECT status,through_seq FROM review_requests WHERE id=?", (req["id"],))
                if completed and completed["status"] == "done" and completed["through_seq"] is not None:
                    db.execute("UPDATE supervision SET covered_seq=MAX(covered_seq,?)"
                               " WHERE run_id=?", (completed["through_seq"], run_id))
                self._maybe_shadow(run_id)

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
        import time
        started = time.monotonic()
        initial_seq = self._last_seq(run_id)
        try:
            await self._run_one_review_impl(run_id, req, brain, b_session)
        finally:
            current = db.query_one("SELECT status,frame_json FROM review_requests WHERE id=?", (req["id"],))
            events = [dict(e) | {"payload": json.loads(e["payload"])} for e in db.query(
                "SELECT seq,type,payload FROM events WHERE run_id=? AND seq>? ORDER BY seq",
                (run_id, initial_seq))]
            usage = [e["payload"] for e in events if e["type"] == "brain.usage.updated"
                     and e["payload"].get("review_id") == req["id"]]
            last = (usage[-1].get("usage") or {}).get("last") if usage else None
            if not isinstance(last, dict):
                last = {}
            decision = next((e["payload"] for e in events if e["type"] == "brain.decision"), None)
            changed = any(e["type"] in ("trial.created", "run.finished", "run.pausing",
                                        "submission.created") for e in events)
            done = next((e["payload"] for e in events if e["type"] == "brain.review_done"), None)
            outcome = ("error" if not current or current["status"] in ("error", "obsolete", "pending", "running") else
                       "decision_direction" if changed else "decision_other" if decision else
                       "guidance" if done and done.get("disposition") == "intervene" else
                       "answer" if req["trigger"] in ("executor_question", "research_question") else "silent")
            db.append_event(run_id, "brain", "brain.review_metrics", {
                "review_id": req["id"],
                "mode": ("question" if req["trigger"] in ("executor_question", "research_question")
                         else "lifecycle" if req["source"] == "lifecycle" else
                         "shadow" if req["source"] == "shadow" else "requested"),
                "trigger": req["trigger"],
                "packet_bytes": len((current["frame_json"] or "").encode("utf-8")) if current else 0,
                "tokens_last_total": last.get("totalTokens"),
                "tokens_input": last.get("inputTokens"),
                "tokens_cached": last.get("cachedInputTokens"),
                "tokens_output": last.get("outputTokens"),
                "latency_s": round(time.monotonic() - started, 3),
                "trace_reads": sum(e["type"] == "brain.trace_read" and
                                   e["payload"].get("review_id") == req["id"] for e in events),
                "outcome": outcome, "direction_changed": changed})

    async def _run_one_review_impl(self, run_id: str, req: Any,
                              brain: BrainRuntime, b_session: Any) -> None:
        """worker 唯一的大脑调用点；结果由控制器短事务单点接受。"""
        self._require_model_authorization(run_id)
        run = self._require_run(run_id)
        if run["phase"] != "running":
            return
        user_review = (req["trigger"] == "user_steer" or req["source"] == "user"
                       or (req["source"] == "requested" and bool(req["blocking"])))
        if run["gate"] == "awaiting_budget" and req["trigger"] != "budget_granted" and not user_review:
            self._obsolete_request(req["id"], "等待 Trial 预算；不唤醒大脑")
            return
        if self._run_minutes_exceeded(run):
            self._obsolete_request(req["id"], "授权时长已用尽")
            db.execute("UPDATE runs SET phase='pausing' WHERE id=? AND phase='running'",(run_id,))
            queue = self._signals.get(run_id)
            if queue is not None:
                queue.put_nowait({"type":"pause"})
            return
        if req["trigger"] in ("executor_question", "research_question"):
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
                    user_guidance=extra.get("user_guidance"),
                    sparse=self._sparse_brain(run))
            else:
                packet = observation.build_frame(
                    run_id, mode=mode, frame_id=frame_id,
                    from_seq=from_seq, through_seq=through_seq,
                    shadow_cfg=cfg, run_defaults=defaults,
                    request={"review_id": req["id"],
                             "checkpoint_id": req["checkpoint_id"],
                             "blocking": bool(req["blocking"])},
                    sparse=self._sparse_brain(run))
                packet["protocol"] = "review_result"
                packet["sparse_brain_version"] = 1 if self._sparse_brain(run) else 0
                authorization = db.query_one(
                    "SELECT note,max_jobs,max_submissions,max_run_minutes FROM authorizations WHERE id=?",
                    (run["authorization_id"],))
                packet["authorization"] = dict(authorization) if authorization else None
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
                 json.dumps(packet if mode != "lifecycle" else {**extra,"packet":packet},ensure_ascii=False),
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
        maintenance_brain: BrainRuntime | None = None
        maintenance_session: Any = None
        try:
            if req["trigger"] == "curation" and self._sparse_brain(run):
                # Curation uses its own native conversation and evidence packet.
                maintenance_brain = self._make_brain(self._runtime_settings(run_id))
                work = config.WORKSPACE_DIR / "runs" / run_id / "curation" / req["id"]
                work.mkdir(parents=True, exist_ok=True)
                maintenance_session = await maintenance_brain.open({
                    "working_directory": str(work)})
            active_brain = maintenance_brain or brain
            active_session = maintenance_session or b_session
            async for ev in active_brain.review(active_session, packet):
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
                elif ev.type == "progress":
                    db.append_event(run_id, "brain", "brain.progress",
                                    _runtime_event_payload(ev.payload))
                elif ev.type == "usage":
                    db.append_event(run_id, "brain", "brain.usage.updated",
                                    _runtime_event_payload(ev.payload) | {"review_id": req["id"]})
                elif ev.type in ("message", "raw"):
                    raw_parts.append(str(ev.payload.get("text", "")))
        except Exception as exc:  # noqa: BLE001
            error_msg = f"{exc.__class__.__name__}: {str(exc)[:300]}"
        finally:
            if maintenance_brain is not None and maintenance_session is not None:
                try:
                    await maintenance_brain.close(maintenance_session)
                except Exception as exc:  # noqa: BLE001
                    error_msg = error_msg or f"维护会话关闭失败: {str(exc)[:200]}"
        if raw_parts:
            db.append_event(run_id, "brain", "brain.raw_output",
                            _runtime_event_payload({"text": "".join(raw_parts)}))

        if error_msg or result is None:
            self._review_failed(run_id, req, mode,
                                error_msg or "大脑未产出有效结果")
            return

        current = self._require_run(run_id)
        if current["phase"] != "running" or self._run_minutes_exceeded(current):
            self._obsolete_request(req["id"], "Run 已关闭受控动作")
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
        """隔离失败；未开始执行的开局/恢复失败须明确暂停，不能假装仍在研究。"""
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
        elif (mode == "lifecycle" and req["trigger"] in ("run_start", "recovery")
              and not self._executor_busy.get(run_id, False)):
            reason = f"大脑{'开局' if req['trigger'] == 'run_start' else '恢复'}判断失败: {error_msg[:300]}"
            with db.transaction() as conn:
                paused = conn.execute(
                    "UPDATE runs SET phase='paused', block_reason=?"
                    " WHERE id=? AND phase='running' AND NOT EXISTS"
                    " (SELECT 1 FROM trials WHERE run_id=? AND status='active')",
                    (reason, run_id, run_id)).rowcount
                if paused:
                    db.append_event_tx(conn, run_id, "controller", "run.paused", {
                        "review_id": req["id"], "trigger": req["trigger"],
                        "reason": reason,
                        "notice": "尚无活动实验且执行器空闲；已暂停，未自动重试或降级模型"})

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
        if run["phase"] != "running" or self._run_minutes_exceeded(run):
            self._obsolete_request(req["id"],"Run 已关闭受控动作")
            return
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
            try:
                experience_context.adopt_tx(conn,run_id,frame.get("trial_id"),result.get("experience_uses",[]),
                                           "brain",f"review:{req['id']}")
            except ValueError as exc:
                db.append_event_tx(conn,run_id,"controller","experience.adoption_rejected",{"reason":str(exc)})
            # SILENT / INTERVENE 都原子保存笔记、观察项与已审阅范围
            conn.execute(
                "UPDATE supervision SET private_note_md=?, watchlist=?,"
                " covered_seq=MAX(covered_seq, ?), updated_at=? WHERE run_id=?",
                (result["private_note_md"],
                 json.dumps(result["watchlist"], ensure_ascii=False),
                 frame.get("processed_through_seq", frame.get("through_seq")) or 0, db.utcnow(), run_id))
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
            " updated_at=? WHERE id=? AND status IN ('pending','running')",
            (status, json.dumps(result, ensure_ascii=False) if result else None,
             error, db.utcnow(), request_id))
        fut = self._question_waiters.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(None)  # 唤醒 executor_question 等待者去读结果
        # 收尾整理审阅完结（无论成败，含暂停中完结）→ 执行被推迟的 finish，防死锁
        self._maybe_finalize_after_curation(request_id)

    # ---------- 生命周期 Decision（旧协议，同一 worker 入口）----------
    def _lifecycle_packet(self, run: Any, trigger: str,
                          user_guidance: str | None = None,
                          sparse: bool = False) -> dict[str, Any]:
        run_id = run["id"]
        settings = self._runtime_settings(run_id)
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
            "sparse_brain_version": 1 if sparse else 0,
            "run_id": run_id,
            "gate": run["gate"],
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
            "enabled_skills": (None if sparse else skills_mod.prompt_segment(
                skills_mod.effective_for(db.get_db(), settings, run["challenge_id"]))),
            "new_events_since_last_review": [
                {"seq": e["seq"], "source": e["source"], "type": e["type"],
                 **({} if sparse else observation.event_excerpt(e))}
                for e in recent if not sparse or e["type"] in (
                    "checkpoint.created", "job.observed", "job.unknown",
                    "trial.stalled", "trial.done", "submission.scored",
                    "submission.score_corrected")][-20:],
            "budget_remaining": {
                "brain_reviews": defaults["max_brain_reviews"]
                - run["brain_reviews_used"],
                "model_turns": (auth["max_model_turns"] if auth else 0),
            },
            "authorization": {
                "note": auth["note"],
                "max_jobs": auth["max_jobs"],
                "max_submissions": auth["max_submissions"],
                "max_run_minutes": auth["max_run_minutes"],
            } if auth else None,
            "experience_manifest": self._memory_manifest(run, settings),
        }
        if self._lifecycle_v2(run):
            packet.pop("current_intention", None)
            packet["lifecycle_version"] = 2
            packet["run_objective"] = run["objective_md"]
            packet["current_trial_goal"] = trial["goal"] if trial else None
            packet["pending_intent"] = json.loads(run["pending_action_json"]) if run["pending_action_json"] else None
        packet["data_status"] = datasets.status(run["challenge_id"])["items"]
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
                "platform_snapshot": json.loads(challenge["platform_snapshot_json"] or "null"),
            }
            if trigger in ("run_start", "recovery"):
                # 开局/恢复帧带完整题面（含工具链 quickstart 与评分契约）
                packet["challenge"]["content"] = challenge["content"]
        if trigger == "curation":
            # 收尾整理：给大脑本题全部经验正文与效果回联（只在此时给，
            # 平时的帧不带——A12）
            packet["curation"] = self._curation_payload(run)
        sup = observation._supervision(run_id)
        feedback = observation.build_frame(run_id,mode="lifecycle",frame_id=_rid("frame"),
            from_seq=sup["covered_seq"]+1,through_seq=self._last_seq(run_id),
            shadow_cfg=self._shadow_cfg(run),run_defaults=defaults,
            sparse=sparse)
        packet["feedback"] = feedback
        packet["experience_manifest"] = feedback["experiences"]
        packet["experience_context_id"] = feedback["experience_context_id"]
        return packet

    def _last_seq(self, run_id: str) -> int:
        row = db.query_one("SELECT COALESCE(MAX(seq),0) AS s FROM events WHERE run_id=?",
                           (run_id,))
        return row["s"]

    def _memory_manifest(self, run: Any, settings: dict[str, Any]) -> list[dict[str, Any]]:
        context = experience_context.for_trial(run["id"],run["current_trial_id"])
        return context["items"] if context else experience_context.select(run["challenge_id"])

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
        settings = self._runtime_settings(run_id)
        defaults = settings["run_defaults"]
        if run["phase"] != "running" or self._run_minutes_exceeded(run):
            db.append_event(run_id,"brain","brain.decision_stale",{"detail":"Run 已关闭受控动作"})
            return
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
        v2 = self._lifecycle_v2(run)
        if (dec.get("schema_version") not in (1, 2) if v2
                else dec.get("schema_version") != 1):
            db.append_event(run_id, "brain", "brain.decision_rejected",
                            {"reasons": ["Decision schema_version 与 Run 生命周期版本不符"]})
            return
        if dec["observed_state_version"] < run["state_version"]:
            db.append_event(run_id, "brain", "brain.decision_stale", {
                "detail": f"判断基于 state_version={dec['observed_state_version']}，"
                          f"当前 {run['state_version']}；保存但不执行"})
            return
        pending = json.loads(run["pending_action_json"]) if v2 and run["pending_action_json"] else None
        if pending:
            if dec.get("schema_version") != 2:
                db.append_event(run_id, "brain", "brain.action_rejected",
                                {"op": "pending_intent", "reason": "待处理意图需要 v2 Decision"})
                return
            resolution = dec.get("pending_intent_resolution")
            if resolution not in ("replay", "revise", "drop"):
                db.append_event(run_id, "brain", "brain.action_rejected",
                                {"op": "pending_intent", "reason": "v2 必须给出 pending_intent_resolution"})
                return
            if resolution == "replay":
                if run["state_version"] != pending["state_version"]:
                    db.append_event(run_id, "brain", "brain.action_rejected",
                                    {"op": "pending_intent", "reason": "待重放意图的状态版本已变化"})
                    return
                dec = {**dec, "actions": [pending["action"]]}
            with db.transaction() as conn:
                conn.execute("UPDATE runs SET pending_action_json=NULL,"
                             " gate=CASE WHEN ?='drop' THEN 'open' ELSE gate END WHERE id=?",
                             (resolution, run_id))
                db.append_event_tx(conn, run_id, "brain", "run.pending_intent_resolved",
                                   {"resolution": resolution, "decision_id": dec["decision_id"]})
            if resolution == "drop":
                if run["phase"] == "running":
                    self._enqueue_lifecycle(run_id, trigger="pending_intent_dropped",
                                            user_guidance=f"大脑放弃意图 {json.dumps(pending, ensure_ascii=False)}；Decision: {dec['decision_id']}")
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

        try:
            with db.transaction() as conn:
                experience_context.adopt_tx(conn,run_id,current_tid,dec.get("experience_uses",[]),
                                           "brain",f"decision:{dec['decision_id']}")
        except ValueError as exc:
            db.append_event(run_id,"controller","experience.adoption_rejected",{"reason":str(exc)})

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
                auth = db.query_one("SELECT max_trials FROM authorizations WHERE id=?",
                                    (run["authorization_id"],)) if v2 else None
                limit = auth["max_trials"] if v2 and auth and auth["max_trials"] else defaults["max_trials"]
                if trial_count >= limit:
                    if v2:
                        pending_action = {"decision_id": dec["decision_id"], "action": action,
                                          "state_version": run["state_version"],
                                          "rejected_at": db.utcnow()}
                        with db.transaction() as conn:
                            conn.execute("UPDATE runs SET gate='awaiting_budget',pending_action_json=? WHERE id=?",
                                         (json.dumps(pending_action,ensure_ascii=False), run_id))
                            db.append_event_tx(conn, run_id, "controller", "run.awaiting_budget",
                                               {"limit": limit, "used": trial_count,
                                                "pending_action": pending_action})
                    else:
                        db.append_event(run_id, "brain", "brain.action_rejected", {
                            "op": op, "reason": f"达到 Trial 上限 {limit}；需要新 Trial 请结束当前 Run 重新授权"})
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
                    if v2:
                        conn.execute("UPDATE runs SET current_trial_id=?,gate='open' WHERE id=?",
                                     (trial_id, run_id))
                    else:
                        conn.execute("UPDATE runs SET current_trial_id=?,intention=?,gate='open' WHERE id=?",
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
                             f"Run ID：{run_id}；Trial ID：{trial_id}。\n"
                             f"交付目录：{config.WORKSPACE_DIR / 'runs' / run_id / 'trials' / trial_id}。\n"
                             "提交包命名 result_package.zip（真实 ARM 包，包含研究轨迹与诚实结果）；"
                             "该目录允许写入。用检查点报告交付，交由控制器提交。\n"
                             f"本轮授权与用户目标：{json.dumps(packet.get('authorization'), ensure_ascii=False)}\n"
                             f"题目与平台契约：{json.dumps(dict(db.query_one('SELECT title,content,resources_json,platform_snapshot_json FROM challenges WHERE id=?', (run['challenge_id'],))), ensure_ascii=False)}\n"
                             f"公开数据物化状态：{json.dumps(datasets.status(run['challenge_id'])['items'], ensure_ascii=False)}\n"
                             "提交包会追加真实事件轨迹并接受准入检查；自有 trace.jsonl 只能使用七种合法 step_type，artifact_path 必须是包内现存文件，禁止编造工具调用或费用。\n"
                             "冻结经验（只使用这份正文；采用时在检查点声明版本）：\n"
                             f"{experience_context.encode(experience_context.for_trial(run_id,trial_id))}\n"
                             f"{executor_instruction_suffix()}"
                             f"{skills_mod.prompt_segment(enabled_skills)}\n"
                             "运行环境：Linux；科学计算只能在 Bohrium Job 中执行。\n"
                             "使用 PATH 中的 bohr；它会脱敏原生 CLI 错误输出，不得绕过代理执行原始 CLI。\n"
                             f"Bohrium 项目 ID：{(settings.get('bohrium') or {}).get('project_id') or '未配置'}。"
                             "认证通过进程环境提供，不得打印、记录或写入提交包。\n")
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
                if v2:
                    assessment = action.get("objective_assessment")
                    if not isinstance(assessment, dict):
                        db.append_event(run_id, "brain", "brain.action_rejected",
                                        {"op": op, "reason": "v2 finish 缺少 objective_assessment"})
                        continue
                    if assessment.get("status") == "achieved":
                        refs = assessment.get("evidence_refs") or []
                        valid = bool(refs) and all(db.query_one(
                            "SELECT 1 FROM events WHERE run_id=? AND (event_id=? OR CAST(seq AS TEXT)=?)",
                            (run_id, ref, str(ref).split("#")[-1])) for ref in refs)
                        if not valid:
                            db.append_event(run_id, "brain", "brain.action_rejected",
                                            {"op": op, "reason": "achieved 缺少可解析的真实证据引用"})
                            continue
                    db.execute("UPDATE runs SET objective_status=?,end_reason=? WHERE id=?",
                               (assessment["status"], action["reason"], run_id))
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
            elif op == "request_submission":
                # Legacy manifest refs have no frozen-package resolution contract.
                # Never reinterpret a ref as package_path or fall back to another bundle.
                db.append_event(run_id, "brain", "brain.action_rejected", {
                    "op": op,
                    "reasons": ["旧 request_submission 尚无 bundle_manifest_ref 到冻结包的解析契约；"
                                "本动作未执行提交。提交建议请在 requested/shadow 审阅的 "
                                "ReviewResult 中使用 guidance.kind=submit，"
                                "仍须通过现有授权、预算和去重检查；这不扩大正式提交授权。"],
                    "bundle_manifest_ref": _runtime_event_payload(
                        {"detail": action["bundle_manifest_ref"]})["detail"],
                    "trial_id": _runtime_event_payload(
                        {"detail": action["trial_id"]})["detail"]})
            elif op == "refresh_platform":
                db.append_event(run_id, "brain", "brain.action_rejected", {
                    "op": op, "detail": "此动作尚未接入；使用已导入题面和实际开放的只读工具"})

    def _apply_experience_proposal(self, run_id: str | None, decision_id: str,
                                   proposal: dict[str, Any]) -> str | None:
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
                if proposal["scope"] != scope or (scope == "challenge" and
                        (not run_id or challenge_id != self._require_run(run_id)["challenge_id"])):
                    raise experiences.ExperienceError("INVALID_EXPERIENCE", "target_id 不属于本 Run 题目/提议作用域")
                if proposal.get("expected_revision") not in (None, prior["revision_id"], prior["current_hash"]):
                    raise experiences.ExperienceError("REVISION_CONFLICT", "提议基于旧版本")
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
            fm = dict(prior["frontmatter"]) if prior else {}
            fm.update({"title": proposal["title"], "scope": scope,
                  "challenge_id": None if is_global else challenge_id,
                  "status": "candidate" if is_global else "active",
                  "evidence_status": proposal.get("evidence_status", "hypothesis"),
                  "kind": kind,
                  "applicability": proposal["applicability"],
                  "evidence_refs": evidence_refs})
            for key in ("tags", "expires_at", "derived_from"):
                if key in proposal:
                    fm[key] = proposal[key]
            if fm["evidence_status"] != "hypothesis" and not proposal.get("evidence_refs"):
                fm["evidence_status"] = "hypothesis"
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
            return exp_id
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
            if exp["frontmatter"].get("challenge_id") != self._require_run(run_id)["challenge_id"]:
                raise experiences.ExperienceError("INVALID_EXPERIENCE","不能激活其他题目经验")
            # 陈旧视图保护：大脑看到的是旧修订时不覆盖别人/自己的新改动
            if action.get("revision_hash") and \
                    action["revision_hash"] != exp["current_hash"]:
                db.append_event(run_id, "brain", "brain.action_rejected", {
                    "op": "promote_experience",
                    "reason": "revision_hash 与当前修订不一致；请重新读取后再操作"})
                return
            fm = dict(exp["frontmatter"])
            fm["status"] = "active"
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
            conn.execute("UPDATE runs SET phase='finished', ended_at=?,end_reason=?"
                         " WHERE id=?", (db.utcnow(), reason, run_id))
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
        manifest = experience_context.select(run["challenge_id"])
        try:
            snap = json.loads(run["experience_snapshot"]) \
                if run["experience_snapshot"] else {}
        except (json.JSONDecodeError, TypeError):
            snap = {}
        snap[key] = {"recorded_at": db.utcnow(), "semantics":"availability_only", "items": manifest}
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
                         "semantics":"availability_only",
                         "run_background_best_score": best["s"] if best else None})
        for row in db.query("SELECT u.* FROM experience_uses u JOIN runs r ON r.id=u.run_id WHERE r.challenge_id=?",(challenge_id,)):
            results = db.query("SELECT payload FROM events WHERE run_id=? AND type='experience.result_linked'"
                               " AND json_extract(payload,'$.experience_id')=?"
                               " AND json_extract(payload,'$.adopted_seq')=? ORDER BY seq",
                               (row["run_id"],row["experience_id"],row["adopted_seq"]))
            usage.setdefault(row["experience_id"],[]).append(
                dict(row) | {"results":[json.loads(result["payload"]) for result in results]})
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
                "protocol": "experience_curation",
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
                if ev.type == "curation_result":
                    decision = ev.payload["result"]
                elif ev.type == "decision":
                    legacy = ev.payload["decision"]
                    if not decision_mod.validate_structure(legacy) and all(a["op"] == "wait" for a in legacy["actions"]):
                        decision = {"schema_version": 1, "message_type": "curation_result",
                                    "summary": legacy["summary"], "experience_proposals": legacy["experience_proposals"]}
                elif ev.type == "error":
                    error_msg = ev.payload.get("message", "")
            if decision is None:
                raise ControllerError(
                    "BRAIN_ERROR",
                    f"大脑未产出整理决策: {error_msg or '无结果'}", False)
            from .curation import schema
            jsonschema.validate(decision, schema())
            applied = 0
            for proposal in decision.get("experience_proposals", [])[:3]:
                if proposal["scope"] != "global":
                    raise ControllerError("INVALID_CURATION", "全局整理只能提议全局候选")
                proposal = {**proposal, "evidence_status": "hypothesis"}
                applied += bool(self._apply_experience_proposal(None, "curation", proposal))
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
        context = experience_context.freeze(run_id,trial_id,f"trial:{trial_id}")
        (trial_dir / "memory_manifest.json").write_text(
            json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 查询 ----------
    async def curate_run_experience(self, run_id: str, operation_id: str) -> dict:
        from .curation import run_evidence
        run = self._require_run(run_id)
        if run['phase'] not in ('paused', 'recovering', 'finished', 'failed', 'cancelled'):
            raise ControllerError('INVALID_STATE', '请先暂停研究，再整理本轮经验')
        if not operation_id or len(operation_id) > 128:
            raise ControllerError('INVALID_OPERATION', '需要稳定的 operation_id')
        # Filesystem experience reconciliation can commit, so perform it
        # before the atomic request insertion.
        evidence = run_evidence(run_id)
        packet = {'protocol': 'experience_curation', 'trigger': 'run_curation',
                  'run_evidence': evidence, 'curation': self._curation_payload(run)}
        with db.transaction() as conn:
            old = conn.execute('SELECT * FROM curation_requests WHERE operation_id=?', (operation_id,)).fetchone()
            if old:
                if old['run_id'] != run_id:
                    raise ControllerError('CONFLICT', '操作 ID 已用于其他 Run')
                return self.run_curation_status(run_id, old['id'])
            if conn.execute("SELECT id FROM curation_requests WHERE run_id=? AND status='running'", (run_id,)).fetchone():
                raise ControllerError('CURATION_RUNNING', '本轮经验整理正在进行')
            request_id = _rid('curation')
            conn.execute('INSERT INTO curation_requests(id,operation_id,run_id,status,packet_json,created_at,updated_at)'
                         " VALUES(?,?,?,'running',?,?,?)", (request_id, operation_id, run_id,
                         json.dumps(packet, ensure_ascii=False), db.utcnow(), db.utcnow()))
            db.append_event_tx(conn, run_id, 'user', 'experience.curation_requested', {'curation_id': request_id})
        asyncio.create_task(self._run_curation(request_id))
        return self.run_curation_status(run_id, request_id)

    def run_curation_status(self, run_id: str, request_id: str | None = None) -> dict:
        self._require_run(run_id)
        row = db.query_one('SELECT * FROM curation_requests WHERE run_id=?' +
                           (' AND id=?' if request_id else '') + ' ORDER BY created_at DESC LIMIT 1',
                           (run_id, request_id) if request_id else (run_id,))
        if not row:
            return {'state': 'idle'}
        result = json.loads(row['result_json'] or '{}')
        return {'id': row['id'], 'state': row['status'], 'error': row['error'],
                'summary': result.get('summary'), 'proposals_applied': result.get('proposals_applied', 0),
                'experience_ids': result.get('experience_ids', [])}

    async def _run_curation(self, request_id: str) -> None:
        from .curation import schema
        row = db.query_one('SELECT * FROM curation_requests WHERE id=?', (request_id,))
        packet = json.loads(row['packet_json'])
        brain, session = None, None
        try:
            brain = self._make_brain(config.load_settings())
            work = config.WORKSPACE_DIR / 'curation' / request_id
            work.mkdir(parents=True, exist_ok=True)
            session = await brain.open({'working_directory': str(work)})
            result = None
            async for event in brain.review(session, packet):
                if event.type == 'curation_result':
                    result = event.payload['result']
                elif event.type == 'error':
                    raise ControllerError('BRAIN_ERROR', _redact(event.payload.get('message', '整理失败')))
            jsonschema.validate(result, schema())
            allowed_refs = set(packet['run_evidence']['evidence_refs'])
            ids = []
            # Validate all references before applying any proposal.
            for proposal in result['experience_proposals']:
                refs = proposal['evidence_refs']
                if not refs or not set(refs) <= allowed_refs:
                    raise ControllerError('INVALID_EVIDENCE', '经验必须引用本次整理快照中存在的证据')
                if proposal['scope'] == 'challenge' and proposal['challenge_id'] != packet['run_evidence']['challenge_id']:
                    raise ControllerError('INVALID_EVIDENCE', '题内经验不能指向其他题目')
            for proposal in result['experience_proposals']:
                eid = self._apply_experience_proposal(row['run_id'], request_id,
                                                     {**proposal, 'evidence_status': 'hypothesis'})
                if eid:
                    ids.append(eid)
            result = {**result, 'experience_ids': ids, 'proposals_applied': len(ids)}
            db.execute("UPDATE curation_requests SET status='done',result_json=?,updated_at=? WHERE id=?",
                       (json.dumps(result, ensure_ascii=False), db.utcnow(), request_id))
            db.append_event(row['run_id'], 'controller', 'experience.curation_done',
                            {'curation_id': request_id, 'proposals_applied': len(ids)})
        except Exception as exc:
            error = _redact(str(exc))[:500]
            db.execute("UPDATE curation_requests SET status='failed',error=?,updated_at=? WHERE id=?",
                       (error, db.utcnow(), request_id))
            db.append_event(row['run_id'], 'controller', 'experience.curation_failed',
                            {'curation_id': request_id, 'error': error})
        finally:
            if brain is not None and session is not None:
                try:
                    await brain.close(session)
                except Exception:
                    log.exception('Curation session close failed')

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
        answers = db.query(
            "SELECT r.id,r.status,r.trigger,r.result_json,r.error,r.created_at,"
            " g.id AS guidance_id,g.status AS delivery_status,"
            " g.delivery_channel,g.ack_disposition"
            " FROM review_requests r LEFT JOIN guidance g"
            " ON g.review_request_id=r.id AND g.run_id=r.run_id"
            " WHERE r.run_id=? AND r.trigger IN ('executor_question','research_question')"
            " ORDER BY r.rowid DESC LIMIT 10", (run_id,))
        d["research_answers"] = []
        for row in answers:
            item = dict(row)
            result = json.loads(item.pop("result_json") or "{}")
            item["answer_md"] = result.get("answer_md")
            item["native_form"] = ("mapped" if result.get("native_answers")
                                   else "declined") if item["status"] == "done" else "pending"
            item["evidence_refs"] = result.get("evidence_refs") or []
            d["research_answers"].append(item)
        reads = db.query(
            "SELECT seq,payload,recorded_at FROM events WHERE run_id=?"
            " AND type='brain.trace_read' ORDER BY seq DESC LIMIT 20", (run_id,))
        d["trace_reads"] = [{"seq": row["seq"], "recorded_at": row["recorded_at"],
                              **json.loads(row["payload"])} for row in reads]
        recent_review = db.query_one(
            "SELECT trigger,source,created_at FROM review_requests"
            " WHERE run_id=? ORDER BY rowid DESC LIMIT 1", (run_id,))
        d["last_wake"] = dict(recent_review) if recent_review else None
        d["latest_seq"] = self._last_seq(run_id)
        return d

    def run_snapshot(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        trials = [dict(t) for t in db.query(
            "SELECT * FROM trials WHERE run_id=? ORDER BY created_at", (run_id,))]
        delivered = {r["trial_id"] for r in db.query(
            "SELECT DISTINCT trial_id FROM events WHERE run_id=?"
            " AND type='trial.reported_complete' AND trial_id IS NOT NULL", (run_id,))}
        for trial in trials:
            trial["delivered"] = trial["id"] in delivered or trial["status"] == "reported_complete"
        d = dict(run)
        d["config_snapshot"] = json.loads(d["config_snapshot"])
        d["trials"] = trials
        d["budget"] = self._budget_status(run)
        return d

    def _run_minutes_exceeded(self, run: Any) -> bool:
        return self._run_seconds_remaining(run) <= 0

    def _run_seconds_remaining(self, run: Any) -> float:
        auth = db.query_one("SELECT * FROM authorizations WHERE id=?",
                            (run["authorization_id"],)) if run["authorization_id"] else None
        minutes = auth["max_run_minutes"] if auth else 0
        if not minutes or not run["started_at"]:
            return float("inf")
        started = _parse_ts(run["started_at"])
        if started is None:
            return float("inf")
        import time as _time
        return minutes * 60 - (_time.time() - started)

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
            "max_trials": (auth["max_trials"] if self._lifecycle_v2(run) and auth and auth["max_trials"]
                           else defaults["max_trials"]),
            "run_minutes_limit": auth["max_run_minutes"] if auth else 0,
            "run_minutes_exceeded": self._run_minutes_exceeded(run),
            "model_turns": {"limit": auth["max_model_turns"] if auth else 0,
                            "used": None,
                            "known_cost": None, "unknown_cost": True,
                            "enforced": False,
                            "note": "原生代理内部调用量尚未完整计量；不能将未知用量视为零"},
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
