"""SQLite 权威存储：Run 状态、事件、Trial、授权、经验修订、操作日志。

事件与关键状态更新在同一事务提交；(run_id, seq) 唯一。
多步写入（检查点+审阅请求、审阅结果+指导 outbox）使用 transaction()。
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator

from . import config

_local = threading.local()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        config.ensure_dirs()
        conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS challenges (
    id TEXT PRIMARY KEY,
    platform_challenge_id TEXT,
    origin TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    contract_status TEXT NOT NULL DEFAULT 'unknown',
    eligibility TEXT,
    imported_at TEXT NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    challenge_id TEXT NOT NULL REFERENCES challenges(id),
    mode TEXT NOT NULL,                -- demo | connected
    phase TEXT NOT NULL DEFAULT 'created',
    state_version INTEGER NOT NULL DEFAULT 0,
    intention TEXT,
    authorization_id TEXT,
    config_snapshot TEXT NOT NULL,
    experience_snapshot TEXT,
    current_trial_id TEXT,
    block_reason TEXT,
    brain_reviews_used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS authorizations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    scope TEXT NOT NULL,               -- demo | model_roundtrip
    allow_model_calls INTEGER NOT NULL DEFAULT 0,
    max_model_turns INTEGER NOT NULL DEFAULT 0,
    max_run_minutes INTEGER NOT NULL DEFAULT 0,
    max_submissions INTEGER NOT NULL DEFAULT 0,
    granted_at TEXT NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS trials (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    parent_trial_id TEXT,
    goal TEXT NOT NULL,
    success_check TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    seq INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    source TEXT NOT NULL,              -- brain | prime | controller | user | demo
    type TEXT NOT NULL,
    trial_id TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    raw_ref TEXT,
    UNIQUE(run_id, seq)
);
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,              -- accepted | confirmed | rejected | unknown
    request_summary TEXT,
    payload_hash TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    trial_id TEXT,
    report TEXT NOT NULL,
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experience_revisions (
    id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL,
    revision_hash TEXT NOT NULL,
    parent_hash TEXT,
    file_path TEXT NOT NULL,
    frontmatter TEXT NOT NULL,
    body_md TEXT NOT NULL,
    full_content TEXT NOT NULL,
    operator TEXT NOT NULL,
    reason TEXT,
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    applied INTEGER NOT NULL DEFAULT 1,
    parent_revision_id TEXT,
    operation_id TEXT,
    activate INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_rev_exp ON experience_revisions(experience_id, created_at);
"""

