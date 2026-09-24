"""Shared native app-server protocol, verified against Linux CLI 0.155.1.

Thread configuration travels over stdio, never through command arguments or a
global config file. Model/effort requests are not silently downgraded.
"""
from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Mapping

from .jsonrpc_stdio import JsonRpcStdio

CLIENT_INFO = {"name": "cyberscientist", "version": "0.1.0"}
COLLAB_TOOLS = ("research_checkpoint", "ack_guidance", "research_job")
BRAIN_TOOLS = ("research_trace",)


# Native authentication stays in Codex's own HOME/CODEX_HOME. This allowlist
# excludes backend business credentials and unrelated provider API keys.
NATIVE_BRAIN_AUTH_ENV_KEYS = ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")
NATIVE_BRAIN_SHELL_ENV_KEYS = (
    "HOME", "CODEX_HOME", "PATH", "USER", "LOGNAME", "SHELL",
    "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TZ",
    "TMPDIR", "TMP", "TEMP", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
    "XDG_DATA_HOME", "XDG_RUNTIME_DIR", "HTTP_PROXY", "HTTPS_PROXY",
    "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy",
    "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)
NATIVE_BRAIN_ENV_KEYS = NATIVE_BRAIN_SHELL_ENV_KEYS + NATIVE_BRAIN_AUTH_ENV_KEYS


def native_brain_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Explicit process environment; this does not isolate readable auth files."""
    values = os.environ if source is None else source
    return {key: values[key] for key in NATIVE_BRAIN_ENV_KEYS if key in values}


async def initialize(rpc: JsonRpcStdio) -> dict[str, Any]:
    result = await rpc.request(
        "initialize", {"clientInfo": CLIENT_INFO, "capabilities": {}}, timeout=30)
    await rpc.notify("initialized")
    return result


def thread_params(spec: dict[str, Any], model: str | None,
                  effort: str | None, *, writable: bool) -> dict[str, Any]:
    params: dict[str, Any] = {
        "approvalPolicy": "never",
        "sandbox": "workspace-write" if writable else "read-only",
    }
    if spec.get("working_directory"):
        params["cwd"] = spec["working_directory"]
    if model:
        params["model"] = model
    # Research sessions use their explicit MCP bridge and native tools. Loading
    # unrelated account apps adds external authority and can delay MCP startup.
    cfg: dict[str, Any] = {
        "features.apps": False,
        "features.memories": False,
        "memories.use_memories": False,
        "memories.generate_memories": False,
    }
    if effort:
        cfg["model_reasoning_effort"] = effort
    if not writable:
        # Tool shells receive only the non-authentication subset. Values are
        # never copied into thread config, prompts or protocol metadata.
        cfg["shell_environment_policy.include_only"] = list(NATIVE_BRAIN_SHELL_ENV_KEYS)
        cfg["shell_environment_policy.ignore_default_excludes"] = False
    if writable and spec.get("network_access") is True:
        cfg["sandbox_workspace_write.network_access"] = True
    if writable and spec.get("writable_roots"):
        cfg["sandbox_workspace_write.writable_roots"] = list(spec["writable_roots"])
    if writable and spec.get("env"):
        # Values stay in the subprocess environment; this only allows known
        # Run capability names through Codex's otherwise secret-filtering policy.
        cfg["shell_environment_policy.include_only"] = list(spec["env"])
        cfg["shell_environment_policy.ignore_default_excludes"] = True
    if spec.get("instructions"):
        params["developerInstructions"] = spec["instructions"]
    # Same session-level spec as ACP, translated to native Codex config. The
    # short-lived Run capability is shared by this MCP child and the Run CLI, not its prompt.
    for server in spec.get("mcp_servers") or []:
        env = server.get("env") or {}
        if isinstance(env, list):
            env = {item["name"]: item["value"] for item in env}
        cfg.setdefault("mcp_servers", {})[server["name"]] = {
            "command": server["command"], "args": server.get("args", []),
            "env_vars": list(env), "enabled": True, "required": True,
        }
        if server["name"] == "cyberscientist":
            # Only the controller's capability-scoped bridge is pre-authorized.
            # New/future tools stay unavailable until explicitly integrated.
            allowed_tools = COLLAB_TOOLS if writable else BRAIN_TOOLS
            cfg["mcp_servers"][server["name"]].update({
                "enabled_tools": list(allowed_tools),
                "tools": {name: {"approval_mode": "approve"}
                          for name in allowed_tools},
            })
    if cfg:
        params["config"] = cfg
    return params


def process_environment(spec: dict[str, Any]) -> dict[str, str] | None:
    """Keep MCP capabilities in the process environment, never saved config."""
    if not spec.get("mcp_servers"):
        return spec.get("env")
    env = dict(spec.get("env") or os.environ)
    for server in spec["mcp_servers"]:
        values = server.get("env") or {}
        if isinstance(values, list):
            values = {item["name"]: item["value"] for item in values}
        env.update(values)
    return env


def verify_thread_config(result: dict[str, Any], model: str | None,
                         effort: str | None) -> None:
    if model and result.get("model") != model:
        raise RuntimeError("Codex 未确认所请求的模型，拒绝静默降级")
    if effort and result.get("reasoningEffort") != effort:
        raise RuntimeError("Codex 未确认所请求的思考强度，拒绝静默降级")


async def deny_requests(
    rpc: JsonRpcStdio, report: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Consume requests during the turn so approvals cannot deadlock it."""
    async for request in rpc.server_requests():
        method = request.get("method", "")
        if method in ("item/commandExecution/requestApproval",
                      "item/fileChange/requestApproval"):
            await rpc.respond(request["id"], result={"decision": "decline"})
        elif method == "item/permissions/requestApproval":
            await rpc.respond(request["id"], result={"permissions": {}, "scope": "turn"})
        else:
            await rpc.respond(request["id"], error={
                "code": -32601, "message": "unsupported by cyberscientist policy"})
        await report({"method": method,
                      "detail": "该原生请求未获工作台授权，已拒绝；未扩大权限"})
