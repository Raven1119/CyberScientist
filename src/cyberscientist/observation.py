"""ObservationFrame：大脑审阅的不可变输入快照（只读有界投影）。

只读数据库与已登记的不可变记录；不访问执行器工作区文件，不触发新计算。
摘要顺序：关键异常/失败 → 结果变化 → 当前意图 → 工具活动计数。
未知字段显式列出；不编造分数、归因或官方评分。
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import db, experiences

# 有界投影的尺寸上限（字符）
_MAX_GOAL = 1500
_MAX_TRIAL = 800
_MAX_CHECKPOINT_EACH = 1200
_MAX_CHECKPOINTS = 6
_MAX_NOTE_EVENTS = 12
_MAX_EXPERIENCE_EACH = 1500
_MAX_EXPERIENCES = 6
_MAX_NOTE = 1200
_MAX_DIGEST_ITEMS = 12
_MAX_DIGEST_EACH = 160

# 执行器思考流的 detail 前缀——不进帧（帧不含原始推理流）
_THINKING_PREFIXES = ("思考:", "思考：")

# 值得摘要进帧的事件类型（异常/失败 → 结果/交付 → 决策）；纯心跳不进入
_NOTABLE = (
    "trial.stalled", "trial.done", "trial.reported_complete",
    "trial.created", "run.blocked", "run.pausing", "run.paused",
    "run.resumed", "run.time_limit", "brain.decision",
    "brain.decision_rejected", "guidance.sent", "guidance.acknowledged",
    "guidance.superseded", "prime.error", "prime.approval.rejected",
    "checkpoint.created",
)

_SECRET_TOKEN_RE = re.compile(
    r"(sk-|AKIA|ghp_|gho_|xoxb-|AIza|Bearer )[A-Za-z0-9_\-.]+")
_SECRET_BLOCK_RE = re.compile(
    r"-----BEGIN[ A-Z]*-----.*?-----END[ A-Z]*-----", re.DOTALL)


def strip_secrets(text: str) -> str:
    """进帧文本脱敏：执行器报告可能混入密钥样本，不能进大脑输入。

    必须吞掉标记后的整个令牌主体；只遮前缀等于没遮。
    """
    text = _SECRET_BLOCK_RE.sub("[已遮蔽：密钥块]", text)
    return _SECRET_TOKEN_RE.sub(r"\1***", text)


def _clip(text: str | None, limit: int) -> tuple[str, bool]:
    t = text or ""
    if len(t) <= limit:
        return t, False
    return t[:limit] + "…[截断]", True


def _substantive_detail(event: dict[str, Any]) -> str:
    """progress 事件的实质进展文本；思考流与空文本返回空串。"""
    if not event["type"].startswith("prime.execution.progress"):
        return ""
    detail = str(event["payload"].get("detail", "")).strip()
    if not detail or detail.startswith(_THINKING_PREFIXES):
        return ""
    return detail


def executor_digest(events: list[dict[str, Any]], *,
                    limit: int = _MAX_DIGEST_ITEMS
                    ) -> tuple[list[dict[str, Any]], int]:
    """执行器实质进展摘要（工具结果/回复/异常等），按序取尾部。

    大脑看不到执行器思考流，checkpoint 又依赖执行器自觉；这里把
    非思考类 progress 的 detail 摘录进帧，避免关键进展（认证通过、
    数据就绪、Job 完成）只存在于执行器思考里。返回 (条目, 省略数)。
    """
    items: list[dict[str, Any]] = []
    for e in events:
        detail = _substantive_detail(e)
        if detail:
            items.append({"seq": e["seq"],
                          "excerpt": strip_secrets(detail)[:_MAX_DIGEST_EACH]})
    if len(items) > limit:
        return items[-limit:], len(items) - limit
    return items, 0


def event_excerpt(event: dict[str, Any]) -> dict[str, str]:
    """生命周期帧的单事件摘要：notable 事件带 payload 摘录，
    执行器实质进展带 detail 摘录；思考流与其余心跳不带。"""
    if event["type"] in _NOTABLE:
        return {"excerpt": strip_secrets(json.dumps(
            event["payload"], ensure_ascii=False))[:200]}
    detail = _substantive_detail(event)
    if detail:
        return {"excerpt": strip_secrets(detail)[:_MAX_DIGEST_EACH]}
    return {}


def _supervision(run_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM supervision WHERE run_id=?", (run_id,))
    if row:
        d = dict(row)
        d["watchlist"] = json.loads(d["watchlist"] or "[]")
        return d
    return {"enabled": 0, "shadow_epoch": 0, "covered_seq": 0,
            "evidence_revision": 0, "reviews_used": 0,
            "private_note_md": "", "watchlist": [], "degraded": 0}


def _selected_experiences(challenge_id: str | None) -> tuple[list[dict], bool]:
    """大脑注入选定 active 修订的正文（不只是标题/hash），全局+本题有界。"""
    out: list[dict[str, Any]] = []
    truncated = False
    listing = experiences.list_experiences(scope=None,
                                           challenge_id=challenge_id)
    for item in listing["items"]:
        if item["status"] != "active":
            continue
        if len(out) >= _MAX_EXPERIENCES:
            truncated = True
            break
        try:
            full = experiences.get_experience(item["id"])
        except Exception:  # noqa: BLE001
            continue
        body, clip = _clip(full.get("body_md", ""), _MAX_EXPERIENCE_EACH)
        truncated = truncated or clip
        out.append({"id": item["id"], "revision_hash": item["revision_hash"],
                    "scope": item["scope"], "title": item["title"],
                    "body_md": body})
    return out, truncated


def build_frame(run_id: str, *, mode: str, frame_id: str,
                from_seq: int, through_seq: int,
                shadow_cfg: dict[str, Any],
                request: dict[str, Any] | None = None,
                run_defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """只读投影；frame 落库后即为审阅的不可变输入。"""
    run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        raise KeyError(f"Run 不存在: {run_id}")
    sup = _supervision(run_id)
    truncated = False

    challenge = db.query_one("SELECT title, content FROM challenges WHERE id=?",
                             (run["challenge_id"],))
    goal_src = f"{challenge['title']}\n{challenge['content']}" if challenge \
        else (run["intention"] or "")
    goal_md, clip = _clip(goal_src, _MAX_GOAL)
    truncated |= clip

    trial = None
    if run["current_trial_id"]:
        trial = db.query_one("SELECT * FROM trials WHERE id=?",
                             (run["current_trial_id"],))
    if trial is None:
        trial = db.query_one("SELECT * FROM trials WHERE run_id=?"
                             " ORDER BY rowid DESC LIMIT 1", (run_id,))
    trial_summary, clip = _clip(
        f"goal: {trial['goal']}\nsuccess_check: {trial['success_check']}"
        if trial else "", _MAX_TRIAL)
    truncated |= clip

    # 检查点摘要：执行器已写下的报告，带来源标注
    cps = db.query(
        "SELECT id, trial_id, report, evidence_refs, stage, source"
        " FROM checkpoints WHERE run_id=? ORDER BY created_at DESC LIMIT ?",
        (run_id, _MAX_CHECKPOINTS))
    total_cps = db.query_one(
        "SELECT COUNT(*) AS n FROM checkpoints WHERE run_id=?", (run_id,))
    checkpoint_summaries = []
    for cp in reversed(cps):
        report, clip = _clip(strip_secrets(cp["report"]), _MAX_CHECKPOINT_EACH)
        truncated |= clip
        checkpoint_summaries.append({
            "checkpoint_id": cp["id"], "stage": cp["stage"],
            "report_md": report,
            "evidence_refs": json.loads(cp["evidence_refs"] or "[]"),
            "source": "executor_report"
                      if cp["source"] == "executor" else "user_report"})
    omitted = max(0, (total_cps["n"] if total_cps else 0) - len(cps))

    # 覆盖范围内事件：值得注意的事件摘要 + 工具活动计数；不含原始推理流
    events = db.events_after(run_id, from_seq - 1, limit=400)
    events = [e for e in events if e["seq"] <= through_seq]
    activity: dict[str, int] = {}
    notable: list[dict[str, Any]] = []
    for e in events:
        if e["type"].startswith("prime.execution.progress"):
            detail = str(e["payload"].get("detail", ""))
            key = "tool_failed" if "失败" in detail else "tool_activity"
            activity[key] = activity.get(key, 0) + 1
        if e["type"] in _NOTABLE:
            notable.append({"seq": e["seq"], "source": e["source"],
                            "type": e["type"],
                            "excerpt": strip_secrets(json.dumps(
                                e["payload"], ensure_ascii=False))[:200]})
    if len(notable) > _MAX_NOTE_EVENTS:
        omitted += len(notable) - _MAX_NOTE_EVENTS
        notable = notable[-_MAX_NOTE_EVENTS:]
        truncated = True

    # 执行器实质进展摘要：关键状态变化不能只存在于执行器思考流里
    digest, digest_omitted = executor_digest(events)
    omitted += digest_omitted
    truncated = truncated or digest_omitted > 0

    exps, clip = _selected_experiences(run["challenge_id"])
    truncated |= clip
    note, clip = _clip(sup["private_note_md"], _MAX_NOTE)
    truncated |= clip

    defaults = run_defaults or {}
    auth = db.query_one("SELECT * FROM authorizations WHERE id=?",
                        (run["authorization_id"],)) \
        if run["authorization_id"] else None

    return {
        "frame_id": frame_id,
        "mode": mode,
        "run_id": run_id,
        "trial_id": trial["id"] if trial else None,
        "trial_status": trial["status"] if trial else None,
        "state_version": run["state_version"],
        "evidence_revision": sup["evidence_revision"],
        "shadow_epoch": sup["shadow_epoch"],
        "from_seq": from_seq,
        "through_seq": through_seq,
        "goal_md": goal_md,
        "current_intention": run["intention"],
        "trial_summary_md": trial_summary,
        "checkpoint_summaries": checkpoint_summaries,
        "notable_events": notable,
        "executor_digest": digest,
        "activity_counts": activity,
        "metrics": [],
        "brain_private_note_md": note,
        "watchlist": sup["watchlist"][:3],
        "experiences": exps,
        "budget": {
            "remaining_shadow_reviews": max(
                0, shadow_cfg.get("max_reviews", 8) - sup["reviews_used"]),
            "remaining_control_turns": max(
                0, defaults.get("max_brain_reviews", 20)
                - run["brain_reviews_used"]),
            "max_model_turns": auth["max_model_turns"] if auth else 0,
            "max_jobs": auth["max_jobs"] if auth else 0,
            "known_cost": None,
        },
        "quality": {
            "truncated": truncated,
            "omitted_count": omitted,
            "unread_refs": [],
            "unknown_fields": ["official_score", "provider_total_cost"],
        },
        "request": request,
    }
