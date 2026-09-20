"""经验：Markdown 文件是编辑界面，SQLite 保存不可覆盖的修订历史。

PUT 必须带 base_hash；不匹配返回 409 与双方内容。回滚创建新修订，不抹历史。
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
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
    return {"frontmatter": fm, "body_md": m.group(2)}


def _exp_dir(scope: str, challenge_id: str | None) -> Path:
    if scope == "global":
        return config.EXPERIENCE_DIR / "global"
    if not challenge_id:
        raise ExperienceError("INVALID_EXPERIENCE", "challenge 作用域需要 challenge_id")
    safe = re.fullmatch(r"[A-Za-z0-9_.-]+", challenge_id or "")
    if not safe:
        raise ExperienceError("INVALID_EXPERIENCE", "challenge_id 含非法字符")
    return config.EXPERIENCE_DIR / "challenges" / challenge_id


def _scan_dir(directory: Path, scope: str, challenge_id: str | None,
              errors: list[dict[str, str]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not directory.exists():
        return items
    for path in sorted(directory.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        try:
            parsed = parse_experience(content, path)
        except ExperienceError as exc:
            errors.append({"file": _rel(path),
                           "error": str(exc)})
            continue
        fm = parsed["frontmatter"]
        rev = db.query_one(
            "SELECT revision_hash, created_at, operator FROM experience_revisions"
            " WHERE experience_id=? ORDER BY created_at DESC LIMIT 1",
            (fm["id"],))
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
            "updated_at": rev["created_at"] if rev else None,
            "updated_by": rev["operator"] if rev else None,
        })
    return items


def list_experiences(scope: str | None = None,
                     challenge_id: str | None = None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    if scope in (None, "global"):
        items += _scan_dir(config.EXPERIENCE_DIR / "global", "global", None, errors)
    if scope in (None, "challenge"):
        root = config.EXPERIENCE_DIR / "challenges"
        if challenge_id:
            items += _scan_dir(root / challenge_id, "challenge", challenge_id, errors)
        elif root.exists():
            for d in sorted(p for p in root.iterdir() if p.is_dir()):
                items += _scan_dir(d, "challenge", d.name, errors)
    return {"items": items, "errors": errors}


def _load_current(exp_id: str) -> tuple[Path, str, dict[str, Any]]:
    """按经验 id 定位当前文件（global 与当前 challenge 目录）。"""
    for directory, scope, cid in (
            (config.EXPERIENCE_DIR / "global", "global", None),):
        path = _find_by_id(directory, exp_id)
        if path:
            content = path.read_text(encoding="utf-8")
            return path, content, parse_experience(content, path)
    root = config.EXPERIENCE_DIR / "challenges"
    if root.exists():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            path = _find_by_id(d, exp_id)
            if path:
                content = path.read_text(encoding="utf-8")
                return path, content, parse_experience(content, path)
    raise ExperienceError("NOT_FOUND", f"经验不存在: {exp_id}")


def _find_by_id(directory: Path, exp_id: str) -> Path | None:
    if not directory.exists():
        return None
    for path in sorted(directory.glob("*.md")):
        try:
            parsed = parse_experience(path.read_text(encoding="utf-8"), path)
        except ExperienceError:
            continue
        if parsed["frontmatter"]["id"] == exp_id:
            return path
    return None


def get_experience(exp_id: str) -> dict[str, Any]:
    path, content, parsed = _load_current(exp_id)
    revisions = get_revisions(exp_id)
    return {
        "id": exp_id, "file": _rel(path),
        "frontmatter": parsed["frontmatter"], "body_md": parsed["body_md"],
        "current_hash": content_hash(content), "revisions": revisions,
    }


def get_revisions(exp_id: str) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT revision_hash, parent_hash, operator, reason, created_at"
        " FROM experience_revisions WHERE experience_id=? ORDER BY created_at",
        (exp_id,))
    return [dict(r) for r in rows]


def _render(frontmatter: dict[str, Any], body_md: str) -> str:
    fm_lines = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm_lines}\n---\n{body_md.rstrip()}\n"


def save_experience(exp_id: str, frontmatter: dict[str, Any], body_md: str,
                    operator: str, reason: str | None, base_hash: str | None,
                    expected_file: str | None = None) -> dict[str, Any]:
    """创建或更新。base_hash 与当前文件不一致 → 409 REVISION_CONFLICT。"""
    fm = dict(frontmatter)
    fm["id"] = exp_id
    fm.setdefault("evidence_refs", [])
    fm.setdefault("tags", [])
    content = _render(fm, body_md)
    parsed = parse_experience(content, Path(expected_file or f"{exp_id}.md"))

    existing_path: Path | None = None
    try:
        existing_path, current_content, _ = _load_current(exp_id)
        current = content_hash(current_content)
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

    if existing_path is None:
        directory = _exp_dir(fm["scope"], fm.get("challenge_id"))
        directory.mkdir(parents=True, exist_ok=True)
        fname = re.sub(r"[^A-Za-z0-9_.-]+", "_", fm["title"])[:60] or exp_id
        existing_path = directory / f"{fname}.md"
        parent_hash = None
    else:
        last = db.query_one(
            "SELECT revision_hash FROM experience_revisions WHERE experience_id=?"
            " ORDER BY created_at DESC LIMIT 1", (exp_id,))
        parent_hash = last["revision_hash"] if last else None

    rev_hash = content_hash(content)
    if parent_hash == rev_hash:
        # 内容未变化，不制造空修订
        return {"id": exp_id, "revision_hash": rev_hash,
                "current_hash": rev_hash, "unchanged": True}

    # 先记修订日志（applied=0），原子替换文件，再标记完成。
    # 回滚到历史内容时 revision_hash 必然已存在（内容寻址）——
    # 这是幂等指向已有修订，不重复插入。
    existing_rev = db.query_one(
        "SELECT id FROM experience_revisions WHERE experience_id=? AND revision_hash=?",
        (exp_id, rev_hash))
    if existing_rev is None:
        db.execute(
            "INSERT INTO experience_revisions(id, experience_id, revision_hash,"
            " parent_hash, file_path, frontmatter, body_md, full_content, operator,"
            " reason, evidence_refs, created_at, applied)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)",
            (f"rev_{uuid.uuid4().hex[:12]}", exp_id, rev_hash, parent_hash,
             _rel(existing_path),
             json.dumps(parsed["frontmatter"], ensure_ascii=False),
             parsed["body_md"], content, operator, reason,
             json.dumps(fm.get("evidence_refs", []), ensure_ascii=False), _now()))
    tmp = existing_path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    import os as _os
    _os.replace(tmp, existing_path)  # 原子替换，避免半写文件
    db.execute(
        "UPDATE experience_revisions SET applied=1 WHERE experience_id=? AND revision_hash=?",
        (exp_id, rev_hash))
    return {"id": exp_id, "revision_hash": rev_hash, "current_hash": rev_hash,
            "file": _rel(existing_path)}


def approve_experience(exp_id: str) -> dict[str, Any]:
    """用户审批通过：candidate → active（全局经验的唯一晋升通道）。"""
    exp = get_experience(exp_id)
    fm = dict(exp["frontmatter"])
    fm["status"] = "active"
    fm["evidence_status"] = "observed"
    fm.pop("review_note", None)
    return save_experience(exp_id, fm, exp["body_md"], operator="user",
                           reason="用户审批通过", base_hash=exp["current_hash"])


def reject_experience(exp_id: str, note: str) -> dict[str, Any]:
    """用户驳回：保持/退回 candidate 并附批注；大脑下轮整理时参考
    review_note 重写或放弃。"""
    if not note.strip():
        raise ExperienceError("INVALID_EXPERIENCE", "驳回必须附批注")
    exp = get_experience(exp_id)
    fm = dict(exp["frontmatter"])
    fm["status"] = "candidate"
    fm["review_note"] = note.strip()[:2000]
    return save_experience(exp_id, fm, exp["body_md"], operator="user",
                           reason=f"用户驳回: {note.strip()[:80]}",
                           base_hash=exp["current_hash"])


def restore_revision(exp_id: str, revision_hash: str, operator: str,
                     reason: str | None = None) -> dict[str, Any]:
    row = db.query_one(
        "SELECT frontmatter, body_md, full_content FROM experience_revisions"
        " WHERE experience_id=? AND revision_hash=?",
        (exp_id, revision_hash))
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
                           reason or f"回滚到 {revision_hash[:12]}", base)


def check_pending_writes() -> list[dict[str, Any]]:
    """启动时核对未完成的写入与实际文件 hash。"""
    rows = db.query(
        "SELECT experience_id, revision_hash, file_path, full_content"
        " FROM experience_revisions WHERE applied=0")
    problems = []
    for r in rows:
        path = config.WORKSPACE_ROOT / r["file_path"]
        on_disk = content_hash(path.read_text(encoding="utf-8")) if path.exists() else None
        if on_disk != content_hash(r["full_content"]):
            problems.append({"experience_id": r["experience_id"],
                             "revision_hash": r["revision_hash"],
                             "on_disk_hash": on_disk})
        else:
            db.execute(
                "UPDATE experience_revisions SET applied=1 WHERE experience_id=? AND revision_hash=?",
                (r["experience_id"], r["revision_hash"]))
    return problems
