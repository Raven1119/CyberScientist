"""JSON-RPC stdio 分帧（synthetic fixture）。

用一个 echo 脚本假扮上游进程，验证 LF 分帧、请求/响应关联、通知通道。
fixture 为显式合成，不属于真实协议回归录制。
"""
from __future__ import annotations

import asyncio
import json
import sys

import pytest

from cyberscientist.jsonrpc_stdio import JsonRpcStdio, ProtocolError

# synthetic fixture：发回 result；对 "boom" 方法直接退出进程
FAKE_SERVER = r"""
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    if msg.get("method") == "boom":
        sys.exit(3)
    if "method" in msg and "id" in msg:
        if msg["method"] == "notify_me":
            continue  # notification，无响应
        print(json.dumps({"id": msg["id"], "result": {"echo": msg["params"]}}), flush=True)
    elif msg.get("method") == "server_push":
        pass
"""


async def _start() -> JsonRpcStdio:
    rpc = JsonRpcStdio([sys.executable, "-c", FAKE_SERVER], name="fake")
    await rpc.start()
    return rpc


async def test_request_response_correlation():
    rpc = await _start()
    try:
        r1 = await rpc.request("ping", {"a": 1})
        r2 = await rpc.request("ping", {"a": 2})
        assert r1["echo"]["a"] == 1
        assert r2["echo"]["a"] == 2
    finally:
        await rpc.stop()


async def test_notification_channel():
    rpc = await _start()
    try:
        await rpc.notify("notify_me", {"x": 1})  # 不应悬挂
        result = await asyncio.wait_for(rpc.request("ping", {}), timeout=5)
        assert "echo" in result
    finally:
        await rpc.stop()


async def test_process_exit_wakes_waiters():
    rpc = await _start()
    try:
        with pytest.raises((ProtocolError, asyncio.TimeoutError)):
            await rpc.request("boom", {}, timeout=5)
    finally:
        await rpc.stop()


async def test_lf_framing_multibyte(tmp_path):
    import os
    script = tmp_path / "fake_server.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    env = dict(os.environ, PYTHONUTF8="1")
    rpc = JsonRpcStdio([sys.executable, str(script)], env=env, name="fake")
    await rpc.start()
    try:
        text = "中文\n换行"
        r = await rpc.request("ping", {"text": text})
        assert r["echo"]["text"] == text
    finally:
        await rpc.stop()


async def test_large_json_line_is_not_truncated():
    rpc = await _start()
    try:
        payload = '科研证据' * 25000
        result = await rpc.request('ping', {'text': payload})
        assert result['echo']['text'] == payload
    finally:
        await rpc.stop()


async def test_eof_wakes_stream_consumers():
    rpc = await _start()
    try:
        pending = asyncio.create_task(rpc.notifications().__anext__())
        with pytest.raises(ProtocolError):
            await rpc.request('boom', {}, timeout=1)
        with pytest.raises(ProtocolError):
            await asyncio.wait_for(pending, 1)
    finally:
        await rpc.stop()


async def test_timed_out_request_does_not_leak_pending():
    rpc = await _start()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await rpc.request('notify_me', {}, timeout=0.01)
        assert rpc._pending == {}
        assert (await rpc.request('ping', {'alive': True}))['echo']['alive']
    finally:
        await rpc.stop()
