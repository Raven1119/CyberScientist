"""Experience kit B01–B07/B20: public save/read/revision/approval behavior."""
from pathlib import Path

import pytest

from cyberscientist import config, db, experiences as exp


def meta(**changes):
    return {"title": "经验", "scope": "global", "status": "candidate",
            "evidence_status": "hypothesis", "kind": "heuristic",
            "tags": [], "evidence_refs": [], **changes}


@pytest.mark.parametrize("titles", [("中文甲", "中文乙"), ("same", "same"),
                                    ("a/b", "a?b"), ("x" * 70 + "a", "x" * 70 + "b")])
def test_distinct_experiences_never_share_a_title_derived_file(titles):
    first = exp.save_experience("first", meta(title=titles[0]), "one", "user", None, None)
    second = exp.save_experience("second", meta(title=titles[1]), "two", "user", None, None)
    assert first["file"] != second["file"]
    assert Path(first["file"]).name == "first.md"
    exp.save_experience("first", meta(title=titles[0]), "updated", "user", None,
                        first["current_hash"])
    assert exp.get_experience("second")["body_md"].strip() == "two"


def test_rollback_redo_tracks_operations_and_the_actual_head():
    one = exp.save_experience("revision", meta(), "v1", "user", None, None)
    two = exp.save_experience("revision", meta(), "v2", "user", None, one["current_hash"])
    rollback = exp.restore_revision("revision", one["revision_hash"], "user", operation_id="rollback-1")
    retry = exp.restore_revision("revision", one["revision_hash"], "user", operation_id="rollback-1")
    assert retry["revision_id"] == rollback["revision_id"]
    assert rollback["revision_id"] != one["revision_id"]
    redo = exp.save_experience("revision", meta(), "v2", "user", None, rollback["current_hash"])
    detail = exp.get_experience("revision")
    assert detail["body_md"].strip() == "v2"
    assert detail["revision_id"] == redo["revision_id"]
    assert detail["current_hash"] == two["current_hash"]
    assert len(detail["revisions"]) == 4


def test_external_edit_is_registered_before_next_save():
    r = exp.save_experience("external", meta(), "original", "user", None, None)
    path = Path(r["file"])
    path.write_text(path.read_text().replace("original", "external"))
    current = exp.get_experience("external")
    assert len(current["revisions"]) == 2
    assert current["revisions"][-1]["operator"] == "external"
    exp.save_experience("external", meta(), "third", "user", None, current["current_hash"])
    assert len(exp.get_revisions("external")) == 3


@pytest.mark.parametrize("field,value", [("status", []), ("title", {}), ("tags", "x"), ("evidence_refs", [{}])])
def test_invalid_metadata_is_a_controlled_error(field, value):
    with pytest.raises(exp.ExperienceError):
        exp.save_experience("bad", meta(**{field: value}), "body", "user", None, None)
    assert exp.list_experiences()["items"] == []


@pytest.mark.parametrize("cid", [".", "..", "/tmp", "../other", "a/b"])
def test_invalid_challenge_paths_never_read_or_write(cid):
    with pytest.raises(exp.ExperienceError):
        exp.save_experience("escape", meta(scope="challenge", challenge_id=cid), "x", "user", None, None)
    with pytest.raises(exp.ExperienceError):
        exp.list_experiences(scope="challenge", challenge_id=cid)


def test_scope_and_directory_identity_are_immutable():
    r = exp.save_experience("bound", meta(scope="challenge", challenge_id="CH1"), "one", "user", None, None)
    with pytest.raises(exp.ExperienceError):
        exp.save_experience("bound", meta(), "two", "user", None, r["current_hash"])


