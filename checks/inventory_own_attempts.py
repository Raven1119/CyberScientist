"""Read-only inventory of already identified own Playground Attempts.

Input account identities and author-filtered lists live under an ignored
``scorer-re-*/raw/accounts`` directory. This script never discovers accounts,
creates platform resources, or stores credentials. It downloads full content
only for accounts with their own token in the project vault; named agents
without their own token contribute public scores and metadata only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cyberscientist import config, db

BASE_URL = "https://play.bohrium.com/api"
MAX_BYTES = 100 * 1024 * 1024
PUBLIC_DETAIL_KEYS = frozenset({
    "id", "authorId", "challengeId", "challengeOrigin", "createdAt", "updatedAt",
    "status", "outcome", "score", "scorecard", "scoringState", "scoringDetails",
    "modelTag", "harness", "agentFramework", "type", "bundleAvailable",
    "rawMessagesAvailable", "traceCount", "version", "parentAttemptId",
    "operatorId", "operatorConfirmed", "scriptAvailable", "answerRedacted",
})


class ReadFailure(Exception):
    pass


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, new_url):
        old = urllib.parse.urlsplit(request.full_url)
        new = urllib.parse.urlsplit(new_url)
        if (new.scheme, new.netloc) != (old.scheme, old.netloc):
            raise ReadFailure("CROSS_ORIGIN_REDIRECT")
        return super().redirect_request(request, fp, code, msg, headers, new_url)


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _get(path: str, token: str | None = None, *, base_url: str = BASE_URL) -> bytes:
    url = base_url.rstrip("/") + path
    headers = {"Authorization": "Bearer " + token} if token else {}
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(_SameOriginRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            data = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ReadFailure(f"HTTP_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ReadFailure(f"NETWORK_{type(exc.reason).__name__}") from exc
    except OSError as exc:
        raise ReadFailure(f"IO_{type(exc).__name__}") from exc
    if len(data) > MAX_BYTES:
        raise ReadFailure("OVER_100_MIB")
    return data


def _subject(root: Path, alias: str, agents: list[dict[str, Any]],
             mailboxes: dict[str, Any]) -> dict[str, Any]:
    if alias in mailboxes:
        row = mailboxes[alias]
        me = json.loads((root / "raw/accounts" / alias / "auth_me.json").read_text())
        return {"alias": alias, "author_id": str(me["id"]),
                "identity": me, "credential_available": bool(config.resolve_secret(row["secret_ref"] or "")),
                "secret_ref": row["secret_ref"], "role": row["role"],
                "status": row["status"]}
    matches = [entry["agentUser"] for entry in agents
               if str(entry.get("agentUser", {}).get("name", "")).lower() == alias]
    if len(matches) != 1:
        raise ValueError(f"{alias}: expected one operator-registered identity, got {len(matches)}")
    user = matches[0]
    operator = json.loads((root / "raw/accounts/operator/auth_me.json").read_text())
    if str(user.get("operatorId")) != str(operator.get("id")) or not user.get("operatorConfirmed"):
        raise ValueError(f"{alias}: ownership not confirmed")
    return {"alias": alias, "author_id": str(user["id"]), "identity": user,
            "credential_available": False, "secret_ref": None, "role": "historical_agent",
            "status": "operator_confirmed"}


def _attempt(root: Path, subject: dict[str, Any], item: dict[str, Any],
             *, base_url: str = BASE_URL) -> dict[str, Any]:
    aid = str(item["id"])
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", aid):
        return {"id": aid, "failures": ["INVALID_ATTEMPT_ID"]}
    if str(item.get("authorId")) != subject["author_id"]:
        return {"id": aid, "failures": ["AUTHOR_MISMATCH_LIST"]}
    alias = subject["alias"]
    own_token = config.resolve_secret(subject["secret_ref"] or "") if subject["credential_available"] else None
    directory = root / "raw/accounts" / alias / "attempts" / aid
    result: dict[str, Any] = {"id": aid, "challenge_id": item.get("challengeId"),
                              "files": {}, "failures": [], "content": "available" if own_token else "unavailable_no_account_credential"}
    for suffix, filename in (("", "detail.json"), ("/score", "score.json")):
        try:
            raw = _get("/attempts/" + aid + suffix, own_token, base_url=base_url)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ReadFailure("NON_OBJECT_JSON")
            if not suffix and str(data.get("authorId")) != subject["author_id"]:
                raise ReadFailure("AUTHOR_MISMATCH_DETAIL")
            if not own_token and not suffix:
                data = {key: value for key, value in data.items() if key in PUBLIC_DETAIL_KEYS}
                raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
            result["files"][filename] = _write(directory / filename, raw)
        except (ReadFailure, ValueError, KeyError, UnicodeDecodeError) as exc:
            result["failures"].append(filename + ":" + str(exc)[:100])
    if not own_token:
        return result
    try:
        raw = _get("/attempts/" + aid + "/trace", own_token, base_url=base_url)
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ReadFailure("NON_LIST_TRACE")
        result["files"]["trace.json"] = _write(directory / "trace.json", raw)
        result["trace_rows"] = len(data)
    except (ReadFailure, ValueError, UnicodeDecodeError) as exc:
        result["failures"].append("trace.json:" + str(exc)[:100])
    if not item.get("bundleAvailable"):
        result["bundle"] = "unavailable_platform_flag"
        return result
    try:
        raw = _get("/attempts/" + aid + "/bundle", own_token, base_url=base_url)
        path = directory / "bundle.zip"
        result["files"]["bundle.zip"] = _write(path, raw)
        with zipfile.ZipFile(path) as archive:
            members = archive.namelist()
        result["bundle"] = "downloaded"
        result["bundle_members"] = members
        result["raw_messages_in_bundle"] = any(
            name.rsplit("/", 1)[-1] == "raw_messages.jsonl" for name in members)
        local = db.query("SELECT id,run_id,trial_id,package_sha256 FROM submissions"
                         " WHERE platform_ref=? OR package_sha256=?",
                         (aid, result["files"]["bundle.zip"]))
        result["local_links"] = [dict(row) for row in local]
    except (ReadFailure, zipfile.BadZipFile, OSError) as exc:
        result["bundle"] = "unavailable"
        result["failures"].append("bundle.zip:" + str(exc)[:100])
    return result


def inventory(root: Path, *, base_url: str = BASE_URL, workers: int = 2) -> dict[str, Any]:
    root = root.resolve()
    agents = json.loads((root / "raw/accounts/operator/registered_agents.json").read_text())
    rows = db.query("SELECT id,role,status,secret_ref FROM mailboxes"
                    " WHERE role IN ('harvest','experiment') ORDER BY created_at,id")
    mailboxes = {row["id"]: row for row in rows}
    account_root = root / "raw/accounts"
    aliases = list(mailboxes) + sorted(
        path.name for path in account_root.iterdir()
        if path.is_dir() and path.name not in mailboxes and path.name != "operator")
    subjects = [_subject(root, alias, agents, mailboxes) for alias in aliases]
    report: dict[str, Any] = {"collected_at_utc": datetime.now(timezone.utc).isoformat(),
                              "source": "own_author_filtered_attempts", "accounts": [],
                              "raw_files": {}}
    for subject in subjects:
        alias = subject["alias"]
        path = root / "raw/accounts" / alias / "attempts_list.json"
        body = json.loads(path.read_text())
        items = body.get("attempts")
        if not isinstance(items, list):
            raise ValueError(f"{alias}: attempts list missing")
        if any(not isinstance(item, dict) or str(item.get("authorId")) != subject["author_id"]
               for item in items):
            raise ValueError(f"{alias}: author-filtered list contains another account")
        if len({str(item["id"]) for item in items}) != len(items):
            raise ValueError(f"{alias}: duplicate Attempt id in list")
        account = {key: subject[key] for key in ("alias", "author_id", "identity", "credential_available", "role", "status")}
        account.update({"attempt_count": len(items), "platform_total": body.get("total"),
                        "total_match": len(items) == body["total"] if isinstance(body.get("total"), int) else None,
                        "total_limitation": None if isinstance(body.get("total"), int) else
                        "GET /attempts?author=... returned no total field; completeness unverified",
                        "attempts": []})
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_attempt, root, subject, item, base_url=base_url): item
                       for item in items}
            for future in as_completed(futures):
                account["attempts"].append(future.result())
        account["attempts"].sort(key=lambda x: str(x["id"]))
        account["bundle_downloaded"] = sum(item.get("bundle") == "downloaded" for item in account["attempts"])
        account["failed_items"] = [item["id"] for item in account["attempts"] if item["failures"]]
        report["accounts"].append(account)
        print(alias, "attempts", len(items), "bundles", account["bundle_downloaded"],
              "failed_items", len(account["failed_items"]), flush=True)
    for path in sorted((root / "raw").rglob("*")):
        if path.is_file() and not path.is_symlink():
            report["raw_files"][str(path.relative_to(root))] = {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (root / "inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _validated_output_root(path: Path) -> Path:
    root = path.resolve()
    ignored_parent = (config.WORKSPACE_ROOT / ".package-checks").resolve()
    if root.parent != ignored_parent or not root.name.startswith("scorer-re-"):
        raise ValueError("output must be a .package-checks/scorer-re-* directory")
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="Existing ignored scorer-re-* directory with verified account lists")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        parser.error("workers must be 1 or 2")
    inventory(_validated_output_root(args.root), workers=args.workers)


if __name__ == "__main__":
    main()