# 协作与静默监督（迁移 v2）：全部幂等（IF NOT EXISTS / 列存在性检查）
SCHEMA_V2_TABLES = """
CREATE TABLE IF NOT EXISTS supervision (
    run_id TEXT PRIMARY KEY REFERENCES runs(id),
    enabled INTEGER NOT NULL DEFAULT 0,
    shadow_epoch INTEGER NOT NULL DEFAULT 0,
    covered_seq INTEGER NOT NULL DEFAULT 0,
    evidence_revision INTEGER NOT NULL DEFAULT 0,
    reviews_used INTEGER NOT NULL DEFAULT 0,
    private_note_md TEXT NOT NULL DEFAULT '',
    watchlist TEXT NOT NULL DEFAULT '[]',
    last_review_at TEXT,
    degraded INTEGER NOT NULL DEFAULT 0,
    degrade_reason TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_requests (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    source TEXT NOT NULL,            -- shadow | executor | user | lifecycle
    blocking INTEGER NOT NULL DEFAULT 0,
    checkpoint_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
        -- pending | running | done | error | obsolete
    trigger TEXT,
    from_seq INTEGER,
    through_seq INTEGER,
    state_version INTEGER,
    evidence_revision INTEGER,
    shadow_epoch INTEGER,
    frame_id TEXT,
    frame_json TEXT,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_requests_run ON review_requests(run_id, status);
CREATE TABLE IF NOT EXISTS guidance (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    review_request_id TEXT,
    frame_id TEXT,
    source TEXT NOT NULL,            -- shadow | requested | user
    target_trial_id TEXT,
    kind TEXT NOT NULL,              -- nudge | steer | stop | submit
    intent TEXT NOT NULL,            -- continue | observe | reframe
    text_md TEXT NOT NULL,
    reason_md TEXT,
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    expected_change_md TEXT,
    revisit_when_md TEXT,
    state_version INTEGER,
    evidence_revision INTEGER,
    shadow_epoch INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',
        -- queued | sending | sent | acknowledged | unknown | rejected
        -- | superseded | invalidated
    delivery_channel TEXT,
    operation_id TEXT,
    ack_disposition TEXT,
    ack_reason_md TEXT,
    acked_at TEXT,
    applied_evidence TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guidance_run ON guidance(run_id, status);
CREATE TABLE IF NOT EXISTS capability_tokens (
    token_hash TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    role TEXT NOT NULL,              -- executor
    session_ref TEXT,
    generation INTEGER NOT NULL DEFAULT 0,
    revoked INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- 邮箱账号：harvest（收割，唯一，用户提供）/ experiment（实验，批量注册）
CREATE TABLE IF NOT EXISTS mailboxes (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    email TEXT NOT NULL,
    platform TEXT NOT NULL,
    secret_ref TEXT,
    status TEXT NOT NULL DEFAULT 'active',  -- active | exhausted | disabled
    submission_limit INTEGER NOT NULL DEFAULT 10,
    submissions_used INTEGER NOT NULL DEFAULT 0,
    is_demo INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    created_at TEXT NOT NULL,
    disabled_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mailboxes_harvest_active
    ON mailboxes(role) WHERE role='harvest' AND status<>'disabled';
-- 提交记录：实验邮箱是提交主体；收割行 is_harvest=1 且引用来源提交
CREATE TABLE IF NOT EXISTS experience_approvals (
 id INTEGER PRIMARY KEY, experience_id TEXT NOT NULL, revision_id TEXT NOT NULL,
 operator TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experience_contexts (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL, trial_id TEXT, boundary TEXT NOT NULL,
 content_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id,boundary)
);
CREATE TABLE IF NOT EXISTS experience_uses (
 run_id TEXT NOT NULL, trial_id TEXT, context_id TEXT NOT NULL, experience_id TEXT NOT NULL,
 revision_id TEXT NOT NULL, revision_hash TEXT NOT NULL, declaration_id TEXT NOT NULL,
 adopted_seq INTEGER NOT NULL, semantics TEXT NOT NULL,
 PRIMARY KEY(run_id,declaration_id,context_id,experience_id)
);
CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    trial_id TEXT,
    mailbox_id TEXT NOT NULL REFERENCES mailboxes(id),
    package_path TEXT NOT NULL,
    package_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown',  -- submitted | failed | unknown
    score REAL,                              -- 不知道就是 NULL
    score_status TEXT NOT NULL DEFAULT 'unknown',  -- unknown|pending|scored|failed
    is_harvest INTEGER NOT NULL DEFAULT 0,
    source_submission_id TEXT,               -- 收割提交引用的实验提交
    operation_id TEXT UNIQUE,                -- 幂等去重
    error TEXT,
    created_at TEXT NOT NULL,
    submitted_at TEXT,
    scored_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_submissions_run ON submissions(run_id);
CREATE INDEX IF NOT EXISTS idx_submissions_mailbox ON submissions(mailbox_id);
-- 随题目启用的技能绑定；source 记录绑定来源（user 等）
CREATE TABLE IF NOT EXISTS challenge_skills (
    challenge_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    PRIMARY KEY (challenge_id, skill_id)
);
"""

