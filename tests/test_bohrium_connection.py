"""Bohrium 连接探针：真实 CLI 命令、配置凭据隔离与异步 HTTP 行为。"""
import asyncio
import json
import subprocess
import threading

from httpx import ASGITransport, AsyncClient

from cyberscientist import config
from cyberscientist.api import create_app


def configure(tmp_path):
    executable = tmp_path / "bohr"
    executable.write_text("fixture executable")
    settings = config.load_settings()
    settings["bohrium"].update({
        "executable": str(executable),
        "access_key_secret_ref": "local:bohrium_test",
        "project_id": 88474,
        "host_overrides": {"OPENAPI_HOST": "https://bohrium.invalid", "PATH": "ignored"},
    })
    config.save_settings(settings)
    config.update_secret("bohrium_test", "fixture-backend-secret")
    return executable


async def test_bohrium_probe_uses_configured_secret_and_read_only_commands(tmp_path, monkeypatch):
    executable = configure(tmp_path)
    monkeypatch.setenv("BOHR_ACCESS_KEY", "old-environment-secret")
    monkeypatch.setenv("ACCESS_KEY", "old-legacy-secret")
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        output = "1.1.0\n" if cmd[1:] == ["version"] else json.dumps([
            {"name": "Project", "projectId": 88474}])
        return subprocess.CompletedProcess(cmd, 0, output,
                                           "https://host.invalid?accessKey=fixture-backend-secret")

    monkeypatch.setattr(subprocess, "run", run)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as client:
        response = await client.post("/api/v1/connections/bohrium/test", json={})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ok"
    assert result["health"]["authenticated"] is True
    assert result["health"]["version"] == "1.1.0"
    assert [cmd for cmd, _ in calls] == [[str(executable), "version"],
                                       [str(executable), "project", "list", "--json"]]
    for cmd, kwargs in calls:
        assert kwargs["env"]["BOHR_ACCESS_KEY"] == "fixture-backend-secret"
        assert kwargs["env"]["ACCESS_KEY"] == "fixture-backend-secret"
        assert kwargs["env"]["OPENAPI_HOST"] == "https://bohrium.invalid"
        assert kwargs["env"]["PATH"] != "ignored"
        assert "fixture-backend-secret" not in " ".join(cmd)
    assert "fixture-backend-secret" not in response.text


async def test_bohrium_probe_failure_never_echoes_cli_credentials(tmp_path, monkeypatch):
    configure(tmp_path)
    error = "Get https://host.invalid?accessKey=fixture-backend-secret: network unavailable"

    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, error, error)

    monkeypatch.setattr(subprocess, "run", run)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as client:
        response = await client.post("/api/v1/connections/bohrium/test", json={})
    assert response.json()["health"]["authenticated"] is None
    assert response.json()["health"]["version"] is None
    assert response.json()["status"] == "unavailable"
    assert "fixture-backend-secret" not in response.text
    assert "login" not in response.text


async def test_bohrium_probe_does_not_block_frontend_requests(tmp_path, monkeypatch):
    configure(tmp_path)
    started = threading.Event()
    release = threading.Event()

    def run(cmd, **kwargs):
        if cmd[1:] == ["version"]:
            started.set()
            release.wait(timeout=3)
            return subprocess.CompletedProcess(cmd, 0, "1.1.0", "")
        return subprocess.CompletedProcess(cmd, 0, "[]", "")

    monkeypatch.setattr(subprocess, "run", run)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as client:
        probe = asyncio.create_task(client.post("/api/v1/connections/bohrium/test", json={}))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            response = await asyncio.wait_for(client.get("/api/v1/settings"), timeout=1)
            assert response.status_code == 200
            assert not probe.done()
        finally:
            release.set()
            await probe
