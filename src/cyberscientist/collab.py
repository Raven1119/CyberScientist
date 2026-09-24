"""协作写路径服务：research_checkpoint / ack_guidance / 能力令牌。

契约见 docs/collaboration/contract.schema.json。身份（run/trial/session）
由后端绑定，不由调用方选择；数据库是权威，内存通知只作唤醒提示。
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import jsonschema

from . import db, experience_context

_CONTRACT_PATH = (Path(__file__).resolve().parent.parent.parent
                  / "docs" / "collaboration" / "contract.schema.json")
_CONTRACT: dict[str, Any] = json.loads(
    _CONTRACT_PATH.read_text(encoding="utf-8"))


class CollabError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _validate(msg: dict[str, Any], def_name: str) -> None:
    schema = {"$ref": f"#/$defs/{def_name}", "$defs": _CONTRACT["$defs"]}
    try:
        jsonschema.validate(msg, schema)
    except jsonschema.ValidationError as exc:
        raise CollabError("INVALID_MESSAGE",
                          f"契约校验失败: {exc.message[:300]}") from exc


def content_hash(msg: dict[str, Any]) -> str:
    """JSON 字段顺序无关的内容哈希。"""
    canonical = json.dumps(msg, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _rid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------- 能力令牌 ----------

def issue_token(conn: sqlite3.Connection, run_id: str, role: str,
                session_ref: str, generation: int,
                ttl_hours: int = 24) -> str:
    """签发仅绑定本 Run/角色/会话代次的短时令牌；只存哈希。"""
    token = f"cst_{secrets.token_urlsafe(24)}"
    expires = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours))
    conn.execute(
        "INSERT INTO capability_tokens(token_hash, run_id, role, session_ref,"
        " generation, revoked, expires_at, created_at)"
        " VALUES(?,?,?,?,?,0,?,?)",
        (hashlib.sha256(token.encode()).hexdigest(), run_id, role,
         session_ref, generation, expires.isoformat(), db.utcnow()))
    return token


def validate_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    row = db.query_one(
        "SELECT * FROM capability_tokens WHERE token_hash=?",
        (hashlib.sha256(token.encode()).hexdigest(),))
    if not row or row["revoked"]:
        return None
    expires = datetime.fromisoformat(row["expires_at"])
    if expires < datetime.now(timezone.utc):
        return None
    return dict(row)


def revoke_run_tokens(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute("UPDATE capability_tokens SET revoked=1 WHERE run_id=?",
                 (run_id,))


def revoke_role_tokens(conn: sqlite3.Connection, run_id: str, role: str) -> None:
    conn.execute("UPDATE capability_tokens SET revoked=1 WHERE run_id=? AND role=?",
                 (run_id, role))


# ---------- 指导 outbox ----------

def _guidance_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["evidence_refs"] = json.loads(d.get("evidence_refs") or "[]")
    return d


def pending_guidance(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM guidance WHERE run_id=? AND status='queued'"
        " ORDER BY created_at", (run_id,)).fetchall()


def guidance_eligible(conn: sqlite3.Connection, run_id: str, g) -> bool:
    run = conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
    shadow = conn.execute("SELECT enabled,shadow_epoch FROM supervision WHERE run_id=?",(run_id,)).fetchone()
    status = None
    if g["target_trial_id"] and g["target_trial_id"] != run["current_trial_id"]:
        status = "superseded"
    elif g["source"] == "shadow" and (not shadow or not shadow["enabled"] or shadow["shadow_epoch"] != g["shadow_epoch"]):
        status = "invalidated"
    # A result produced from an older Job state must not steer the executor
    # after a material transition. User-authored guidance has no frame binding.
    if not status and g['status'] == 'queued' and g['frame_id']:
        frame = conn.execute('SELECT frame_json FROM review_requests WHERE frame_id=?', (g['frame_id'],)).fetchone()
        if frame and frame['frame_json']:
            cutoff = json.loads(frame['frame_json']).get('through_seq', 0)
            newer = conn.execute("SELECT 1 FROM events WHERE run_id=? AND seq>? AND type IN "
                                 "('job.reserved','job.accepted','job.unknown','job.observed','job.stop_requested') LIMIT 1",
                                 (run_id, cutoff)).fetchone()
            if newer:
                status = 'superseded'
    if status:
        conn.execute("UPDATE guidance SET status=?,updated_at=? WHERE id=? AND status IN ('queued','sent')",
                     (status,db.utcnow(),g["id"]))
        db.append_event_tx(conn,run_id,"controller","guidance."+status,{"guidance_id":g["id"]},trial_id=g["target_trial_id"])
        return False
    return run["phase"] == "running" and run["gate"] == "open"


def eligible_guidance(conn: sqlite3.Connection, run_id: str):
    return [g for g in pending_guidance(conn,run_id) if guidance_eligible(conn,run_id,g)]


def deliver_via_checkpoint_return(conn: sqlite3.Connection, run_id: str,
                                  trial_id: str | None) -> list[dict[str, Any]]:
    delivered = []
    for g in eligible_guidance(conn,run_id):
        op_id = 'op_' + uuid.uuid4().hex
        changed = conn.execute("UPDATE guidance SET status='sent',delivery_channel='checkpoint_tool',"
                               "operation_id=?,updated_at=? WHERE id=? AND status='queued'",
                               (op_id,db.utcnow(),g['id'])).rowcount
        if not changed:
            continue
        db.append_event_tx(conn,run_id,"controller","guidance.sent",
                           {"guidance_id":g['id'],"kind":g['kind'],"channel":"checkpoint_tool","operation_id":op_id},
                           trial_id=g['target_trial_id'])
        delivered.append(_guidance_row_to_dict(g) | {"status":"sent","operation_id":op_id})
    return delivered


def create_guidance(conn: sqlite3.Connection, run_id: str, *,
                    source: str, g: dict[str, Any],
                    target_trial_id: str | None,
                    review_request_id: str | None, frame_id: str | None,
                    state_version: int, evidence_revision: int,
                    shadow_epoch: int) -> str:
    gid = _rid("guidance")
    now = db.utcnow()
    row = conn.execute("SELECT content_json FROM experience_contexts WHERE run_id=? AND boundary=?",
                       (run_id,f"trial:{target_trial_id}")).fetchone()
    items = json.loads(row["content_json"])["items"] if row else []
    context = experience_context.freeze_tx(conn,run_id,target_trial_id,f"guidance:{gid}",items)
    text_md = g["text_md"]
    if items:
        text_md += "\n冻结经验（采用时回报包与版本）：\n" + experience_context.encode(context)
    conn.execute(
        "INSERT INTO guidance(id, run_id, review_request_id, frame_id, source,"
        " target_trial_id, kind, intent, text_md, reason_md, evidence_refs,"
        " expected_change_md, revisit_when_md, state_version,"
        " evidence_revision, shadow_epoch, status, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'queued',?,?)",
        (gid, run_id, review_request_id, frame_id, source, target_trial_id,
         g["kind"], g["intent"], text_md, g["reason_md"],
         json.dumps(g.get("evidence_refs", []), ensure_ascii=False),
         g["expected_change_md"], g["revisit_when_md"],
         state_version, evidence_revision, shadow_epoch, now, now))
    return gid


# ---------- research_checkpoint ----------

def submit_checkpoint(run_id: str, msg: dict[str, Any], *,
                      source: str,
                      notify: Callable[[str], None] | None = None
                      ) -> dict[str, Any]:
    """执行器/UI 统一的检查点入口：契约校验 + 去重 + 原子保存 + 审阅排队。

    返回 checkpoint_id / review_id / next_action / 本次投递的指导。
    同 key 同内容幂等返回原收据；同 key 不同内容返回冲突。
    """
    _validate(msg, "Checkpoint")
    if msg.get("research_question") and (msg["review"] == "none" or
                                         msg["stage"] == "trial_complete"):
        raise CollabError("INVALID_MESSAGE", "研究问题需 async/blocking 审阅，不能与 trial_complete 合并")
    if msg.get("research_question") and len(json.dumps(
            msg["research_question"], ensure_ascii=False)) > 12000:
        raise CollabError("INVALID_MESSAGE", "研究问题过长")
    run = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        raise CollabError("NOT_FOUND", f"Run 不存在: {run_id}")
    if run["phase"] in ("finished", "failed", "cancelled"):
        raise CollabError("RUN_ENDED", f"Run 已终态 {run['phase']}")
    trial_id = run["current_trial_id"]  # 身份由后端绑定
    key = msg["checkpoint_key"]
    digest = content_hash(msg)

    with db.transaction() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        trial_id = run["current_trial_id"]
        existing = conn.execute(
            "SELECT * FROM checkpoints WHERE run_id=? AND trial_id IS ?"
            " AND checkpoint_key=?",
            (run_id, trial_id, key)).fetchone()
        if existing:
            if existing["content_hash"] == digest:
                receipt = json.loads(existing["receipt_json"] or "{}")
                review = conn.execute("SELECT id FROM review_requests WHERE checkpoint_id=?"
                                      " ORDER BY created_at LIMIT 1", (existing["id"],)).fetchone()
                next_action = "continue" if run["phase"] == "running" and run["gate"] == "open" else "yield"
                replay = []
                for item in receipt.get("guidance", []):
                    g = conn.execute("SELECT * FROM guidance WHERE id=?", (item["id"],)).fetchone()
                    if g and g["status"] in ("sent", "acknowledged") and guidance_eligible(conn,run_id,g):
                        replay.append(item)
                return {"checkpoint_id": existing["id"], "review_id": receipt.get("review_id") or (review["id"] if review else None),
                        "next_action": next_action, "deduplicated": True,
                        "guidance": replay if next_action == "continue" else []}
            raise CollabError(
                "CONFLICT",
                f"checkpoint_key={key} 已存在不同内容；请使用新的 key")

        cp_id = _rid("cp")
        now = db.utcnow()
        conn.execute(
            "INSERT INTO checkpoints(id, run_id, trial_id, report,"
            " evidence_refs, created_at, checkpoint_key, content_hash,"
            " stage, review, source)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (cp_id, run_id, trial_id, msg["report_md"],
             json.dumps(msg["evidence_refs"], ensure_ascii=False), now,
             key, digest, msg["stage"], msg["review"], source))
        db.append_event_tx(
            conn, run_id, source if source in ("executor", "user") else "executor",
            "checkpoint.created",
            {"checkpoint_id": cp_id, "checkpoint_key": key,
             "stage": msg["stage"], "review": msg["review"],
             "report_excerpt": msg["report_md"][:300]}, trial_id=trial_id)
        try:
            experience_context.adopt_tx(conn,run_id,trial_id,msg.get("experience_uses",[]),
                                       source,f"checkpoint:{cp_id}")
        except ValueError as exc:
            raise CollabError("INVALID_MESSAGE",str(exc)) from exc
        # 检查点是已登记科学证据：提升证据版本
        conn.execute(
            "UPDATE supervision SET evidence_revision=evidence_revision+1,"
            " updated_at=? WHERE run_id=?", (now, run_id))

        review_id: str | None = None
        next_action = "continue"
        if msg["stage"] == "trial_complete":
            # 执行器声明交付：先记 reported_complete，由生命周期审阅裁决；
            # 不代表评分通过或控制器已确认科学结论
            if trial_id:
                conn.execute(
                    "UPDATE trials SET status='reported_complete'"
                    " WHERE id=? AND status='active'", (trial_id,))
            conn.execute("UPDATE runs SET gate='yielding' WHERE id=?",
                         (run_id,))
            review_id = _enqueue_request_tx(
                conn, run_id, source="lifecycle", blocking=True,
                trigger="trial_complete", checkpoint_id=cp_id)
            db.append_event_tx(conn, run_id, "controller",
                               "trial.reported_complete",
                               {"trial_id": trial_id, "checkpoint_id": cp_id},
                               trial_id=trial_id)
            next_action = "yield"
        elif msg["review"] != "none":
            blocking = msg["review"] == "blocking"
            review_id = _enqueue_request_tx(
                conn, run_id, source="executor", blocking=blocking,
                trigger=("research_question" if msg.get("research_question")
                         else f"checkpoint:{msg['review']}"), checkpoint_id=cp_id)
            if msg.get("research_question"):
                from . import observation
                safe_question = json.loads(observation.strip_secrets(
                    json.dumps(msg["research_question"], ensure_ascii=False)))
                conn.execute("UPDATE review_requests SET frame_json=? WHERE id=?",
                             (json.dumps({"question": safe_question},
                                         ensure_ascii=False), review_id))
            if blocking:
                conn.execute("UPDATE runs SET gate='yielding' WHERE id=?",
                             (run_id,))
                next_action = "yield"
        # 检查点工具返回是排队指导的选定投递点之一
        delivered = deliver_via_checkpoint_return(conn, run_id, trial_id)
        current = conn.execute("SELECT phase,gate FROM runs WHERE id=?", (run_id,)).fetchone()
        next_action = "continue" if current["phase"] == "running" and current["gate"] == "open" else "yield"
        conn.execute("UPDATE checkpoints SET receipt_json=? WHERE id=?",
                     (json.dumps({"review_id":review_id,"guidance":delivered},ensure_ascii=False),cp_id))

    if notify:
        notify(run_id)  # 新检查点即使不要求审阅，也要唤醒 shadow 评估
    return {"checkpoint_id": cp_id, "review_id": review_id,
            "next_action": next_action, "deduplicated": False,
            "guidance": delivered}


def _enqueue_request_tx(conn: sqlite3.Connection, run_id: str, *,
                        source: str, blocking: bool, trigger: str,
                        checkpoint_id: str | None = None) -> str:
    rid = _rid("rev")
    now = db.utcnow()
    conn.execute(
        "INSERT INTO review_requests(id, run_id, source, blocking,"
        " checkpoint_id, status, trigger, created_at, updated_at)"
        " VALUES(?,?,?,?,?,'pending',?,?,?)",
        (rid, run_id, source, int(blocking), checkpoint_id, trigger,
         now, now))
    db.append_event_tx(conn, run_id, "controller", "review.requested",
                       {"review_id": rid, "source": source,
                        "blocking": blocking, "trigger": trigger},
                       trial_id=None)
    return rid


# ---------- ack_guidance ----------

def ack_guidance(run_id: str, msg: dict[str, Any]) -> dict[str, Any]:
    """执行器确认指导。只能 ACK 已实际投递（sent）的指导；重复幂等。

    会话绑定在令牌鉴权层成立：旧会话令牌在新会话签发时已撤销，
    到达本函数的调用必然持当前会话令牌。
    """
    _validate(msg, "GuidanceAck")
    gid = msg["guidance_id"]
    with db.transaction() as conn:
        g = conn.execute("SELECT * FROM guidance WHERE id=? AND run_id=?",
                         (gid, run_id)).fetchone()
        if not g:
            raise CollabError("NOT_FOUND", f"指导不存在或不属于本 Run: {gid}")
        if g["status"] == "acknowledged":
            return {"guidance_id": gid, "status": "acknowledged",
                    "deduplicated": True}
        if g["status"] != "sent":
            raise CollabError(
                "NOT_DELIVERED",
                f"指导 {gid} 状态 {g['status']}，未实际投递到本会话，不能确认")
        now = db.utcnow()
        conn.execute(
            "UPDATE guidance SET status='acknowledged', ack_disposition=?,"
            " ack_reason_md=?, acked_at=?, updated_at=? WHERE id=?",
            (msg["disposition"], msg["reason_md"], now, now, gid))
        db.append_event_tx(
            conn, run_id, "executor", "guidance.acknowledged",
            {"guidance_id": gid, "disposition": msg["disposition"],
             "reason_md": msg["reason_md"][:500]},
            trial_id=g["target_trial_id"])
    return {"guidance_id": gid, "status": "acknowledged",
            "deduplicated": False}


def mark_applied(run_id: str, guidance_id: str,
                 evidence_refs: list[str]) -> None:
    """后续检查点引用同一 guidance 及证据 → applied_reported。"""
    with db.transaction() as conn:
        conn.execute(
            "UPDATE guidance SET applied_evidence=?, updated_at=?"
            " WHERE id=? AND run_id=? AND status='acknowledged'",
            (json.dumps(evidence_refs, ensure_ascii=False), db.utcnow(),
             guidance_id, run_id))
