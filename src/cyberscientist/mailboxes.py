"""邮箱管理双轨服务：实验邮箱（提交主体，限量）+ 收割邮箱（唯一，手动确认）。

事实纪律：分数不知道就是 NULL/unknown；外部调用（适配器）绝不在事务内；
operation_id 幂等去重；收割提交只接受「实验邮箱已提交且得分最高」的现成包。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from . import config, db
from .mailbox_platform import MailboxPlatform, PlatformError, get_platform


class MailboxError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _rid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _platform() -> MailboxPlatform:
    return get_platform(config.load_settings()["mailbox"]["platform"])


def _store_secret(secret_id: str, value: str) -> str:
    secrets = config.load_secrets()
    secrets[secret_id] = value
    config.save_secrets(secrets)
    return f"local:{secret_id}"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d.pop("secret_ref", None)  # 凭据引用不出服务层
    d["secret_configured"] = bool(row["secret_ref"]) and \
        config.secret_configured(row["secret_ref"])
    return d


# ---------- 查询 ----------

def list_mailboxes() -> dict[str, Any]:
    rows = db.query("SELECT * FROM mailboxes ORDER BY role, created_at")
    return {"items": [_row(r) for r in rows],
            "platform": config.load_settings()["mailbox"]["platform"],
            "platform_is_demo": _platform().is_demo}


def list_submissions(run_id: str) -> dict[str, Any]:
    rows = db.query(
        "SELECT s.*, m.email AS mailbox_email, m.role AS mailbox_role"
        " FROM submissions s JOIN mailboxes m ON m.id=s.mailbox_id"
        " WHERE s.run_id=? ORDER BY s.created_at", (run_id,))
    return {"items": [dict(r) for r in rows]}


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
    return {"items": [dict(r) for r in rows]}


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
    try:
        accounts = [platform.register_account() for _ in range(count)]
    except PlatformError as exc:
        raise MailboxError("MISSING_CREDENTIAL", str(exc)) from exc
    limit = config.load_settings()["mailbox"]["submission_limit"]
    items = []
    with db.transaction() as conn:
        for acc in accounts:
            mid = _rid("mbox")
            secret_ref = _store_secret(f"mailbox_{mid}", acc["password"])
            conn.execute(
                "INSERT INTO mailboxes(id, role, email, platform, secret_ref,"
                " status, submission_limit, is_demo, created_at)"
                " VALUES(?,?,?,?,?,'active',?,?,?)",
                (mid, "experiment", acc["email"], platform.name, secret_ref,
                 limit, int(platform.is_demo), db.utcnow()))
            items.append(mid)
    rows = db.query(
        f"SELECT * FROM mailboxes WHERE id IN ({','.join('?' * len(items))})",
        items)
    return {"items": [_row(r) for r in rows], "is_demo": platform.is_demo}


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
        candidates += [tdir / "result_package.json", tdir / "submission.csv"]
    for p in candidates:
        if p.exists() and p.is_file() and root in p.parents:
            return p
    raise MailboxError(
        "NOT_FOUND",
        "未找到提交包：需要 Trial 目录下的 result_package.json /"
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


def _check_budget(run_id: str) -> None:
    """授权上限的第一个真实消费点：max_submissions=0 即未授权提交。"""
    run = db.query_one("SELECT authorization_id FROM runs WHERE id=?",
                       (run_id,))
    if not run:
        raise MailboxError("NOT_FOUND", f"Run 不存在: {run_id}")
    auth = db.query_one("SELECT max_submissions FROM authorizations"
                        " WHERE id=?", (run["authorization_id"],)) \
        if run["authorization_id"] else None
    limit = auth["max_submissions"] if auth else 0
    used = db.query_one(
        "SELECT COUNT(*) AS n FROM submissions WHERE run_id=?"
        " AND is_harvest=0 AND status='submitted'", (run_id,))["n"]
    if used >= limit:
        raise MailboxError(
            "NEEDS_AUTHORIZATION",
            f"提交授权已用尽（{used}/{limit}）；请在产品上追加单轮授权")


def submit_experiment(run_id: str, trial_id: str | None,
                      package_path: str | None,
                      operation_id: str) -> dict[str, Any]:
    """实验邮箱提交：配额原子预占 → 适配器调用（事务外）→ 结果落库。"""
    if not operation_id:
        raise MailboxError("INVALID_MESSAGE", "缺少 operation_id（幂等键）")
    dup = db.query_one("SELECT * FROM submissions WHERE operation_id=?",
                       (operation_id,))
    if dup:
        return dict(dup) | {"deduplicated": True}
    _check_budget(run_id)
    package = _resolve_package(run_id, trial_id, package_path)
    challenge_id = _run_challenge_id(run_id)  # 配额预占前解析，失败不占额度
    digest = hashlib.sha256(package.read_bytes()).hexdigest()

    # 事务 1：原子选一个有余量的实验邮箱并预占配额
    # 只选与当前平台一致的邮箱（真实平台提交不能落到 demo 合成账号）
    platform = _platform()
    with db.transaction() as conn:
        mb = conn.execute(
            "SELECT * FROM mailboxes WHERE role='experiment'"
            " AND status='active' AND submissions_used < submission_limit"
            " AND platform=? AND is_demo=?"
            " ORDER BY submissions_used, created_at LIMIT 1",
            (platform.name, int(platform.is_demo))).fetchone()
        if not mb:
            raise MailboxError(
                "NO_MAILBOX",
                f"无可用实验邮箱（平台 {platform.name} 下全部用尽或未注册）；"
                "请先注册实验邮箱")
        conn.execute(
            "UPDATE mailboxes SET submissions_used=submissions_used+1,"
            " status=CASE WHEN submissions_used+1>=submission_limit"
            " THEN 'exhausted' ELSE status END WHERE id=?", (mb["id"],))
        sid = _rid("sub")
        conn.execute(
            "INSERT INTO submissions(id, run_id, trial_id, mailbox_id,"
            " package_path, package_sha256, status, operation_id, created_at)"
            " VALUES(?,?,?,?,?,?,'unknown',?,?)",
            (sid, run_id, trial_id, mb["id"],
             str(package.relative_to(
                 config.WORKSPACE_DIR.resolve()).as_posix()),
             digest, operation_id, db.utcnow()))
        db.append_event_tx(conn, run_id, "controller", "submission.created", {
            "submission_id": sid, "mailbox": mb["email"],
            "package_sha256": digest}, trial_id=trial_id)

    # 适配器调用在事务外
    secret = config.resolve_secret(
        db.query_one("SELECT secret_ref FROM mailboxes WHERE id=?",
                     (mb["id"],))["secret_ref"] or "")
    try:
        receipt = platform.submit_package(
            mb["email"], secret, str(package), challenge_id=challenge_id)
        ok, error = bool(receipt.get("accepted")), None
        platform_ref = str(receipt.get("receipt") or "") or None
    except PlatformError as exc:
        ok, error, platform_ref = False, str(exc), None
    except Exception as exc:  # 兜底：补偿事务必须执行以释放配额
        ok, error, platform_ref = False, \
            f"平台调用未预期失败: {type(exc).__name__}: {exc}", None

    # 事务 2：结果落库；失败则释放邮箱配额
    with db.transaction() as conn:
        conn.execute(
            "UPDATE submissions SET status=?, score_status=?, error=?,"
            " platform_ref=?, submitted_at=? WHERE id=?",
            ("submitted" if ok else "failed",
             "pending" if ok else "unknown", error, platform_ref,
             db.utcnow() if ok else None, sid))
        if not ok:
            conn.execute(
                "UPDATE mailboxes SET submissions_used=submissions_used-1,"
                " status='active' WHERE id=?", (mb["id"],))
        db.append_event_tx(
            conn, run_id, "controller",
            "submission.submitted" if ok else "submission.failed",
            {"submission_id": sid, "mailbox": mb["email"],
             "error": error, "is_demo": platform.is_demo},
            trial_id=trial_id)
    return dict(db.query_one("SELECT * FROM submissions WHERE id=?",
                             (sid,))) | {"deduplicated": False}


def poll_scores(run_id: str | None = None,
                challenge_id: str | None = None) -> dict[str, Any]:
    """经平台 API 拉回得分；拉不到保持 unknown，不编造。"""
    sql = ("SELECT s.*, m.email, m.secret_ref FROM submissions s"
           " JOIN mailboxes m ON m.id=s.mailbox_id"
           " JOIN runs r ON r.id=s.run_id"
           " WHERE s.status='submitted' AND s.score_status IN ('unknown','pending')")
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
    for r in rows:
        ref = r["platform_ref"]
        if not ref:
            still_unknown += 1  # 无平台回执引用：没有可查的对象，保持 unknown
            continue
        try:
            score = platform.fetch_score(
                r["email"], config.resolve_secret(r["secret_ref"] or ""), ref)
        except PlatformError:
            errors += 1
            continue
        if score is None:
            still_unknown += 1
            continue
        with db.transaction() as conn:
            # 并发轮询（手动+后台）幂等：只有 pending/unknown→scored 的真实
            # 状态迁移才落库并记事件；被并发方抢先迁移则本次不重复记
            cur = conn.execute(
                "UPDATE submissions SET score=?, score_status='scored',"
                " scored_at=? WHERE id=?"
                " AND score_status IN ('unknown','pending')",
                (score, db.utcnow(), r["id"]))
            if cur.rowcount != 1:
                continue
            db.append_event_tx(conn, r["run_id"], "controller",
                               "submission.scored",
                               {"submission_id": r["id"], "score": score})
        updated += 1
    return {"polled": len(rows), "updated": updated,
            "still_unknown": still_unknown, "errors": errors}


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
        " WHERE s.status='submitted' AND s.score_status IN ('unknown','pending')")
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
    return {"challenges": results}


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
    dup = db.query_one("SELECT * FROM submissions WHERE operation_id=?",
                       (operation_id,))
    if dup:
        return dict(dup) | {"deduplicated": True}
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
    secret = config.resolve_secret(harvest["secret_ref"] or "")
    challenge_id = _run_challenge_id(src["run_id"])
    try:
        receipt = platform.submit_package(
            harvest["email"], secret, str(package), challenge_id=challenge_id,
            meta={"method": "CyberScientist harvest: best verified package"})
        ok, error = bool(receipt.get("accepted")), None
        platform_ref = str(receipt.get("receipt") or "") or None
    except PlatformError as exc:
        ok, error, platform_ref = False, str(exc), None
    except Exception as exc:  # 兜底：失败行必须落库而非悬挂
        ok, error, platform_ref = False, \
            f"平台调用未预期失败: {type(exc).__name__}: {exc}", None

    with db.transaction() as conn:
        sid = _rid("sub")
        conn.execute(
            "INSERT INTO submissions(id, run_id, trial_id, mailbox_id,"
            " package_path, package_sha256, status, score_status, is_harvest,"
            " source_submission_id, operation_id, error, platform_ref,"
            " created_at, submitted_at)"
            " VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)",
            (sid, src["run_id"], src["trial_id"], harvest["id"],
             src["package_path"], src["package_sha256"],
             "submitted" if ok else "failed",
             "pending" if ok else "unknown",
             submission_id, operation_id, error, platform_ref, db.utcnow(),
             db.utcnow() if ok else None))
        conn.execute(
            "UPDATE mailboxes SET submissions_used=submissions_used+1"
            " WHERE id=?", (harvest["id"],))
        db.append_event_tx(
            conn, src["run_id"], "user",
            "submission.harvested" if ok else "submission.harvest_failed",
            {"submission_id": sid, "source_submission_id": submission_id,
             "mailbox": harvest["email"], "source_score": src["score"],
             "error": error, "is_demo": platform.is_demo},
            trial_id=src["trial_id"])
    return dict(db.query_one("SELECT * FROM submissions WHERE id=?",
                             (sid,))) | {"deduplicated": False}
