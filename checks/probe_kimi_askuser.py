"""AskUserQuestion 线协议探针：elicitation/create 与 request_permission 回退形状。

会话 A：声明 elicitation.form 能力 → 问题应走 elicitation/create。
会话 B：不声明 → 问题应回退 session/request_permission（q*_opt_* 选项）。
两条路径都尝试用「第二个选项」应答，验证选择是否真正生效（工具结果应回显所选项）。

会真实调用 Kimi K3（两次小回合）。输出原始报文到
checks/fixtures/real/kimi-acp-askuser-probe.jsonl。
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

from src.cyberscientist.brains.kimi import KimiBrain, ACP_PROTOCOL_VERSION  # noqa: E402

OUT = Path("checks/fixtures/real/kimi-acp-askuser-probe.jsonl")

PROMPT = ("调用 AskUserQuestion 工具，只问一个问题：'冒烟测试用哪个 GPU？'，"
          "选项：'A100（推荐）' 和 'L20'。收到回答后用一句话告诉我你收到了什么，"
          "不要做任何其他事。")


async def run_session(tag: str, elicitation: bool, frames: list[dict]) -> None:
    workdir = tempfile.mkdtemp(prefix=f"cs-askprobe-{tag}-")
    b = KimiBrain(model="kimi-code/k3-256k")
    rpc = await b._spawn(["acp"], cwd=workdir)

    def rec(direction: str, msg: dict) -> None:
        frames.append({"session": tag, "dir": direction, "msg": msg})

    caps: dict = {"fs": {"readTextFile": False, "writeTextFile": False},
                  "terminal": False}
    if elicitation:
        caps["elicitation"] = {"form": {}}
    init = await rpc.request(
        "initialize", {"protocolVersion": ACP_PROTOCOL_VERSION,
                       "clientCapabilities": caps}, timeout=30)
    rec("init-result", init if isinstance(init, dict) else {"raw": str(init)})
    sess = await rpc.request("session/new", {"cwd": workdir, "mcpServers": []},
                             timeout=30)
    sid = sess.get("sessionId")
    print(f"[{tag}] session:", sid, "| elicitation advertised:", elicitation)

    async def answer_requests() -> None:
        async for r in rpc.server_requests():
            rec("in-req", r)
            method = r.get("method")
            params = r.get("params", {})
            if method == "elicitation/create":
                print(f"[{tag}] ELICITATION:",
                      json.dumps(params, ensure_ascii=False)[:600])
                # 尽力构造回答：取每个 field 的第二个选项（验证选择生效）
                answered = await answer_elicitation(rpc, r["id"], params)
                print(f"[{tag}] elicitation answered:", answered)
            elif method == "session/request_permission":
                options = params.get("options", [])
                print(f"[{tag}] PERMISSION options:",
                      json.dumps(options, ensure_ascii=False)[:400])
                # 问题型请求（q*_opt_*）选第二个选项；普通审批选第一个 allow
                qopts = [o for o in options
                         if str(o.get("optionId", "")).startswith("q")]
                pick = None
                if qopts:
                    pick = qopts[1] if len(qopts) > 1 else qopts[0]
                else:
                    pick = next((o for o in options
                                 if "allow" in str(o.get("kind", ""))), None)
                if pick:
                    await rpc.respond(r["id"], result={
                        "outcome": {"outcome": "selected",
                                    "optionId": pick["optionId"]}})
                    print(f"[{tag}]   -> selected:", pick["optionId"])
                else:
                    await rpc.respond(r["id"], result={
                        "outcome": {"outcome": "cancelled"}})
                    print(f"[{tag}]   -> cancelled (no allow/question option)")
            else:
                rec("in-req-unsupported", {"method": method})
                await rpc.respond(r["id"], error={
                    "code": -32601, "message": "probe: unsupported"})

    async def watch() -> None:
        async for m in rpc.notifications():
            rec("in-notif", m)

    rq = asyncio.create_task(answer_requests())
    w = asyncio.create_task(watch())
    try:
        resp = await rpc.request(
            "session/prompt",
            {"sessionId": sid,
             "prompt": [{"type": "text", "text": PROMPT}]},
            timeout=300)
        rec("in-resp", {"method": "session/prompt:result", "result": resp})
        print(f"[{tag}] stopReason:",
              resp.get("stopReason") if isinstance(resp, dict) else resp)
    except Exception as exc:  # noqa: BLE001
        rec("prompt-error", {"error": f"{exc.__class__.__name__}: {exc}"})
        print(f"[{tag}] prompt error:", exc)
    finally:
        rq.cancel()
        w.cancel()
        try:
            await rpc.stop()
        except Exception:  # noqa: BLE001
            pass


async def answer_elicitation(rpc, req_id, params: dict) -> str:
    """elicitation/create：requestedSchema.properties 的每个属性是一道题，
    oneOf[].const 是可选答案。MCP 风格响应：{action: accept, content: {...}}。"""
    props = (params.get("requestedSchema") or {}).get("properties") or {}
    content: dict = {}
    for qid, spec in props.items():
        opts = spec.get("oneOf") or []
        if opts:
            chosen = opts[1] if len(opts) > 1 else opts[0]
            content[qid] = chosen.get("const")
    try:
        await rpc.respond(req_id, result={"action": "accept",
                                          "content": content})
        return f"accept {content}"
    except Exception as exc:  # noqa: BLE001
        return f"respond failed: {exc}"


async def main() -> int:
    frames: list[dict] = []
    await run_session("elicitation", True, frames)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        for fr in frames:
            f.write(json.dumps(fr, ensure_ascii=False) + "\n")
    print("frames:", len(frames), "->", OUT)
    return 0


sys.exit(asyncio.run(main()))
