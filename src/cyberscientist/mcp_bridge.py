"""MCP 桥：以 stdio MCP server 形态注入执行器会话（ACP session/new mcpServers）。

只转发到本机后端的受限业务入口（/api/v1/tools/*），携带后端签发的
短时能力令牌（CS_TOOL_TOKEN，经进程环境传入，不进提示词/URL/事件/Git）。
不直接写数据库。协议为 MCP stdio（换行分帧 JSON-RPC 2.0）。

运行方式：python -m cyberscientist.mcp_bridge
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

_TOOLS = [
    {
        "name": "research_checkpoint",
        "description": "在自然研究节点登记检查点：事实/解释/异常/问题/下一步/"
                       "恢复信息。review=none 继续工作；async 请大脑异步审阅；"
                       "blocking 交棒等待大脑（保存状态并结束当前 turn）。"
                       "返回可能携带排队的大脑指导。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "experience_uses": {'type': 'array', 'maxItems': 32, 'items': {'type': 'object', 'additionalProperties': False, 'properties': {'context_id': {'type': 'string', 'minLength': 1}, 'experience_id': {'type': 'string', 'minLength': 1}, 'revision_id': {'type': 'string', 'minLength': 1}}, 'required': ['context_id', 'experience_id', 'revision_id']}},
                "checkpoint_key": {"type": "string", "maxLength": 128},
                "review": {"enum": ["none", "async", "blocking"]},
                "stage": {"enum": ["progress", "blocked", "trial_complete"]},
                "report_md": {"type": "string", "maxLength": 12000},
                "evidence_refs": {"type": "array",
                                  "items": {"type": "string", "maxLength": 256},
                                  "maxItems": 32},
            },
            "required": ["checkpoint_key", "review", "stage", "report_md",
                         "evidence_refs"],
        },
    },
    {
        "name": "ack_guidance",
        "description": "确认已投递的大脑指导：accepted 或 challenged 并给依据。"
                       "重复 ID 幂等；ACK 不代表已完成指导。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "guidance_id": {"type": "string", "maxLength": 128},
                "disposition": {"enum": ["accepted", "challenged"]},
                "reason_md": {"type": "string", "maxLength": 2000},
            },
            "required": ["guidance_id", "disposition", "reason_md"],
        },
    },
]

_TOOLS.append({
    "name": "research_job",
    "description": "本 Run 的受控 Bohrium Job：创建前原子预留额度；相同 operation_id 幂等，unknown 先 reconcile 不重建。暂停后只读/停止，禁止新增计算。",
    "inputSchema": {"type": "object", "additionalProperties": False,
        "properties": {"action": {"enum": ["submit", "list", "reconcile", "stop"]},
                       "operation_id": {"type": "string", "maxLength": 100},
                       "spec": {"type": "object"}, "input_directory": {"type": "string"}},
        "required": ["action"]}})


def _post(path: str, payload: dict) -> dict:
    url = os.environ.get("CS_API_URL", "http://127.0.0.1:8765") + path
    token = os.environ.get("CS_TOOL_TOKEN", "")
    # 执行器报告可能含孤代理字符（读取二进制日志带进的 \udcXX）：
    # 严格 UTF-8 编码会直接抛异常杀死桥进程，替换为 U+FFFD 保住通道
    body = json.dumps(payload, ensure_ascii=False).encode(
        "utf-8", errors="replace")
    last_err: Exception | None = None
    # 瞬时挂起自愈：短超时 + 一次重试，整体 <25s 低于常见 MCP 客户端超时
    for attempt in (1, 2):
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            return {"error": f"HTTP {exc.code}: {detail}"}  # 协议错误不重试
        except OSError as exc:
            last_err = exc
            if attempt == 1:
                time.sleep(1)
    return {"error": f"后端不可达: {last_err}"}


def _tool_result(payload: dict) -> dict:
    is_error = "error" in payload or payload.get("ok") is False or payload.get("status") in ("unknown", "not_started")
    return {"content": [{"type": "text",
                         "text": json.dumps(payload, ensure_ascii=False)}],
            "isError": is_error}


def _handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": msg.get("params", {}).get(
                "protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "cyberscientist-collab", "version": "0.2.0"}}}
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": _TOOLS}}
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "research_checkpoint":
            out = _post("/api/v1/tools/checkpoint", args)
        elif name == "research_job":
            if args.get("action") in ("submit", "stop") and not args.get("operation_id"):
                out = {"error": "submit/stop 需要稳定的 operation_id"}
            else:
                out = _post("/api/v1/tools/job", args)
        elif name == "ack_guidance":
            out = _post("/api/v1/tools/ack", args)
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {
                "code": -32602, "message": f"unknown tool: {name}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": _tool_result(out)}
    if mid is not None:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"unsupported: {method}"}}
    return None


def main() -> None:
    # MCP stdio 协议是 UTF-8；Windows 默认 GBK 会让协议里的非 GBK 字符
    # 在读/写时炸掉桥进程（与孤代理崩溃同族），统一显式声明
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            # 非对象 JSON（null/数组/标量）不是合法 JSON-RPC 请求：
            # 回标准错误响应而不是让 msg.get 抛 AttributeError 杀死桥进程
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32600,
                           "message": "invalid request: expected JSON-RPC object"}},
                ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue
        try:
            resp = _handle(msg)
        except Exception as exc:  # noqa: BLE001 — 桥进程永远不能死：
            # 任何未料异常都以 JSON-RPC 错误返回，避免 -32000 Connection closed
            resp = {"jsonrpc": "2.0", "id": msg.get("id"),
                    "error": {"code": -32603,
                              "message": f"bridge internal: {exc!r}"[:300]}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
