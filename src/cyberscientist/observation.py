"""ObservationFrame：大脑审阅的不可变输入快照（只读有界投影）。

只读数据库与已登记的不可变记录；不访问执行器工作区文件，不触发新计算。
摘要顺序：关键异常/失败 → 结果变化 → 当前意图 → 工具活动计数。
未知字段显式列出；不编造分数、归因或官方评分。
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import datasets, db, experience_context, submission_predictions

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
    "brain.decision_rejected", "brain.action_rejected", "run.objective_assessment_unknown", "run.final_package_unknown", "run.final_package_checked",
    "guidance.sent", "guidance.acknowledged",
    "guidance.superseded", "prime.error", "prime.approval.rejected",
    "checkpoint.created", "submission.scored", "submission.score_corrected",
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
    from .bohr_proxy import redact
    from . import config
    secrets = config.sensitive_values()
    return redact(_SECRET_TOKEN_RE.sub(r"\1***", text), secrets)


def authority_facts(run_id: str) -> dict[str, Any]:
    """One non-secret authorization projection for every brain review surface."""
    auth = db.query_one('SELECT a.* FROM authorizations a JOIN runs r'
                        ' ON r.authorization_id=a.id AND a.run_id=r.id WHERE r.id=?', (run_id,))
    values = ({name: auth[name] for name in (
        'note', 'max_jobs', 'max_sandboxes', 'max_sandbox_minutes',
        'max_submissions', 'max_run_minutes', 'max_compute_cost_cny', 'max_environment_saves')} if auth else None)
    if values is not None:
        values['note'] = strip_secrets(values['note']) if values['note'] else values['note']
        from .compute import validate_limits
        values['job_limits'] = validate_limits(json.loads(auth['job_limits_json']))
        values.update(allow_sandbox_gpu=bool(auth['allow_sandbox_gpu']),
                      allow_data_download=bool(auth['allow_data_download']))
    from . import runtime_environments, runtime_facts
    result: dict[str, Any] = {'authorization': values,
                              'runtime_environments': runtime_environments.facts(),
                              'operating_facts': runtime_facts.facts(run_id)}
    run = db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (run_id,))
    template = json.loads(run['config_snapshot']).get('competition', {}) if run else {}
    result['solver_note'] = template.get('solver_note', '')
    result['round_challenge_snapshot'] = template.get('challenge_snapshot')
    return result


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
            payload = e['payload']
            item = {"seq": e["seq"], "excerpt": strip_secrets(detail)[:_MAX_DIGEST_EACH]}
            for source, dest in (('item_id', 'operation_id'), ('status', 'status'), ('exit_code', 'exit_code')):
                if source in payload:
                    item[dest] = payload[source]
            output = payload.get('output') or payload.get('content') or payload.get('result')
            if output:
                item['output_excerpt'] = strip_secrets(output if isinstance(output, str) else json.dumps(output, ensure_ascii=False))[:2000]
            # A completed receipt replaces its earlier started activity.
            if item.get('operation_id'):
                items = [old for old in items if old.get('operation_id') != item['operation_id']]
            items.append(item)
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
    items = experience_context.select(challenge_id, role='brain')
    return items, any(it.get("body_truncated") for it in items)


def events_through(run_id, from_seq, through_seq):
    events = []
    through_seq = through_seq or 0
    cursor = from_seq - 1
    while cursor < through_seq:
        batch = db.events_after(run_id, cursor, limit=400)
        batch = [e for e in batch if e["seq"] <= through_seq]
        if not batch:
            break
        events.extend(batch)
        cursor = batch[-1]["seq"]
    return events


def score_deltas(events):
    return [{**e["payload"],"source_seq":e["seq"],"source_time":e["recorded_at"]}
            for e in events if e["type"] in ("submission.scored","submission.score_corrected")]


def job_states(run_id: str, through_seq: int) -> list[dict]:
    """State at the frame cutoff, reconstructed from durable public events."""
    states = {}
    for e in events_through(run_id, 1, through_seq):
        p = e['payload']
        if not e['type'].startswith('job.') or not p.get('operation_id'):
            continue
        if e['type'] not in ('job.reserved', 'job.accepted', 'job.unknown', 'job.not_started',
                             'job.observed', 'job.stop_requested', 'job.stop_receipt',
                             'job.retrieval_failed', 'job.retrieved', 'job.concurrency_released'):
            continue
        op = p['operation_id']
        state = states.setdefault(op, {'operation_id': op})
        statuses = {'job.reserved': 'submitting', 'job.accepted': 'accepted',
                    'job.unknown': 'unknown', 'job.not_started': 'not_started',
                    'job.stop_requested': 'stopping', 'job.stop_receipt': 'stop_unknown'}
        state['status'] = p.get('status') or statuses.get(e['type'], state.get('status', 'unknown'))
        state['platform_job_id'] = p.get('platform_job_id') or state.get('platform_job_id')
        if e['type'] in ('job.retrieval_failed', 'job.retrieved'):
            operation_status = 'retrieved' if e['type'] == 'job.retrieved' else 'failed'
            if p.get('operation') == 'download' and operation_status == 'retrieved':
                state['_download_ever_retrieved'] = True
            state['retrieval_status'] = ('retrieved' if state.get('_download_ever_retrieved')
                                         else operation_status)
        state['evidence_ref'] = f"event:{run_id}:{e['seq']}"
    for state in states.values():
        state.pop('_download_ever_retrieved', None)
        state.setdefault('retrieval_status', 'not_attempted')
    return list(states.values())[-30:]


def build_frame(run_id: str, *, mode: str, frame_id: str,
                from_seq: int, through_seq: int,
                shadow_cfg: dict[str, Any],
                request: dict[str, Any] | None = None,
                run_defaults: dict[str, Any] | None = None,
                sparse: bool = False) -> dict[str, Any]:
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

    # 稀疏帧只带显式研究摘要；完整报告由 research_trace 按需读取。
    cps = db.query(
        "SELECT c.* FROM checkpoints c JOIN events e ON e.run_id=c.run_id"
        " AND e.type='checkpoint.created' AND json_extract(e.payload,'$.checkpoint_id')=c.id"
        " WHERE c.run_id=? AND e.seq<=? ORDER BY e.seq DESC LIMIT ?",
        (run_id, through_seq, _MAX_CHECKPOINTS))
    total_cps = db.query_one(
        "SELECT COUNT(*) AS n FROM checkpoints WHERE run_id=?", (run_id,))
    checkpoint_summaries = []
    for cp in reversed(cps):
        item = {
            "checkpoint_id": cp["id"], "stage": cp["stage"],
            "evidence_refs": json.loads(cp["evidence_refs"] or "[]"),
            "source": "executor_report"
                      if cp["source"] == "executor" else "user_report"}
        if sparse:
            summary = cp["research_summary_md"]
            item["research_summary_available"] = bool(summary)
            if summary:
                item["research_summary_md"] = strip_secrets(summary)
        else:
            report, clip = _clip(strip_secrets(cp["report"]),
                                 _MAX_CHECKPOINT_EACH)
            truncated |= clip
            item["report_md"] = report
        checkpoint_summaries.append(item)
    omitted = max(0, (total_cps["n"] if total_cps else 0) - len(cps))

    # 覆盖范围内事件：值得注意的事件摘要 + 工具活动计数；不含原始推理流
    events = events_through(run_id, from_seq, through_seq)
    activity: dict[str, int] = {}
    notable: list[dict[str, Any]] = []
    for e in events:
        if e["type"].startswith("prime.execution.progress"):
            detail = str(e["payload"].get("detail", ""))
            key = "tool_failed" if "失败" in detail else "tool_activity"
            activity[key] = activity.get(key, 0) + 1
        if e["type"] in _NOTABLE and (not sparse or e["type"] in (
                "trial.stalled", "trial.done", "trial.reported_complete",
                "submission.scored",
                "submission.score_corrected", "run.blocked",
                "brain.action_rejected", "brain.decision_rejected", "run.objective_assessment_unknown", "run.final_package_unknown", "run.final_package_checked")):
            notable.append({"seq": e["seq"], "source": e["source"],
                            "type": e["type"],
                            "excerpt": strip_secrets(json.dumps(
                                e["payload"], ensure_ascii=False))[:200]})
    if len(notable) > _MAX_NOTE_EVENTS:
        omitted += len(notable) - _MAX_NOTE_EVENTS
        notable = notable[-_MAX_NOTE_EVENTS:]
        truncated = True

    # 执行器实质进展摘要：关键状态变化不能只存在于执行器思考流里
    digest, digest_omitted = ([], 0) if sparse else executor_digest(events)
    omitted += digest_omitted
    truncated = truncated or digest_omitted > 0

    context = experience_context.freeze(run_id,run["current_trial_id"],
                                        f"frame:{frame_id}",role='brain')
    exps = context["items"]
    truncated |= any(it.get("body_truncated") for it in exps)
    note, clip = _clip(sup["private_note_md"], _MAX_NOTE)
    truncated |= clip

    known_scores = {}
    durable_events = events_through(run_id, 1, through_seq)
    for value in score_deltas(durable_events):
        known_scores[value["submission_id"]] = value
    submission_summary = None
    for event in reversed(durable_events):
        if (event["type"] == "submission.created" and
                event.get("trial_id") == (trial["id"] if trial else None) and
                "trace_diagnostics" in event["payload"]):
            diagnostic = event["payload"]["trace_diagnostics"]
            submission_summary = {
                "submission_id": event["payload"].get("submission_id"),
                "package_sha256": event["payload"].get("package_sha256"),
                "trace_diagnostics": {"status": diagnostic.get("status", "unavailable"),
                    "checklist_cap": diagnostic.get("checklist_cap"),
                    "advisories": diagnostic.get("advisories", [])[:8]},
            }
            break
    defaults = run_defaults or {}
    auth = db.query_one("SELECT * FROM authorizations WHERE id=?",
                        (run["authorization_id"],)) \
        if run["authorization_id"] else None

    if sparse:
        # Research context carries coarse milestones and receipts. Full tool
        # output is available only through an explicit research_trace read.
        notable = [e for e in notable if e["type"] in (
            "trial.stalled", "trial.done", "trial.reported_complete",
            "submission.scored",
            "submission.score_corrected", "run.blocked",
            "brain.action_rejected", "brain.decision_rejected", "run.objective_assessment_unknown", "run.final_package_unknown", "run.final_package_checked")]
        for item in notable:
            item["excerpt"] = item["excerpt"][:120]

    from . import local_scoring
    return {
        "frame_id": frame_id,
        "mode": mode,
        "run_id": run_id,
        **authority_facts(run_id),
        **local_scoring.latest_final_check(run_id),
        "gate": run["gate"],
        "trial_id": trial["id"] if trial else None,
        "trial_status": trial["status"] if trial else None,
        "state_version": run["state_version"],
        "evidence_revision": sup["evidence_revision"],
        "shadow_epoch": sup["shadow_epoch"],
        "from_seq": from_seq,
        "through_seq": through_seq,
        "processed_through_seq": events[-1]["seq"] if events else from_seq-1,
        "goal_md": goal_md,
        **({"lifecycle_version": 2, "run_objective": run["objective_md"],
            "current_trial_goal": trial["goal"] if trial else None,
            "pending_intent": json.loads(run["pending_action_json"]) if run["pending_action_json"] else None}
           if json.loads(run["config_snapshot"]).get("lifecycle_version") == 2
           else {"current_intention": run["intention"]}),
        "trial_summary_md": trial_summary,
        "checkpoint_summaries": checkpoint_summaries,
        "notable_events": notable,
        "executor_digest": digest,
        "trace_access": ({"tool": "research_trace", "optional": True,
                          "through_seq": through_seq} if sparse else None),
        "compute_jobs": job_states(run_id, through_seq),
        "data_status": datasets.status(run["challenge_id"])["items"],
        "activity_counts": activity,
        "metrics": score_deltas(events),
        "known_scores":list(known_scores.values()),
        "submission_summary": submission_summary,
        "submission_prediction_version":json.loads(run['config_snapshot']).get('submission_prediction_version'),
        "prediction_outcomes":submission_predictions.outcomes(run_id,through_seq=through_seq),
        "experience_context_id": context["id"],
        "brain_private_note_md": note,
        "watchlist": sup["watchlist"],
        "experiences": exps,
        "experience_index": context.get("index", []),
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
            "unknown_fields": (["official_score"] if not known_scores else []) + ["provider_total_cost"],
        },
        "request": request,
    }
