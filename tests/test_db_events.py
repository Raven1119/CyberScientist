"""事件 seq 单调与唯一约束、操作日志幂等。"""
from __future__ import annotations

import pytest

from cyberscientist import db


def _run(run_id="run_t1"):
    db.execute(
        "INSERT OR IGNORE INTO challenges(id, platform_challenge_id, origin, title,"
        " content, content_hash, imported_at, is_demo)"
        " VALUES('DEMO_CHALLENGE','DEMO_000','demo://local','演示题','内容','hash',?,1)",
        (db.utcnow(),))
    db.execute(
        "INSERT INTO runs(id, challenge_id, mode, phase, config_snapshot, created_at)"
        " VALUES(?,?,?,?,?,?)",
        (run_id, "DEMO_CHALLENGE", "demo", "created", "{}", db.utcnow()))


def test_seq_monotonic_and_unique():
    _run()
    e1 = db.append_event("run_t1", "controller", "a")
    e2 = db.append_event("run_t1", "brain", "b")
    e3 = db.append_event("run_t1", "prime", "c")
    assert [e1["seq"], e2["seq"], e3["seq"]] == [1, 2, 3]
    with pytest.raises(db.sqlite3.IntegrityError):
        db.get_db().execute(
            "INSERT INTO events(event_id, run_id, seq, occurred_at, recorded_at,"
            " source, type, payload) VALUES('evt_dup','run_t1',2,'t','t','x','y','{}')")
        db.get_db().commit()


def test_events_after_paging():
    _run()
    for i in range(5):
        db.append_event("run_t1", "controller", f"e{i}")
    page1 = db.events_after("run_t1", 0, limit=2)
    page2 = db.events_after("run_t1", page1[-1]["seq"], limit=2)
    assert [e["seq"] for e in page1] == [1, 2]
    assert [e["seq"] for e in page2] == [3, 4]
    assert db.events_after("run_t1", 99) == []


def test_record_operation_idempotent():
    _run()
    assert db.record_operation("op1", "run_t1", "control.steer", "accepted") is True
    assert db.record_operation("op1", "run_t1", "control.steer", "accepted") is False
    row = db.query_one("SELECT status FROM operations WHERE operation_id='op1'")
    assert row["status"] == "accepted"


def test_bump_state_version():
    _run()
    assert db.bump_state_version("run_t1") == 1
    assert db.bump_state_version("run_t1") == 2