# Persistent cloud operations and independent curation sessions.
SCHEMA_RELIABILITY = """
CREATE TABLE IF NOT EXISTS compute_jobs (
    operation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    trial_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    input_directory TEXT NOT NULL,
    platform_job_id INTEGER UNIQUE,
    status TEXT NOT NULL,
    receipt_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_compute_run ON compute_jobs(run_id, status);
CREATE TABLE IF NOT EXISTS data_materializations (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    challenge_id TEXT NOT NULL REFERENCES challenges(id),
    resource_key TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    retrieval_ref TEXT,
    expected_hash TEXT,
    hash_semantics TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL,
    store_path TEXT,
    files_json TEXT NOT NULL DEFAULT '[]',
    total_bytes INTEGER,
    error_code TEXT,
    receipt_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_data_materializations_challenge
 ON data_materializations(challenge_id, resource_key);
CREATE TABLE IF NOT EXISTS image_facts (
    image_address TEXT NOT NULL,
    facts_sha256 TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    source_operation_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY(image_address, facts_sha256)
);
CREATE TABLE IF NOT EXISTS curation_requests (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES runs(id),
    status TEXT NOT NULL,
    packet_json TEXT NOT NULL,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# submissions 表 v2 新增列（对既有库做幂等 ALTER）
SUBMISSION_V2_COLUMNS = {
    "platform_ref": "TEXT",  # 平台侧 attempt id 等回执引用
    "request_hash": "TEXT",
    "stage": "TEXT NOT NULL DEFAULT 'legacy'",
    "reservation_released": "INTEGER NOT NULL DEFAULT 0",
    "source_package_sha256": "TEXT",
    "admission_json": "TEXT",
}

# checkpoints 表 v2 新增列（对既有库做幂等 ALTER）
CHECKPOINT_V2_COLUMNS = {
    "receipt_json": "TEXT",
    "checkpoint_key": "TEXT",
    "content_hash": "TEXT",
    "stage": "TEXT",
    "review": "TEXT",
    "source": "TEXT NOT NULL DEFAULT 'user'",
    "research_summary_md": "TEXT",
}

# runs 表 v2 新增列：研究门禁（checkpoint blocking / stop / stalled 用）
RUN_V2_COLUMNS = {
    # open | yielding | waiting_brain | stopped
    "gate": "TEXT NOT NULL DEFAULT 'open'",
    "objective_md": "TEXT",
    "objective_status": "TEXT NOT NULL DEFAULT 'open'",
    "end_reason": "TEXT",
    "pending_action_json": "TEXT",
}

# authorizations 表 v2 新增列：付费算力（Bohrium Job）有界授权
AUTHORIZATION_V2_COLUMNS = {
    "max_jobs": "INTEGER NOT NULL DEFAULT 0",
    "job_limits_json": "TEXT NOT NULL DEFAULT '{}'",
    "allow_data_download": "INTEGER NOT NULL DEFAULT 0",
    "max_trials": "INTEGER",
}

COMPUTE_V2_COLUMNS = {
    "data_refs_json": "TEXT NOT NULL DEFAULT '[]'",
    "purpose": "TEXT NOT NULL DEFAULT 'compute'",
}

# challenges 表 v2 新增列：平台资源清单（数据集/工具/服务），导入时从
# 平台详情 JSON 落库，供大脑 run_start 探查与规划
CHALLENGE_V2_COLUMNS = {
    "resources_json": "TEXT",
    "platform_snapshot_json": "TEXT",
}

_db_lock = threading.RLock()


def _ensure_columns(conn: sqlite3.Connection, table: str,
                    columns: dict[str, str]) -> None:
    existing = {r["name"] for r in
                conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, decl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_db() -> None:
    with _db_lock:
        conn = get_db()
        legacy_columns = {r["name"] for r in conn.execute("PRAGMA table_info(experience_revisions)")}
        if legacy_columns and "parent_revision_id" not in legacy_columns:
            _backup_experience_migration(conn)
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_V2_TABLES)
        conn.executescript(SCHEMA_RELIABILITY)
        _ensure_columns(conn, "checkpoints", CHECKPOINT_V2_COLUMNS)
        _ensure_columns(conn, "runs", RUN_V2_COLUMNS)
        _ensure_columns(conn, "submissions", SUBMISSION_V2_COLUMNS)
        _ensure_columns(conn, "authorizations", AUTHORIZATION_V2_COLUMNS)
        _ensure_columns(conn, "challenges", CHALLENGE_V2_COLUMNS)
        _ensure_columns(conn, "compute_jobs", COMPUTE_V2_COLUMNS)
        _migrate_experience_revisions(conn)
        conn.commit()


def _backup_experience_migration(conn: sqlite3.Connection) -> None:
    """Before any DDL, save committed WAL and editable files, never secrets."""
    import uuid
    import shutil
    backup = config.DATA_DIR / 'migrations' / ('experience-v3-' + uuid.uuid4().hex)
    backup.mkdir(parents=True)
    conn.commit()
    with sqlite3.connect(backup / 'database.sqlite') as saved:
        conn.backup(saved)
    if config.EXPERIENCE_DIR.exists():
        shutil.copytree(config.EXPERIENCE_DIR, backup / 'experience', dirs_exist_ok=True)


def _migrate_experience_revisions(conn: sqlite3.Connection) -> None:
    """Offline startup migration. Keep historical IDs; never invent lost operations."""
    cols = {r['name'] for r in conn.execute('PRAGMA table_info(experience_revisions)')}
    if 'parent_revision_id' not in cols:
        conn.execute('BEGIN IMMEDIATE')
        try:
            conn.execute('ALTER TABLE experience_revisions RENAME TO experience_revisions_legacy')
            table = SCHEMA.split('CREATE TABLE IF NOT EXISTS experience_revisions (', 1)[1].split(');', 1)[0]
            conn.execute('CREATE TABLE experience_revisions (' + table + ')')
            names = ','.join(r['name'] for r in conn.execute('PRAGMA table_info(experience_revisions_legacy)'))
            conn.execute(f'INSERT INTO experience_revisions ({names}) SELECT {names} FROM experience_revisions_legacy')
            conn.execute('DROP TABLE experience_revisions_legacy')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    conn.executescript('''
        CREATE INDEX IF NOT EXISTS idx_rev_exp ON experience_revisions(experience_id, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_revision_operation
          ON experience_revisions(experience_id, operation_id) WHERE operation_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS experience_heads (
          experience_id TEXT PRIMARY KEY, file_path TEXT NOT NULL,
          scope TEXT NOT NULL, challenge_id TEXT,
          head_revision_id TEXT, active_revision_id TEXT, problem TEXT
        );
    ''')

    # Initialize only previously untracked legacy identities. Invalid external edits
    # cannot erase the last registered approved bytes during the first new startup.
    for row in conn.execute("SELECT r.* FROM experience_revisions r WHERE applied=1"
                            " AND rowid=(SELECT MAX(r2.rowid) FROM experience_revisions r2 WHERE r2.experience_id=r.experience_id AND r2.applied=1)"
                            " AND NOT EXISTS(SELECT 1 FROM experience_heads h WHERE h.experience_id=r.experience_id)").fetchall():
        import json
        fm = json.loads(row['frontmatter'])
        active = row['id'] if fm.get('status') == 'active' else None
        conn.execute("INSERT INTO experience_heads(experience_id,file_path,scope,challenge_id,head_revision_id,active_revision_id) VALUES(?,?,?,?,?,?)",
                     (row['experience_id'],row['file_path'],fm['scope'],fm.get('challenge_id'),row['id'],active))


@contextlib.contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """多步写入的唯一事务入口。事务内只允许用 conn 直接执行和
    append_event_tx 等 _tx 变体；禁止调用会自行 commit 的旧 helper。"""
    with _db_lock:
        conn = get_db()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with _db_lock:
        return get_db().execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> None:
    with _db_lock:
        get_db().execute(sql, tuple(params))
        get_db().commit()


def append_event_tx(conn: sqlite3.Connection, run_id: str, source: str,
                    type_: str, payload: dict[str, Any] | None = None,
                    trial_id: str | None = None,
                    raw_ref: str | None = None) -> dict[str, Any]:
    """append_event 的事务内变体：分配 seq 但不 commit。"""
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) + 1 AS next FROM events WHERE run_id=?",
        (run_id,)).fetchone()
    seq = row["next"]
    import uuid
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    now = utcnow()
    conn.execute(
        "INSERT INTO events(event_id, run_id, seq, occurred_at, recorded_at,"
        " source, type, trial_id, payload, raw_ref) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (event_id, run_id, seq, now, now, source, type_, trial_id,
         json.dumps(payload or {}, ensure_ascii=False), raw_ref))
    return {"event_id": event_id, "run_id": run_id, "seq": seq,
            "occurred_at": now, "recorded_at": now, "source": source,
            "type": type_, "trial_id": trial_id,
            "payload": payload or {}, "raw_ref": raw_ref}


def append_event(run_id: str, source: str, type_: str,
                 payload: dict[str, Any] | None = None,
                 trial_id: str | None = None,
                 raw_ref: str | None = None) -> dict[str, Any]:
    """在事务内分配 seq 并追加事件。"""
    with _db_lock:
        conn = get_db()
        result = append_event_tx(conn, run_id, source, type_, payload,
                                 trial_id, raw_ref)
        conn.commit()
        return result


def bump_state_version(run_id: str) -> int:
    with _db_lock:
        conn = get_db()
        conn.execute("UPDATE runs SET state_version = state_version + 1 WHERE id=?",
                     (run_id,))
        conn.commit()
        row = query_one("SELECT state_version FROM runs WHERE id=?", (run_id,))
        return row["state_version"] if row else 0


def events_after(run_id: str, after_seq: int, limit: int = 500) -> list[dict[str, Any]]:
    rows = query("SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
                 (run_id, after_seq, limit))
    return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]


def record_operation(operation_id: str, run_id: str, kind: str, status: str,
                     request_summary: str = "",
                     payload_hash: str = "") -> bool:
    """记录受控操作；重复 operation_id 返回 False（不创建重复外部动作）。"""
    with _db_lock:
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO operations(operation_id, run_id, kind, status,"
                " request_summary, payload_hash, created_at) VALUES(?,?,?,?,?,?,?)",
                (operation_id, run_id, kind, status, request_summary,
                 payload_hash, utcnow()))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def list_challenge_skills(conn: sqlite3.Connection,
                          challenge_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT skill_id FROM challenge_skills WHERE challenge_id=?"
        " ORDER BY skill_id", (challenge_id,)).fetchall()
    return [r["skill_id"] for r in rows]


def bind_challenge_skill(conn: sqlite3.Connection, challenge_id: str,
                         skill_id: str, source: str = "user") -> None:
    """事务内变体：不自行 commit，由调用方事务收尾。"""
    conn.execute(
        "INSERT OR IGNORE INTO challenge_skills(challenge_id, skill_id,"
        " source, created_at) VALUES(?,?,?,?)",
        (challenge_id, skill_id, source, utcnow()))


def unbind_challenge_skill(conn: sqlite3.Connection, challenge_id: str,
                           skill_id: str) -> None:
    """事务内变体：不自行 commit，由调用方事务收尾。"""
    conn.execute(
        "DELETE FROM challenge_skills WHERE challenge_id=? AND skill_id=?",
        (challenge_id, skill_id))
