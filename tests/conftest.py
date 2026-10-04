"""测试共用：每个测试用独立临时工作区（数据目录 + 经验目录）。"""
from __future__ import annotations

import errno
import os
import socket

import pytest
import pytest_asyncio

from cyberscientist import config, db


def _use_write_for_sandboxed_asyncio_wakeup() -> None:
    """Some sandboxes deny send(2) on a socketpair but permit write(2).

    asyncio's cross-thread wakeup uses send(2); if denied, to_thread completes
    but asyncio.run hangs while shutting down its default executor. Keep this
    equivalent workaround in the test process only.
    """
    try:
        reader, writer = socket.socketpair()
        try:
            try:
                writer.send(b"\0")
                return
            except OSError as exc:
                if exc.errno != errno.EPERM:
                    return
            try:
                os.write(writer.fileno(), b"\0")
            except OSError:
                return
        finally:
            reader.close()
            writer.close()
    except OSError:
        return
    from asyncio import selector_events

    def write_to_self(loop):
        sock = loop._csock
        if sock is not None:
            try:
                os.write(sock.fileno(), b"\0")
            except OSError:
                pass

    selector_events.BaseSelectorEventLoop._write_to_self = write_to_self


_use_write_for_sandboxed_asyncio_wakeup()


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    from cyberscientist import backend_identity
    monkeypatch.setattr(backend_identity, '_loaded', None)
    data = tmp_path / ".cyberscientist"
    ws = tmp_path / "workspace"
    exp = tmp_path / "experience"
    for d in (data, ws, exp / "global"):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "DB_PATH", data / "test.db")
    monkeypatch.setattr(config, "SECRETS_PATH", data / "secrets.json")
    monkeypatch.setattr(config, "SETTINGS_PATH", data / "settings.json")
    monkeypatch.setattr(config, "LOCK_PATH", data / "controller.lock")
    monkeypatch.setattr(config, "WORKSPACE_DIR", ws)
    monkeypatch.setattr(config, "EXPERIENCE_DIR", exp)
    # Backend-only dotenv is outside test data; tests cannot use its real key.
    monkeypatch.setattr(config, 'deepseek_key', lambda: None)
    # A connected ledger fixture is not permission to call the developer's
    # installed native model. Protocol tests use explicit temp fake binaries.
    from pathlib import Path
    from cyberscientist.jsonrpc_stdio import JsonRpcStdio
    original_start = JsonRpcStdio.start
    async def fixture_process_only(rpc):
        executable = Path(rpc.argv[0]).resolve()
        if any(mode in rpc.argv for mode in ('app-server', 'acp')) and not executable.is_relative_to(tmp_path):
            raise RuntimeError('应用单元测试使用协议 fake，不调用已安装原生模型')
        await original_start(rpc)
    monkeypatch.setattr(JsonRpcStdio, 'start', fixture_process_only)
    # 断开可能存在的旧连接
    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn


    db.init_db()
    yield
    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn


@pytest_asyncio.fixture(autouse=True)
async def drain_run_maintenance(isolated_workspace):
    """Independent model workers must not outlive their test database."""
    yield
    import asyncio
    from cyberscientist import maintenance, auto_harvest
    db.execute("INSERT OR REPLACE INTO system_state(key,value) VALUES('shutdown_requested','1')")
    await auto_harvest.drain()
    while pending := [task for task in maintenance.ACTIVE_TASKS if not task.done()]:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
