"""Run-authorized public task data materialization with immutable local receipts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from . import config, db
from .bohr_proxy import redact

MAX_BYTES = 1024 ** 3


class DataError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def resource_key(resource: dict[str, Any]) -> str | None:
    dataset_id = resource.get("dataset_id")
    version = resource.get("version_id") or resource.get("version")
    if dataset_id and version:
        return f"wenyon:{dataset_id}@{version}"
    url = resource.get("url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return "url:" + hashlib.sha256(url.encode()).hexdigest()
    if resource.get("access_method") == "paper2task_api":
        return "paper2task:" + hashlib.sha256(_json(resource).encode()).hexdigest()[:24]
    return None


def register_resources(challenge_id: str, resources: list[dict[str, Any]]) -> None:
    now = db.utcnow()
    with db.transaction() as conn:
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            key = resource_key(resource)
            if not key:
                continue
            kind = key.split(":", 1)[0]
            status = "unsupported" if kind == "paper2task" else "registered"
            expected = resource.get("public_manifest_sha256") or resource.get("sha256")
            conn.execute("INSERT OR IGNORE INTO data_materializations"
                         "(id,operation_id,challenge_id,resource_key,source_kind,retrieval_ref,"
                         "expected_hash,status,created_at,updated_at)"
                         " VALUES(?,?,?,?,?,?,?,?,?,?)",
                         ("dm_" + uuid.uuid4().hex[:12], "register:" + challenge_id + ":" + key,
                          challenge_id, key, kind, resource.get("retrieval_ref") or resource.get("url"),
                          expected, status, now, now))


def _resource(challenge_id: str, key: str) -> dict[str, Any]:
    challenge = db.query_one("SELECT resources_json FROM challenges WHERE id=?", (challenge_id,))
    if not challenge:
        raise DataError("NOT_FOUND", "题目不存在")
    try:
        resources = json.loads(challenge["resources_json"] or "[]")
    except ValueError:
        resources = []
    for item in resources:
        if isinstance(item, dict) and resource_key(item) == key:
            return item
    raise DataError("NOT_FOUND", "题目未登记该数据资源")


def status(challenge_id: str) -> dict[str, Any]:
    resources = db.query("SELECT * FROM data_materializations WHERE challenge_id=? ORDER BY created_at",
                         (challenge_id,))
    return {"items": [_public(row) for row in resources]}


def _public(row: Any) -> dict[str, Any]:
    key = row["resource_key"]
    item = {"materialization_id": row["id"], "resource_key": key,
            "source_kind": row["source_kind"], "status": row["status"],
            "error_code": row["error_code"], "hash_semantics": row["hash_semantics"],
            "total_bytes": row["total_bytes"]}
    if row["store_path"]:
        item["content_sha256"] = Path(row["store_path"]).name
        item["workspace_path"] = str(config.WORKSPACE_DIR / "challenges" / row["challenge_id"] /
                                     "data" / re.sub(r"[^A-Za-z0-9_-]", "_", key))
    return item


def _authorized(conn, challenge_id: str, run_id: str | None = None) -> str:
    run = conn.execute("SELECT r.id FROM runs r JOIN authorizations a ON a.id=r.authorization_id"
                       " WHERE r.challenge_id=? AND r.mode='connected'"
                       " AND r.phase='running' AND r.gate='open'"
                       " AND a.allow_data_download=1"
                       + (" AND r.id=?" if run_id else "")
                       + " ORDER BY r.created_at DESC LIMIT 1",
                       (challenge_id, run_id) if run_id else (challenge_id,)).fetchone()
    if not run:
        raise DataError("NOT_AUTHORIZED", "本 Run 未授权用账号下载题目公开数据")
    return run["id"]


def _manifest(root: Path) -> list[list[Any]]:
    files = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise DataError("INVALID_DATA", "数据下载包含符号链接")
        if path.is_file():
            if path.name == "DATA_MANIFEST.json":
                raise DataError("INVALID_DATA", "数据集含保留清单文件名")
            size = path.stat().st_size
            total += size
            if total > MAX_BYTES:
                raise DataError("TOO_LARGE", "数据超过 1 GiB")
            files.append([path.relative_to(root).as_posix(), _sha256_file(path), size])
    if not files:
        raise DataError("CLI_ERROR", "未收到任何数据文件")
    return files


def _verify_wenyon(resource: dict[str, Any], root: Path,
                   files: list[list[Any]]) -> tuple[str, str]:
    """Verify the observed v1 public manifest, without guessing other formats."""
    expected = resource.get("public_manifest_sha256")
    if not expected:
        return "unverified", "unknown"
    manifest = root / "public-manifest.json"
    if not manifest.is_file():
        raise DataError("HASH_MISMATCH", "下载结果缺少题目登记的公开清单")
    if _sha256_file(manifest) != expected:
        raise DataError("HASH_MISMATCH", "公开清单原文字节哈希与题目登记值不符")
    total = sum(size for _, _, size in files)
    if resource.get("bytes") is not None and resource["bytes"] != total:
        raise DataError("HASH_MISMATCH", "下载总字节数与题目登记值不符")
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return "unverified", "manifest_sha256"
    if not isinstance(document, dict) or document.get("schema_version") != "playground-wenyon-public-manifest/v1":
        return "unverified", "manifest_sha256"
    resources = document.get("resources")
    if not isinstance(resources, list):
        return "unverified", "manifest_sha256"
    declared = []
    for item in resources:
        if not isinstance(item, dict):
            raise DataError("HASH_MISMATCH", "公开清单资源格式无效")
        declared.append([item.get("staged_path"), item.get("sha256"), item.get("size")])
    observed = [entry for entry in files if entry[0] != "public-manifest.json"]
    if sorted(declared, key=str) != sorted(observed, key=str):
        raise DataError("HASH_MISMATCH", "下载文件与公开清单不一致")
    return "verified", "manifest_sha256"


def input_refs(source: Path) -> list[str]:
    """Verify every declared materialization actually frozen with this input."""
    refs = []
    for manifest_path in source.rglob("DATA_MANIFEST.json"):
        try:
            doc = json.loads(manifest_path.read_text())
            root = manifest_path.parent
            materialization_id = doc["materialization_id"]
            row = db.query_one("SELECT status,files_json FROM data_materializations WHERE id=?",
                               (materialization_id,))
            if not row or row["status"] not in ("verified", "unverified"):
                raise ValueError("未登记可用的数据物化记录")
            files = doc["files"]
            if files != json.loads(row["files_json"]):
                raise ValueError("数据清单与登记记录不符")
            for rel, sha, size in files:
                path = (root / rel).resolve()
                if not path.is_relative_to(root.resolve()) or not path.is_file() or path.is_symlink():
                    raise ValueError("物化数据文件缺失或路径非法")
                if path.stat().st_size != size or _sha256_file(path) != sha:
                    raise ValueError("物化数据已被篡改")
            refs.append(materialization_id)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise DataError("DATA_CHANGED", "冻结 Job 输入前数据清单校验失败") from exc
    return sorted(set(refs))


def evidence_class(conn: Any, run_id: str, trial_id: str | None) -> str:
    run = conn.execute("SELECT c.resources_json FROM runs r JOIN challenges c"
                       " ON c.id=r.challenge_id WHERE r.id=?", (run_id,)).fetchone()
    try:
        resources = json.loads(run["resources_json"] or "[]") if run else []
    except ValueError:
        resources = []
    required = any(isinstance(item, dict) and item.get("role") == "task-public-data"
                   for item in resources)
    if not required:
        return "not_applicable"
    rows = conn.execute("SELECT data_refs_json FROM compute_jobs WHERE run_id=?"
                        + (" AND trial_id=?" if trial_id else ""),
                        (run_id, trial_id) if trial_id else (run_id,)).fetchall()
    return "official_data" if any(json.loads(row["data_refs_json"] or "[]") for row in rows) else "proxy"


def materialize(challenge_id: str, key: str, operation_id: str,
                run_id: str | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", operation_id or ""):
        raise DataError("INVALID_OPERATION", "需要稳定安全的 operation_id")
    resource = _resource(challenge_id, key)
    kind = key.split(":", 1)[0]
    with db.transaction() as conn:
        # A Run-scoped request must never inherit a prior request or another Run's grant.
        authorized_run = _authorized(conn, challenge_id, run_id) if run_id else None
        old = conn.execute("SELECT * FROM data_materializations WHERE operation_id=?", (operation_id,)).fetchone()
        if old:
            if old["challenge_id"] != challenge_id or old["resource_key"] != key:
                raise DataError("CONFLICT", "operation_id 已用于其他资源")
            return _public(old) | {"deduplicated": True}
        run_id = authorized_run or _authorized(conn, challenge_id)
        if kind == "paper2task":
            raise DataError("UNSUPPORTED", "Paper2Task API 数据包尚未接入")
        now = db.utcnow()
        identifier = "dm_" + uuid.uuid4().hex[:12]
        conn.execute("INSERT INTO data_materializations"
                     "(id,operation_id,challenge_id,resource_key,source_kind,retrieval_ref,expected_hash,"
                     "status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,'downloading',?,?)",
                     (identifier, operation_id, challenge_id, key, kind,
                      resource.get("retrieval_ref") or resource.get("url"),
                      resource.get("public_manifest_sha256") or resource.get("sha256"), now, now))
        db.append_event_tx(conn, run_id, "controller", "data.materialize_requested",
                           {"materialization_id": identifier, "resource_key": key,
                            "operation_id": operation_id})
    staging = config.DATA_DIR / "data-staging" / operation_id
    receipt: dict[str, Any] = {}
    native_receipt: dict[str, Any] | None = None
    error_code = None
    state = "unverified"
    hash_semantics = "unknown"
    files: list[list[Any]] = []
    content_hash = None
    try:
        staging.mkdir(parents=True, exist_ok=False)
        if kind == "wenyon":
            from . import compute
            match = re.fullmatch(r"wenyon:([^@]+)@(.+)", key)
            assert match
            receipt = compute._native(["wenyon", "dataset", "download", match[1],
                                       "--version", match[2], "--output-dir", str(staging),
                                       "--output", "json"], timeout=180)
            native_receipt = receipt
            if receipt.get("unknown"):
                raise DataError("TIMEOUT", "数据下载回执未知，禁止自动重试")
            if not receipt.get("ok"):
                raw = receipt.get("stdout", "") + "\n" + receipt.get("stderr", "")
                code = ("WENYON_CLI_UNAVAILABLE" if
                        ('unknown command "wenyon"' in raw or 'wenyon is not installed' in raw)
                        else "AUTH_REQUIRED" if "401" in raw else
                        "FORBIDDEN" if "403" in raw else
                        "NOT_FOUND" if "404" in raw else "CLI_ERROR")
                raise DataError(code, "Wenyon 数据下载失败")
        elif kind == "url":
            req = urllib.request.Request(resource["url"])
            with urllib.request.urlopen(req, timeout=120) as response:
                reported = response.headers.get("Content-Length")
                if reported and int(reported) > MAX_BYTES:
                    raise DataError("TOO_LARGE", "响应长度超过 1 GiB")
                out = staging / "download"
                with out.open("wb") as stream:
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise DataError("TOO_LARGE", "响应超过 1 GiB")
                        stream.write(chunk)
            receipt = {"http_status": 200, "bytes": size}
            if resource.get("bytes") is not None and size != int(resource["bytes"]):
                raise DataError("HASH_MISMATCH", "下载大小与题目登记值不符")
            digest = _sha256_file(out)
            if resource.get("sha256") and digest != resource["sha256"]:
                raise DataError("HASH_MISMATCH", "下载哈希与题目登记值不符")
            state = "verified" if resource.get("sha256") else "unverified"
        else:
            raise DataError("UNSUPPORTED", "资源类型未接入")
        files = _manifest(staging)
        if kind == "wenyon":
            state, hash_semantics = _verify_wenyon(resource, staging, files)
        elif state == "verified":
            hash_semantics = "file_sha256"
        content_hash = hashlib.sha256(_json(files).encode()).hexdigest()
        store = config.DATA_DIR / "data-store" / content_hash
        store.parent.mkdir(parents=True, exist_ok=True)
        if store.exists():
            shutil.rmtree(staging)
        else:
            os.replace(staging, store)
            for path in store.rglob("*"):
                path.chmod(0o555 if path.is_dir() else 0o444)
            store.chmod(0o555)
        workspace = config.WORKSPACE_DIR / "challenges" / challenge_id / "data" / re.sub(r"[^A-Za-z0-9_-]", "_", key)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        if workspace.exists():
            shutil.rmtree(workspace)
        shutil.copytree(store, workspace)
        for directory in [workspace, *(p for p in workspace.rglob("*") if p.is_dir())]:
            directory.chmod(0o755)
        (workspace / "DATA_MANIFEST.json").write_text(_json({"materialization_id": identifier,
            "content_sha256": content_hash, "files": files, "source": key,
            "hash_semantics": hash_semantics}))
        receipt = {"ok": True, "source_kind": kind, "file_count": len(files),
                   "bytes": sum(f[2] for f in files)}
        if native_receipt is not None:
            stdout = native_receipt.get("stdout", "")
            receipt["cli_exit_code"] = native_receipt.get("exit_code")
            receipt["cli_stdout_sha256"] = hashlib.sha256(stdout.encode()).hexdigest()
            try:
                cli_result = json.loads(stdout)
            except (TypeError, ValueError):
                cli_result = None
            if isinstance(cli_result, dict):
                receipt["cli_result"] = {
                    key: cli_result[key] for key in
                    ("dataset_id", "version", "total", "downloaded", "skipped", "failed", "bytes")
                    if key in cli_result and isinstance(cli_result[key], (str, int))
                }
    except DataError as exc:
        error_code = exc.code
        state = "unknown" if exc.code == "TIMEOUT" else "failed"
    except urllib.error.HTTPError as exc:
        error_code = {401: "AUTH_REQUIRED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(exc.code, "CLI_ERROR")
        state = "failed"
    except (OSError, urllib.error.URLError, ValueError) as exc:
        error_code = "CLI_ERROR"
        state = "failed"
        receipt = {"error_type": type(exc).__name__}
    finally:
        if staging.exists() and state != "unknown":
            shutil.rmtree(staging)
    safe = redact(_json(receipt), list(config.load_secrets().values()))
    with db.transaction() as conn:
        conn.execute("UPDATE data_materializations SET status=?,store_path=?,files_json=?,total_bytes=?,"
                     "error_code=?,receipt_json=?,updated_at=?,hash_semantics=? WHERE id=?",
                     (state, str(config.DATA_DIR / "data-store" / content_hash)
                      if content_hash and state in ("verified", "unverified") else None,
                      _json(files), sum(f[2] for f in files) if files else None,
                     error_code, safe, db.utcnow(),
                      hash_semantics, identifier))
        db.append_event_tx(conn, run_id, "controller",
                           "data.access_denied" if error_code in ("AUTH_REQUIRED", "FORBIDDEN") else
                           ("data.materialized" if not error_code else "data.materialize_failed"),
                           {"materialization_id": identifier, "status": state,
                            "error_code": error_code, "content_sha256": content_hash})
    return _public(db.query_one("SELECT * FROM data_materializations WHERE id=?", (identifier,)))
