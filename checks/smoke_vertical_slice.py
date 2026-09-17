"""阶段 1 垂直切片端到端 smoke：配置→导入→授权→启动→观察→指导→经验→重启可见。

用法：后端已启动时  uv run python checks/smoke_vertical_slice.py
覆盖 BUILD.md 阶段 1 用户路径的 API 层验证（Demo 模式）。
错误响应统一为 {"detail": {code, message, recoverable, details_ref?, details?}}。
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import httpx

B = "http://127.0.0.1:8765/api/v1"
ROOT = Path(__file__).resolve().parents[1]
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name} {extra}")


def code_of(r: httpx.Response) -> str | None:
    d = r.json().get("detail") or {}
    return d.get("code")


def main() -> int:
    code = (ROOT / ".cyberscientist" / "pairing.code").read_text().strip()
    s = httpx.Client(timeout=30)
    r = s.post(f"{B}/pair", json={"code": code})
    check("配对建立会话", r.status_code == 200 and "x-csrf-token" in r.headers)
    H = {"X-CSRF-Token": r.headers["x-csrf-token"]}

    r = s.post(f"{B}/challenges/import", json={"mode": "demo"}, headers=H)
    check("导入演示题目", r.status_code == 200, r.text[:60])
    cid = r.json()["challenge"]["id"]

    r = s.post(f"{B}/runs", json={"challenge_id": cid}, headers=H)
    rid = r.json()["id"]
    r = s.post(f"{B}/runs/{rid}/start", headers=H)
    check("未授权启动被拒(NEEDS_AUTHORIZATION)",
          r.status_code == 403 and code_of(r) == "NEEDS_AUTHORIZATION")

    r = s.post(f"{B}/runs/{rid}/authorize",
               json={"scope": "demo", "allow_model_calls": False,
                     "max_model_turns": 0, "max_run_minutes": 30,
                     "max_submissions": 0}, headers=H)
    check("保存有界授权", r.status_code == 200)

    seen: list[dict] = []
    stop_flag = {"stop": False}

    def event_reader() -> None:
        after = 0
        buf = ""
        with httpx.Client(timeout=None) as c2:
            while not stop_flag["stop"]:
                try:
                    with c2.stream("GET", f"{B}/runs/{rid}/events?after={after}") as resp:
                        for chunk in resp.iter_text():
                            if stop_flag["stop"]:
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
    t = threading.Thread(target=event_reader, daemon=True)
    t.start()

    def wait_for(pred, timeout: float = 20, desc: str = "") -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if pred():
                return True
            time.sleep(0.4)
        return False

    r = s.post(f"{B}/runs/{rid}/start", headers=H)
    check("启动 Run", r.status_code == 200 and r.json()["phase"] == "running")

    ok = wait_for(lambda: "trial.created" in [e["type"] for e in seen], 10)
    check("大脑 Decision → trial.created", ok,
          str([e["type"] for e in seen]))

    # 暂停语义：先验证 pausing→paused（代理确认才显示），再恢复
    r = s.post(f"{B}/runs/{rid}/control",
               json={"action": "pause",
                     "operation_id": f"op_{uuid.uuid4().hex[:10]}"}, headers=H)
    check("暂停受理", r.json().get("status") == "accepted")
    ok = wait_for(lambda: s.get(f"{B}/runs/{rid}").json()["phase"] == "paused", 10)
    check("暂停语义 pausing→paused（代理确认才显示）", ok)
    r = s.post(f"{B}/runs/{rid}/control",
               json={"action": "resume",
                     "operation_id": f"op_{uuid.uuid4().hex[:10]}"}, headers=H)
    check("恢复运行", r.json().get("status") == "confirmed")

    # 运行期 operation_id 去重（同一 op 的 steer 重发只受理一次）
    op_dup = f"op_dup_{uuid.uuid4().hex[:8]}"
    r1 = s.post(f"{B}/runs/{rid}/control",
                json={"action": "steer", "text": "去重测试", "operation_id": op_dup},
                headers=H)
    r2 = s.post(f"{B}/runs/{rid}/control",
                json={"action": "steer", "text": "去重测试", "operation_id": op_dup},
                headers=H)
    check("重复 operation_id 去重",
          r1.json().get("status") == "queued"
          and r2.json().get("deduplicated") is True)

    r = s.post(f"{B}/runs/{rid}/control",
               json={"action": "steer", "text": "smoke: 先验证证据链",
                     "operation_id": f"op_{uuid.uuid4().hex[:10]}"}, headers=H)
    check("指导返回 queued", r.json().get("status") == "queued")

    def types() -> list[str]:
        return [e["type"] for e in seen]

    ok = wait_for(lambda: "prime.steer.consumed" in types(), 15)
    check("steer queued→accepted→consumed 序列",
          ok and "user.steer.queued" in types() and "prime.steer" in types(),
          str(types()))

    ok = wait_for(lambda: "run.finished" in types(), 25)
    run = s.get(f"{B}/runs/{rid}").json()
    check("Trial 完成(done)", any(t["status"] == "done" for t in run["trials"]))
    check("大脑 finish → Run 终态 finished",
          ok and run["phase"] == "finished", f"phase={run['phase']}")

    exps = s.get(f"{B}/experiences").json()
    demo_exp = [i for i in exps["items"] if "演示" in i["title"]]
    check("经验候选已保存(candidate)", bool(demo_exp),
          str([(i["id"], i["status"]) for i in demo_exp]))

    if demo_exp:
        eid = demo_exp[0]["id"]
        e = s.get(f"{B}/experiences/{eid}").json()
        fm = dict(e["frontmatter"]); fm["status"] = "active"
        r = s.put(f"{B}/experiences/{eid}",
                  json={"frontmatter": fm, "body_md": e["body_md"] + "\n- smoke 修订\n",
                        "base_hash": e["current_hash"], "reason": "smoke 激活"},
                  headers=H)
        check("经验编辑保存", r.status_code == 200, r.text[:80])
        e2 = s.get(f"{B}/experiences/{eid}").json()
        r = s.put(f"{B}/experiences/{eid}",
                  json={"frontmatter": fm, "body_md": "冲突草稿",
                        "base_hash": e["current_hash"], "reason": "smoke 冲突"},
                  headers=H)
        det = (r.json().get("detail") or {}).get("details") or {}
        check("过期 base_hash 返回 409 REVISION_CONFLICT（含双方内容）",
              r.status_code == 409 and code_of(r) == "REVISION_CONFLICT"
              and "current_content" in det and "your_content" in det)
        first_rev = e2["revisions"][0]["revision_hash"]
        r = s.post(f"{B}/experiences/{eid}/restore",
                   json={"revision_hash": first_rev, "reason": "smoke 回滚"},
                   headers=H)
        check("回滚为新修订（幂等指向已有修订）",
              r.status_code == 200 and r.json()["revision_hash"] == first_rev,
              r.text[:100])
        revs = s.get(f"{B}/experiences/{eid}/revisions").json()["items"]
        check("修订历史完整保留", len(revs) >= 2, f"{len(revs)} 条唯一内容修订")

    r = s.post(f"{B}/connections/brain/test", json={"kind": "inspect"}, headers=H)
    check("大脑 inspect 探针", r.status_code == 200, r.text[:100])
    r = s.post(f"{B}/connections/prime/test", json={"kind": "inspect"}, headers=H)
    check("Prime inspect 探针(demo)", r.status_code == 200, r.text[:80])
    r = s.post(f"{B}/connections/brain/test", json={"kind": "model_roundtrip"},
               headers=H)
    check("模型往返未确认消耗被拒",
          r.status_code == 403 and code_of(r) == "NEEDS_AUTHORIZATION")

    stop_flag["stop"] = True
    print(f"\n=== {len(PASS)} PASS / {len(FAIL)} FAIL ===")
    for f in FAIL:
        print("FAIL:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
