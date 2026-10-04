"""Atomic global admission over the existing local resource ledgers."""
from __future__ import annotations

import asyncio
import json
from collections import Counter

_auxiliary_tasks: dict[str, asyncio.Task] = {}
from . import config, db


class ResourceWait(ValueError):
    code = 'RESOURCE_WAIT'


def provider(choice: dict) -> str:
    return choice.get('provider') or choice.get('runtime', 'codex')


def reserve_sessions_tx(conn, owner: str, choices: dict) -> None:
    barrier = conn.execute("SELECT value FROM system_state WHERE key='shutdown_requested'").fetchone()
    if barrier and barrier['value'] == '1':
        raise ResourceWait('安全关机已关闭新会话，等待启动对账')
    limits = config.load_settings().get('resources', {}).get('provider_sessions', {})
    wanted = {role: provider(choice) for role, choice in choices.items()}
    for name in set(wanted.values()):
        backoff = conn.execute('SELECT retry_at FROM model_provider_backoff WHERE provider=?', (name,)).fetchone()
        if backoff and backoff['retry_at'] > db.utcnow():
            raise ResourceWait(f'{name} 限速退避至 {backoff["retry_at"]}')
    existing = {r['role']: r['provider'] for r in conn.execute(
        'SELECT role,provider FROM model_session_leases WHERE owner=?', (owner,))}
    needed = Counter(p for role, p in wanted.items() if role not in existing)
    for name, count in needed.items():
        limit = limits.get(name, 10)
        used = conn.execute('SELECT COUNT(*) FROM model_session_leases WHERE provider=?',
                            (name,)).fetchone()[0]
        if type(limit) is not int or limit < 1:
            raise ValueError('提供方并发上限必须是正整数')
        if used + count > limit:
            raise ResourceWait(f'{name} 会话已占用 {used}/{limit}，等待释放')
    for role, name in wanted.items():
        if role in existing and existing[role] != name:
            raise ValueError('会话租约不能切换提供方')
        conn.execute('INSERT OR IGNORE INTO model_session_leases VALUES(?,?,?,?)',
                     (owner, role, name, db.utcnow()))


def release_sessions(owner: str) -> None:
    _auxiliary_tasks.pop(owner, None)
    db.execute('DELETE FROM model_session_leases WHERE owner=?', (owner,))


def reserve_auxiliary(owner: str, settings: dict, role: str = 'brain') -> None:
    from . import power
    if power.shutdown_requested():
        raise ResourceWait('安全关机已关闭新会话，等待启动对账')
    if settings['app']['mode'] == 'connected':
        with db.transaction() as conn:
            reserve_sessions_tx(conn, owner, {role: settings[role]})
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    if task is not None:
        _auxiliary_tasks[owner] = task


def auxiliary_tasks() -> list[asyncio.Task]:
    return [task for task in set(_auxiliary_tasks.values()) if not task.done()]


def register_auxiliary(owner: str, task: asyncio.Task) -> None:
    _auxiliary_tasks[owner] = task


def throttle(name: str, retry_at: str) -> None:
    db.execute('INSERT INTO model_provider_backoff(provider,retry_at,first_at) VALUES(?,?,?)'
               ' ON CONFLICT(provider) DO UPDATE SET retry_at=MAX(retry_at,excluded.retry_at)',
               (name, retry_at, db.utcnow()))


def require_compute_slot_tx(conn, kind: str) -> None:
    settings = config.load_settings().get('resources', {})
    limit = settings.get('max_concurrent_jobs' if kind == 'job' else 'max_concurrent_sandboxes')
    if limit is None:
        return
    if type(limit) is not int or limit < 1:
        raise ValueError('全局算力并发上限必须是正整数或 null')
    if kind == 'job':
        from .compute import occupies_slot
        used = sum(occupies_slot(row) for row in conn.execute('SELECT * FROM compute_jobs').fetchall())
    else:
        used = conn.execute("SELECT COUNT(*) FROM compute_sandboxes WHERE status NOT IN"
                            " ('deleted','failed')").fetchone()[0]
    if used >= limit:
        from .compute import ComputeError
        raise ComputeError('GLOBAL_CONCURRENCY_LIMIT', f'全局 {kind} 并发 {used}/{limit}')


def status() -> dict:
    return {'limits': config.load_settings().get('resources', {}),
            'sessions': [dict(r) for r in db.query('SELECT provider,COUNT(*) AS used'
                                                ' FROM model_session_leases GROUP BY provider')],
            'rate_limits': [dict(r) for r in db.query('SELECT * FROM model_rate_limits')]}


def close_failed(owner: str, exc: BaseException) -> None:
    db.execute('INSERT OR REPLACE INTO system_state(key,value) VALUES(?,?)',
               ('native_close_unknown:' + owner, json.dumps({'owner': owner, 'error': type(exc).__name__})))


def close_unknowns() -> list[dict]:
    return [json.loads(row['value']) for row in db.query("SELECT value FROM system_state WHERE key LIKE 'native_close_unknown:%'")]
