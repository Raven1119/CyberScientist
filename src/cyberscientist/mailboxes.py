"""邮箱管理双轨服务：实验邮箱与收割邮箱均按题目预留额度。

事实纪律：分数不知道就是 NULL/unknown；外部调用（适配器）绝不在事务内；
operation_id 幂等去重；额度只从未释放的 submissions 预留计算。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import arm_admission, config, datasets, db, experience_context, package_seal, trace_diagnostics, trace_narrative, trace_selection
from .mailbox_platform import (MailboxPlatform, PlatformError, final_score,
                               explicit_create_rejection, get_platform, public_feedback)


class MailboxError(Exception):
    def __init__(self, code: str, message: str, *, warnings: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.warnings = warnings or []


def _rid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _platform() -> MailboxPlatform:
    return get_platform(config.load_settings()["mailbox"]["platform"])


def _store_secret(secret_id: str, value: str) -> str:
    config.update_secret(secret_id, value)
    return f"local:{secret_id}"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d.pop("secret_ref", None)  # 凭据引用不出服务层
    d.pop("submissions_used", None)  # 旧全局计数器仅为 schema 兼容保留
    d["submission_limit"] = config.load_settings()["mailbox"]["submission_limit"]
    d["secret_configured"] = bool(row["secret_ref"]) and \
        config.secret_configured(row["secret_ref"])
    return d


# ---------- 查询 ----------

def list_mailboxes() -> dict[str, Any]:
    rows = db.query("SELECT * FROM mailboxes ORDER BY role, created_at")
    return {"items": [_row(r) for r in rows],
            "platform": config.load_settings()["mailbox"]["platform"],
            "platform_is_demo": _platform().is_demo}


def mailbox_usage() -> dict[str, Any]:
    """All registered challenge × mailbox pairs; usage derives from submissions."""
    limit = config.load_settings()["mailbox"]["submission_limit"]
    rows = db.query("SELECT m.id AS mailbox_id,m.email,m.role,"
                    " COALESCE(NULLIF(c.platform_challenge_id,''),'local:'||c.id) AS platform_challenge_id,"
                    " MIN(c.title) AS challenge_title,COUNT(s.id) AS used"
                    " FROM challenges c CROSS JOIN mailboxes m"
                    " LEFT JOIN runs r ON r.challenge_id=c.id"
                    " LEFT JOIN submissions s ON s.run_id=r.id AND s.mailbox_id=m.id"
                    " AND s.reservation_released=0"
                    " GROUP BY m.id,COALESCE(NULLIF(c.platform_challenge_id,''),'local:'||c.id)"
                    " ORDER BY challenge_title,m.role,m.created_at")
    return {"items": [dict(row) | {"limit": limit} for row in rows], "limit": limit}


def _challenge_key(conn: sqlite3.Connection, run_id: str) -> str:
    row = conn.execute("SELECT c.id,c.platform_challenge_id FROM runs r"
                       " JOIN challenges c ON c.id=r.challenge_id WHERE r.id=?", (run_id,)).fetchone()
    if not row:
        raise MailboxError("NOT_FOUND", f"Run 不存在: {run_id}")
    return row["platform_challenge_id"] or "local:" + row["id"]


def _used_for(conn: sqlite3.Connection, mailbox_id: str, challenge_key: str) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM submissions s"
        " JOIN runs r ON r.id=s.run_id JOIN challenges c ON c.id=r.challenge_id"
        " WHERE s.mailbox_id=? AND s.reservation_released=0"
        " AND COALESCE(NULLIF(c.platform_challenge_id,''),'local:'||c.id)=?",
        (mailbox_id, challenge_key)).fetchone()["n"]


def _instant(value: str | None) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None
        return parsed.replace(tzinfo=timezone.utc) if parsed and parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _round_end(snapshot: str | None) -> datetime | None:
    try:
        value = json.loads(snapshot or '{}')
    except (ValueError, TypeError):
        return None
    def find(node):
        if isinstance(node, dict):
            if 'roundEndAt' in node:
                return _instant(node['roundEndAt'])
            for child in node.values():
                found = find(child)
                if found: return found
        elif isinstance(node, list):
            for child in node:
                found = find(child)
                if found: return found
        return None
    return find(value)


def _poll_deadline(row) -> datetime | None:
    round_end = _round_end(row['platform_snapshot_json'])
    if round_end:
        return round_end + timedelta(hours=72)
    submitted = _instant(row['submitted_at'] or row['created_at'])
    return submitted + timedelta(days=7) if submitted else None


def _score_anomaly(details: dict[str, Any] | None) -> str | None:
    if not isinstance(details, dict):
        return 'score details unavailable'
    state = details.get('scoringState')
    if not isinstance(state, dict):
        return 'scoringState unavailable'
    reasons = []
    if state.get('zeroReason') not in (None, ''):
        reasons.append('zeroReason')
    if state.get('provisionalScore') not in (None, ''):
        reasons.append('provisionalScore')
    def has_error(node):
        if isinstance(node, dict):
            return any((key.lower() in ('error', 'errorinfo', 'errors', 'errormessage')
                        and value not in (None, '', [], {})) or has_error(value)
                       for key, value in node.items())
        if isinstance(node, list):
            return any(has_error(value) for value in node)
        return False
    if has_error(details):
        reasons.append('scoring error')
    worker = state.get('workerStatus')
    if worker is not None:
        if str(worker).lower() not in ('completed', 'complete', 'finished', 'success', 'succeeded', 'done', 'ok'):
            reasons.append('workerStatus=' + str(worker)[:40])
    elif state.get('state') != 'final' and state.get('scoreIsFinal') is not True:
        reasons.append('worker status unknown')
    if 'displayScore' not in state:
        reasons.append('displayScore unavailable')
    return '; '.join(dict.fromkeys(reasons)) or None


def _score_components(attempt: dict[str, Any] | None,
                      score_details: dict[str, Any] | None = None) -> tuple[float | None, float | None]:
    """Attempt scorecard is authoritative; old /score components are fallback."""
    def find(node, key):
        if isinstance(node, dict):
            scorecard = node.get('scorecard')
            if isinstance(scorecard, dict) and key in scorecard:
                return scorecard[key]
            if key in node: return node[key]
            for child in node.values():
                found = find(child, key)
                if found is not None: return found
        elif isinstance(node, list):
            for child in node:
                found = find(child, key)
                if found is not None: return found
        return None
    def finite(value):
        return float(value) if type(value) in (int, float) and math.isfinite(value) else None
    def preferred(key):
        first = finite(find(attempt, key))
        return first if first is not None else finite(find(score_details, key))
    return preferred('harbor_score'), preferred('trace_score')


def _scorecard_consistency(details: dict[str, Any] | None, display: float,
                           score_details: dict[str, Any] | None = None) -> int | None:
    harbor, trace = _score_components(details, score_details)
    if harbor is None or trace is None:
        return None
    expected = harbor * max(0.0, min(1.0, (trace - 30.0) / 40.0))
    return int(abs(display - expected) <= 0.5)


def list_submissions(run_id: str) -> dict[str, Any]:
    rows = db.query(
        "SELECT s.*, m.email AS mailbox_email, m.role AS mailbox_role"
        " FROM submissions s JOIN mailboxes m ON m.id=s.mailbox_id"
        " WHERE s.run_id=? ORDER BY s.created_at", (run_id,))
    return {"items": _submission_items(rows)}


def list_challenge_submissions(challenge_id: str) -> dict[str, Any]:
    """题目级提交聚合：该题所有 Run 的提交，新的在前。
    item 形状与 list_submissions 完全一致（s.* + mailbox_email/role），
    供前端「提交与评分」tab 按题聚合。"""
    if not db.query_one("SELECT id FROM challenges WHERE id=?",
                        (challenge_id,)):
        raise MailboxError("NOT_FOUND", f"题目不存在: {challenge_id}")
    rows = db.query(
        "SELECT s.*, m.email AS mailbox_email, m.role AS mailbox_role"
        " FROM submissions s JOIN mailboxes m ON m.id=s.mailbox_id"
        " JOIN runs r ON r.id=s.run_id"
        " WHERE r.challenge_id=? ORDER BY s.created_at DESC", (challenge_id,))
    return {"items": _submission_items(rows)}


def _submission_items(rows) -> list[dict[str, Any]]:
    """Project durable feedback events into the existing submission API."""
    items = {row["id"]: dict(row) | {"platform_feedback": {}} for row in rows}
    run_ids = sorted({row["run_id"] for row in rows})
    if not run_ids:
        return []
    marks = ",".join("?" for _ in run_ids)
    events = db.query(
        f"SELECT payload,recorded_at FROM events WHERE run_id IN ({marks})"
        " AND type='submission.platform_feedback' ORDER BY seq DESC", run_ids)
    for event in events:
        payload = json.loads(event["payload"])
        item = items.get(payload.get("submission_id"))
        if item is not None:
            item["platform_feedback"].setdefault(payload["kind"], {
                "response": payload["response"], "recorded_at": event["recorded_at"]})
    return list(items.values())


def _record_feedback(conn, row, kind: str, response: dict[str, Any]) -> bool:
    """Keep changed platform observations, including non-final grader failures."""
    previous = conn.execute(
        "SELECT payload FROM events WHERE run_id=?"
        " AND type='submission.platform_feedback'"
        " AND json_extract(payload,'$.submission_id')=?"
        " AND json_extract(payload,'$.kind')=? ORDER BY seq DESC LIMIT 1",
        (row["run_id"], row["id"], kind)).fetchone()
    if previous and json.loads(previous["payload"])["response"] == response:
        return False
    db.append_event_tx(conn, row["run_id"], "controller", "submission.platform_feedback", {
        "submission_id": row["id"], "platform_ref": row["platform_ref"],
        "kind": kind, "response": response}, trial_id=row["trial_id"])
    return True


def _submission_metadata(run_id: str) -> dict[str, Any]:
    """Model identity follows the frozen Run, not today's connection settings."""
    run = db.query_one("SELECT mode,config_snapshot FROM runs WHERE id=?", (run_id,))
    settings = json.loads(run["config_snapshot"]).get("settings", {})
    executor = settings.get("executor") or {}
    runtime = "demo" if run["mode"] == "demo" else executor.get("runtime")
    label = {"codex": "Codex", "kimi": "Kimi Code", "prime": "Prime Agent",
             "demo": "Demo"}.get(runtime, "unknown")
    model = "demo" if runtime == "demo" else executor.get("model_id")
    return {"model": model, "harness": f"CyberScientist ({label})"}


