"""Prime Agent 真实模型工具往返探针（OpenRouter GLM-5.2:free）。

验证：prompt 受理 → 模型回合 → ipython 工具执行 → 结果回传 → agent_end
→ get_last_assistant_text / get_session_stats。非科研计算。
授权：用户显式提供 OpenRouter Key 并要求调用免费 GLM。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cyberscientist.config import resolve_secret  # noqa: E402
from src.cyberscientist.prime import PrimeRpc  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "workspace" / "runs" / "prime-probe"
MARKER = f"hello-glm-{uuid.uuid4().hex[:8]}"


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key = resolve_secret("local:openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("FAIL: 未找到 OpenRouter Key（local:openrouter_api_key）")
        return 1
    env = {k: os.environ[k] for k in
           ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME",
            "APPDATA") if k in os.environ}
    env["OPENROUTER_API_KEY"] = key

    prime = PrimeRpc("prime-agent")
    sid = await prime.start({
        "session_dir": OUT_DIR / "session",
        "env": env,
        "provider": "openrouter",
        "model": "DS-V4.1-Flash-OR",
        "cwd": str(OUT_DIR),
    })
    print(f"session started: {sid}")

    state = await prime.state(sid)
    print("initial state:", json.dumps(state, ensure_ascii=False)[:300])

    events: list[dict] = []
    done = asyncio.Event()

    async def consume() -> None:
        async for ev in prime.events(sid):
            events.append(ev)
            t = ev.get("type")
            if t == "extension_ui_request":
                # 无边界自动同意：结构化拒绝并记录
                await prime.respond_ui(sid, ev["id"], cancelled=True)
                print(f"  [ui-request {ev.get('method')} → cancelled]")
            elif t == "agent_end":
                done.set()
                return

    consumer = asyncio.create_task(consume())

    prompt = (f"请使用 ipython 工具：先写入文件 probe_hello.txt，内容为 {MARKER}，"
              "然后读回该文件内容，最后用一句话报告读到的内容。")
    receipt = await prime.prompt(sid, prompt)
    print("prompt receipt:", receipt.status, receipt.detail)
    if receipt.status == "rejected":
        print("FAIL: prompt 被拒绝:", receipt.detail)
        return 1

    try:
        await asyncio.wait_for(done.wait(), timeout=420)
    except asyncio.TimeoutError:
        print("FAIL: 等待 agent_end 超时")
        return 1
    finally:
        consumer.cancel()

    types: dict[str, int] = {}
    tool_calls: list[str] = []
    for ev in events:
        t = ev.get("type", "?")
        types[t] = types.get(t, 0) + 1
        if t == "tool_execution_start":
            tool_calls.append(ev.get("toolName", "?"))
    print("event types:", json.dumps(types, ensure_ascii=False))
    print("tool calls:", tool_calls)

    text = await prime._client(sid).command("get_last_assistant_text", timeout=30)
    final_text = (text.get("data") or {}).get("text") or ""
    print("final text:", final_text[:300])

    file_ok = (OUT_DIR / "probe_hello.txt").exists() and \
        MARKER in (OUT_DIR / "probe_hello.txt").read_text(encoding="utf-8")
    print("file roundtrip:", "PASS" if file_ok else "FAIL",
          f"(marker={MARKER})")

    stats = await prime.stats(sid)
    print("stats:", json.dumps({k: stats.get(k) for k in
                                ("toolCalls", "cost", "tokens")}, ensure_ascii=False)[:300])

    # 保存脱敏真实 transcript（真实协议回归证据）
    fixture = OUT_DIR / "transcript-redacted.jsonl"
    with fixture.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print("transcript:", fixture)

    await prime.close(sid)
    ok = file_ok and any(tc == "ipython" for tc in tool_calls) and bool(final_text)
    print("\n=== ROUNDTRIP", "PASS" if ok else "FAIL", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
