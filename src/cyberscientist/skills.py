"""技能目录扫描与生效技能合并。

技能本体物理装在 skills 目录，由 Kimi/Codex CLI 自动发现；
本模块只提供目录清单（UI 展示）与生效集合计算（controller 拼提示文本）。
"启用" = 将生效技能的名称、描述及 SKILL.md 绝对路径注入会话任务文本。
"""
from __future__ import annotations

import re
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import yaml

from . import db

SKILL_DIRS: tuple[Path, ...] = (
    Path(__file__).resolve().parents[2] / 'skills',
    Path.home() / ".kimi-code" / "skills",
    Path.home() / ".agents" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".codex" / "plugins" / "cache" / "openai-curated-remote",
)

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?", re.DOTALL)
BUILTIN_EXECUTOR_SKILLS = ('cyberscientist-sandbox', 'cyberscientist-clean-rerun', 'cyberscientist-job-spec', 'bohrium-lkm')


def _parse_skill_md(path: Path) -> dict[str, str]:
    """解析 SKILL.md frontmatter；缺 frontmatter/字段时回退默认值。"""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    if not isinstance(fm, dict):
        return {}
    out: dict[str, str] = {}
    metadata = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    for key in ("name", "description", "audience"):
        value = metadata.get("audience") if key == "audience" else fm.get(key)
        if isinstance(value, str) and value.strip():
            # 描述用于单行注入提示文本，折叠内部换行
            out[key] = " ".join(value.split())
    return out


def scan_catalog(skill_dirs: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    """扫描技能目录，返回 [{id, name, description, source}]，按 id 排序。

    目录不存在则跳过；子目录无 SKILL.md 不算技能。
    同名技能多目录出现时前者优先（按 skill_dirs 顺序）。
    """
    dirs = SKILL_DIRS if skill_dirs is None else skill_dirs
    found: dict[str, dict[str, Any]] = {}
    for root in dirs:
        root = Path(root)
        if not root.is_dir():
            continue
        for sub in sorted(root.iterdir()):
            if not sub.is_dir():
                continue
            if not (sub / "SKILL.md").is_file():
                continue
            if sub.name in found:
                continue
            fm = _parse_skill_md(sub / "SKILL.md")
            found[sub.name] = {
                "id": sub.name,
                "name": fm.get("name") or sub.name,
                "description": fm.get("description", ""),
                "audience": fm.get("audience", "both"),
                "source": str(root),
            }
    return [found[k] for k in sorted(found)]


def file_catalog() -> list[dict[str, str]]:
    """Registered skill roots only, including nested system/plugin packages.

    Keep the UI's direct-child catalog unchanged. A relative package path is
    the stable reader ID; duplicate IDs retain the configured root precedence.
    """
    found = {}
    for root in SKILL_DIRS:
        root = Path(root)
        if root.is_symlink():
            continue
        for directory, children, files in os.walk(root, followlinks=False):
            children[:] = sorted(name for name in children
                                 if name != '.git' and not (Path(directory) / name).is_symlink())
            if 'SKILL.md' not in files or (Path(directory) / 'SKILL.md').is_symlink():
                continue
            identifier = Path(directory).relative_to(root).as_posix()
            if identifier != '.':
                found.setdefault(identifier, {'id': identifier, 'source_path': directory})
    return [found[key] for key in sorted(found)]


def effective_for(conn: sqlite3.Connection, settings: dict[str, Any],
                  challenge_id: str | None,
                  catalog: list[dict[str, Any]] | None = None,
                  role: str = 'brain'
                  ) -> list[dict[str, Any]]:
    """常驻 ∪ 本题绑定，去重；引用已删除技能的条目静默跳过。"""
    if catalog is None:
        catalog = scan_catalog()
    by_id = {s["id"]: s for s in catalog}
    always_on = (settings.get("skills") or {}).get("always_on") or []
    bound = db.list_challenge_skills(conn, challenge_id) if challenge_id else []
    ids: list[str] = []
    defaults = BUILTIN_EXECUTOR_SKILLS if role == 'executor' else ('bohrium-lkm',)
    for sid in list(defaults) + list(always_on) + bound:
        if sid in by_id and sid not in ids:
            ids.append(sid)
    return [by_id[sid] for sid in ids
            if by_id[sid].get("audience", "both") in ("both", role)]


def prompt_segment(skills_: list[dict[str, Any]]) -> str:
    """拼进会话任务文本的技能段落；source 保持技能根目录的既有语义。"""
    if not skills_:
        return ""
    lines = []
    for skill in skills_:
        path = (Path(skill["source"]) / skill["id"] / "SKILL.md").resolve()
        lines.append(f"- {skill['name']}: {skill['description']}\n"
                     f"  SKILL.md: {path}")
    return ("\n\n本 Trial 可参考技能（调用前建议阅读对应的 SKILL.md，"
            "采用适合当前证据的做法；引用的相对路径以该文件所在目录为准）：\n"
            + "\n".join(lines))


def brain_prompt_segment(skills_: list[dict[str, Any]]) -> str:
    """D-56: index only; skill bodies travel through scoped read receipts."""
    return prompt_segment(skills_) + '\n需要时用research_files读取对应SKILL.md及引用文件；技能正文不是授权。\n'
