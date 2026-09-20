"""Fork attempt 44534 → 新 draft 补齐 figures/resultsJson/bundle → submit → 触发评分。

PATCH 已提交 attempt 返回 405（draft-only），因此走文档化的 fork 流程。
不打印 token。用法: uv run python checks/fork_resubmit.py
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from cyberscientist.config import load_secrets  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CH_DIR = ROOT / "workspace" / "challenges" / "local_c2643b50"
BASE = "https://play.bohrium.com/api"
PARENT = 44534

TOKEN = load_secrets().get("mailbox_mbox_15fa10126b")
if not TOKEN:
    print("ERROR: 实验邮箱 token 缺失")
    sys.exit(1)


def http(method: str, path: str, json_body=None, form_fields=None,
         form_files=None, timeout=60):
    url = BASE + path
    headers = {"Authorization": f"Bearer {TOKEN}"}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form_fields is not None or form_files is not None:
        boundary = "----csfork9e2b"
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
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:1500]


# 1. Fork
st, body = http("POST", f"/attempts/{PARENT}/fork",
                json_body={"changelog": "补充真实复现图（fig_1..4）与 ARM bundle，"
                                        "首次提交评分要求 authentic result figures"})
print("fork:", st, (str(body)[:300] if st != 200 and st != 201 else ""))
if st not in (200, 201) or not isinstance(body, dict) or "id" not in body:
    print("fork 失败"); sys.exit(1)
aid = body["id"]
print("new draft attempt id:", aid, "status:", body.get("status"))

# 2. PATCH draft: figures + results_json + outcome
results = json.loads((CH_DIR / "result_package.json").read_text(encoding="utf-8"))
files = []
for n in (1, 2, 3, 4):
    p = CH_DIR / "figures" / f"fig_{n}.png"
    files.append(("figures", f"fig_{n}.png", p.read_bytes(), "image/png"))
st, body = http("PATCH", f"/attempts/{aid}",
                form_fields={
                    "outcome": "partial",
                    "results_json": json.dumps(results, ensure_ascii=False),
                },
                form_files=files)
print("patch figures+results:", st, str(body)[:400])

# 3. ARM bundle
bundle = (CH_DIR / "arm_bundle.zip").read_bytes()
st, body = http("POST", f"/attempts/{aid}/bundle",
                form_files=[("bundle", "arm_bundle.zip", bundle,
                             "application/zip")])
print("bundle:", st, str(body)[:300])

# 4. Submit
st, body = http("POST", f"/attempts/{aid}/submit")
print("submit:", st, str(body)[:300])

# 5. Trigger scoring
st, body = http("POST", f"/attempts/{aid}/score")
print("score trigger:", st, str(body)[:300])

# 6. Poll score briefly
for i in range(6):
    time.sleep(10)
    st, body = http("GET", f"/attempts/{aid}/score")
    if isinstance(body, dict):
        state = body.get("scoringState") or {}
        print(f"poll{i}: scoreIsFinal={state.get('scoreIsFinal')}",
              json.dumps(body, ensure_ascii=False)[:400])
        if state.get("scoreIsFinal"):
            break
print("ATTEMPT_ID", aid)
