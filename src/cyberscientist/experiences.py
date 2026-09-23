"""经验：Markdown 文件是编辑界面，SQLite 保存不可覆盖的修订历史。

PUT 必须带 base_hash；不匹配返回 409 与双方内容。回滚创建新修订，不抹历史。
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
import functools
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import config, db

VALID_STATUS = {"candidate", "active", "retired"}
VALID_EVIDENCE = {"hypothesis", "observed", "validated", "contradicted"}
VALID_KIND = {"heuristic", "procedure", "failure", "platform"}
REQUIRED_FRONTMATTER = ["id", "title", "scope", "status", "evidence_status", "kind"]

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
_write_lock = threading.RLock()


def _locked(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with _write_lock:
            return fn(*args, **kwargs)
    return wrapped


def _rel(path: Path) -> str:
    """优先返回相对工作区根的路径；临时工作区（测试）下返回绝对路径。"""
    try:
        return str(path.relative_to(config.WORKSPACE_ROOT))
    except ValueError:
        return str(path)


class ExperienceError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _head(exp_id: str):
    return db.query_one("SELECT * FROM experience_heads WHERE experience_id=?", (exp_id,))


def _point_at(row) -> None:
    fm = json.loads(row["frontmatter"])
    with db.transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO experience_heads(experience_id,file_path,scope,challenge_id)"
                     " VALUES(?,?,?,?)", (row["experience_id"], row["file_path"], fm["scope"], fm.get("challenge_id")))
        conn.execute("UPDATE experience_revisions SET applied=1 WHERE id=?", (row["id"],))
        conn.execute("UPDATE experience_heads SET head_revision_id=?,problem=NULL WHERE experience_id=?",
                     (row["id"], row["experience_id"]))
        if row["activate"]:
            conn.execute("UPDATE experience_heads SET active_revision_id=? WHERE experience_id=?",
                         (row["id"], row["experience_id"]))
        elif fm["status"] == "retired" or fm["scope"] == "challenge":
            conn.execute("UPDATE experience_heads SET active_revision_id=NULL WHERE experience_id=?",
                         (row["experience_id"],))


def _register_head(exp_id: str, content: str) -> None:
    if _head(exp_id):
        return
    row = db.query_one("SELECT * FROM experience_revisions WHERE experience_id=? AND revision_hash=?"
                       " AND full_content=? AND applied=1 ORDER BY rowid DESC LIMIT 1",
                       (exp_id, content_hash(content), content))
    if row:
        fm = json.loads(row["frontmatter"])
        db.execute("UPDATE experience_revisions SET activate=? WHERE id=?",
                   (int(fm["status"] == "active"), row["id"]))
        _point_at(db.query_one("SELECT * FROM experience_revisions WHERE id=?", (row["id"],)))


def parse_experience(content: str, file_path: Path) -> dict[str, Any]:
    m = FRONTMATTER_RE.match(content)
    if not m:
        raise ExperienceError("INVALID_EXPERIENCE",
                              f"{file_path.name}: 缺少 YAML frontmatter")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ExperienceError("INVALID_EXPERIENCE",
                              f"{file_path.name}: frontmatter 解析失败: {exc}") from exc
    if not isinstance(fm, dict):
        raise ExperienceError("INVALID_EXPERIENCE", "frontmatter 必须是键值映射")
    missing = [k for k in REQUIRED_FRONTMATTER if k not in fm]
    if missing:
        raise ExperienceError("INVALID_EXPERIENCE",
                              f"frontmatter 缺少字段: {', '.join(missing)}")
    for key in REQUIRED_FRONTMATTER:
        if not isinstance(fm[key], str) or not fm[key].strip() or len(fm[key]) > 1000:
            raise ExperienceError("INVALID_EXPERIENCE", f"{key} 必须是有界非空字符串")
    _safe_id(fm["id"])
    for key in ("tags", "evidence_refs", "derived_from"):
        value = fm.get(key, [])
        if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
            raise ExperienceError("INVALID_EXPERIENCE", f"{key} 必须是字符串列表")
    for key in ("applicability", "review_note", "expires_at"):
        if fm.get(key) is not None and not isinstance(fm[key], str):
            raise ExperienceError("INVALID_EXPERIENCE", f"{key} 必须是字符串")
    if fm["scope"] == "challenge":
        _safe_id(fm.get("challenge_id"))
    elif fm.get("challenge_id") is not None:
        raise ExperienceError("INVALID_EXPERIENCE", "全局经验不能绑定 challenge_id")
    if fm["scope"] not in ("global", "challenge"):
        raise ExperienceError("INVALID_EXPERIENCE", "scope 必须是 global 或 challenge")
    if fm["status"] not in VALID_STATUS:
        raise ExperienceError("INVALID_EXPERIENCE", f"status 必须是 {sorted(VALID_STATUS)}")
    if fm["evidence_status"] not in VALID_EVIDENCE:
        raise ExperienceError("INVALID_EXPERIENCE",
                              f"evidence_status 必须是 {sorted(VALID_EVIDENCE)}")
    if fm["kind"] not in VALID_KIND:
        raise ExperienceError("INVALID_EXPERIENCE", f"kind 必须是 {sorted(VALID_KIND)}")
    if not isinstance(fm.get("evidence_refs", []), list):
        raise ExperienceError("INVALID_EXPERIENCE", "evidence_refs 必须是列表")
    try:
        json.dumps(fm, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ExperienceError("INVALID_EXPERIENCE","元数据必须可表示为 JSON 值") from exc
    return {"frontmatter": fm, "body_md": m.group(2)}


def _safe_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,119}", value):
        raise ExperienceError("INVALID_EXPERIENCE", "ID 含非法字符或点目录段")
    return value


def _safe_path(path: Path) -> Path:
    root = config.EXPERIENCE_DIR
    if not path.resolve().is_relative_to(root.resolve()):
        raise ExperienceError("INVALID_EXPERIENCE", "经验路径越界")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ExperienceError("INVALID_EXPERIENCE", "经验路径不能经过符号链接")
        if part == root:
            break
    return path


def _exp_dir(scope: str, challenge_id: str | None) -> Path:
    if scope == "global":
        return _safe_path(config.EXPERIENCE_DIR / "global")
    if not challenge_id:
        raise ExperienceError("INVALID_EXPERIENCE", "challenge 作用域需要 challenge_id")
    if scope != "challenge":
        raise ExperienceError("INVALID_EXPERIENCE", "未知作用域")
    return _safe_path(config.EXPERIENCE_DIR / "challenges" / _safe_id(challenge_id))


@_locked
def _reconcile(path: Path, scope: str, cid: str | None) -> dict[str, Any]:
    _safe_path(path)
    content = path.read_text(encoding="utf-8")
    parsed = parse_experience(content, path)
    parsed["_content"] = content
    fm = parsed["frontmatter"]
    if fm["scope"] != scope or fm.get("challenge_id") != cid:
        raise ExperienceError("INVALID_EXPERIENCE", "frontmatter 与目录归属不一致")
    eid = fm["id"]
    owner = db.query_one("SELECT experience_id FROM experience_heads WHERE file_path=?", (_rel(path),))
    if owner and owner["experience_id"] != eid:
        raise ExperienceError("REVISION_CONFLICT", "经验文件的不可变 ID 已被修改")
    _register_head(eid, content)
    head = _head(eid)
    if head and (config.WORKSPACE_ROOT / head["file_path"]).resolve() != path.resolve():
        raise ExperienceError("REVISION_CONFLICT", "同一经验 ID 出现在不同文件")
    old = db.query_one("SELECT * FROM experience_revisions WHERE id=?", (head["head_revision_id"],)) if head else None
    if old and old["full_content"] == content:
        return parsed
    pending = db.query_one("SELECT * FROM experience_revisions WHERE experience_id=? AND applied=0", (eid,))
    if pending:
        if pending["full_content"] == content and pending["parent_revision_id"] == (old["id"] if old else None):
            _point_at(pending)
            return parsed
        raise ExperienceError("REVISION_CONFLICT", "存在未完成写入，需先对账")
    rid = 'rev_' + uuid.uuid4().hex
    # 外部字节原样登记，不能给未登记文件配上另一版历史 hash。
    db.execute("INSERT INTO experience_revisions(id,experience_id,revision_hash,parent_hash,file_path,"
               "frontmatter,body_md,full_content,operator,reason,evidence_refs,created_at,applied,"
               "parent_revision_id,activate) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
               (rid,eid,content_hash(content),old["revision_hash"] if old else None,_rel(path),
                json.dumps(fm,ensure_ascii=False),parsed["body_md"],content,"external",
                "登记当前磁盘内容；此前未记录的变化时间未知",json.dumps(fm.get("evidence_refs",[])),_now(),
                old["id"] if old else None,int(scope == "challenge" and fm["status"] == "active")))
    _point_at(db.query_one("SELECT * FROM experience_revisions WHERE id=?", (rid,)))
    return parsed


def _display_metadata(fm: dict, head) -> dict:
    fm = dict(fm)
    if fm["scope"] == "global" and fm["status"] != "retired":
        fm["status"] = "active" if head and head["active_revision_id"] == head["head_revision_id"] else "candidate"
        if fm["status"] == "active":
            fm.pop("review_note", None)
    return fm


def _scan_dir(directory: Path, scope: str, challenge_id: str | None,
              errors: list[dict[str, str]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not directory.exists():
        return items
    for path in sorted(directory.glob("*.md")):
        try:
            parsed = _reconcile(path, scope, challenge_id)
        except ExperienceError as exc:
            errors.append({"file": _rel(path),
                           "error": str(exc)})
            continue
        fm = parsed["frontmatter"]
        content = parsed["_content"]
        head = _head(fm["id"])
        fm = _display_metadata(fm, head)
        rev = db.query_one("SELECT r.* FROM experience_heads h JOIN experience_revisions r"
                           " ON r.id=h.head_revision_id WHERE h.experience_id=?", (fm["id"],))
        items.append({
            "id": fm["id"], "title": fm["title"], "scope": fm["scope"],
            "challenge_id": fm.get("challenge_id") if scope == "challenge" else None,
            "status": fm["status"], "evidence_status": fm["evidence_status"],
            "kind": fm["kind"], "tags": fm.get("tags", []),
            "applicability": fm.get("applicability", ""),
            "evidence_refs": fm.get("evidence_refs", []),
            "expires_at": fm.get("expires_at"),
            "review_note": fm.get("review_note"),
            "file": _rel(path),
            "current_hash": content_hash(content),
            "revision_hash": rev["revision_hash"] if rev else None,
            "revision_id": rev["id"] if rev else None,
            "active_revision_id": head["active_revision_id"] if head else None,
            "updated_at": rev["created_at"] if rev else None,
            "updated_by": rev["operator"] if rev else None,
        })
    return items


@_locked
def list_experiences(scope: str | None = None,
                     challenge_id: str | None = None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    if challenge_id is not None:
        _exp_dir("challenge", challenge_id)
    if scope in (None, "global"):
        items += _scan_dir(_exp_dir("global", None), "global", None, errors)
    if scope in (None, "challenge"):
        root = config.EXPERIENCE_DIR / "challenges"
        if challenge_id:
            items += _scan_dir(root / challenge_id, "challenge", challenge_id, errors)
        elif root.exists():
            for d in sorted(p for p in root.iterdir() if p.is_dir()):
                items += _scan_dir(_exp_dir("challenge", d.name), "challenge", d.name, errors)
    return {"items": items, "errors": errors}


def _load_current(exp_id: str) -> tuple[Path, str, dict[str, Any]]:
    """按经验 id 定位当前文件（global 与当前 challenge 目录）。"""
    _safe_id(exp_id)
    head = _head(exp_id)
    if head:
        path = _safe_path(config.WORKSPACE_ROOT / head["file_path"])
        if not path.exists():
            raise ExperienceError("REVISION_CONFLICT", "经验当前文件缺失，保留历史等待对账")
        parsed = _reconcile(path, head["scope"], head["challenge_id"])
        if parsed["frontmatter"]["id"] != exp_id:
            raise ExperienceError("REVISION_CONFLICT", "磁盘文件的经验身份改变")
        return path, parsed["_content"], parsed
    for directory, scope, cid in (
            (config.EXPERIENCE_DIR / "global", "global", None),):
        path = _find_by_id(directory, exp_id)
        if path:
            return _load_current(exp_id)
    root = config.EXPERIENCE_DIR / "challenges"
    if root.exists():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            path = _find_by_id(d, exp_id)
            if path:
                return _load_current(exp_id)
    raise ExperienceError("NOT_FOUND", f"经验不存在: {exp_id}")


def _find_by_id(directory: Path, exp_id: str) -> Path | None:
    if not directory.exists():
        return None
    for path in sorted(directory.glob("*.md")):
        _safe_path(path)
        try:
            parsed = parse_experience(path.read_text(encoding="utf-8"), path)
        except ExperienceError:
            continue
        if parsed["frontmatter"]["id"] == exp_id:
            scope = "global" if directory == config.EXPERIENCE_DIR / "global" else "challenge"
            _reconcile(path, scope, None if scope == "global" else directory.name)
            return path
    return None


@_locked
def get_experience(exp_id: str) -> dict[str, Any]:
    path, content, parsed = _load_current(exp_id)
    _register_head(exp_id, content)
    head = _head(exp_id)
    revisions = get_revisions(exp_id)
    return {
        "id": exp_id, "file": _rel(path),
        "frontmatter": _display_metadata(parsed["frontmatter"], head), "body_md": parsed["body_md"],
        "current_hash": content_hash(content), "revisions": revisions,
        "adoptions": [dict(r) for r in db.query("SELECT run_id,trial_id,revision_id,adopted_seq,semantics FROM experience_uses WHERE experience_id=? ORDER BY rowid DESC LIMIT 30",(exp_id,))],
        "revision_id": head["head_revision_id"] if head else None,
        "active_revision_id": head["active_revision_id"] if head else None,
    }


def get_revisions(exp_id: str) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT id AS revision_id, revision_hash, parent_revision_id, parent_hash, operator, reason, created_at"
        " FROM experience_revisions WHERE experience_id=? AND applied=1 ORDER BY rowid",
        (exp_id,))
    return [dict(r) for r in rows]


def _render(frontmatter: dict[str, Any], body_md: str) -> str:
    fm_lines = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm_lines}\n---\n{body_md.rstrip()}\n"


@_locked
def save_experience(exp_id: str, frontmatter: dict[str, Any], body_md: str,
                    operator: str, reason: str | None, base_hash: str | None,
                    expected_file: str | None = None, *, operation_id: str | None = None,
                    force_revision: bool = False) -> dict[str, Any]:
    """创建或更新。base_hash 与当前文件不一致 → 409 REVISION_CONFLICT。"""
    if not isinstance(frontmatter, dict) or not isinstance(body_md, str):
        raise ExperienceError("INVALID_EXPERIENCE", "frontmatter 必须是对象且正文必须是字符串")
    if not isinstance(exp_id, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,119}", exp_id):
        raise ExperienceError("INVALID_EXPERIENCE", "经验 ID 含非法字符")
    fm = dict(frontmatter)
    if fm.get("scope") == "global" and fm.get("status") == "active":
        fm["status"] = "candidate"  # Only version-bound approval enables global bytes.
    fm["id"] = exp_id
    fm.setdefault("evidence_refs", [])
    fm.setdefault("tags", [])
    try:
        content = _render(fm, body_md)
    except (yaml.YAMLError, TypeError, ValueError) as exc:
        raise ExperienceError("INVALID_EXPERIENCE", "frontmatter 无法序列化") from exc
    parsed = parse_experience(content, Path(expected_file or f"{exp_id}.md"))
    if operation_id:
        previous = db.query_one("SELECT * FROM experience_revisions WHERE experience_id=? AND operation_id=?",
                                (exp_id, operation_id))
        if previous:
            if previous["full_content"] != content:
                raise ExperienceError("REVISION_CONFLICT", "operation_id 已用于不同内容")
            if not previous["applied"]:
                raise ExperienceError("REVISION_CONFLICT", "该写入尚待对账")
            return {"id": exp_id, "revision_id": previous["id"], "revision_hash": previous["revision_hash"],
                    "current_hash": previous["revision_hash"], "duplicate": True}

    existing_path: Path | None = None
    try:
        existing_path, current_content, prior = _load_current(exp_id)
        prior_fm = prior["frontmatter"]
        if (fm["scope"], fm.get("challenge_id")) != (prior_fm["scope"], prior_fm.get("challenge_id")):
            raise ExperienceError("INVALID_EXPERIENCE", "普通更新不能改变经验作用域或题目归属")
        current = content_hash(current_content)
        _register_head(exp_id, current_content)
    except ExperienceError as exc:
        if exc.code != "NOT_FOUND":
            raise
        current = None

    if current is not None and base_hash is None:
        raise ExperienceError("REVISION_CONFLICT",
                              "保存必须携带 base_hash", {"current_hash": current})
    if current is not None and base_hash != current:
        raise ExperienceError("REVISION_CONFLICT",
                              "当前文件已被其他修改覆盖", {
                                  "current_hash": current,
                                  "current_content": current_content,
                                  "your_content": content})

    creating = existing_path is None
    if creating:
        directory = _exp_dir(fm["scope"], fm.get("challenge_id"))
        directory.mkdir(parents=True, exist_ok=True)
        existing_path = directory / f"{exp_id}.md"
        if existing_path.exists() or existing_path.is_symlink():
            raise ExperienceError("REVISION_CONFLICT", "经验路径已被其他内容占用")
        parent_hash = None
    else:
        last = db.query_one("SELECT r.* FROM experience_heads h JOIN experience_revisions r"
                            " ON r.id=h.head_revision_id WHERE h.experience_id=?", (exp_id,))
        parent_hash = last["revision_hash"] if last else None

    rev_hash = content_hash(content)
    if current == rev_hash and not force_revision:
        # 内容未变化，不制造空修订
        return {"id": exp_id, "revision_id": _head(exp_id)["head_revision_id"], "revision_hash": rev_hash,
                "current_hash": rev_hash, "unchanged": True}

    if db.query_one("SELECT id FROM experience_revisions WHERE experience_id=? AND applied=0",(exp_id,)):
        raise ExperienceError("REVISION_CONFLICT","存在未完成写入，需先对账")
    # 操作身份与内容哈希独立；只有 operation_id 能去重操作。
    revision_id = f"rev_{uuid.uuid4().hex}"
    parent = _head(exp_id)
    db.execute(
            "INSERT INTO experience_revisions(id, experience_id, revision_hash,"
            " parent_hash, file_path, frontmatter, body_md, full_content, operator,"
            " reason, evidence_refs, created_at, applied,parent_revision_id,operation_id,activate)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?)",
            (revision_id, exp_id, rev_hash, parent_hash,
             _rel(existing_path),
             json.dumps(parsed["frontmatter"], ensure_ascii=False),
             parsed["body_md"], content, operator, reason,
             json.dumps(fm.get("evidence_refs", []), ensure_ascii=False), _now(),
             parent["head_revision_id"] if parent else None, operation_id,
             int(fm["status"] == "active" and (fm["scope"] == "challenge" or creating))))
    import os as _os
    if creating:
        with existing_path.open("x", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            _os.fsync(handle.fileno())
    else:
        tmp = existing_path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        _os.replace(tmp, existing_path)
    _point_at(db.query_one("SELECT * FROM experience_revisions WHERE id=?", (revision_id,)))
    return {"id": exp_id, "revision_id": revision_id, "revision_hash": rev_hash, "current_hash": rev_hash,
            "file": _rel(existing_path)}


@_locked
def approve_experience(exp_id: str, *, expected_revision: str | None = None) -> dict[str, Any]:
    """用户审批通过：candidate → active（全局经验的唯一晋升通道）。"""
    exp = get_experience(exp_id)
    if expected_revision is None or expected_revision != exp["revision_id"]:
        raise ExperienceError("REVISION_CONFLICT", "审批版本已改变，请重新审阅", exp)
    with db.transaction() as conn:
        if exp["active_revision_id"] != exp["revision_id"]:
            conn.execute("INSERT INTO experience_approvals(experience_id,revision_id,operator,created_at) VALUES(?,?,'user',?)",
                         (exp_id,exp["revision_id"],_now()))
        updated = conn.execute("UPDATE experience_heads SET active_revision_id=head_revision_id"
                               " WHERE experience_id=? AND head_revision_id=?", (exp_id,exp["revision_id"]))
        if not updated.rowcount:
            raise ExperienceError("REVISION_CONFLICT", "审批版本已改变")
    return get_experience(exp_id)


@_locked
def reject_experience(exp_id: str, note: str, *, expected_revision: str | None = None) -> dict[str, Any]:
    """用户驳回：保持/退回 candidate 并附批注；大脑下轮整理时参考
    review_note 重写或放弃。"""
    if not note.strip():
        raise ExperienceError("INVALID_EXPERIENCE", "驳回必须附批注")
    exp = get_experience(exp_id)
    if expected_revision is None or expected_revision != exp["revision_id"]:
        raise ExperienceError("REVISION_CONFLICT", "驳回版本已改变，请重新审阅", exp)
    fm = dict(exp["frontmatter"])
    fm["status"] = "candidate"
    fm["review_note"] = note.strip()[:2000]
    return save_experience(exp_id, fm, exp["body_md"], operator="user",
                           reason=f"用户驳回: {note.strip()[:80]}",
                           base_hash=exp["current_hash"])


@_locked
def active_experiences(challenge_id: str | None = None) -> list[dict[str, Any]]:
    """Runtime reads registered active bytes, including when the editable draft is invalid."""
    list_experiences(challenge_id=challenge_id)
    rows = db.query("SELECT r.*,h.scope,h.challenge_id FROM experience_heads h JOIN experience_revisions r"
                    " ON r.id=h.active_revision_id WHERE r.applied=1 AND (h.scope='global' OR h.challenge_id=?)",
                    (challenge_id,))
    result = []
    for row in rows:
        fm = json.loads(row["frontmatter"])
        result.append({**fm,"status":"active","revision_id":row["id"],"revision_hash":row["revision_hash"],
                       "current_hash":row["revision_hash"],"body_md":row["body_md"],"full_content":row["full_content"]})
    return result


@_locked
def restore_revision(exp_id: str, revision_hash: str, operator: str,
                     reason: str | None = None, *, operation_id: str | None = None) -> dict[str, Any]:
    row = db.query_one(
        "SELECT frontmatter, body_md, full_content FROM experience_revisions"
        " WHERE experience_id=? AND (revision_hash=? OR id=?) AND applied=1 ORDER BY rowid DESC LIMIT 1",
        (exp_id, revision_hash, revision_hash))
    if not row:
        raise ExperienceError("NOT_FOUND", f"修订不存在: {revision_hash}")
    try:
        _, current_content, _ = _load_current(exp_id)
        base = content_hash(current_content)
    except ExperienceError as exc:
        if exc.code != "NOT_FOUND":
            raise
        base = None
    fm = json.loads(row["frontmatter"])
    return save_experience(exp_id, fm, row["body_md"], operator,
                           reason or f"回滚到 {revision_hash[:12]}", base,
                           operation_id=operation_id, force_revision=True)


@_locked
def check_pending_writes() -> list[dict[str, Any]]:
    """Complete only bytes proven to belong to the recorded pending operation."""
    import os
    problems = []
    for row in db.query("SELECT * FROM experience_revisions WHERE applied=0 ORDER BY rowid"):
        try:
            path = _safe_path(config.WORKSPACE_ROOT / row["file_path"])
            parsed = parse_experience(row["full_content"], path)
            fm = parsed["frontmatter"]
            if fm["id"] != row["experience_id"] or content_hash(row["full_content"]) != row["revision_hash"]:
                raise ExperienceError("REVISION_CONFLICT", "pending 内容身份/hash 不符")
            if path.parent.resolve() != _exp_dir(fm["scope"], fm.get("challenge_id")).resolve():
                raise ExperienceError("REVISION_CONFLICT", "pending 路径归属不符")
            head = _head(row["experience_id"])
            if (head["head_revision_id"] if head else None) != row["parent_revision_id"]:
                raise ExperienceError("REVISION_CONFLICT", "pending 父版本已改变")
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != row["full_content"]:
                parent = db.query_one("SELECT full_content FROM experience_revisions WHERE id=?", (row["parent_revision_id"],))
                if actual is None and not parent:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("x", encoding="utf-8") as handle:
                        handle.write(row["full_content"])
                elif parent and actual == parent["full_content"]:
                    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
                    tmp.write_text(row["full_content"], encoding="utf-8")
                    os.replace(tmp, path)
                else:
                    raise ExperienceError("REVISION_CONFLICT", "磁盘字节既非父版本亦非待写版本")
            _point_at(row)
        except (ExperienceError, OSError, UnicodeError) as exc:
            problems.append({"experience_id":row["experience_id"], "revision_id":row["id"],
                             "revision_hash":row["revision_hash"], "error":str(exc)})
    return problems
