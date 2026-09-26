"""邮箱管理双轨服务：实验邮箱与收割邮箱均按题目预留额度。

事实纪律：分数不知道就是 NULL/unknown；外部调用（适配器）绝不在事务内；
operation_id 幂等去重；额度只从未释放的 submissions 预留计算。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
import zipfile
from pathlib import Path
from typing import Any

from . import arm_admission, config, db, experience_context, package_seal, trace_selection
from .mailbox_platform import (MailboxPlatform, PlatformError, final_score,
                               get_platform, public_feedback)


class MailboxError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


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
        from datetime import datetime, timezone
        deadline = datetime.fromisoformat(run["started_at"].replace("Z","+00:00")).timestamp() + auth["max_run_minutes"]*60
        if datetime.now(timezone.utc).timestamp() >= deadline:
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


def _protocol_snapshot() -> dict[str, Any] | None:
    path = Path(__file__).resolve().parents[2] / "contracts" / "arm_protocol.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _data_inputs(run_id: str, trial_id: str | None) -> dict[str, Any]:
    run = db.query_one("SELECT c.resources_json FROM runs r JOIN challenges c"
                       " ON c.id=r.challenge_id WHERE r.id=?", (run_id,))
    try:
        resources = json.loads(run["resources_json"] or "[]") if run else []
    except ValueError:
        resources = []
    requires_data = any(isinstance(r, dict) and r.get("role") == "task-public-data"
                        for r in resources)
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


def preflight_submission(run_id: str, trial_id: str | None,
                         package_path: str | None, *, allow_proxy_evidence: bool = False,
                         allow_indeterminate_admission: bool = False) -> dict[str, Any]:
    if type(allow_proxy_evidence) is not bool or type(allow_indeterminate_admission) is not bool:
        raise MailboxError("INVALID_ARGUMENT", "提交准入覆盖标志必须是显式布尔值")
    package = _resolve_package(run_id, trial_id, package_path)
    source = package.read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    data = _data_inputs(run_id, trial_id)
    is_bundle = package.suffix.lower() == ".zip"
    sealed, steps = source, []
    report = {"verdict": "not_applicable", "signals": {}}
    if is_bundle:
        last = db.query_one("SELECT MAX(seq) AS n FROM events WHERE run_id=?", (run_id,))
        try:
            sealed, steps = package_seal.seal(source, run_id, trial_id, last["n"] or 0, data)
        except (KeyError, ValueError, TypeError, sqlite3.Error, OSError, zipfile.BadZipFile) as exc:
            with db.transaction() as conn:
                db.append_event_tx(conn, run_id, "controller", "submission.preflight_failed",
                    {"code": "INVALID_PACKAGE", "reason": str(exc)[:200],
                     "source_package_sha256": source_hash}, trial_id=trial_id)
            raise MailboxError("INVALID_PACKAGE", f"ARM 包无法封存：{type(exc).__name__}") from exc
        report = arm_admission.check(sealed, _protocol_snapshot())
    code = None
    if report["verdict"] == "blocked":
        code = "TRACE_ADMISSION_BLOCKED"
    elif report["verdict"] == "indeterminate" and not allow_indeterminate_admission:
        code = "TRACE_ADMISSION_INDETERMINATE"
    elif data["evidence_class"] == "proxy" and not allow_proxy_evidence:
        code = "PROXY_EVIDENCE"
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
            code = exc.code
        except (KeyError, ValueError, zipfile.BadZipFile):
            code = "INVALID_PACKAGE"
    return {"source_package_sha256": source_hash,
            "sealed_package_sha256": hashlib.sha256(sealed).hexdigest(),
            "sealed_bytes": sealed, "admission": report, "projected_steps": steps,
            "data_inputs": data, "allow_proxy_evidence": allow_proxy_evidence,
            "allow_indeterminate_admission": allow_indeterminate_admission,
            "error_code": code}


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
        safe = public_feedback(response, *config.load_secrets().values())
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
                      allow_indeterminate_admission: bool = False) -> dict[str, Any]:
    if not operation_id:
        raise MailboxError("INVALID_MESSAGE", "缺少 operation_id（幂等键）")
    package = _resolve_package(run_id, trial_id, package_path)
    source_content = package.read_bytes()
    source_digest = hashlib.sha256(source_content).hexdigest()
    platform = _platform()
    challenge_id = _run_challenge_id(run_id)
    fingerprint = _request_hash({"run_id":run_id,"trial_id":trial_id,
        "package_path":str(package),"hash":source_digest,"platform":platform.name,
        "challenge":challenge_id,"allow_proxy_evidence":allow_proxy_evidence,
        "allow_indeterminate_admission":allow_indeterminate_admission})
    with db.transaction() as conn:
        dup = _duplicate(conn, operation_id, fingerprint)
        if dup: return dup
    check = preflight_submission(run_id, trial_id, package_path,
        allow_proxy_evidence=allow_proxy_evidence,
        allow_indeterminate_admission=allow_indeterminate_admission)
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
                     " status,operation_id,created_at,request_hash,stage,source_package_sha256,admission_json)"
                     " VALUES(?,?,?,?,?,?,'unknown',?,?,?,'reserved',?,?)",
                     (sid,run_id,trial_id,mb["id"],frozen,digest,operation_id,db.utcnow(),fingerprint,
                      source_digest,json.dumps(check["admission"],ensure_ascii=False)))
        db.append_event_tx(conn,run_id,"controller","submission.created",
                           {"submission_id":sid,"package_sha256":digest,
                            "source_package_sha256":source_digest,
                            "allow_proxy_evidence":allow_proxy_evidence,
                            "allow_indeterminate_admission":allow_indeterminate_admission},trial_id=trial_id)
    return _perform_submission(sid,platform,challenge_id)


def poll_scores(run_id: str | None = None,
                challenge_id: str | None = None) -> dict[str, Any]:
    """经平台 API 拉回得分；拉不到保持 unknown，不编造。"""
    sql = ("SELECT s.*, m.email, m.secret_ref, m.platform FROM submissions s"
           " JOIN mailboxes m ON m.id=s.mailbox_id"
           " JOIN runs r ON r.id=s.run_id"
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
    changed_runs = set()
    for r in rows:
        ref = r["platform_ref"]
        if not ref:
            still_unknown += 1  # 无平台回执引用：没有可查的对象，保持 unknown
            continue
        try:
            row_platform = platform if r["platform"] == platform.name else get_platform(r["platform"])
            secret = config.resolve_secret(r["secret_ref"] or "")
            detail_query = getattr(row_platform, "fetch_score_details", None)
            details = None
            if callable(detail_query):
                details = detail_query(r["email"], secret, ref)
                details = public_feedback(details, secret, *config.load_secrets().values())
                score = final_score(details)
            else:
                score = row_platform.fetch_score(r["email"], secret, ref)
        except Exception as exc:
            errors += 1
            with db.transaction() as conn:
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
            continue
        import math
        if not math.isfinite(score):
            still_unknown += 1
            continue
        with db.transaction() as conn:
            current = conn.execute("SELECT * FROM submissions WHERE id=?",(r["id"],)).fetchone()
            # Compare-and-swap: a response requested before another update cannot overwrite it.
            if (current["score_status"],current["score"],current["scored_at"]) != (r["score_status"],r["score"],r["scored_at"]):
                continue
            if current["score_status"] == "scored" and current["score"] == score:
                continue
            correction = current["score_status"] == "scored"
            conn.execute("UPDATE submissions SET score=?,score_status='scored',status='submitted',"
                         " scored_at=?,stage='scored' WHERE id=?",(score,db.utcnow(),r["id"]))
            event = db.append_event_tx(conn,r["run_id"],"controller",
                "submission.score_corrected" if correction else "submission.scored",{
                    "submission_id":r["id"],"trial_id":r["trial_id"],
                    "package_sha256":r["package_sha256"],"score":score,
                    "previous_score":current["score"] if correction else None,
                    "score_status":"scored","is_final":True,
                    "finality_basis":"platform.fetch_score requires scoringState.scoreIsFinal",
                    "platform_ref":r["platform_ref"],
                    "platform_feedback":details},trial_id=r["trial_id"])
            experience_context.link_result_tx(conn,r,score,event["seq"])
        updated += 1
        changed_runs.add(r["run_id"])
    return {"polled":len(rows),"updated":updated,"still_unknown":still_unknown,
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
        " WHERE s.status IN ('submitted','unknown')")
    return [{"challenge_id": r["challenge_id"]} for r in rows
            if r["challenge_id"] not in skip]


def _poll_challenge(challenge_id: str) -> dict[str, Any]:
    result = poll_scores(challenge_id=challenge_id)
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
        "     AND s.score_status IN ('unknown','pending') THEN 1 ELSE 0 END)"
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
    return _poll_challenge(challenge_id)


# ---------- 收割 ----------

def harvest_candidates(challenge_id: str) -> dict[str, Any]:
    """实验邮箱已提交且已有官方得分的包，按得分降序。"""
    rows = db.query(
        "SELECT s.*, m.email AS mailbox_email FROM submissions s"
        " JOIN mailboxes m ON m.id=s.mailbox_id"
        " JOIN runs r ON r.id=s.run_id"
        " WHERE r.challenge_id=? AND s.is_harvest=0"
        " AND s.status='submitted' AND s.score_status='scored'"
        " ORDER BY s.score DESC", (challenge_id,))
    return {"items": [dict(r) for r in rows]}


def harvest_submit(submission_id: str, operation_id: str,
                   confirm: bool) -> dict[str, Any]:
    """收割提交：只对实验邮箱已提交且得分最高的现成包，必须用户手动确认。"""
    if not confirm:
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
        "SELECT s.id, s.score FROM submissions s JOIN mailboxes m"
        " ON m.id=s.mailbox_id JOIN runs r ON r.id=s.run_id"
        " WHERE r.challenge_id=(SELECT challenge_id FROM runs WHERE id=?)"
        " AND s.is_harvest=0 AND s.status='submitted'"
        " AND s.score_status='scored' ORDER BY s.score DESC LIMIT 1",
        (src["run_id"],))
    if not best or best["id"] != submission_id:
        raise MailboxError(
            "INVALID_STATE",
            f"该提交不是最高分（当前最高 {best['score'] if best else '无'}）；"
            "收割邮箱只提交得分最高的现成包")
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
                     " status,is_harvest,source_submission_id,operation_id,created_at,request_hash,stage)"
                     " VALUES(?,?,?,?,?,?,'unknown',1,?,?,?,?,'reserved')",
                     (sid,src["run_id"],src["trial_id"],harvest["id"],frozen,src["package_sha256"],
                      submission_id,operation_id,db.utcnow(),fingerprint))
    return _perform_submission(sid,platform,challenge_id)