# ---------- 邮箱管理 ----------

def add_harvest(email: str, secret_value: str) -> dict[str, Any]:
    """收割邮箱：用户提供，全局唯一（DB 部分唯一索引强制）。"""
    email = email.strip()
    if not email or "@" not in email:
        raise MailboxError("INVALID_MESSAGE", "邮箱地址格式不正确")
    if not secret_value:
        raise MailboxError("MISSING_CREDENTIAL", "收割邮箱需要凭据（密码/令牌）")
    platform = _platform()
    mid = _rid("mbox")
    secret_ref = _store_secret(f"mailbox_{mid}", secret_value)
    try:
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO mailboxes(id, role, email, platform, secret_ref,"
                " status, submission_limit, is_demo, created_at)"
                " VALUES(?,?,?,?,?,'active',?,?,?)",
                (mid, "harvest", email, platform.name, secret_ref,
                 config.load_settings()["mailbox"]["submission_limit"],
                 int(platform.is_demo), db.utcnow()))
    except sqlite3.IntegrityError as exc:
        raise MailboxError("CONFLICT",
                           "已存在可用的收割邮箱；先停用旧的再添加") from exc
    return _row(db.query_one("SELECT * FROM mailboxes WHERE id=?", (mid,)))


def register_experiment(count: int) -> dict[str, Any]:
    """批量注册实验邮箱。真实平台未配置时报准确缺项。"""
    if not 1 <= count <= 20:
        raise MailboxError("INVALID_MESSAGE", "单次注册数量须为 1-20")
    platform = _platform()
    limit = config.load_settings()["mailbox"]["submission_limit"]
    items, errors = [], []
    for index in range(count):
        try:
            acc = platform.register_account()
        except Exception as exc:
            if not items and isinstance(exc, PlatformError):
                raise MailboxError("MISSING_CREDENTIAL", str(exc)) from exc
            errors.append({"index": index, "error": type(exc).__name__,
                           "outcome": "unknown", "retry_safe": False})
            break
        mid = _rid("mbox")
        secret_ref = _store_secret(f"mailbox_{mid}", acc["password"])
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO mailboxes(id, role, email, platform, secret_ref,"
                " status, submission_limit, is_demo, created_at)"
                " VALUES(?,?,?,?,?,'active',?,?,?)",
                (mid, "experiment", acc["email"], platform.name, secret_ref,
                 limit, int(platform.is_demo), db.utcnow()))
        items.append(_row(db.query_one("SELECT * FROM mailboxes WHERE id=?", (mid,))))
    return {"items": items, "is_demo": platform.is_demo, "errors": errors}


def disable_mailbox(mailbox_id: str) -> dict[str, Any]:
    with db.transaction() as conn:
        cur = conn.execute(
            "UPDATE mailboxes SET status='disabled', disabled_at=?"
            " WHERE id=? AND status<>'disabled'", (db.utcnow(), mailbox_id))
        if cur.rowcount == 0:
            raise MailboxError("NOT_FOUND", f"邮箱不存在或已停用: {mailbox_id}")
    return _row(db.query_one("SELECT * FROM mailboxes WHERE id=?",
                             (mailbox_id,)))


# ---------- 提交 ----------

def _resolve_package(run_id: str, trial_id: str | None,
                     package_path: str | None) -> Path:
    """定位现成提交包：显式相对路径，或 Trial 目录下的约定文件。"""
    root = config.WORKSPACE_DIR.resolve()
    candidates: list[Path] = []
    if package_path:
        candidates.append((root / package_path).resolve())
    if trial_id:
        tdir = root / "runs" / run_id / "trials" / trial_id
        candidates += [tdir / "result_package.zip", tdir / "result_package.json",
                       tdir / "submission.csv"]
    for p in candidates:
        if p.exists() and p.is_file() and root in p.parents:
            return p
    raise MailboxError(
        "NOT_FOUND",
        "未找到提交包：需要 Trial 目录下的 result_package.zip / result_package.json /"
        " submission.csv，或显式 package_path（工作区相对路径）")


def _run_challenge_id(run_id: str) -> str:
    """真实平台提交目标是 challenges.platform_challenge_id（平台侧 slug），
    不是本地 challenge id。"""
    row = db.query_one(
        "SELECT c.platform_challenge_id AS pid FROM runs r"
        " JOIN challenges c ON c.id=r.challenge_id WHERE r.id=?", (run_id,))
    if not row:
        raise MailboxError("NOT_FOUND", f"Run 不存在: {run_id}")
    return row["pid"] or ""


def _check_budget(conn, run_id: str) -> None:
    run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise MailboxError("NOT_FOUND", f"Run 不存在: {run_id}")
    if run["phase"] in ("pausing", "paused", "cancelled", "failed", "finished", "recovering"):
        raise MailboxError("INVALID_STATE", "当前 Run 不允许新增提交")
    auth = conn.execute("SELECT * FROM authorizations WHERE id=? AND run_id=?",
                        (run["authorization_id"], run_id)).fetchone()
    if auth and auth["max_run_minutes"] and run["started_at"]:
        from . import run_clock
        if run_clock.remaining(run, auth) <= 0:
            raise MailboxError("NEEDS_AUTHORIZATION","本轮授权时长已用尽")
    limit = auth["max_submissions"] if auth else 0
    used = conn.execute("SELECT COUNT(*) AS n FROM submissions WHERE run_id=?"
                        " AND is_harvest=0 AND reservation_released=0",
                        (run_id,)).fetchone()["n"]
    if used >= limit:
        raise MailboxError("NEEDS_AUTHORIZATION", f"提交授权已用尽（{used}/{limit}）")


def _request_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _duplicate(conn, operation_id: str, fingerprint: str):
    row = conn.execute("SELECT * FROM submissions WHERE operation_id=?",
                       (operation_id,)).fetchone()
    if row and row["request_hash"] != fingerprint:
        raise MailboxError("CONFLICT", "幂等键已用于不同请求或历史请求身份无法确认")
    return dict(row) | {"deduplicated": True} if row else None


def _freeze(sid: str, package: Path, content: bytes) -> str:
    directory = config.WORKSPACE_DIR / "submissions" / sid
    directory.mkdir(parents=True, exist_ok=True)
    frozen = directory / ("package" + package.suffix)
    with frozen.open("xb") as stream:
        stream.write(content)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    return frozen.relative_to(config.WORKSPACE_DIR).as_posix()


