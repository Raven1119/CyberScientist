"""创建新 attempt（创建时带 4 张复现图）→ bundle → submit → 评分 → 轮询。

背景：PATCH 已提交 attempt 405（draft-only）；hackathon 题禁止 fork（403）。
故用 Path A 新建 draft，创建时即附 figures。实验邮箱本题第 2 次提交（上限 10）。
不打印 token。用法: uv run python checks/resubmit_with_figures.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from cyberscientist.config import load_secrets  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CH_DIR = ROOT / "workspace" / "challenges" / "local_c2643b50"
BASE = "https://play.bohrium.com/api"
CID = "aiyagari-1994-qje"

TOKEN = load_secrets().get("mailbox_mbox_15fa10126b")
if not TOKEN:
    print("ERROR: 实验邮箱 token 缺失"); sys.exit(1)


def http(method, path, json_body=None, form_fields=None, form_files=None,
         timeout=90):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form_fields is not None or form_files is not None:
        boundary = "----csresub4a1c"
        parts = []
        for k, v in (form_fields or {}).items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{k}"\r\n\r\n{v}\r\n'.encode())
        for name, fname, blob, ctype in (form_files or []):
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{name}"; filename="{fname}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n".encode() + blob + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:1500]


results = json.loads((CH_DIR / "result_package.json").read_text(encoding="utf-8"))
figs = [("figures", f"fig_{n}.png",
         (CH_DIR / "figures" / f"fig_{n}.png").read_bytes(), "image/png")
        for n in (1, 2, 3, 4)]
trace = [{
    "type": "tool_call",
    "title": "Aiyagari Table II reproduction",
    "body": "VFI 家计政策函数 + 稳态均衡（二分求 r*），8 组 (sigma, beta, mu) "
            "实测求解；fig_1 政策函数、fig_2 总资源、fig_3 利率-人均资产、"
            "fig_4 稳态决定均为真实计算输出。",
}]

# 1. 创建 draft（带 figures 与 results_json）
st, body = http("POST", f"/challenges/{CID}/attempts",
                form_fields={
                    "method": "VFI + bisection equilibrium (numpy/scipy)",
                    "type": "agent",
                    "status": "draft",
                    "outcome": "partial",
                    "harness": "CyberScientist",
                    "model": "Kimi K3",
                    "trace": json.dumps(trace, ensure_ascii=False),
                    "results_json": json.dumps(results, ensure_ascii=False),
                },
                form_files=figs)
print("create:", st, str(body)[:500])
if st not in (200, 201) or not isinstance(body, dict) or "id" not in body:
    print("创建失败"); sys.exit(1)
aid = body["id"]
print("attempt id:", aid)

# 2. ARM bundle
st, body = http("POST", f"/attempts/{aid}/bundle",
                form_files=[("bundle", "arm_bundle.zip",
                             (CH_DIR / "arm_bundle.zip").read_bytes(),
                             "application/zip")])
print("bundle:", st, str(body)[:300])

# 3. Submit
st, body = http("POST", f"/attempts/{aid}/submit")
print("submit:", st, str(body)[:300])
if st not in (200, 201):
    print("submit 失败"); sys.exit(1)

# 4. 触发评分
st, body = http("POST", f"/attempts/{aid}/score")
print("score trigger:", st, str(body)[:300])

# 5. 轮询评分
for i in range(12):
    time.sleep(10)
    st, body = http("GET", f"/attempts/{aid}/score")
    if isinstance(body, dict):
        state = body.get("scoringState") or {}
        final = state.get("scoreIsFinal")
        print(f"poll{i}: final={final}", json.dumps(body, ensure_ascii=False)[:500])
        if final:
            break
    else:
        print(f"poll{i}:", st, str(body)[:200])
print("ATTEMPT_ID", aid)
