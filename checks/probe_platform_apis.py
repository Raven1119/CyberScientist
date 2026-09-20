"""Playground / Bohrium 只读最小探针（无提交、无注册、无写操作）。

只发 GET，记录状态码与脱敏片段；结果写入 checks/results/platform_probe.json。
不知道就记 unknown，绝不编造字段形状。

运行：uv run python checks/probe_platform_apis.py
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from cyberscientist import config  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "platform_probe.json"

PG_KEY = config.resolve_secret("local:playground_token")
BOH_KEY = config.resolve_secret("local:bohrium_access_key")


def probe(name: str, url: str, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15,
                                    context=ssl.create_default_context()) as r:
            body = r.read(600).decode("utf-8", errors="replace")
            return {"name": name, "url": url, "status": r.status,
                    "body_excerpt": body[:400]}
    except urllib.error.HTTPError as e:
        body = e.read(400).decode("utf-8", errors="replace")
        return {"name": name, "url": url, "status": e.code,
                "body_excerpt": body[:300]}
    except Exception as e:  # noqa: BLE001
        return {"name": name, "url": url, "status": None,
                "error": f"{e.__class__.__name__}: {str(e)[:200]}"}


def main() -> None:
    results = []
    pg = "https://play.bohrium.com/api"
    bearer = {"Authorization": f"Bearer {PG_KEY}"} if PG_KEY else {}

    results.append(probe("pg_docs_noauth", f"{pg}/docs", {}))
    if PG_KEY:
        results.append(probe("pg_challenges_bearer",
                             f"{pg}/challenges", bearer))
        results.append(probe("pg_me_bearer", f"{pg}/user", bearer))

    boh = "https://openapi.bohrium.com"
    if BOH_KEY:
        results.append(probe("boh_account_ak_header",
                             f"{boh}/api/v1/account",
                             {"accessKey": BOH_KEY}))
        results.append(probe("boh_account_bearer",
                             f"{boh}/api/v1/account",
                             {"Authorization": f"Bearer {BOH_KEY}"}))

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    for r in results:
        print(f"[{r['status']}] {r['name']}: "
              f"{r.get('body_excerpt', r.get('error', ''))[:120]!r}")
    print(f"\n已存 {OUT}")


if __name__ == "__main__":
    main()
