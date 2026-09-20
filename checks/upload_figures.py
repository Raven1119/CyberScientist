"""上传 4 张复现图到 attempt 44534（PATCH multipart），不打印 token。"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from cyberscientist.config import load_secrets  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "workspace" / "challenges" / "local_c2643b50" / "figures"
HOST = "https://play.bohrium.com/api"
ATTEMPT = 44534

secrets = load_secrets()
token = secrets.get("mailbox_mbox_15fa10126b")  # 真实实验邮箱 cyberscientist-exp-b8f242
if not token:
    print("ERROR: no experiment mailbox token in secrets")
    sys.exit(1)

# multipart/form-data 手工构造
boundary = "----csfigboundary7f3a"
parts = []
for n in (1, 2, 3, 4):
    data = (FIG_DIR / f"fig_{n}.png").read_bytes()
    parts.append(
        b"--" + boundary.encode() + b"\r\n"
        b'Content-Disposition: form-data; name="figures"; filename="fig_' + str(n).encode() + b'.png"\r\n'
        b"Content-Type: image/png\r\n\r\n" + data + b"\r\n"
    )
parts.append(b"--" + boundary.encode() + b"--\r\n")
body = b"".join(parts)

req = urllib.request.Request(
    f"{HOST}/api/attempts/{ATTEMPT}",
    data=body,
    method="PATCH",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    },
)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        print("PATCH status:", resp.status)
        print(resp.read().decode()[:2000])
except urllib.error.HTTPError as e:
    print("PATCH HTTP", e.code)
    print(e.read().decode()[:2000])