def _science_artifact_hashes(bundle: bytes) -> dict[str, str]:
    """Exact byte hashes for every non-trace, non-manifest bundle member."""
    import io
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise MailboxError('INVALID_PACKAGE', '来源包存在同名 ZIP 成员')
        root = trace_selection.bundle_root({name: b'' for name in names})
        return {name[len(root):]: hashlib.sha256(archive.read(name)).hexdigest()
                for name in names if name.startswith(root)
                and not name.endswith('/') and name != root + 'arm_manifest.json'
                and not name.startswith(root + 'traces/')
                and not name.startswith(root + 'trace/')
                and name != root + 'trace.json'}


def _protocol_snapshot() -> dict[str, Any] | None:
    path = Path(__file__).resolve().parents[2] / "contracts" / "arm_protocol.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _data_inputs(run_id: str, trial_id: str | None) -> dict[str, Any]:
    from . import artifact_contracts
    run = artifact_contracts.for_run(run_id)
    try:
        resources = json.loads(run["resources_json"] or "[]") if run else []
    except ValueError:
        resources = []
    requires_data = datasets.task_requires_data(run["content"] if run else None, resources)
    rows = db.query("SELECT data_refs_json FROM compute_jobs WHERE run_id=?"
                    + (" AND trial_id=?" if trial_id else ""),
                    (run_id, trial_id) if trial_id else (run_id,))
    refs = sorted({ref for row in rows for ref in json.loads(row["data_refs_json"] or "[]")})
    materializations = []
    for ref in refs:
        item = db.query_one("SELECT id,resource_key,store_path,status FROM data_materializations WHERE id=?", (ref,))
        if item and item["store_path"]:
            materializations.append({"id": item["id"], "resource_key": item["resource_key"],
                                     "content_sha256": Path(item["store_path"]).name,
                                     "status": item["status"]})
    return {"evidence_class": "official_data" if refs else ("proxy" if requires_data else "not_applicable"),
            "materializations": materializations}


def _narrative_for_trial(run_id: str, trial_id: str | None) -> tuple[bytes | None, str | None]:
    if not trial_id:
        return None, None
    trial = db.query_one("SELECT 1 FROM trials WHERE id=? AND run_id=?", (trial_id, run_id))
    if not trial:
        return None, None
    root = config.WORKSPACE_DIR.resolve()
    base = (root / "runs" / run_id / "trials" / trial_id).resolve()
    if root not in base.parents:
        raise MailboxError("INVALID_TRACE_NARRATIVE", "叙述文件路径越界")
    path = base / "trace_narrative.jsonl"
    if not path.exists():
        return None, None
    if path.is_symlink() or path.resolve().parent != base or not path.is_file():
        raise MailboxError("INVALID_TRACE_NARRATIVE", "叙述文件必须是当前 Trial 内的普通文件")
    from datetime import datetime, timezone
    written_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return path.read_bytes(), written_at


def preflight_submission(run_id: str, trial_id: str | None,
                         package_path: str | None, *, allow_proxy_evidence: bool = False,
                         allow_indeterminate_admission: bool = False,
                         narrative_snapshot: tuple[bytes | None, str | None, int] | None = None,
                         data_inputs_override: dict[str, Any] | None = None) -> dict[str, Any]:
    if type(allow_proxy_evidence) is not bool or type(allow_indeterminate_admission) is not bool:
        raise MailboxError("INVALID_ARGUMENT", "提交准入覆盖标志必须是显式布尔值")
    package = _resolve_package(run_id, trial_id, package_path)
    source = package.read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    data = data_inputs_override if data_inputs_override is not None else _data_inputs(run_id, trial_id)
    is_bundle = package.suffix.lower() == ".zip"
    sealed, steps = source, []
    report = {"verdict": "not_applicable", "signals": {}}
    if is_bundle:
        if narrative_snapshot is None:
            last = db.query_one("SELECT MAX(seq) AS n FROM events WHERE run_id=?", (run_id,))
            through_seq = last["n"] or 0
            narrative_bytes, narrative_written_at = _narrative_for_trial(run_id, trial_id)
        else:
            narrative_bytes, narrative_written_at, through_seq = narrative_snapshot
        try:
            sealed, steps = package_seal.seal(
                source, run_id, trial_id, through_seq, data,
                narrative_bytes=narrative_bytes,
                narrative_written_at=narrative_written_at)
        except trace_narrative.InvalidTraceNarrative as exc:
            with db.transaction() as conn:
                db.append_event_tx(conn, run_id, "controller", "submission.preflight_failed",
                    {"code": "INVALID_TRACE_NARRATIVE", "reasons": exc.reasons[:50],
                     "source_package_sha256": source_hash}, trial_id=trial_id)
            raise MailboxError("INVALID_TRACE_NARRATIVE",
                               "轨迹叙述校验失败：" + "; ".join(exc.reasons),
                               warnings=exc.reasons) from exc
        except (KeyError, ValueError, TypeError, sqlite3.Error, OSError, zipfile.BadZipFile) as exc:
            with db.transaction() as conn:
                db.append_event_tx(conn, run_id, "controller", "submission.preflight_failed",
                    {"code": "INVALID_PACKAGE", "reason": str(exc)[:200],
                     "source_package_sha256": source_hash}, trial_id=trial_id)
            raise MailboxError("INVALID_PACKAGE", f"ARM 包无法封存：{type(exc).__name__}") from exc
        report = arm_admission.check(sealed, _protocol_snapshot())
    code = None
    advisory_warnings = []
    if report["verdict"] in ('blocked', 'indeterminate'):
        advisory_warnings.append('轨迹诊断：' + report['verdict'])
    if data["evidence_class"] == "proxy":
        advisory_warnings.append('数据证据为 proxy，正式评分适用性仍需确认')
    if code is None and is_bundle:
        import io
        from . import job_preflight
        try:
            with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
                names = archive.namelist()
                all_files = {name: archive.read(name) for name in names}
                root = trace_selection.select(all_files).bundle_root
                manifest = json.loads(all_files[root + "arm_manifest.json"])
                files = {name[len(root):]: raw for name, raw in all_files.items()
                         if name.startswith(root) and name.endswith((".py", ".txt"))
                         and len(raw) <= 2_000_000}
            job_preflight.check_sources(files, entry=manifest.get("entrypoint"))
        except job_preflight.PreflightError as exc:
            advisory_warnings.append('环境/源码预检建议：' + exc.code)
        except (KeyError, ValueError, zipfile.BadZipFile):
            code = "INVALID_PACKAGE"
    diagnostic = trace_diagnostics.unavailable("non_ARM_bundle")
    if is_bundle:
        try:
            from . import artifact_contracts
            challenge = artifact_contracts.for_run(run_id)
            diagnostic = trace_diagnostics.diagnose_sealed_package(
                sealed, challenge["content"] if challenge else "")
        except Exception as exc:
            diagnostic = trace_diagnostics.unavailable(type(exc).__name__)
    return {"source_package_sha256": source_hash,
            "sealed_package_sha256": hashlib.sha256(sealed).hexdigest(),
            "sealed_bytes": sealed, "admission": report, "projected_steps": steps,
            "data_inputs": data, "trace_diagnostics": diagnostic,
            "allow_proxy_evidence": allow_proxy_evidence,
            "allow_indeterminate_admission": allow_indeterminate_admission,
            "error_code": code, "advisory_warnings": advisory_warnings,
            "artifact_contract": _artifact_contract(run_id, sealed)}


def _artifact_contract(run_id: str, sealed: bytes) -> dict[str, Any]:
    from . import artifact_contracts
    run = db.query_one('SELECT challenge_id FROM runs WHERE id=?', (run_id,))
    return artifact_contracts.inspect(run['challenge_id'], sealed, task_content=artifact_contracts.for_run(run_id)['content'])


