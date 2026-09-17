"""Kimi ACP 执行器协议探针：工具事件形状、权限请求选项、模型/模式配置面。

会真实调用 Kimi K3 模型（订阅额度）并执行一次微小工具任务（写一个 probe 文件）。
输出原始报文到 checks/fixtures/real/kimi-acp-executor-probe.jsonl。
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

OUT = Path("checks/fixtures/real/kimi-acp-executor-probe.jsonl")


async def main() -> int:
    workdir = tempfile.mkdtemp(prefix="cs-kimi-exec-")
    b = KimiBrain(model="kimi-code/k3-256k")
    frames: list[dict] = []

    def rec(direction: str, msg: dict) -> None:
        frames.append({"dir": direction, "msg": msg})

    s = await b.open({"working_directory": workdir})
    print("session:", s.session_id, "| cwd:", workdir)
    rpc = b.rpc
    assert rpc is not None

    async def watch():
        async for m in rpc.notifications():
            rec("in-notif", m)

    async def answer_perms():
        async for r in rpc.server_requests():
            rec("in-req", r)
            if r.get("method") == "session/request_permission":
                options = r.get("params", {}).get("options", [])
                print("PERMISSION options:", json.dumps(options, ensure_ascii=False)[:300])
                allow = next((o for o in options
                              if "allow" in str(o.get("kind", ""))), None)
                if allow:
                    await rpc.respond(r["id"], result={
                        "outcome": {"selected": [allow.get("optionId")]}})
                    print("  -> approved:", allow.get("optionId"))
                else:
                    await rpc.respond(r["id"], result={
                        "outcome": {"selected": ["reject_once"]}})
                    print("  -> no allow option, rejected")
            else:
                await rpc.respond(r["id"], error={"code": -32601,
                                                  "message": "probe: unsupported"})

    w = asyncio.create_task(watch())
    rq = asyncio.create_task(answer_perms())

    resp = await rpc.request(
        "session/prompt",
        {"sessionId": s.session_id,
         "prompt": [{"type": "text", "text":
                     "在当前目录创建文件 probe_out.txt，内容写入 OK，"
                     "然后列出当前目录文件确认它存在。完成后用一句话报告。"}]},
        timeout=600)
    rec("in-resp", {"method": "session/prompt:result", "result": resp})
    print("prompt stopReason:", resp.get("stopReason") if isinstance(resp, dict) else resp)

    w.cancel()
    rq.cancel()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for fr in frames:
            f.write(json.dumps(fr, ensure_ascii=False) + "\n")
    print("frames:", len(frames), "->", OUT)

    kinds: dict[str, int] = {}
    for fr in frames:
        m = fr["msg"]
        if m.get("method") == "session/update":
            k = m.get("params", {}).get("update", {}).get("sessionUpdate", "?")
            kinds[k] = kinds.get(k, 0) + 1
    print("sessionUpdate kinds:", json.dumps(kinds))
    # 打印每种新形状的第一帧
    seen: set[str] = set()
    for fr in frames:
        m = fr["msg"]
        if m.get("method") == "session/update":
            k = m.get("params", {}).get("update", {}).get("sessionUpdate", "?")
            if k not in seen and k != "agent_message_chunk":
                seen.add(k)
                print(f"--- first {k}:")
                print(json.dumps(m, ensure_ascii=False)[:500])
    ok = Path(workdir, "probe_out.txt").exists()
    print("PROBE", "PASS" if ok else "FAIL", "(probe_out.txt 落盘)" if ok else "")
    await b.close(s)
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
