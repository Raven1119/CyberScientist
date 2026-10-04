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
                       "返回可能携带排队的大脑指导或系统修复反馈。",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "experience_uses": {'type': 'array', 'maxItems': 32, 'items': {'type': 'object', 'additionalProperties': False, 'properties': {'context_id': {'type': 'string', 'minLength': 1}, 'experience_id': {'type': 'string', 'minLength': 1}, 'revision_id': {'type': 'string', 'minLength': 1}}, 'required': ['context_id', 'experience_id', 'revision_id']}},
                "checkpoint_key": {"type": "string", "maxLength": 128},
                "review": {"enum": ["none", "async", "blocking"]},
                "stage": {"enum": ["progress", "blocked", "trial_complete"]},
                "report_md": {"type": "string", "maxLength": 12000},
                "research_summary_md": {"type": "string", "minLength": 1, "maxLength": 1600,
                                        "description": "可选研究状态摘要（结果/失败/未知与下一问题）；仅是执行器解释，不等于验证"},
                "research_question": {"type": "object", "description": "可选研究问题；选项仅供参考，审阅异步进行"},
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
        "description": "确认已投递的指导或系统修复反馈：accepted 或 challenged 并给依据。"
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
                       "spec": {"type": "object"}, "input_directory": {"type": "string"},
                       "preflight": {"type": "object"}},
        "required": ["action"]}})

_TOOLS.append({
    "name": "research_sandbox",
    "description": "本 Run 的受控 Bohrium 沙箱：有界创建、执行、文件传输、查询与删除；create/exec/files.write 需稳定 operation_id，结果未知时先对账不重发。",
    "inputSchema": {"type": "object", "additionalProperties": False,
        "properties": {"action": {"enum": ["create", "reconcile", "exec", "files.read",
                                            "files.write", "delete", "list", "describe",
                                            "quota", "machine.list", "template.list"]},
                       "operation_id": {"type": "string", "maxLength": 100},
                       "sandbox_id": {"type": "string"},
                       "request": {"type": "object"},
                       "command": {"type": "string"},
                       "timeout": {"type": "integer"},
                       "remote_path": {"type": "string"},
                       "local_path": {"type": "string"},
                       "content": {"type": "string"}},
        "required": ["action"]}})

_TOOLS.append({
    "name": "research_package_check",
    "description": "只读检查当前 Trial 的 ARM 封存包，返回六项轨迹准入信号与封存哈希；不提交。",
    "inputSchema": {"type": "object", "additionalProperties": False,
        "properties": {"package_path": {"type": "string"},
                       "trial_id": {"type": "string"}},
        "required": []}})

_NARRATIVE_TOOL = {
    "name": "research_trace_narrative_check",
    "description": "只读校验当前 Trial 的 trace_narrative.jsonl 引用、合并轨迹与本地准入；不封存或提交。",
    "inputSchema": {"type": "object", "additionalProperties": False,
        "properties": {"package_path": {"type": "string"},
                       "trial_id": {"type": "string"}},
        "required": []}}
_TOOLS.append(_NARRATIVE_TOOL)

_TOOLS.append({
    "name": "research_local_score",
    "description": "本地评分：evaluate 系统执行；prepare 返回固定哈希输入与可信评分命令，执行器自行准备环境、传输并用 research_sandbox exec 执行；register 按 execution_operation_id 核对通道回执登记正式分。prepare_job 在 Job 中执行同样固定评分命令，register_job 由后端下载核验；不得修改评分器；不提交。",
    "inputSchema": {"type": "object", "additionalProperties": False,
        "properties": {"action": {"enum": ["evaluate", "prepare", "register", "prepare_job", "register_job"]},
                       "trial_id": {"type": "string"},
                       "sandbox_id": {"type": "string"},
                       "operation_id": {"type": "string"},
                       "package_path": {"type": "string"},
                       "execution_operation_id": {"type": "string"},
                       "environment_paths": {"type": "object"}},
        "required": ["trial_id", "operation_id"]}})

_DATA_TOOL = {
    "name": "research_data",
    "description": "查询或按本 Run 独立授权物化题目公开数据。request 需要 operation_id。",
    "inputSchema": {"type": "object", "additionalProperties": False,
        "properties": {"action": {"enum": ["list", "status", "request"]},
                       "resource_key": {"type": "string"},
                       "operation_id": {"type": "string"}},
        "required": ["action"]}}
_TOOLS.append(_DATA_TOOL)

_FACTS_TOOL = {
    'name': 'research_operating_facts',
    'description': '只读查询原授权剩余时间、Job/沙箱额度、CPU价格、费用估算、环境和评分耗时事实；不创建资源。',
    'inputSchema': {'type': 'object', 'additionalProperties': False, 'properties': {}}}
