"""测试共用：每个测试用独立临时工作区（数据目录 + 经验目录）。"""
from __future__ import annotations

import pytest

from cyberscientist import config, db


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
