"""经验：文件+修订历史、冲突、回滚、外部编辑、校验。"""
from __future__ import annotations

import pytest

from cyberscientist import experiences
from cyberscientist.experiences import ExperienceError


def fm(**over):
    base = {"title": "测试经验", "scope": "global", "status": "candidate",
            "evidence_status": "hypothesis", "kind": "heuristic",
            "applicability": "所有题目", "evidence_refs": ["demo://x"]}
    base.update(over)
    return base


def test_create_and_read():
    r = experiences.save_experience("exp_a", fm(), "正文内容", "user", "创建", None)
    assert r["revision_hash"] == r["current_hash"]
    e = experiences.get_experience("exp_a")
    assert e["frontmatter"]["title"] == "测试经验"
    assert e["body_md"].strip() == "正文内容"


def test_requires_base_hash_on_update():
    experiences.save_experience("exp_b", fm(), "v1", "user", "创建", None)
    with pytest.raises(ExperienceError) as exc:
        experiences.save_experience("exp_b", fm(), "v2", "user", "改", None)
    assert exc.value.code == "REVISION_CONFLICT"


def test_stale_base_hash_conflict_carries_both_versions():
    r1 = experiences.save_experience("exp_c", fm(), "v1", "user", "创建", None)
    r2 = experiences.save_experience("exp_c", fm(), "v2", "user", "改",
                                     r1["current_hash"])
    with pytest.raises(ExperienceError) as exc:
        experiences.save_experience("exp_c", fm(), "草稿", "user", "冲突",
                                    r1["current_hash"])
    assert exc.value.code == "REVISION_CONFLICT"
    assert "v2" in exc.value.details["current_content"]
    assert "草稿" in exc.value.details["your_content"]


def test_external_edit_detected():
    r1 = experiences.save_experience("exp_d", fm(), "v1", "user", "创建", None)
    path = experiences._load_current("exp_d")[0]
    content = path.read_text(encoding="utf-8").replace("v1", "外部修改")
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ExperienceError) as exc:
        experiences.save_experience("exp_d", fm(), "v2", "user", "改",
                                    r1["current_hash"])
    assert exc.value.code == "REVISION_CONFLICT"
    # 用当前 hash 重试成功
    cur = experiences.content_hash(content)
    r = experiences.save_experience("exp_d", fm(), "v2", "user", "改", cur)
    assert r.get("unchanged") is not True


def test_restore_preserves_content_and_records_a_new_operation():
    r1 = experiences.save_experience("exp_e", fm(), "v1", "user", "创建", None)
    experiences.save_experience("exp_e", fm(), "v2", "user", "改", r1["current_hash"])
    r = experiences.restore_revision("exp_e", r1["revision_hash"], "user")
    assert r["revision_hash"] == r1["revision_hash"]
    e = experiences.get_experience("exp_e")
    assert "v1" in e["body_md"]
    revs = experiences.get_revisions("exp_e")
    assert len(revs) == 3  # 回滚是独立操作，内容 hash 可以重复


def test_invalid_frontmatter_rejected():
    with pytest.raises(ExperienceError) as exc:
        experiences.save_experience("exp_f", fm(status="validated_fact"),
                                    "x", "user", None, None)
    assert exc.value.code == "INVALID_EXPERIENCE"


def test_challenge_scope_path_and_bad_id():
    r = experiences.save_experience(
        "exp_g", fm(scope="challenge", challenge_id="CH1"), "x", "user", None, None)
    assert "challenges" in r["file"]
    with pytest.raises(ExperienceError):
        experiences.save_experience(
            "exp_h", fm(scope="challenge", challenge_id="../evil"), "x",
            "user", None, None)


def test_pending_write_recovery(tmp_path):
    experiences.save_experience("exp_i", fm(), "v1", "user", "创建", None)
    # 模拟崩溃：插入 applied=0 的修订且文件未更新
    from cyberscientist import db
    db.execute(
        "INSERT INTO experience_revisions(id, experience_id, revision_hash,"
        " parent_hash, file_path, frontmatter, body_md, full_content, operator,"
        " reason, evidence_refs, created_at, applied)"
        " VALUES('rev_x','exp_i','deadbeef',NULL,'experience/global/测试经验.md',"
        " '{}','ghost','ghost content','user','crash','[]','2026-01-01',0)")
    problems = experiences.check_pending_writes()
    assert len(problems) == 1 and problems[0]["experience_id"] == "exp_i"
