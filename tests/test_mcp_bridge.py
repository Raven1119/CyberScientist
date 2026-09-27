"""MCP 桥协议韧性：非对象 JSON 行只能得到错误响应，不能杀死桥进程。"""
from __future__ import annotations

import json
import subprocess
import sys

from cyberscientist import mcp_bridge


def test_bridge_survives_non_object_json_lines():
    proc = subprocess.Popen(
        [sys.executable, "-m", "cyberscientist.mcp_bridge"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        assert proc.stdin and proc.stdout
        # null / 数组 / 标量都不是合法 JSON-RPC 请求对象
        proc.stdin.write("null\n")
        proc.stdin.write('[1, 2]\n')
        proc.stdin.write('"just a string"\n')
        proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n")
        proc.stdin.flush()
        responses = []
        for _ in range(4):  # 3 个 invalid request + 1 个 ping
            line = proc.stdout.readline()
            assert line, f"桥进程提前退出（returncode={proc.poll()}）"
            responses.append(json.loads(line))
        for r in responses[:3]:
            assert r["jsonrpc"] == "2.0" and r["id"] is None
            assert r["error"]["code"] == -32600
        assert responses[3]["id"] == 1 and responses[3]["result"] == {}
        # 桥仍然存活，继续正常服务
        proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        assert line and json.loads(line)["result"]["tools"]
        assert proc.poll() is None
    finally:
        proc.kill()
        proc.wait()


def test_sandbox_and_scoring_calls_wait_without_replay(monkeypatch):
    calls=[]
    def unreachable(request, timeout):
        calls.append(timeout)
        raise OSError('timed out')
    monkeypatch.setattr(mcp_bridge.urllib.request, 'urlopen', unreachable)
    for name in ('research_sandbox', 'research_local_score'):
        result=mcp_bridge._handle({'jsonrpc':'2.0','id':1,'method':'tools/call',
                                   'params':{'name':name,'arguments':{'action':'list'}}})
        assert result['result']['isError'] is True
    assert calls == [180,180]
