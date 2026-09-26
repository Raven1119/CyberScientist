"""测试共用：每个测试用独立临时工作区（数据目录 + 经验目录）。"""
from __future__ import annotations

import errno
import os
import socket

import pytest

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
    # 断开可能存在的旧连接
    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn
    db.init_db()
    yield
    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn
