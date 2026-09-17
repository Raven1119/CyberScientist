"""Kimi ACP 探针 v2：正确的权限应答形状 + thinking 配置项 setter。

真实调用 K3（订阅额度）执行一次写文件任务，验证 approve 后工具真的执行。
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"C:\Users\wmywb\PycharmProjects\CyberScientist")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.cyberscientist.brains.kimi import KimiBrain  # noqa: E402


async def main() -> int:
    workdir = tempfile.mkdtemp(prefix="cs-kimi-exec2-")
    b = KimiBrain(model="kimi-code/k3-256k")
    s = await b.open({"working_directory": workdir})
    print("session:", s.session_id)
    rpc = b.rpc
    assert rpc is not None

    # thinking 配置 setter 探针（不触发模型调用）
    for method in ("session/set_config_option",):
        try:
            r = await rpc.request(method, {"sessionId": s.session_id,
                                           "configId": "thinking",
                                           "value": "low"}, timeout=15)
            print(f"{method} OK:", json.dumps(r, ensure_ascii=False)[:200])
        except Exception as exc:
            print(f"{method} ERR: {exc.__class__.__name__}: {str(exc)[:150]}")

    async def answer_perms():
        async for r in rpc.server_requests():
            if r.get("method") == "session/request_permission":
                options = r.get("params", {}).get("options", [])
                allow = next((o for o in options
                              if "allow" in str(o.get("kind", ""))), None)
                # ACP 标准形状：{"outcome": {"outcome": "selected", "optionId": ...}}
                await rpc.respond(r["id"], result={
                    "outcome": {"outcome": "selected",
                                "optionId": (allow or {}).get("optionId", "approve_once")}})
                print("approved via standard shape:", (allow or {}).get("optionId"))
            else:
                await rpc.respond(r["id"], error={"code": -32601,
                                                  "message": "probe: unsupported"})

    rq = asyncio.create_task(answer_perms())
    resp = await rpc.request(
        "session/prompt",
        {"sessionId": s.session_id,
         "prompt": [{"type": "text", "text":
                     "创建文件 probe_out.txt 写入 OK，然后列出目录确认。一句话报告。"}]},
        timeout=600)
    print("stopReason:", resp.get("stopReason") if isinstance(resp, dict) else resp)
    rq.cancel()
    ok = Path(workdir, "probe_out.txt").exists()
    print("PROBE", "PASS" if ok else "FAIL", "probe_out.txt", "存在" if ok else "不存在")
    await b.close(s)
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
