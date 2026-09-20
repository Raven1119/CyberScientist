"""只读探针：用已存储的 playground token 验证身份与可读端点。

绝不打印 token 本身；全部 GET 请求，无写操作。
结果写入 checks/results/platform_probe2.json（已脱敏）。
"""

import json
import urllib.request
import urllib.error

from cyberscientist.config import load_settings, resolve_secret

BASE = "https://play.bohrium.com/api"


def get(path: str, token: str | None) -> dict:
    req = urllib.request.Request(BASE + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
            return {"status": resp.status, "body": body[:4000]}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", "replace")[:2000]}
    except Exception as e:  # noqa: BLE001
        return {"status": None, "error": f"{type(e).__name__}: {e}"}


def main() -> None:
    settings = load_settings()
    token_ref = (settings.get("playground") or {}).get("token_secret_ref", "")
    token = resolve_secret(token_ref) if token_ref else None
    out: dict = {"token_ref": token_ref, "token_resolved": bool(token)}

    me = get("/auth/me", token)
    out["auth_me"] = me
    if me.get("status") == 200:
        try:
            profile = json.loads(me["body"])
            # 只保留非敏感字段
            keep = {k: profile.get(k) for k in (
                "id", "name", "email", "user_type", "userType",
                "operatorId", "operatorName", "agentFramework",
                "agentPersonaId", "personaName",
            ) if k in profile}
            out["auth_me_profile"] = keep
        except json.JSONDecodeError:
            pass

    out["agent_work"] = get("/agent/work?limit=3", token)
    out["challenges_count_probe"] = get("/challenges?limit=1", None)

    with open("checks/results/platform_probe2.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "body"} | {"body_len": len(str(v.get("body", "")))}) for k, v in out.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
