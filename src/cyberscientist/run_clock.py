"""Persisted active time; remote resource lifetimes remain wall-clock time."""
from __future__ import annotations
import time
from datetime import datetime
from . import db

MAX_HEARTBEAT_GAP = 45


def elapsed(run, now: float | None = None) -> float:
    now = time.time() if now is None else now
    if not run['clock_version']:
        return max(0, now - datetime.fromisoformat(run['started_at']).timestamp()) if run['started_at'] else 0
    saved = float(run['active_elapsed_seconds'])
    since = run['clock_active_since']
    heartbeat = run['clock_heartbeat_at']
    if since is not None and heartbeat is not None:
        # An unobserved interval is unknown/offline, never charged as active time.
        end = now if 0 <= now - heartbeat <= MAX_HEARTBEAT_GAP else heartbeat
        saved += max(0, end - since)
    return saved


def remaining(run, auth, now: float | None = None) -> float:
    return auth['max_run_minutes'] * 60 - elapsed(run, now)


def start(run_id: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        accumulated = elapsed(row, now)
        conn.execute('UPDATE runs SET clock_version=1,active_elapsed_seconds=?,clock_active_since=?,clock_heartbeat_at=?,resume_on_startup=1 WHERE id=?',
                     (accumulated, now, now, run_id))


def freeze(run_id: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        if row and row['clock_version']:
            conn.execute('UPDATE runs SET active_elapsed_seconds=?,clock_active_since=NULL,clock_heartbeat_at=? WHERE id=?',
                         (elapsed(row, now), now, run_id))


def heartbeat(now: float | None = None) -> None:
    now = time.time() if now is None else now
    with db.transaction() as conn:
        for row in conn.execute('SELECT * FROM runs WHERE clock_version=1 AND clock_active_since IS NOT NULL').fetchall():
            gap = now - row['clock_heartbeat_at']
            active = row['phase'] in ('running', 'pausing')
            if gap > MAX_HEARTBEAT_GAP:
                db.append_event_tx(conn, row['id'], 'controller', 'run.offline_gap',
                                   {'seconds': gap, 'charged': False, 'remote_costs_continue': True})
            conn.execute('UPDATE runs SET active_elapsed_seconds=?,clock_active_since=?,clock_heartbeat_at=? WHERE id=?',
                         (elapsed(row, now), now if active else None, now, row['id']))