_TOOLS.append(_FACTS_TOOL)
_TOOLS.append({'name': 'research_environment', 'description': '在环境保存数量授权内构建私有公开软件镜像；固定配方和冒烟命令入账；unknown 不重发。list/reconcile 只读。',
    'inputSchema': {'type': 'object', 'additionalProperties': False, 'properties': {
        'action': {'enum': ['save', 'list', 'reconcile']}, 'operation_id': {'type': 'string'},
        'dockerfile': {'type': 'string'}, 'recipe': {'type': 'string'}, 'smoke_command': {'type': 'string'}}, 'required': ['action']}})

_TRACE_TOOL = {
    "name": "research_trace",
    "description": "仅大脑可用：按需 list/read 当前审阅截止前的公开研究记录；不会自动读取。",
    "inputSchema": {"type": "object", "additionalProperties": False,
        "properties": {"action": {"enum": ["list", "read"]},
                       "ref": {"type": "string", "maxLength": 256},
                       "cursor": {"type": "integer", "minimum": 0},
                       "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                       "offset": {"type": "integer", "minimum": 0},
                       "keyword": {"type": "string", "maxLength": 100},
                       "event_type": {"type": "string", "maxLength": 100}},
        "required": ["action"]}}

_SCORES_TOOL = {
    "name": "platform_scores",
    "description": "仅大脑可用：只读查询本题公开尝试的匿名分数分布，供分诊参考；不能把分布当优化目标。",
    "inputSchema": {"type": "object", "additionalProperties": False,
                    "properties": {}, "required": []}}


def _post(path: str, payload: dict, *, timeout: int = 10,
          retry_transient: bool = True) -> dict:
    url = os.environ.get("CS_API_URL", "http://127.0.0.1:8765") + path
    token = os.environ.get("CS_TOOL_TOKEN", "")
    # 执行器报告可能含孤代理字符（读取二进制日志带进的 \udcXX）：
    # 严格 UTF-8 编码会直接抛异常杀死桥进程，替换为 U+FFFD 保住通道
    body = json.dumps(payload, ensure_ascii=False).encode(
        "utf-8", errors="replace")
    last_err: Exception | None = None
    # Mutating/long-running calls must not be repeated after a client timeout:
    # the first request may still be executing in the backend.
    attempts = 2 if retry_transient else 1
    for attempt in range(attempts):
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read(48000).decode("utf-8", errors="replace")
            try:
                structured = json.loads(detail)
            except ValueError:
                structured = {'detail': detail[:4000]}
            return {'error': f'HTTP {exc.code}', **structured}  # 协议错误不重试
        except OSError as exc:
            last_err = exc
            if attempt + 1 < attempts:
                time.sleep(1)
    return {'error': f'后端不可达: {last_err}', 'failure_feedback': {
        'tool': path, 'cause': str(last_err), 'possible_remote_effect': 'unknown',
        'automatic_resend': False,
        'choices': ['只读核对原 operation_id；后端可能仍在执行，不自动重发'],
        'authority': '此错误不改变原授权'}}


def _tool_result(payload: dict) -> dict:
    is_error = "error" in payload or payload.get("ok") is False or payload.get("status") in ("unknown", "not_started", "failed")
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
        role = os.environ.get("CS_TOOL_ROLE", "executor")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "tools": [_TRACE_TOOL, _DATA_TOOL, _SCORES_TOOL, _NARRATIVE_TOOL, _FACTS_TOOL] if role == "brain" else _TOOLS}}
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
                action = args.get("action")
                out = _post("/api/v1/tools/job", args,
                            timeout=1350 if action == "submit" else 120 if action == "stop" else 30,
                            retry_transient=action not in ("submit", "stop"))
        elif name == "research_sandbox":
            requested = args.get('timeout')
            wait = (max(180, requested + 45) if args.get('action') == 'exec'
                    and type(requested) is int and 1 <= requested <= 10800 else
                    375 if args.get('action') in ('files.read', 'files.write') else 180)
            out = _post("/api/v1/tools/sandbox", args, timeout=wait,
                        retry_transient=False)
        elif name == "research_package_check":
            out = _post("/api/v1/tools/package_check", args)
        elif name == "research_trace_narrative_check":
            out = _post("/api/v1/tools/trace_narrative_check", args)
        elif name == 'research_environment':
            out = _post('/api/v1/tools/environment', args, timeout=90, retry_transient=False)
        elif name == 'research_operating_facts':
            out = _post('/api/v1/tools/operating_facts', {}, retry_transient=False)
        elif name == "research_local_score":
            out = _post("/api/v1/tools/local_score", args, timeout=180,
                        retry_transient=False)
        elif name == "research_data":
            out = _post("/api/v1/tools/data", args)
        elif name == "ack_guidance":
            out = _post("/api/v1/tools/ack", args)
        elif name == "research_trace":
            out = _post("/api/v1/tools/trace", args)
        elif name == "platform_scores":
            out = _post("/api/v1/tools/platform_scores", args)
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
