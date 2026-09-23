"""Run-local bohr entry point: prevent CLI diagnostics from exposing credentials.

The CLI sometimes includes accessKey in network-error URLs, even for `version`.
Capture both streams before returning them to the agent; never retry a command.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import sys
from typing import Iterable
from urllib.parse import quote, quote_plus


_ACCESS_KEY_QUERY = re.compile(r"([?&]access_?key=)[^&\s\"'<>]+", re.IGNORECASE)
_SECRET_ENV_NAMES = ("BOHR_ACCESS_KEY", "ACCESS_KEY", "BOHRCTL_ACCESS_KEY", "CS_TOOL_TOKEN")


def redact(text: str, secret_values: Iterable[str]) -> str:
    """Remove known credential values and unknown keys echoed inside URLs."""
    variants = {
        variant
        for value in secret_values if value
        for variant in (value, quote(value, safe=""), quote_plus(value, safe=""))
    }
    for value in sorted(variants, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = _ACCESS_KEY_QUERY.sub(r"\1[REDACTED]", text)
    text = re.sub(r'(?i)(\b(?:BOHR_ACCESS_KEY|ACCESS_KEY|CS_TOOL_TOKEN|API_KEY)\s*=\s*)[^\s"\']+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)("(?:access[_-]?key|api[_-]?key|authorization|token)"\s*:\s*")[^"]*', r'\1[REDACTED]', text)
    return re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9_.~+/=-]+", r"\1[REDACTED]", text)


def install_proxy(bin_dir: Path) -> Path:
    """Install a non-secret entry point; caller supplies a Run capability token."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    entry = bin_dir / "bohr"
    entry.write_text(
        "#!/bin/sh\n"
        f"exec {shlex.quote(sys.executable)} -m cyberscientist.bohr_proxy \"$@\"\n",
        encoding="utf-8",
    )
    entry.chmod(0o700)
    return entry


def main() -> int:
    """Credential-free client. Dispatch once; an uncertain response is never retried."""
    import json
    import urllib.request
    import urllib.error
    token = os.environ.get("CS_TOOL_TOKEN", "")
    base = os.environ.get("CS_API_URL", "http://127.0.0.1:8765")
    if not token:
        print("缺少 Run 能力令牌；禁止直接调用原生 bohr", file=sys.stderr)
        return 77
    body = json.dumps({"args": sys.argv[1:], "cwd": os.getcwd()}).encode()
    request = urllib.request.Request(base + "/api/v1/tools/bohr", data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        print(redact(exc.read().decode(errors="replace"), [token]), file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(redact(f"请求结果 unknown；请先查询 Run Job 账本：{exc}", [token]), file=sys.stderr)
        return 75
    print(redact(json.dumps(result, ensure_ascii=False), [token]))
    if result.get("platform_job_id"):
        print(f"JobId: {result['platform_job_id']}")
    return 0 if result.get("ok", True) and result.get("status") not in ("unknown", "not_started") else 1


if __name__ == "__main__":
    raise SystemExit(main())
