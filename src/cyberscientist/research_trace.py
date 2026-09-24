"""Bounded, on-demand access to already persisted public Run evidence.

The capability identity and current review, never model arguments, choose the Run
and immutable event cutoff. No workspace paths or remote operations are accepted.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from . import config, db, observation

_EVENT_REF = re.compile(r"^event:([^:]+):(\d+)$")
_CHECKPOINT_REF = re.compile(r"^checkpoint:([A-Za-z0-9_-]+)$")
_MANIFEST_REF = re.compile(r"^manifest:([A-Za-z0-9_-]+)$")
_PER_CALL = 6000
_PER_REVIEW = 24000


class TraceError(ValueError):
    pass


def _active_review(run_id: str) -> Any:
    run = db.query_one("SELECT phase FROM runs WHERE id=?", (run_id,))
    review = db.query_one(
        "SELECT id,through_seq FROM review_requests WHERE run_id=?"
        " AND status='running' AND through_seq IS NOT NULL"
        " ORDER BY rowid DESC LIMIT 1", (run_id,))
    if not run or run["phase"] != "running" or not review:
        raise TraceError("当前没有可读取的运行中大脑审阅")
    return review


def _checkpoint(run_id: str, cp_id: str, cutoff: int) -> tuple[dict, int] | None:
    row = db.query_one("SELECT * FROM checkpoints WHERE run_id=? AND id=?",
                       (run_id, cp_id))
    if not row:
        return None
    event = db.query_one(
        "SELECT seq FROM events WHERE run_id=? AND type='checkpoint.created'"
        " AND json_extract(payload,'$.checkpoint_id')=? AND seq<=?",
        (run_id, cp_id, cutoff))
    return (dict(row), event["seq"]) if event else None


def _manifest(run_id: str, op_id: str, cutoff: int) -> tuple[dict, int, str] | None:
    job = db.query_one("SELECT request_hash FROM compute_jobs WHERE run_id=?"
                       " AND operation_id=?", (run_id, op_id))
    if not job:
        return None
    event = db.query_one(
        "SELECT seq FROM events WHERE run_id=? AND seq<=?"
        " AND type IN ('job.accepted','job.unknown','job.not_started')"
        " AND json_extract(payload,'$.operation_id')=?"
        " ORDER BY seq LIMIT 1", (run_id, cutoff, op_id))
    if not event:
        return None
    path = config.DATA_DIR / "job-inputs" / op_id / "manifest.json"
    if (not path.is_file() or path.is_symlink() or path.parent.is_symlink()
            or path.stat().st_size > 200_000):
        return None
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(data, dict) or data.get("request_hash") != job["request_hash"]
            or not isinstance(data.get("files"), list)):
        return None
    return data, event["seq"], hashlib.sha256(raw).hexdigest()


def ref_exists(run_id: str, ref: str, cutoff: int) -> bool:
    """Validate a cited public reference without reading its content."""
    if match := _EVENT_REF.fullmatch(ref):
        if match[1] != run_id or int(match[2]) > cutoff:
            return False
        return db.query_one("SELECT 1 FROM events WHERE run_id=? AND seq=?"
                            " AND source!='brain'", (run_id, int(match[2]))) is not None
    if match := _CHECKPOINT_REF.fullmatch(ref):
        return _checkpoint(run_id, match[1], cutoff) is not None
    if match := _MANIFEST_REF.fullmatch(ref):
        return _manifest(run_id, match[1], cutoff) is not None
    return False


def access(run_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Read a page or a stored record, then audit the exact slice returned."""
    review = _active_review(run_id)
    cutoff, review_id = review["through_seq"], review["id"]
    action = args.get("action")
    if action == "list":
        cursor = args.get("cursor", 0)
        limit = args.get("limit", 25)
        keyword = args.get("keyword", "")
        kind = args.get("event_type", "")
        if (not isinstance(cursor, int) or cursor < 0 or
                not isinstance(limit, int) or not 1 <= limit <= 50 or
                not isinstance(keyword, str) or len(keyword) > 100 or
                not isinstance(kind, str) or len(kind) > 100):
            raise TraceError("查询范围无效")
        rows = db.query(
            "SELECT seq,type,source,payload,recorded_at FROM events"
            " WHERE run_id=? AND seq>? AND seq<=? AND source!='brain'"
            " AND (?='' OR type=?) AND (?='' OR instr(payload,?)>0)"
            " ORDER BY seq LIMIT ?",
            (run_id, cursor, cutoff, kind, kind, keyword, keyword, limit + 1))
        items = []
        next_cursor = None
        for row in rows[:limit]:
            ref = f"event:{run_id}:{row['seq']}"
            payload = json.loads(row["payload"])
            item = {"ref": ref, "seq": row["seq"], "type": row["type"],
                    "source": row["source"], "recorded_at": row["recorded_at"],
                    "excerpt": observation.strip_secrets(row["payload"])[:120]}
            if row["type"] == "checkpoint.created" and payload.get("checkpoint_id"):
                item["checkpoint_ref"] = f"checkpoint:{payload['checkpoint_id']}"
            if row["type"].startswith("job.") and payload.get("operation_id"):
                if _manifest(run_id, payload["operation_id"], cutoff):
                    item["manifest_ref"] = f"manifest:{payload['operation_id']}"
            if len(json.dumps(items + [item], ensure_ascii=False)) > _PER_CALL - 500:
                next_cursor = items[-1]["seq"] if items else cursor
                break
            items.append(item)
        if next_cursor is None and len(rows) > len(items):
            next_cursor = items[-1]["seq"] if items else cursor
        result = {"action": "list", "run_id": run_id, "review_id": review_id,
                  "through_seq": cutoff, "items": items,
                  "next_cursor": next_cursor,
                  "scope": "stored_public_records"}
    elif action == "read":
        ref, offset = args.get("ref"), args.get("offset", 0)
        if not isinstance(ref, str) or not isinstance(offset, int) or offset < 0:
            raise TraceError("引用或范围无效")
        seq: int
        if match := _EVENT_REF.fullmatch(ref):
            if match[1] != run_id or int(match[2]) > cutoff:
                raise TraceError("引用不在本次审阅范围")
            row = db.query_one("SELECT * FROM events WHERE run_id=? AND seq=?"
                               " AND source!='brain'", (run_id, int(match[2])))
            if not row:
                raise TraceError("公开事件不存在")
            seq = row["seq"]
            raw = {"type": row["type"], "source": row["source"],
                   "recorded_at": row["recorded_at"],
                   "trial_id": row["trial_id"], "payload": json.loads(row["payload"])}
            version = f"event-seq:{seq}"
        elif match := _CHECKPOINT_REF.fullmatch(ref):
            item = _checkpoint(run_id, match[1], cutoff)
            if not item:
                raise TraceError("检查点不存在或晚于本次审阅")
            row, seq = item
            raw = {"source": row["source"], "stage": row["stage"],
                   "report_md": row["report"],
                   "evidence_refs": json.loads(row["evidence_refs"] or "[]")}
            version = row["content_hash"]
        elif match := _MANIFEST_REF.fullmatch(ref):
            item = _manifest(run_id, match[1], cutoff)
            if not item:
                raise TraceError("冻结输入清单不存在或版本无法确认")
            raw, seq, digest = item
            version = f"saved-manifest-sha256:{digest}"
        else:
            raise TraceError("只支持已登记的 event/checkpoint/manifest 引用")
        body = observation.strip_secrets(json.dumps(raw, ensure_ascii=False))
        if offset > len(body):
            raise TraceError("读取范围超出记录长度")
        part = body[offset:offset + _PER_CALL]
        while len(json.dumps({"content": part}, ensure_ascii=False)) > _PER_CALL - 400:
            part = part[:max(1, len(part) - 500)]
        result = {"action": "read", "ref": ref, "source_seq": seq,
                  "review_id": review_id, "through_seq": cutoff,
                  "version": version, "content": part,
                  "truncated": offset + len(part) < len(body),
                  "next_offset": offset + len(part) if offset + len(part) < len(body) else None,
                  "scope": "stored_public_record; original_external_log_may_be_unavailable"}
    else:
        raise TraceError("只支持 list/read")

    size = len(json.dumps(result, ensure_ascii=False))
    with db.transaction() as conn:
        current = conn.execute("SELECT status,through_seq FROM review_requests WHERE id=?",
                               (review_id,)).fetchone()
        phase = conn.execute("SELECT phase FROM runs WHERE id=?", (run_id,)).fetchone()
        if not current or current["status"] != "running" or current["through_seq"] != cutoff \
                or not phase or phase["phase"] != "running":
            raise TraceError("审阅已变更；读取结果未交付")
        used = conn.execute("SELECT COALESCE(SUM(json_extract(payload,'$.chars')),0) AS n"
                            " FROM events WHERE run_id=? AND type='brain.trace_read'"
                            " AND json_extract(payload,'$.review_id')=?",
                            (run_id, review_id)).fetchone()["n"]
        if size + used > _PER_REVIEW:
            raise TraceError("本轮读取额度已用尽；未自动展开更多轨迹")
        db.append_event_tx(conn, run_id, "brain", "brain.trace_read",
                           {"review_id": review_id, "action": action,
                            "ref": result.get("ref"), "source_seq": result.get("source_seq"),
                            "count": len(result.get("items", [])), "chars": size,
                            "through_seq": cutoff})
    return result
