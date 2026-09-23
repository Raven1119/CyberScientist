"""Environment regressions use fake credentials and no model requests."""
import asyncio
import json
import os
import subprocess
import sys

import pytest

from cyberscientist.brains.codex import CodexBrain
from cyberscientist.codex_protocol import native_brain_environment, thread_params


NATIVE_ENV = {
    "HOME": "/native-home",
    "CODEX_HOME": "/native-home/custom-codex",
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "HTTPS_PROXY": "http://proxy.invalid:8080",
    "SSL_CERT_FILE": "/native-home/ca.pem",
    "OPENAI_API_KEY": "fixture-openai-auth",
    "CODEX_API_KEY": "fixture-codex-auth",
    "CODEX_ACCESS_TOKEN": "fixture-codex-token",
}
BUSINESS_ENV = {
    "BOHR_ACCESS_KEY": "fixture-bohr",
    "ACCESS_KEY": "fixture-access",
    "BOHR_PROJECT_ID": "fixture-project",
    "PLAYGROUND_USER_TOKEN": "fixture-playground",
    "CS_TOOL_TOKEN": "fixture-capability",
    "CS_BACKEND_SECRET": "fixture-backend",
    "ANTHROPIC_API_KEY": "fixture-anthropic",
    "KIMI_API_KEY": "fixture-kimi",
    "MOONSHOT_API_KEY": "fixture-moonshot",
    "GOOGLE_API_KEY": "fixture-google",
    "GEMINI_API_KEY": "fixture-gemini",
    "UNRELATED_SECRET": "fixture-unrelated",
}


def test_whitelist_retains_native_auth_but_excludes_backend_credentials():
    source = {**NATIVE_ENV, **BUSINESS_ENV}
    assert native_brain_environment(source) == NATIVE_ENV
    assert source == {**NATIVE_ENV, **BUSINESS_ENV}


def test_empty_environment_does_not_fall_back_to_parent(monkeypatch):
    monkeypatch.setenv("BOHR_ACCESS_KEY", "fixture-parent-bohr")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-parent-openai")
    assert native_brain_environment({}) == {}


def test_filtered_child_process_does_not_inherit_parent_business_keys(monkeypatch):
    # Check the actual OS subprocess boundary, printing names only.
    for key, value in BUSINESS_ENV.items():
        monkeypatch.setenv(key, value)
    env = native_brain_environment({**NATIVE_ENV, **BUSINESS_ENV})
    result = subprocess.run(
        [sys.executable, "-c", "import json, os; print(json.dumps(sorted(os.environ)))"],
        env=env, check=True, capture_output=True, text=True, timeout=10,
    )
    child_names = set(json.loads(result.stdout))
    assert set(NATIVE_ENV) <= child_names
    assert not set(BUSINESS_ENV) & child_names


@pytest.mark.parametrize("entrypoint", ["open", "inspect"])
@pytest.mark.parametrize("parent_env", [{}, {**NATIVE_ENV, **BUSINESS_ENV}])
async def test_both_brain_entrypoints_supply_explicit_filtered_environment(
    monkeypatch, tmp_path, entrypoint, parent_env,
):
    captured = []

    class CaptureRpc:
        def __init__(self, argv, **kwargs):
            self.argv = argv
            self.kwargs = kwargs
            captured.append(self)

        async def start(self):
            pass

        async def stop(self):
            pass

        async def notify(self, method, params=None):
            assert method == "initialized"

        async def request(self, method, params=None, **kwargs):
            if method == "initialize":
                return {"userAgent": "codex/0.155.1 fixture"}
            assert method == "thread/start"
            return {"thread": {"id": "fixture-thread"}, "model": params["model"],
                    "reasoningEffort": params["config"]["model_reasoning_effort"]}

        async def server_requests(self):
            await asyncio.Future()
            yield  # pragma: no cover

    monkeypatch.setattr(os, "environ", dict(parent_env))
    monkeypatch.setattr("cyberscientist.brains.codex.JsonRpcStdio", CaptureRpc)
    brain = CodexBrain(sys.executable, "gpt-6-astra", "xhigh")
    if entrypoint == "inspect":
        health = await brain.inspect()
        assert health.installed and health.version == "0.155.1"
    else:
        # A caller's executor environment must not widen a brain's environment.
        session = await brain.open({"working_directory": str(tmp_path),
                                    "env": BUSINESS_ENV})
        await brain.close(session)
    assert len(captured) == 1
    assert captured[0].kwargs["env"] == (NATIVE_ENV if parent_env else {})
    assert all(value not in repr(captured[0].argv) for value in BUSINESS_ENV.values())


def test_brain_native_shell_policy_excludes_auth_and_keeps_read_only_sandbox():
    params = thread_params(
        {"env": {**NATIVE_ENV, **BUSINESS_ENV}, "network_access": True,
         "writable_roots": ["/unsafe-root"]}, "gpt-6-astra", "xhigh", writable=False,
    )
    cfg = params["config"]
    allowed = set(cfg["shell_environment_policy.include_only"])
    assert {"HOME", "CODEX_HOME", "PATH", "LANG"} <= allowed
    assert not {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"} & allowed
    assert not set(BUSINESS_ENV) & allowed
    assert cfg["shell_environment_policy.ignore_default_excludes"] is False
    assert params["sandbox"] == "read-only"
    assert params["approvalPolicy"] == "never"
    assert "sandbox_workspace_write.network_access" not in cfg
    assert "sandbox_workspace_write.writable_roots" not in cfg
    assert not any(value in json.dumps(params) for value in BUSINESS_ENV.values())
