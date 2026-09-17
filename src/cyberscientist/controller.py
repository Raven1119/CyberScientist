"""RunController：进程内单活跃 Run 的研究闭环与状态机。

事件流是权威记录；控制器只追加。暂停/终止语义按 ARCHITECTURE：
只有代理确认停下才显示 paused；steer 接受不等于生效。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from . import config, db, decision as decision_mod, experiences
from .brains.base import BrainRuntime
from .brains.codex import CodexBrain
from .brains.demo import DemoBrain
from .brains.kimi import KimiBrain
from .prime import DemoPrime, PrimeRpc, PrimeRuntime

log = logging.getLogger("cyberscientist.controller")

PHASES = ("created", "running", "pausing", "paused", "blocked",
          "recovering", "finished", "failed", "cancelled")


class ControllerError(Exception):
    def __init__(self, code: str, message: str, recoverable: bool = True):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


def _rid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


_SECRET_PATTERNS = ("sk-", "AKIA", "Bearer ", "ghp_", "gho_", "xoxb-",
                    "AIza", "-----BEGIN")


def _redact(text: str | None, limit: int = 2000) -> str:
    """指导文本入库前截断并遮蔽明显密钥形态（事件库等同日志）。"""
    if not text:
        return ""
    t = text[:limit]
    for pat in _SECRET_PATTERNS:
        if pat in t:
            t = t.replace(pat, f"{pat[:2]}***")
    return t


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


class RunController:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._signals: dict[str, asyncio.Queue] = {}
        self._prime_sessions: dict[str, str] = {}
        self._demo_prime = DemoPrime()
        self._brain_sessions: dict[str, Any] = {}

    # ---------- 组件工厂 ----------
    def _make_brain(self, settings: dict[str, Any]) -> BrainRuntime:
        if settings["app"]["mode"] == "demo":
            return DemoBrain()
        runtime = settings["brain"]["runtime"]
        if runtime == "codex":
            return CodexBrain(executable=settings["brain"].get("executable") or None,
                              model=settings["brain"].get("model_id"))
        return KimiBrain()

    def _make_prime(self, settings: dict[str, Any]) -> PrimeRuntime:
        if settings["app"]["mode"] == "demo":
            return self._demo_prime
        return PrimeRpc(settings["prime"].get("executable", ""))

    # ---------- Run 生命周期 ----------
    def create_run(self, challenge_id: str, mode: str | None = None) -> dict[str, Any]:
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
        snapshot = {"settings": self._redacted_settings(settings),
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

    def authorize(self, run_id: str, scope: str, allow_model_calls: bool,
                  max_model_turns: int, max_run_minutes: int,
                  max_submissions: int, note: str | None) -> dict[str, Any]:
        run = self._require_run(run_id)
        if run["phase"] not in ("created", "blocked"):
            raise ControllerError("INVALID_STATE", f"当前阶段 {run['phase']} 不能授权")
        auth_id = _rid("auth")
        db.execute(
            "INSERT INTO authorizations(id, run_id, scope, allow_model_calls,"
            " max_model_turns, max_run_minutes, max_submissions, granted_at, note)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (auth_id, run_id, scope, int(allow_model_calls), max_model_turns,
             max_run_minutes, max_submissions, db.utcnow(), note))
        db.execute("UPDATE runs SET authorization_id=?, block_reason=NULL WHERE id=?",
                   (auth_id, run_id))
        if run["phase"] == "blocked":
            db.execute("UPDATE runs SET phase='created' WHERE id=?", (run_id,))
        db.append_event(run_id, "controller", "run.authorized",
                        {"scope": scope, "allow_model_calls": allow_model_calls})
        return {"authorization_id": auth_id}

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
                problems.append(f"Prime 不可用：{p_health.detail}")
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
                    "detail": "指导已排队；以 steer.consumed 事件确认生效"}
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
            db.execute("UPDATE runs SET phase='pausing' WHERE id=?", (run_id,))
            db.append_event(run_id, "controller", "run.pausing", {
                "notice": "正在暂停；已有远程任务可能继续运行/计费"})
            await q.put({"type": "pause"})
            return {"status": "accepted", "detail": "暂停中，等待代理确认"}
        if action == "resume":
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
            db.execute("UPDATE runs SET phase='cancelled', ended_at=? WHERE id=?",
                       (db.utcnow(), run_id))
            db.append_event(run_id, "controller", "run.terminated", {
                "notice": "证据与历史 Attempt 保留；远程 Job 取消属阶段 2 范围"})
            if q:
                await q.put({"type": "terminate"})
            task = self._tasks.pop(run_id, None)
            if task:
                task.cancel()
            return {"status": "confirmed"}
        raise ControllerError("INVALID_ACTION", f"未知控制动作: {action}")

    # ---------- 主循环 ----------
    async def _run_loop(self, run_id: str, q: asyncio.Queue) -> None:
        settings = config.load_settings()
        brain = self._make_brain(settings)
        prime = self._make_prime(settings)
        run = self._require_run(run_id)
        try:
            b_session = await brain.open({"working_directory": None})
            self._brain_sessions[run_id] = b_session
        except Exception as exc:  # noqa: BLE001
            db.execute("UPDATE runs SET phase='failed' WHERE id=?", (run_id,))
            db.append_event(run_id, "brain", "brain.session_error",
                            {"message": str(exc)[:300]})
            return

        prime_sid = await prime.start({"run_id": run_id})
        self._prime_sessions[run_id] = prime_sid

        async def prime_event_pump() -> None:
            try:
                async for ev in prime.events(prime_sid):
                    await q.put({"type": "prime_event", "event": ev})
                    if ev.get("type") in ("trial.completed", "run.aborted"):
                        break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                await q.put({"type": "prime_error", "message": str(exc)[:300]})

        pump = asyncio.create_task(prime_event_pump())
        try:
            # 启动即唤醒大脑
            await self._brain_review(run_id, brain, b_session, trigger="run_start")
            while True:
                run = self._require_run(run_id)
                phase = run["phase"]
                if phase in ("finished", "failed", "cancelled"):
                    break
                # 有界授权：运行时长上限
                if self._run_minutes_exceeded(run):
                    db.execute("UPDATE runs SET phase='paused', block_reason=? WHERE id=?",
                               ("达到本轮授权运行时长上限", run_id))
                    db.append_event(run_id, "controller", "run.time_limit",
                                    {"notice": "达到授权时长上限；已暂停新增受控操作"})
                    continue
                if phase == "pausing":
                    receipt = await prime.abort(prime_sid)
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
                                          brain=brain, b_session=b_session,
                                          prime=prime, prime_sid=prime_sid)
                if signal["type"] == "steer":
                    # 用户指导立即唤醒一次判断
                    await self._brain_review(run_id, brain, b_session,
                                             trigger="user_steer",
                                             user_guidance=signal.get("text"))
        except asyncio.CancelledError:
            pass
        finally:
            pump.cancel()
            try:
                await brain.close(b_session)
            except Exception:  # noqa: BLE001
                pass
            self._signals.pop(run_id, None)
            self._tasks.pop(run_id, None)
            self._prime_sessions.pop(run_id, None)
            self._brain_sessions.pop(run_id, None)

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
                if etype in ("trial.completed", "run.aborted"):
                    db.append_event(run_id, "controller", "prime.late_event_ignored", {
                        "type": etype,
                        "notice": "暂停期间不驱动状态推进；恢复后由代理状态核对"})
                return
            if etype == "trial.completed":
                db.execute("UPDATE trials SET status='done' WHERE id=?", (trial_id,))
                db.append_event(run_id, "controller", "trial.done",
                                {"trial_id": trial_id})
                await self._brain_review(run_id, ctx["brain"], ctx["b_session"],
                                         trigger="trial_done")
            if etype == "run.aborted":
                db.append_event(run_id, "prime", "prime.aborted",
                                {"detail": ev.get("detail", "")})
        elif stype == "steer":
            # 已由 control() 记录 queued 事件；此处只唤醒判断
            pass
        elif stype == "resume":
            # 恢复：重新挂接执行器。若仍有活跃 Trial 且执行器空闲，
            # 重新下发任务让其继续（远程 Job 的实际状态核对属阶段 2）。
            run = self._require_run(run_id)
            trial_id = run["current_trial_id"]
            if trial_id:
                trial = db.query_one("SELECT * FROM trials WHERE id=?", (trial_id,))
                if trial and trial["status"] == "active":
                    state = await ctx["prime"].state(ctx["prime_sid"])
                    if state.get("status") == "idle":
                        receipt = await ctx["prime"].prompt(
                            ctx["prime_sid"],
                            f"继续目标：{trial['goal']}\n成功判据：{trial['success_check']}")
                        db.append_event(run_id, "prime", "prime.task_resumed",
                                        {"status": receipt.status,
                                         "detail": receipt.detail},
                                        trial_id=trial_id)
        elif stype in ("pause", "terminate"):
            pass  # 状态转换已在 control()/主循环处理
        elif stype == "prime_error":
            db.append_event(run_id, "prime", "prime.error",
                            {"message": signal.get("message", "")})

    async def _brain_review(self, run_id: str, brain: BrainRuntime,
                            b_session: Any, trigger: str,
                            user_guidance: str | None = None) -> None:
        run = self._require_run(run_id)
        settings = config.load_settings()
        auth = db.query_one("SELECT * FROM authorizations WHERE id=?",
                            (run["authorization_id"],)) if run["authorization_id"] else None
        defaults = settings["run_defaults"]
        reviews_used = run["brain_reviews_used"]
        if reviews_used >= defaults["max_brain_reviews"]:
            db.execute("UPDATE runs SET phase='paused', block_reason=? WHERE id=?",
                       (f"达到大脑判断上限 {defaults['max_brain_reviews']} 次", run_id))
            db.append_event(run_id, "controller", "run.review_limit",
                            {"limit": defaults["max_brain_reviews"]})
            return

        trial = db.query_one("SELECT * FROM trials WHERE id=?",
                             (run["current_trial_id"],)) if run["current_trial_id"] else None
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
            "trial_count": len(db.query("SELECT id FROM trials WHERE run_id=?", (run_id,))),
            "challenge_id": run["challenge_id"],
            "user_guidance": user_guidance,
            "new_events_since_last_review": [
                {"seq": e["seq"], "source": e["source"], "type": e["type"]}
                for e in recent][-20:],
            "budget_remaining": {
                "brain_reviews": defaults["max_brain_reviews"] - reviews_used,
                "model_turns": (auth["max_model_turns"] if auth else 0),
            },
            "experience_manifest": self._memory_manifest(run, settings),
        }
        db.execute("UPDATE runs SET brain_reviews_used=? WHERE id=?",
                   (reviews_used + 1, run_id))
        try:
            async for ev in brain.review(b_session, packet):
                if ev.type == "decision":
                    await self._apply_decision(run_id, ev.payload["decision"],
                                               packet, brain, b_session)
                elif ev.type == "error":
                    db.append_event(run_id, "brain", "brain.error",
                                    {"message": ev.payload.get("message", "")})
                elif ev.type == "approval_request":
                    db.append_event(run_id, "brain", "brain.approval_request",
                                    ev.payload)
                # token/message：高频增量只记最后一条
        except Exception as exc:  # noqa: BLE001
            db.append_event(run_id, "brain", "brain.error",
                            {"message": f"{exc.__class__.__name__}: {str(exc)[:300]}"})

    def _last_seq(self, run_id: str) -> int:
        row = db.query_one("SELECT COALESCE(MAX(seq),0) AS s FROM events WHERE run_id=?",
                           (run_id,))
        return row["s"]

    def _memory_manifest(self, run: Any, settings: dict[str, Any]) -> list[dict[str, Any]]:
        scope = "challenge" if run["challenge_id"] else None
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
            db.append_event(run_id, "brain", "brain.decision_rejected",
                            {"reasons": structural})
            return
        if dec["observed_state_version"] < run["state_version"]:
            db.append_event(run_id, "brain", "brain.decision_stale", {
                "detail": f"判断基于 state_version={dec['observed_state_version']}，"
                          f"当前 {run['state_version']}；保存但不执行"})
            return
        semantic = decision_mod.validate_semantics(
            dec, has_active_trial=bool(run["current_trial_id"]),
            current_trial_id=run["current_trial_id"],
            allow_formal_submission=settings["policy"]["allow_formal_submission"])
        if semantic:
            db.append_event(run_id, "brain", "brain.decision_rejected",
                            {"reasons": semantic})
            return

        for proposal in dec.get("experience_proposals", [])[:3]:
            try:
                fm = {"title": proposal["title"], "scope": proposal["scope"],
                      "challenge_id": proposal.get("challenge_id"),
                      "status": "candidate", "evidence_status": "hypothesis",
                      "kind": "heuristic",
                      "applicability": proposal["applicability"],
                      "evidence_refs": proposal.get("evidence_refs", [])}
                exp_id = _rid("exp")
                result = experiences.save_experience(
                    exp_id, fm, proposal["body_md"], operator="brain",
                    reason=f"Decision {dec['decision_id']} 提议", base_hash=None)
                db.append_event(run_id, "brain", "experience.proposed",
                                {"experience_id": exp_id, "title": proposal["title"],
                                 "status": "candidate"})
            except experiences.ExperienceError as exc:
                db.append_event(run_id, "brain", "experience.proposal_rejected",
                                {"reason": str(exc)[:200]})

        prime_sid = self._prime_sessions.get(run_id)
        prime = self._make_prime(settings)
        for action in dec["actions"]:
            op = action["op"]
            if op == "start_trial":
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
                db.execute(
                    "INSERT INTO trials(id, run_id, parent_trial_id, goal, success_check,"
                    " status, created_at) VALUES(?,?,?,?,?,'active',?)",
                    (trial_id, run_id, parent, action["goal"],
                     action["success_check"], db.utcnow()))
                db.execute("UPDATE runs SET current_trial_id=?, intention=? WHERE id=?",
                           (trial_id, action["goal"], run_id))
                self._snapshot_memory(run_id, trial_id, settings)
                db.append_event(run_id, "controller", "trial.created",
                                {"trial_id": trial_id, "goal": action["goal"]},
                                trial_id=trial_id)
                receipt = await prime.prompt(
                    prime_sid, f"目标：{action['goal']}\n成功判据：{action['success_check']}")
                db.append_event(run_id, "prime", "prime.task_accepted",
                                {"status": receipt.status, "detail": receipt.detail},
                                trial_id=trial_id)
            elif op == "steer":
                receipt = await prime.steer(prime_sid, action["message"])
                db.append_event(run_id, "prime", "prime.steer", {
                    "status": receipt.status,
                    "detail": receipt.detail or "accepted 只代表已接收"},
                    trial_id=action["trial_id"])
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
                db.execute("UPDATE runs SET phase='finished', ended_at=? WHERE id=?",
                           (db.utcnow(), run_id))
                db.append_event(run_id, "controller", "run.finished",
                                {"reason": action["reason"]})
                q = self._signals.get(run_id)
                if q:
                    await q.put({"type": "terminate"})
            elif op == "promote_experience":
                self._promote(run_id, action)
            elif op in ("refresh_platform", "request_submission"):
                db.append_event(run_id, "brain", "brain.action_deferred", {
                    "op": op, "detail": "阶段 2 能力：真实平台核对/提交尚未接入"})

    def _promote(self, run_id: str, action: dict[str, Any]) -> None:
        try:
            exp = experiences.get_experience(action["experience_id"])
            scope = exp["frontmatter"]["scope"]
            if scope == "global":
                db.append_event(run_id, "brain", "brain.action_rejected", {
                    "op": "promote_experience",
                    "reason": "全局晋升需要独立复现与人工审查；阶段 1 仅允许题目内激活"})
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
        }

    def list_runs(self) -> list[dict[str, Any]]:
        rows = db.query("SELECT * FROM runs ORDER BY created_at DESC")
        out = []
        for r in rows:
            d = dict(r)
            d.pop("config_snapshot", None)
            out.append(d)
        return out