def inspect_trace_narrative(run_id: str, trial_id: str | None,
                            package_path: str | None) -> dict[str, Any]:
    """Read-only preview of exactly the narrative merge and local admission."""
    package = _resolve_package(run_id, trial_id, package_path)
    trial_root = (config.WORKSPACE_DIR.resolve() / "runs" / run_id / "trials" / (trial_id or "")).resolve()
    if not trial_id or trial_root not in package.parents or not db.query_one(
            "SELECT 1 FROM trials WHERE id=? AND run_id=?", (trial_id, run_id)):
        return {"valid": False, "reasons": ["提交包必须位于当前 Run 的 Trial 目录"]}
    if package.suffix.lower() != ".zip":
        return {"valid": False, "reasons": ["轨迹叙述需要 ARM ZIP 提交包"]}
    narrative_bytes, written_at = _narrative_for_trial(run_id, trial_id)
    if narrative_bytes is None:
        return {"valid": False, "reasons": ["当前 Trial 没有 trace_narrative.jsonl"]}
    source = package.read_bytes()
    last = db.query_one("SELECT MAX(seq) AS n FROM events WHERE run_id=?", (run_id,))
    try:
        sealed, merged = package_seal.seal(
            source, run_id, trial_id, last["n"] or 0,
            _data_inputs(run_id, trial_id), narrative_bytes=narrative_bytes,
            narrative_written_at=written_at)
    except trace_narrative.InvalidTraceNarrative as exc:
        return {"valid": False, "error_code": "INVALID_TRACE_NARRATIVE",
                "reasons": exc.reasons}
    except (ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        return {"valid": False, "error_code": "INVALID_PACKAGE",
                "reasons": [f"ARM 包无法封存：{type(exc).__name__}"]}
    return {"valid": True, "error_code": None, "reasons": [],
            "source_package_sha256": hashlib.sha256(source).hexdigest(),
            "sealed_package_sha256": hashlib.sha256(sealed).hexdigest(),
            "merged_trace": merged,
            "admission": arm_admission.check(sealed, _protocol_snapshot())}


def _perform_submission(sid: str, platform: MailboxPlatform, challenge_id: str) -> dict:
    row = db.query_one("SELECT s.*, m.email, m.secret_ref, m.platform FROM submissions s"
                       " JOIN mailboxes m ON m.id=s.mailbox_id WHERE s.id=?", (sid,))
    def stage(name, attempt_id=None):
        with db.transaction() as conn:
            conn.execute("UPDATE submissions SET stage=?,platform_ref=COALESCE(?,platform_ref) WHERE id=?",
                         (name, str(attempt_id) if attempt_id is not None else None, sid))
            db.append_event_tx(conn,row["run_id"],"controller","submission.stage",
                               {"submission_id":sid,"stage":name,"platform_ref":attempt_id},
                               trial_id=row["trial_id"])
    def feedback(kind, response):
        if not isinstance(response, dict):
            return
        safe = public_feedback(response, *config.sensitive_values())
        with db.transaction() as conn:
            current = conn.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
            _record_feedback(conn, current, kind, safe)
    stage("prepared")
    try:
        frozen_bytes = (config.WORKSPACE_DIR / row["package_path"]).read_bytes()
        if hashlib.sha256(frozen_bytes).hexdigest() != row["package_sha256"]:
            raise PlatformError("冻结提交包哈希不匹配，未发送",no_side_effect=True)
        receipt = platform.submit_package(
            row["email"], config.resolve_secret(row["secret_ref"] or ""),
            str(config.WORKSPACE_DIR / row["package_path"]), challenge_id=challenge_id,
            meta={"on_stage": stage, "on_feedback": feedback,
                  "package_bytes": frozen_bytes,
                  "trace": _form_trace(frozen_bytes), **_submission_metadata(row["run_id"])})
        # Only explicit definitive rejection without a remote side effect releases quota.
        status = "submitted" if receipt.get("accepted") is True else "unknown"
        if receipt.get("accepted") is False and receipt.get("no_side_effect") is True:
            status = "failed"
        error = None
        if receipt.get("receipt"):
            stage("submitted" if status == "submitted" else "unknown", receipt["receipt"])
    except Exception as exc:
        status = "failed" if isinstance(exc, PlatformError) and exc.no_side_effect else "unknown"
        # External response bodies can contain credentials; record only classified errors.
        error = str(exc) if isinstance(exc, PlatformError) else type(exc).__name__
    with db.transaction() as conn:
        current = conn.execute("SELECT * FROM submissions WHERE id=?",(sid,)).fetchone()
        conn.execute("UPDATE submissions SET status=?,score_status=?,error=?,submitted_at=? WHERE id=?",
                     (status,"pending" if status == "submitted" else "unknown",error,
                      db.utcnow() if status == "submitted" else None,sid))
        if status == "failed" and not current["reservation_released"]:
            conn.execute("UPDATE submissions SET reservation_released=1 WHERE id=?",(sid,))
        db.append_event_tx(conn,row["run_id"],"controller",f"submission.{status}",
                           {"submission_id":sid,"error":error,"is_demo":platform.is_demo},
                           trial_id=row["trial_id"])
    return dict(db.query_one("SELECT * FROM submissions WHERE id=?",(sid,))) | {"deduplicated":False}


def reconcile_explicit_create_rejection(submission_id: str) -> dict[str, Any]:
    """Release only a create reservation with a persisted server no-storage claim."""
    with db.transaction() as conn:
        row = conn.execute("SELECT * FROM submissions WHERE id=?", (submission_id,)).fetchone()
        if row is None:
            raise MailboxError("NOT_FOUND", "提交不存在")
        if (row["status"] != "unknown" or row["stage"] != "create_sent"
                or row["platform_ref"] is not None or row["reservation_released"]
                or not explicit_create_rejection(row["error"])):
            raise MailboxError("RECONCILIATION_NOT_PROVEN",
                               "没有明确的创建未存储回执，保留 unknown 与预留")
        conn.execute("UPDATE submissions SET status='failed',reservation_released=1 WHERE id=?",
                     (submission_id,))
        db.append_event_tx(conn, row["run_id"], "controller", "submission.failed",
                           {"submission_id": submission_id,
                            "reason": "platform_create_nothing_stored",
                            "reconciled": True}, trial_id=row["trial_id"])
    return dict(db.query_one("SELECT * FROM submissions WHERE id=?", (submission_id,)))


def _form_trace(package_bytes: bytes) -> list[dict[str, Any]]:
    import io
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
            selected = trace_selection.select(files)
            rows = [json.loads(line) for line in files[selected.bundle_root + package_seal.TRACE].splitlines()
                    if line.strip()]
        return rows[-20:] or [{"step_type": "observation", "title": "Sealed package",
                               "body": "提交封存包 " + hashlib.sha256(package_bytes).hexdigest()}]
    except (KeyError, ValueError, zipfile.BadZipFile):
        return [{"step_type": "observation", "title": "Sealed package",
                 "body": "提交封存包 " + hashlib.sha256(package_bytes).hexdigest()}]


def submit_experiment(run_id: str, trial_id: str | None,
                      package_path: str | None, operation_id: str,
                      allow_proxy_evidence: bool = False,
                      allow_indeterminate_admission: bool = False,
                      prediction_md: str | None = None, *,
                      variant_context: dict[str, Any] | None = None) -> dict[str, Any]:
    if not operation_id:
        raise MailboxError("INVALID_MESSAGE", "缺少 operation_id（幂等键）")
    if prediction_md is not None and (not isinstance(prediction_md,str) or
            not prediction_md.strip() or len(prediction_md)>4000):
        raise MailboxError('INVALID_MESSAGE','prediction_md 必须是有界非空文本')
    if prediction_md is not None:
        from .observation import strip_secrets
        prediction_md=strip_secrets(prediction_md)
        if not prediction_md.strip():
            raise MailboxError('INVALID_MESSAGE','prediction_md 不能只包含密钥')
    package = _resolve_package(run_id, trial_id, package_path)
    source_content = package.read_bytes()
    source_digest = hashlib.sha256(source_content).hexdigest()
    platform = _platform()
    challenge_id = _run_challenge_id(run_id)
    fingerprint_input = {"run_id":run_id,"trial_id":trial_id,
        "package_path":str(package),"hash":source_digest,"platform":platform.name,
        "challenge":challenge_id,"allow_proxy_evidence":allow_proxy_evidence,
        "allow_indeterminate_admission":allow_indeterminate_admission}
    if prediction_md is not None:
        fingerprint_input['prediction_md']=prediction_md
    if variant_context is not None:
        fingerprint_input['variant_of'] = variant_context['source_submission_id']
        fingerprint_input['narrative_sha256'] = variant_context['narrative_sha256']
    fingerprint = _request_hash(fingerprint_input)
    with db.transaction() as conn:
        dup = _duplicate(conn, operation_id, fingerprint)
        if dup: return dup
    check = preflight_submission(run_id, trial_id, package_path,
        allow_proxy_evidence=allow_proxy_evidence,
        allow_indeterminate_admission=allow_indeterminate_admission,
        narrative_snapshot=variant_context['narrative_snapshot'] if variant_context else None,
        data_inputs_override=variant_context['data_inputs'] if variant_context else None)
    science_hashes = None
    if check['source_package_sha256'] != source_digest:
        raise MailboxError('PACKAGE_CHANGED', '包在提交冻结期间变化，未预约或发起提交')
    if variant_context is not None:
        science_hashes = _science_artifact_hashes(check['sealed_bytes'])
        if science_hashes != variant_context['science_artifact_hashes']:
            raise MailboxError('SCIENCE_ARTIFACT_CHANGED',
                               '轨迹变体的非轨迹文件与来源冻结包不一致')
    if check["error_code"]:
        with db.transaction() as conn:
            db.append_event_tx(conn, run_id, "controller", "submission.preflight_failed",
                {"code": check["error_code"], "source_package_sha256": source_digest,
                 "sealed_package_sha256": check["sealed_package_sha256"],
                 "admission": check["admission"]}, trial_id=trial_id)
        raise MailboxError(check["error_code"], "提交包预检未通过")
    content = check["sealed_bytes"]
    digest = check["sealed_package_sha256"]
    with db.transaction() as conn:
        dup = _duplicate(conn,operation_id,fingerprint)
        if dup: return dup
        _check_budget(conn,run_id)
        challenge_key = _challenge_key(conn, run_id)
        limit = config.load_settings()["mailbox"]["submission_limit"]
        accounts = conn.execute("SELECT * FROM mailboxes WHERE role='experiment' AND status='active'"
                                " AND platform=? AND is_demo=? ORDER BY created_at,id",
                                (platform.name,int(platform.is_demo))).fetchall()
        available = [(mb, _used_for(conn, mb["id"], challenge_key)) for mb in accounts]
        available = [(mb, used) for mb, used in available if used < limit]
        mb = sorted(available, key=lambda item: (item[1] == 0, -item[1], item[0]["created_at"], item[0]["id"]))[0][0] if available else None
        if not mb:
            raise MailboxError("NO_MAILBOX",f"题目 {challenge_key} 的实验邮箱额度已用尽或无可用邮箱（平台 {platform.name}）")
        sid = _rid("sub")
        frozen = _freeze(sid,package,content)
        conn.execute("INSERT INTO submissions(id,run_id,trial_id,mailbox_id,package_path,package_sha256,"
                     " status,operation_id,created_at,request_hash,stage,source_package_sha256,admission_json,prediction_md,"
                     " source_submission_id,variant_of,narrative_sha256,science_artifact_hashes_json,science_artifact_match)"
                     " VALUES(?,?,?,?,?,?,'unknown',?,?,?,'reserved',?,?,?,?,?,?,?,?)",
                     (sid,run_id,trial_id,mb["id"],frozen,digest,operation_id,db.utcnow(),fingerprint,
                      source_digest,json.dumps(check["admission"],ensure_ascii=False),prediction_md,
                      variant_context['source_submission_id'] if variant_context else None,
                      variant_context['source_submission_id'] if variant_context else None,
                      variant_context['narrative_sha256'] if variant_context else None,
                      json.dumps(science_hashes,sort_keys=True) if science_hashes is not None else None,
                      1 if science_hashes is not None else None))
        from . import local_scoring
        local_scoring.bind_submission_tx(conn, sid, content)
        db.append_event_tx(conn,run_id,"controller","submission.created",
                           {"submission_id":sid,"package_sha256":digest,
                            "source_package_sha256":source_digest,
                            "trace_diagnostics": {
                                "status": check["trace_diagnostics"]["status"],
                                "checklist_cap": check["trace_diagnostics"].get("advisory_cap"),
                                "advisories": check["trace_diagnostics"].get("advisories", [])[:8]},
                            "allow_proxy_evidence":allow_proxy_evidence,
                            "allow_indeterminate_admission":allow_indeterminate_admission,
                            "advisory_warnings": check.get('advisory_warnings', [])},trial_id=trial_id)
    return _perform_submission(sid,platform,challenge_id)


def submit_trace_variant(source_submission_id: str, operation_id: str,
                         prediction_md: str | None, *,
                         allow_proxy_evidence: bool = False,
                         allow_indeterminate_admission: bool = False,
                         projection_only: bool = False) -> dict[str, Any]:
    """Resubmit frozen science bytes with a new, reference-checked narrative."""
    import io

    if type(projection_only) is not bool:
        raise MailboxError('INVALID_ARGUMENT', 'projection_only 必须是显式布尔值')
    source = db.query_one("SELECT * FROM submissions WHERE id=?", (source_submission_id,))
    if not source or source['is_harvest'] or source['score_confidence'] != 'confirmed':
        raise MailboxError('INVALID_STATE', '轨迹变体来源必须是已确认评分的实验提交')
    run_id, trial_id = source['run_id'], source['trial_id']
    if not trial_id or not operation_id:
        raise MailboxError('INVALID_MESSAGE', '轨迹变体需要来源 Trial 与 operation_id')
    if projection_only:
        narrative_bytes, written_at, narrative_hash = None, None, None
    else:
        narrative_bytes, written_at = _narrative_for_trial(run_id, trial_id)
        if narrative_bytes is None or written_at is None:
            raise MailboxError('INVALID_TRACE_NARRATIVE', '来源 Trial 缺少 trace_narrative.jsonl')
        narrative_hash = hashlib.sha256(narrative_bytes).hexdigest()
    previous = db.query_one('SELECT * FROM submissions WHERE operation_id=?', (operation_id,))
    if previous:
        if (previous['variant_of'] != source_submission_id or
                previous['narrative_sha256'] != narrative_hash or
                (previous['prediction_md'] or None) != (prediction_md.strip() if prediction_md else None)):
            raise MailboxError('CONFLICT', '轨迹变体幂等键已用于不同来源、叙述或预测')
        return dict(previous) | {'deduplicated': True}
    frozen_path = (config.WORKSPACE_DIR / source['package_path']).resolve()
    if config.WORKSPACE_DIR.resolve() not in frozen_path.parents:
        raise MailboxError('INVALID_PACKAGE', '来源冻结包路径越界')
    frozen = frozen_path.read_bytes()
    if hashlib.sha256(frozen).hexdigest() != source['package_sha256']:
        raise MailboxError('INVALID_PACKAGE', '来源冻结包哈希不匹配')
    if frozen_path.suffix.lower() != '.zip':
        raise MailboxError('INVALID_PACKAGE', '只有已封存 ARM ZIP 可以生成轨迹变体')
    try:
        with zipfile.ZipFile(io.BytesIO(frozen)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError('duplicate ZIP member')
            files = {name: archive.read(name) for name in names}
        root = trace_selection.bundle_root(files)
        if root + package_seal.TRACE not in files:
            raise ValueError('source is not a sealed ARM bundle')
        frozen_rows = [json.loads(line) for line in files[root + package_seal.TRACE].splitlines()
                       if line.strip()]
        source_refs = [ref for row in frozen_rows if isinstance(row, dict)
                       for ref in ([row.get('cs_ref')] + (row.get('cs_refs') or []))
                       if isinstance(ref, str)]
        prefix = re.compile(rf'{re.escape(run_id)}#([1-9][0-9]*)\Z')
        cutoff = max((int(match.group(1)) for ref in source_refs
                      if (match := prefix.fullmatch(ref))), default=None)
        if cutoff is None:
            raise ValueError('source trace has no durable event reference')
        data_inputs = json.loads(files.pop(root + package_seal.DATA))
        files.pop(root + package_seal.TRACE)
        files.pop(root + 'traces/trace_narrative.jsonl', None)
        if projection_only:
            files = {name: raw for name, raw in files.items()
                     if not name.startswith((root + 'traces/', root + 'trace/'))
                     and name != root + 'trace.json'}
            manifest_name = root + 'arm_manifest.json'
            manifest = json.loads(files[manifest_name])
            manifest['trace'] = 'traces/trace.jsonl'
            files[manifest_name] = json.dumps(manifest, ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode()
            files[root + 'traces/trace.jsonl'] = b''
    except (KeyError, ValueError, TypeError, zipfile.BadZipFile) as exc:
        raise MailboxError('INVALID_PACKAGE', '来源冻结包不可用于轨迹变体') from exc
    base_buffer = io.BytesIO()
    with zipfile.ZipFile(base_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    base = base_buffer.getvalue()
    base_hash = hashlib.sha256(base).hexdigest()
    variant_dir = config.WORKSPACE_DIR / 'runs' / run_id / 'trials' / trial_id / 'trace_variants'
    variant_dir.mkdir(parents=True, exist_ok=True)
    variant_path = variant_dir / (base_hash + '.zip')
    if variant_path.exists():
        if variant_path.read_bytes() != base:
            raise MailboxError('CONFLICT', '同名变体基础包内容不一致')
    else:
        with variant_path.open('xb') as stream:
            stream.write(base)
    relative = variant_path.relative_to(config.WORKSPACE_DIR).as_posix()
    snapshot = (narrative_bytes, written_at, cutoff)
    expected = _science_artifact_hashes(frozen)
    check = preflight_submission(
        run_id, trial_id, relative,
        allow_proxy_evidence=allow_proxy_evidence,
        allow_indeterminate_admission=allow_indeterminate_admission,
        narrative_snapshot=snapshot, data_inputs_override=data_inputs)
    if _science_artifact_hashes(check['sealed_bytes']) != expected:
        raise MailboxError('SCIENCE_ARTIFACT_CHANGED',
                           '轨迹变体的非轨迹文件与来源冻结包不一致')
    if check['error_code']:
        raise MailboxError(check['error_code'], '轨迹变体未通过本地提交准入')
    result = submit_experiment(
        run_id, trial_id, relative, operation_id,
        allow_proxy_evidence=allow_proxy_evidence,
        allow_indeterminate_admission=allow_indeterminate_admission,
        prediction_md=prediction_md,
        variant_context={'source_submission_id': source_submission_id,
                         'narrative_sha256': narrative_hash,
                         'science_artifact_hashes': expected,
                         'data_inputs': data_inputs,
                         'narrative_snapshot': snapshot})
    db.append_event(run_id, 'controller', 'submission.trace_variant_created', {
        'submission_id': result['id'], 'source_submission_id': source_submission_id,
        'variant_of': source_submission_id, 'science_artifact_match': True,
        'science_artifact_hashes': expected}, trial_id=trial_id)
    return result


def submit_exact_replay(source_submission_id: str, operation_id: str,
                        prediction_md: str) -> dict[str, Any]:
    """Submit the frozen baseline bytes again to measure scorer noise."""
    source = db.query_one('SELECT * FROM submissions WHERE id=?', (source_submission_id,))
    if (not source or source['is_harvest'] or source['variant_of']
            or source['score_confidence'] != 'confirmed' or source['score_status'] != 'scored'):
        raise MailboxError('INVALID_STATE', '重复提交来源必须是已确认评分的普通实验基线')
    if not operation_id or not isinstance(prediction_md, str) or not prediction_md.strip() \
            or len(prediction_md) > 4000:
        raise MailboxError('INVALID_MESSAGE', '重复提交需要 operation_id 和非空有界预测')
    from .observation import strip_secrets
    prediction = strip_secrets(prediction_md)
    if not prediction.strip():
        raise MailboxError('INVALID_MESSAGE', '预测不能只包含密钥')
    run_id, trial_id = source['run_id'], source['trial_id']
    if not trial_id:
        raise MailboxError('INVALID_STATE', '重复提交来源缺少 Trial')
    frozen_path = (config.WORKSPACE_DIR / source['package_path']).resolve()
    if config.WORKSPACE_DIR.resolve() not in frozen_path.parents or not frozen_path.is_file():
        raise MailboxError('INVALID_PACKAGE', '来源冻结包不存在或路径越界')
    frozen = frozen_path.read_bytes()
    digest = hashlib.sha256(frozen).hexdigest()
    if digest != source['package_sha256']:
        raise MailboxError('INVALID_PACKAGE', '来源冻结包哈希不匹配')
    platform = _platform()
    challenge_id = _run_challenge_id(run_id)
    fingerprint = _request_hash({'replay_of':source_submission_id,'run_id':run_id,
                                 'package_sha256':digest,'prediction_md':prediction,
                                 'platform':platform.name,'challenge':challenge_id})
    with db.transaction() as conn:
        dup = _duplicate(conn, operation_id, fingerprint)
        if dup:
            return dup
        _check_budget(conn, run_id)
        challenge_key = _challenge_key(conn, run_id)
        limit = config.load_settings()['mailbox']['submission_limit']
        accounts = conn.execute("SELECT * FROM mailboxes WHERE role='experiment' AND status='active'"
                                " AND platform=? AND is_demo=? ORDER BY created_at,id",
                                (platform.name,int(platform.is_demo))).fetchall()
        available = [(mb, _used_for(conn, mb['id'], challenge_key)) for mb in accounts]
        available = [(mb, used) for mb, used in available if used < limit]
        mb = sorted(available, key=lambda item: (item[1] == 0, -item[1],
                                                 item[0]['created_at'], item[0]['id']))[0][0] if available else None
        if not mb:
            raise MailboxError('NO_MAILBOX', '本题实验邮箱额度已用尽或无可用邮箱')
        sid = _rid('sub')
        path = _freeze(sid, frozen_path, frozen)
        science_hashes = _science_artifact_hashes(frozen)
        conn.execute('INSERT INTO submissions(id,run_id,trial_id,mailbox_id,package_path,'
                     'package_sha256,status,operation_id,created_at,request_hash,stage,'
                     'source_package_sha256,admission_json,prediction_md,source_submission_id,'
                     'replay_of,science_artifact_hashes_json,science_artifact_match)'
                     " VALUES(?,?,?,?,?,?,'unknown',?,?,?,'reserved',?,?,?,?,?,?,1)",
                     (sid,run_id,trial_id,mb['id'],path,digest,operation_id,db.utcnow(),
                      fingerprint,digest,source['admission_json'],prediction,
                      source_submission_id,source_submission_id,
                      json.dumps(science_hashes,sort_keys=True)))
        from . import local_scoring
        local_scoring.bind_submission_tx(conn, sid, frozen)
        db.append_event_tx(conn,run_id,'controller','submission.replay_created',
                           {'submission_id':sid,'replay_of':source_submission_id,
                            'package_sha256':digest,'exact_bytes':True},trial_id=trial_id)
    return _perform_submission(sid,platform,challenge_id)


def poll_scores(run_id: str | None = None,
                challenge_id: str | None = None, *, manual: bool = False) -> dict[str, Any]:
    """经平台 API 拉回得分；拉不到保持 unknown，不编造。"""
    sql = ("SELECT s.*, m.email, m.secret_ref, m.platform,c.platform_snapshot_json FROM submissions s"
           " JOIN mailboxes m ON m.id=s.mailbox_id"
           " JOIN runs r ON r.id=s.run_id"
           " JOIN challenges c ON c.id=r.challenge_id"
           " WHERE s.status IN ('submitted','unknown')")
    params: list[Any] = []
    if run_id:
        sql += " AND s.run_id=?"
        params.append(run_id)
    if challenge_id:
        sql += " AND r.challenge_id=?"
        params.append(challenge_id)
    rows = db.query(sql, params)
    platform = _platform()
    updated, still_unknown, errors = 0, 0, 0
    polled = 0
    changed_runs = set()
    polling_settings = config.load_settings().get('polling') or {}
    confirmation_seconds = max(0, int(polling_settings.get('score_confirmation_seconds', 600)))
    confirmed_interval = max(1, int(polling_settings.get('confirmed_interval_seconds', 3600)))
    for r in rows:
        now = db.utcnow()
        when = _instant(now)
        deadline = _poll_deadline(r)
        if not manual and (r['polling_stopped_at'] or (deadline and when >= deadline)):
            if not r['polling_stopped_at']:
                with db.transaction() as conn:
                    conn.execute('UPDATE submissions SET polling_stopped_at=? WHERE id=?', (now,r['id']))
            continue
        if (not manual and r['score_confidence'] == 'confirmed'
                and r['score_last_polled_at'] and _instant(r['score_last_polled_at'])
                and (when - _instant(r['score_last_polled_at'])).total_seconds() < confirmed_interval):
            continue
        ref = r["platform_ref"]
        if not ref:
            still_unknown += 1  # 无平台回执引用：没有可查的对象，保持 unknown
            continue
        polled += 1
        attempt = None
        try:
            row_platform = platform if r["platform"] == platform.name else get_platform(r["platform"])
            secret = config.resolve_secret(r["secret_ref"] or "")
            attempt_query = getattr(row_platform, "fetch_attempt", None)
            if callable(attempt_query):
                try:
                    observed = attempt_query(r["email"], secret, ref)
                    observed = public_feedback(observed, secret, *config.sensitive_values())
                    if isinstance(observed, dict):
                        attempt = {key: observed[key] for key in
                                   ("scorecard", "scoringState", "bundleStatus", "updatedAt")
                                   if key in observed}
                        with db.transaction() as conn:
                            if _record_feedback(conn, r, "attempt", attempt):
                                changed_runs.add(r["run_id"])
                except Exception as exc:
                    errors += 1
                    with db.transaction() as conn:
                        if _record_feedback(conn, r, "attempt_query_error", {
                                "error_type": type(exc).__name__, "outcome": "unknown"}):
                            changed_runs.add(r["run_id"])
            detail_query = getattr(row_platform, "fetch_score_details", None)
            details = None
            if callable(detail_query):
                details = detail_query(r["email"], secret, ref)
                details = public_feedback(details, secret, *config.sensitive_values())
                score = final_score(details)
            else:
                score = row_platform.fetch_score(r["email"], secret, ref)
        except Exception as exc:
            errors += 1
            with db.transaction() as conn:
                conn.execute('UPDATE submissions SET score_last_polled_at=? WHERE id=?', (now,r['id']))
                if _record_feedback(conn, r, "score_query_error", {
                        "error_type": type(exc).__name__, "outcome": "unknown"}):
                    changed_runs.add(r["run_id"])
            continue
        if isinstance(details, dict):
            with db.transaction() as conn:
                if _record_feedback(conn, r, "score", details):
                    changed_runs.add(r["run_id"])
        if score is None:
            still_unknown += 1
            db.execute('UPDATE submissions SET score_last_polled_at=? WHERE id=?', (now,r['id']))
            continue
        if not math.isfinite(score):
            still_unknown += 1
            continue
        anomaly = _score_anomaly(details)
        harbor, trace = _score_components(attempt, details)
        consistent = _scorecard_consistency(attempt, score, details)
        with db.transaction() as conn:
            current = conn.execute("SELECT * FROM submissions WHERE id=?",(r["id"],)).fetchone()
            # Compare-and-swap: a response requested before another update cannot overwrite it.
            if (current['score_status'],current['score'],current['score_confidence'],
                    current['score_last_polled_at']) != (r['score_status'],r['score'],
                    r['score_confidence'],r['score_last_polled_at']):
                continue
            prior_scored = current['score_status'] == 'scored'
            changed_score = not prior_scored or current['score'] != score
            correction = prior_scored and current['score'] != score
            first_seen = now if changed_score or not current['score_first_seen_at'] else current['score_first_seen_at']
            last_changed = now if changed_score else current['score_last_changed_at']
            observed_twice = (not changed_score and current['score_last_polled_at'] is not None
                and _instant(first_seen) and (when - _instant(first_seen)).total_seconds() >= confirmation_seconds)
            confidence = ('confirmed' if not anomaly and observed_twice
                          else 'provisional')
            if current['score_confidence'] == 'confirmed' and not changed_score and not anomaly:
                confidence = 'confirmed'
            meaningful = (changed_score or confidence != current['score_confidence']
                or anomaly != current['score_anomaly'] or consistent != current['scorecard_consistent']
                or harbor != current['harbor_score'] or trace != current['trace_score'])
            conn.execute("UPDATE submissions SET score=?,score_status='scored',status='submitted',"
                         " scored_at=COALESCE(scored_at,?),stage='scored',score_confidence=?,"
                         " score_first_seen_at=?,score_last_changed_at=?,score_anomaly=?,"
                         " scorecard_consistent=?,harbor_score=?,trace_score=?,"
                         " score_last_polled_at=? WHERE id=?",
                         (score,now,confidence,first_seen,last_changed,anomaly,consistent,
                          harbor,trace,now,r['id']))
            if current['prediction_verdict'] and (changed_score or confidence!='confirmed'):
                conn.execute("UPDATE submissions SET prediction_verdict=NULL,prediction_note_md=NULL"
                             " WHERE id=?",(r['id'],))
                db.append_event_tx(conn,r['run_id'],'controller','prediction.verdict_invalidated',
                                   {'submission_id':r['id'],'reason':'评分变化或不再确认'},
                                   trial_id=r['trial_id'])
            if current['score_confidence'] == 'confirmed' and confidence != 'confirmed':
                experience_context.retract_result_tx(conn, r, 'post_confirmation_revision' if correction else 'score_anomaly')
            if meaningful:
                reason = ('post_confirmation_revision' if correction and current['score_confidence'] == 'confirmed'
                          else 'score_revision' if correction else 'score_confirmation'
                          if confidence == 'confirmed' else 'score_observed')
                event = db.append_event_tx(conn,r['run_id'],'controller',
                    'submission.score_corrected' if correction else 'submission.scored',{
                        'submission_id':r['id'],'trial_id':r['trial_id'],
                        'package_sha256':r['package_sha256'],'score':score,
                        'previous_score':current['score'] if correction else None,
                        'score_status':'scored','score_confidence':confidence,
                        'score_anomaly':anomaly,'scorecard_consistent':consistent,
                        'harbor_score':harbor,'trace_score':trace,
                        'reason':reason,'is_final':True,'platform_ref':r['platform_ref'],
                        'platform_feedback':details},trial_id=r['trial_id'])
                if confidence == 'confirmed' and current['score_confidence'] != 'confirmed' and not anomaly:
                    experience_context.link_result_tx(conn,r,score,event['seq'])
            from . import local_scoring
            local_scoring.calibrate_tx(conn, r['id'])
        if meaningful:
            updated += 1
            changed_runs.add(r['run_id'])
    return {"polled":polled,"updated":updated,"still_unknown":still_unknown,
            "errors":errors,"changed_run_ids":sorted(changed_runs)}


# ---------- 评分轮询任务（按题目管理，可中断/启用） ----------

# 每题最后一次轮询的内存记录；重启丢失可接受。
POLL_STATE: dict[str, dict[str, Any]] = {}


def _disabled_challenges() -> set[str]:
    settings = config.load_settings()
    return set((settings.get("polling") or {}).get("disabled_challenges") or [])


def pollable_challenges(disabled: set[str] | None = None) -> list[dict[str, Any]]:
    """有待评分提交的题目清单（后台轮询选题），跳过用户中断的题目。"""
    skip = _disabled_challenges() if disabled is None else set(disabled)
    rows = db.query(
        "SELECT DISTINCT r.challenge_id AS challenge_id FROM submissions s"
        " JOIN runs r ON r.id=s.run_id"
        " WHERE s.status IN ('submitted','unknown') AND s.polling_stopped_at IS NULL")
    return [{"challenge_id": r["challenge_id"]} for r in rows
            if r["challenge_id"] not in skip]


def _poll_challenge(challenge_id: str, *, manual: bool = False) -> dict[str, Any]:
    result = poll_scores(challenge_id=challenge_id, manual=manual)
    POLL_STATE[challenge_id] = {"last_poll_at": db.utcnow(),
                                "last_result": result}
    return result


def poll_pending_by_challenge() -> dict[str, Any]:
    """后台轮询入口：按题目分组逐题轮询，跳过 disabled_challenges。"""
    results = {}
    for ch in pollable_challenges():
        results[ch["challenge_id"]] = _poll_challenge(ch["challenge_id"])
    return {"challenges": results,"changed_run_ids":sorted({rid for r in results.values() for rid in r.get("changed_run_ids",[])})}


def _task_row(row: sqlite3.Row, disabled: set[str]) -> dict[str, Any]:
    state = POLL_STATE.get(row["challenge_id"], {})
    return {"challenge_id": row["challenge_id"], "title": row["title"],
            "pending": row["pending"],
            "enabled": row["challenge_id"] not in disabled,
            "last_poll_at": state.get("last_poll_at"),
            "last_result": state.get("last_result")}


def polling_tasks() -> dict[str, Any]:
    """所有有过提交的题目的轮询任务视图（pending 为待评分数）。"""
    disabled = _disabled_challenges()
    rows = db.query(
        "SELECT r.challenge_id AS challenge_id, c.title AS title,"
        " SUM(CASE WHEN s.status='submitted'"
        "     AND (s.score_status IN ('unknown','pending') OR s.score_confidence='provisional')"
        "     AND s.polling_stopped_at IS NULL THEN 1 ELSE 0 END)"
        " AS pending"
        " FROM submissions s JOIN runs r ON r.id=s.run_id"
        " JOIN challenges c ON c.id=r.challenge_id"
        " GROUP BY r.challenge_id ORDER BY c.title")
    return {"tasks": [_task_row(r, disabled) for r in rows]}


@config.serialized_mutation
def set_polling_enabled(challenge_id: str, enabled: bool) -> dict[str, Any]:
    """中断/启用某题的自动评分轮询（写 settings.polling.disabled_challenges）。"""
    ch = db.query_one("SELECT id, title FROM challenges WHERE id=?",
                      (challenge_id,))
    if not ch:
        raise MailboxError("NOT_FOUND", f"题目不存在: {challenge_id}")
    settings = config.load_settings()
    polling = settings.setdefault("polling", {})
    disabled = [c for c in (polling.get("disabled_challenges") or [])
                if c != challenge_id]
    if not enabled:
        disabled.append(challenge_id)
    polling["disabled_challenges"] = disabled
    settings["revision"] = settings.get("revision", 0) + 1
    config.save_settings(settings)
    for task in polling_tasks()["tasks"]:
        if task["challenge_id"] == challenge_id:
            return task
    # 题目无提交记录时不出现在任务清单，合成一个空任务返回
    return {"challenge_id": challenge_id, "title": ch["title"], "pending": 0,
            "enabled": enabled, "last_poll_at": None, "last_result": None}


def poll_scores_now(challenge_id: str) -> dict[str, Any]:
    """手动触发单题轮询，不受 enabled 限制。"""
    if not db.query_one("SELECT id FROM challenges WHERE id=?",
                        (challenge_id,)):
        raise MailboxError("NOT_FOUND", f"题目不存在: {challenge_id}")
    return _poll_challenge(challenge_id, manual=True)


# ---------- 收割 ----------

def harvest_candidates(challenge_id: str) -> dict[str, Any]:
    """实验邮箱已提交且已有官方得分的包，按得分降序。"""
    rows = db.query(
        "SELECT s.*, m.email AS mailbox_email FROM submissions s"
        " JOIN mailboxes m ON m.id=s.mailbox_id"
        " JOIN runs r ON r.id=s.run_id"
        " WHERE r.challenge_id=? AND s.is_harvest=0"
        " AND s.status='submitted' AND s.score_status='scored'"
        " ORDER BY s.score DESC,s.created_at ASC,s.id", (challenge_id,))
    items = _submission_items(rows)
    highest = items[0]['score'] if items else None
    for item in items:
        feedback = item.get('platform_feedback') or {}
        attempt = feedback.get('attempt', {}).get('response')
        detail = feedback.get('score', {}).get('response')
        harbor, trace = _score_components(attempt, detail)
        item['harbor_score'] = harbor if harbor is not None else item.get('harbor_score')
        item['trace_score'] = trace if trace is not None else item.get('trace_score')
        item['displayScore'] = item['score']
        item['is_highest'] = item['score'] == highest
        item['warnings'] = _harvest_warnings(item, highest)
    return {"items": items}


def _harvest_warnings(candidate, highest) -> list[str]:
    warnings = []
    if candidate['score'] != highest:
        warnings.append('不是当前最高分')
    if candidate['score_confidence'] != 'confirmed':
        warnings.append('分数仍为暂定，尚未确认')
    if candidate['score_anomaly']:
        warnings.append('评分异常：' + candidate['score_anomaly'])
    if candidate['scorecard_consistent'] == 0:
        warnings.append('展示分与评分分项不一致')
    return warnings


def harvest_submit(submission_id: str, operation_id: str,
                   confirm: bool, acknowledge_warnings: bool = False) -> dict[str, Any]:
    """收割任意已出分的实验包；警示必须经显式知悉。"""
    if type(confirm) is not bool or type(acknowledge_warnings) is not bool:
        raise MailboxError('INVALID_MESSAGE', '确认标志必须是显式布尔值')
    if confirm is not True:
        raise MailboxError("NEEDS_CONFIRM", "收割提交需要用户手动确认")
    if not operation_id:
        raise MailboxError("INVALID_MESSAGE", "缺少 operation_id（幂等键）")
    fingerprint = _request_hash({"harvest_source": submission_id})
    with db.transaction() as conn:
        dup = _duplicate(conn, operation_id, fingerprint)
        if dup: return dup
    src = db.query_one(
        "SELECT s.*, m.role AS mailbox_role, m.email AS src_email"
        " FROM submissions s JOIN mailboxes m ON m.id=s.mailbox_id"
        " WHERE s.id=?", (submission_id,))
    if not src:
        raise MailboxError("NOT_FOUND", f"来源提交不存在: {submission_id}")
    if src["mailbox_role"] != "experiment" or src["is_harvest"]:
        raise MailboxError("INVALID_STATE", "收割来源必须是实验邮箱的提交")
    if src["status"] != "submitted" or src["score_status"] != "scored":
        raise MailboxError(
            "INVALID_STATE",
            f"来源提交无已知官方得分（status={src['status']},"
            f" score_status={src['score_status']}）；不能收割未知分的包")
    best = db.query_one(
        "SELECT MAX(s.score) AS score FROM submissions s JOIN runs r ON r.id=s.run_id"
        " WHERE r.challenge_id=(SELECT challenge_id FROM runs WHERE id=?)"
        " AND s.is_harvest=0 AND s.status='submitted'"
        " AND s.score_status='scored'",
        (src["run_id"],))
    warnings = _harvest_warnings(src, best['score'] if best else None)
    if warnings and not acknowledge_warnings:
        raise MailboxError('NEEDS_CONFIRM', '请知悉全部收割警示后再提交', warnings=warnings)
    harvest = db.query_one(
        "SELECT * FROM mailboxes WHERE role='harvest' AND status='active'")
    if not harvest:
        raise MailboxError("NO_MAILBOX", "未配置收割邮箱")

    package = (config.WORKSPACE_DIR.resolve() / src["package_path"]).resolve()
    if not package.exists():
        raise MailboxError("NOT_FOUND",
                           f"提交包文件已不存在: {src['package_path']}")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    if digest != src["package_sha256"]:
        raise MailboxError("CONFLICT",
                           "提交包内容已变化（哈希不匹配）；拒绝收割，"
                           "请重新经实验邮箱验证")

    platform = _platform()
    challenge_id = _run_challenge_id(src["run_id"])
    with db.transaction() as conn:
        dup = _duplicate(conn,operation_id,fingerprint)
        if dup: return dup
        current_src = conn.execute('SELECT * FROM submissions WHERE id=?',(submission_id,)).fetchone()
        if (not current_src or current_src['status'] != 'submitted'
                or current_src['score_status'] != 'scored'):
            raise MailboxError('INVALID_STATE', '来源提交的已出分状态已变化')
        best = conn.execute(
            "SELECT MAX(s.score) AS score FROM submissions s JOIN runs r ON r.id=s.run_id"
            " WHERE r.challenge_id=(SELECT challenge_id FROM runs WHERE id=?)"
            " AND s.is_harvest=0 AND s.status='submitted' AND s.score_status='scored'",
            (src['run_id'],)).fetchone()
        warnings = _harvest_warnings(current_src, best['score'] if best else None)
        if warnings and not acknowledge_warnings:
            raise MailboxError('NEEDS_CONFIRM', '请知悉全部收割警示后再提交', warnings=warnings)
        harvest = conn.execute("SELECT * FROM mailboxes WHERE id=? AND status='active'"
                               " AND platform=? AND is_demo=?",
                               (harvest["id"],platform.name,int(platform.is_demo))).fetchone()
        if not harvest:
            raise MailboxError("NO_MAILBOX", "收割邮箱已停用或平台不匹配")
        challenge_key = _challenge_key(conn, src["run_id"])
        if _used_for(conn, harvest["id"], challenge_key) >= config.load_settings()["mailbox"]["submission_limit"]:
            raise MailboxError("NO_MAILBOX", f"题目 {challenge_key} 的收割邮箱额度已用尽")
        content = package.read_bytes()
        if hashlib.sha256(content).hexdigest() != src["package_sha256"]:
            raise MailboxError("CONFLICT", "来源包哈希不匹配")
        sid = _rid("sub")
        frozen = _freeze(sid,package,content)
        conn.execute("INSERT INTO submissions(id,run_id,trial_id,mailbox_id,package_path,package_sha256,"
                     " status,is_harvest,source_submission_id,operation_id,created_at,request_hash,stage,prediction_md)"
                     " VALUES(?,?,?,?,?,?,'unknown',1,?,?,?,?,'reserved',?)",
                     (sid,src["run_id"],src["trial_id"],harvest["id"],frozen,src["package_sha256"],
                      submission_id,operation_id,db.utcnow(),fingerprint,src['prediction_md']))
        db.append_event_tx(conn,src['run_id'],'controller','submission.harvest_reserved',{
            'submission_id':sid,'source_submission_id':submission_id,
            'warnings':warnings,'acknowledge_warnings':acknowledge_warnings},
            trial_id=src['trial_id'])
    return _perform_submission(sid,platform,challenge_id)
