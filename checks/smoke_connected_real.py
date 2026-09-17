"""阶段 1.6：connected 模式全真实 Run —— 默认路径：Kimi K3 大脑 + Kimi Code K3-256k 执行器。

授权：用户明确指示默认路径切换为 Kimi Code 执行并用其测试（走 kimi.com 订阅额度）。
"""
from __future__ import annotations

import json
import sys
import time
import uuid

import httpx

B = "http://127.0.0.1:8765/api/v1"
PASS: list[str] = []
FAIL: list[str] = []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name} {extra}")


def main() -> int:
    s = httpx.Client(timeout=60)
    H: dict[str, str] = {}

    # 设置：connected + 默认路径（K3 大脑 + Kimi 执行器）
    st = s.get(f"{B}/settings").json()
    st["app"]["mode"] = "connected"
    st["brain"]["runtime"] = "kimi"
    st["brain"]["model_id"] = "kimi-code/k3"
    st["brain"]["reasoning_effort"] = "high"
    st["executor"] = {"runtime": "kimi", "executable": "",
                      "model_id": "kimi-code/k3-256k", "reasoning_effort": "high"}
    r = s.put(f"{B}/settings", json={"settings": st, "base_revision": st["revision"]},
              headers=H)
    check("切换 connected + 默认 Kimi 路径", r.status_code == 200)

    # 双组件真实探针
    r = s.post(f"{B}/connections/brain/test", json={"kind": "inspect"}, headers=H)
    bh = r.json()["health"]
    check("Kimi K3 大脑探针", bh["installed"] and "ACP initialize 成功" in bh["detail"],
          bh["version"] or "")
    r = s.post(f"{B}/connections/executor/test", json={"kind": "inspect"}, headers=H)
    eh = r.json()["health"]
    check("Kimi 执行器探针", eh["installed"], eh["version"] or "")

    r = s.post(f"{B}/challenges/import", json={"mode": "demo"}, headers=H)
    cid = r.json()["challenge"]["id"]
    r = s.post(f"{B}/runs", json={"challenge_id": cid}, headers=H)
    rid = r.json()["id"]
    r = s.post(f"{B}/runs/{rid}/authorize",
               json={"scope": "model_roundtrip", "allow_model_calls": True,
                     "max_model_turns": 8, "max_run_minutes": 20,
                     "max_submissions": 0, "note": "默认路径 K3脑+K3-256k执行 全真实闭环"}, headers=H)
    check("授权（含模型调用）", r.status_code == 200)

    seen: list[dict] = []
    stop = {"flag": False}

    def reader():
        after = 0
        buf = ""
        with httpx.Client(timeout=None) as c2:
            while not stop["flag"]:
                try:
                    with c2.stream("GET", f"{B}/runs/{rid}/events?after={after}") as resp:
                        for chunk in resp.iter_text():
                            if stop["flag"]:
                                return
                            buf += chunk
                            while "\n\n" in buf:
                                frame, buf = buf.split("\n\n", 1)
                                for line in frame.splitlines():
                                    if line.startswith("data:"):
                                        ev = json.loads(line[5:])
                                        if ev["seq"] > after:
                                            after = ev["seq"]
                                            seen.append(ev)
                except httpx.HTTPError:
                    time.sleep(1)

    import threading
    t = threading.Thread(target=reader, daemon=True)
    t.start()

    r = s.post(f"{B}/runs/{rid}/start", headers=H)
    check("启动真实 Run", r.status_code == 200 and r.json().get("phase") == "running",
          r.text[:150] if r.status_code != 200 else "")

    def types():
        return [e["type"] for e in seen]

    FATAL = ("prime.error", "brain.session_error", "brain.error",
             "brain.decision_rejected")

    def wait_for(pred, timeout=600, desc=""):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if pred():
                return True
            if any(t in FATAL for t in types()):  # 失败早停，不空等
                return False
            time.sleep(1.0)
        return False

    ok = wait_for(lambda: "trial.created" in types(), 120, "trial.created")
    check("K3 Decision → trial.created", ok, str(types()[:8]))
    ok = wait_for(lambda: s.get(f"{B}/runs/{rid}").json()["phase"] == "finished", 1500)
    run = s.get(f"{B}/runs/{rid}").json()
    prime_events = [t for t in types() if t.startswith("prime.")]
    check("Prime 真实执行事件", any("工具" in (e["payload"].get("detail") or "") or
          e["type"] == "prime.trial.completed" for e in seen), str(prime_events[:6]))
    check("Trial 完成", any(tr["status"] == "done" for tr in run["trials"]))
    check("K3 finish → Run 终态", ok and "run.finished" in types(),
          f"phase={run['phase']} reviews={run['brain_reviews_used']}")
    check("费用未知不显示 0", run["budget"]["model_turns"].get("known_cost") in (None,))

    stop["flag"] = True
    print(f"\n=== {len(PASS)} PASS / {len(FAIL)} FAIL ===")
    for f in FAIL:
        print("FAIL:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
