"""Kimi K3 真实大脑 Decision 往返探针（ACP）。

验证：session/new → session/set_model(kimi-code/k3) → session/prompt
（ReviewPacket）→ 流式收消息 → 终态 → 输出为 schema 合法 Decision。
授权：用户明确「做好之后用 Kimi Code K3 测试」。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cyberscientist.brains.kimi import KimiBrain  # noqa: E402
from src.cyberscientist import decision as decision_mod  # noqa: E402

PACKET = {
    "run_id": "run_probe_kimi",
    "state_version": 0,
    "trigger": "run_start",
    "current_intention": None,
    "trial_summary": None,
    "trial_count": 0,
    "challenge_id": "DEMO_CHALLENGE",
    "new_events_since_last_review": [],
    "budget_remaining": {"brain_reviews": 6, "model_turns": 1},
    "experience_manifest": [],
}


async def main() -> int:
    brain = KimiBrain(model="kimi-code/k3")
    session = await brain.open({"working_directory": None})
    print("session:", session.session_id)
    final = None
    async for ev in brain.review(session, PACKET):
        if ev.type == "decision":
            final = ev.payload["decision"]
        elif ev.type == "error":
            print("ERROR:", ev.payload.get("message", "")[:300])
        elif ev.type == "approval_request":
            print("approval_request:", str(ev.payload)[:200])
    await brain.close(session)

    if not final:
        print("\n=== BRAIN ROUNDTRIP FAIL（无 Decision）===")
        return 1
    errors = decision_mod.validate_structure(final)
    print("decision:", json.dumps({k: final[k] for k in
                                   ("decision_id", "summary", "actions")},
                                  ensure_ascii=False)[:500])
    print("schema errors:", errors or "无")
    ok = not errors
    print("\n=== BRAIN ROUNDTRIP", "PASS" if ok else "FAIL", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