def test_approval_binds_seen_revision_and_keeps_evidence_and_old_active():
    r1 = exp.save_experience("approval", meta(evidence_status="contradicted"), "one", "user", None, None)
    exp.approve_experience("approval", expected_revision=r1["revision_id"])
    assert exp.get_experience("approval")["frontmatter"]["evidence_status"] == "contradicted"
    r2 = exp.save_experience("approval", meta(evidence_status="hypothesis"), "two", "brain", None, r1["current_hash"])
    with pytest.raises(exp.ExperienceError) as error:
        exp.approve_experience("approval", expected_revision=r1["revision_id"])
    assert error.value.code == "REVISION_CONFLICT"
    detail = exp.get_experience("approval")
    assert detail["active_revision_id"] == r1["revision_id"]
    assert detail["revision_id"] == r2["revision_id"]
    path = Path(detail["file"])
    path.write_text("broken yaml")
    active = exp.active_experiences()
    assert active[0]["revision_id"] == r1["revision_id"]
    assert active[0]["body_md"].strip() == "one"


def test_symlink_directory_cannot_write_outside_experience(tmp_path):
    outside=tmp_path/'outside'; outside.mkdir()
    root=config.EXPERIENCE_DIR/'challenges'; root.mkdir()
    (root/'escape').symlink_to(outside,target_is_directory=True)
    with pytest.raises(exp.ExperienceError):
        exp.save_experience('bad',meta(scope='challenge',challenge_id='escape'),'x','user',None,None)
    assert list(outside.iterdir())==[]


def test_crash_after_file_before_pointer_reconciles_once(monkeypatch):
    r1=exp.save_experience('crash',meta(),'first','user',None,None)
    point=exp._point_at
    def fail(row): raise OSError('injected between file and pointer')
    monkeypatch.setattr(exp,'_point_at',fail)
    with pytest.raises(OSError):
        exp.save_experience('crash',meta(),'second','user',None,r1['current_hash'])
    monkeypatch.setattr(exp,'_point_at',point)
    assert exp.check_pending_writes()==[]
    assert exp.check_pending_writes()==[]
    current=exp.get_experience('crash')
    assert current['body_md'].strip()=='second' and len(current['revisions'])==2
    assert current['current_hash']==current['revisions'][-1]['revision_hash']


async def test_stale_api_approval_conflicts_without_changing_active():
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app
    r1=exp.save_experience('review',meta(),'first','user',None,None)
    exp.approve_experience('review',expected_revision=r1['revision_id'])
    exp.save_experience('review',meta(),'second','user',None,r1['current_hash'])
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://local') as client:
        response=await client.post('/api/v1/experiences/review/approve',json={'expected_revision':r1['revision_id']})
    assert response.status_code==409
    assert exp.get_experience('review')['active_revision_id']==r1['revision_id']


def test_legacy_migration_preserves_approved_bytes_and_history(tmp_path):
    r=exp.save_experience('legacy',meta(),'approved bytes','user',None,None)
    # Explicit legacy fixture: the old schema stored approval as status=active.
    conn=db.get_db()
    content=Path(r['file']).read_text().replace('status: candidate','status: active')
    parsed=exp.parse_experience(content,Path(r['file']))
    import json
    conn.execute('UPDATE experience_revisions SET full_content=?,frontmatter=?,revision_hash=? WHERE id=?',
                 (content,json.dumps(parsed['frontmatter']),exp.content_hash(content),r['revision_id']))
    conn.executescript('DROP TABLE experience_heads; DROP INDEX idx_revision_operation;')
    for column in ('parent_revision_id','operation_id','activate'):
        conn.execute(f'ALTER TABLE experience_revisions DROP COLUMN {column}')
    conn.commit()
    Path(r['file']).write_text('invalid external draft')
    db.init_db(); db.init_db()
    active=exp.active_experiences()
    assert len(active)==1 and active[0]['revision_id']==r['revision_id']
    assert active[0]['body_md'].strip()=='approved bytes'
    assert len(exp.get_revisions('legacy'))==1
    assert list((config.DATA_DIR/'migrations').glob('*/database.sqlite'))
