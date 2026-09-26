"""Conservative classification and timing for native model throttling."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any


_LIMIT = re.compile(
    r"\b(?:HTTP(?:/[\d.]+)?\s*429|(?:status|code|status_code|error)['\"]?\s*[:= ]\s*429"
    r"|429\s*[-:]?\s*Too Many Requests)\b|^429$"
    r"|rate[ _-]?limit(?:ed|[ _-]?(?:exceeded|reached))?"
    r"|quota[ _-]exceeded|insufficient[ _-]quota|额度(?:不足|耗尽)|限流",
    re.IGNORECASE,
)
_RETRY_AFTER = re.compile(r"retry[ _-]?after\s*[:=]\s*(\d{1,6})\s*(?:s|sec|seconds)?\b",
                          re.IGNORECASE)


@dataclass(frozen=True)
class RateLimit:
    retry_after_seconds: int | None = None
    reason: str = "rate_limit"


def classify(error: Any) -> RateLimit | None:
    """Only explicit 429/rate-limit/quota text is classified; ambiguity stays unknown."""
    if isinstance(error, dict):
        code = error.get("code") or error.get("status") or error.get("statusCode")
        message = str(error.get("message") or error.get("error") or "")
        retry = error.get("retry_after", error.get("retryAfter"))
        code_text = str(code or "")
        if code_text != "429" and not _LIMIT.search(message) and not _LIMIT.search(code_text):
            return None
        reason = ("quota_exhausted" if re.search(
            r"quota[ _-]exceeded|insufficient[ _-]quota|额度(?:不足|耗尽)",
            message + " " + code_text, re.IGNORECASE) else "rate_limit")
        if isinstance(retry, (int, float)) and 0 <= retry <= 86400:
            return RateLimit(int(retry), reason)
        if isinstance(retry, str) and retry.isdecimal() and int(retry) <= 86400:
            return RateLimit(int(retry), reason)
        error = message
    else:
        error = str(error or "")[:2000]
        if not _LIMIT.search(error):
            return None
        reason = ("quota_exhausted" if re.search(
            r"quota[ _-]exceeded|insufficient[ _-]quota|额度(?:不足|耗尽)",
            error, re.IGNORECASE) else "rate_limit")
    match = _RETRY_AFTER.search(error)
    if match:
        return RateLimit(int(match.group(1)), reason)
    date_match = re.search(r"retry[ _-]?after\s*:\s*([^\r\n]+)", error,
                           re.IGNORECASE)
    if date_match:
        try:
            when = parsedate_to_datetime(date_match.group(1))
            return RateLimit(max(0, int((when - datetime.now(timezone.utc)).total_seconds())),
                             reason)
        except (TypeError, ValueError, OverflowError):
            pass
    return RateLimit(reason=reason)


def retry_delay(attempt: int, info: RateLimit) -> int:
    if info.retry_after_seconds is not None:
        return max(1, info.retry_after_seconds)
    return min(900, 60 * 2 ** min(max(attempt - 1, 0), 4))


def retry_at(now: datetime, delay_seconds: int) -> str:
    return (now.astimezone(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
