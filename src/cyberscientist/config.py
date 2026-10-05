"""工作区路径、配置与秘密存储。

秘密只存 .cyberscientist/secrets.json（权限 0600），绝不写入配置、经验或日志。
"""
from __future__ import annotations

import json
import functools
import os
import stat
import threading
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = WORKSPACE_ROOT / ".cyberscientist"
DB_PATH = DATA_DIR / "cyberscientist.db"
SECRETS_PATH = DATA_DIR / "secrets.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
WORKSPACE_DIR = WORKSPACE_ROOT / "workspace"
EXPERIENCE_DIR = WORKSPACE_ROOT / "experience"
LOCK_PATH = DATA_DIR / "controller.lock"

_lock_file = None
_lock_guard = threading.Lock()
mutation_lock = threading.RLock()


def serialized_mutation(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with mutation_lock:
            return fn(*args, **kwargs)
    return wrapped


def update_secret(secret_id: str, value: str | None) -> None:
    with mutation_lock:
        secrets = load_secrets()
        if value is None:
            secrets.pop(secret_id, None)
        else:
            secrets[secret_id] = value
        save_secrets(secrets)

DEFAULT_SETTINGS: dict[str, Any] = {
    'features': {'environment_catalog': True, 'scorer_audit': True, 'await_score': True, 'shared_area': True},
    "schema_version": 1,
    "revision": 0,
    "app": {"host": "127.0.0.1", "port": 8765, "mode": "demo",
            "data_dir": str(DATA_DIR)},
    "brain": {"runtime": "codex", "provider": "codex",
              "executable": "",
              "auth_mode": "native",
              "model_id": "gpt-6-astra",
              "reasoning_effort": "xhigh",
              "custom_profile_id": None},
    "executor": {"runtime": "codex",
                 "executable": "",
                 "model_id": "gpt-6-sol",
                 "reasoning_effort": "high"},
    "reviewer": {"runtime": "codex", "provider": "codex", "executable": "",
                 "model_id": "gpt-6.1-sol", "reasoning_effort": "high"},
    "post_review": {"runtime": "codex", "provider": "deepseek", "executable": "",
                    "model_id": "deepseek-flash", "reasoning_effort": "high"},
    "solver_roster": [],
    "model_pricing": {"deepseek/deepseek-flash": {
        "currency": "USD", "source": "https://api-docs.deepseek.com/quick_start/pricing/",
        "observed_on": "2026-10-05", "billing_tier": "unknown",
        "off_peak": {"input": 0.15, "cached_input": 0.003, "output": 0.6},
        "peak": {"input": 0.3, "cached_input": 0.006, "output": 1.2}}},
    "prime": {"executable": "", "llm_profile_id": "",
              "automatic_refine": False, "subagents_enabled": False},
    "llm_profiles": [],
    "playground": {"base_url": "https://play.bohrium.com/api",
                   "token_secret_ref": ""},
    "bohrium": {"executable": "", "wenyon_executable": "", "wenyon_home": "",
                "access_key_secret_ref": "", "project_id": None, "host_overrides": {}},
    "policy": {"science_compute": "local_seconds_remote_heavy",
               "default_authorization": "read_only",
               "allow_formal_submission": False,
               "require_ended_submission": False, "allowed_submission_targets": []},
    "harvest": {"score_threshold": 100, "experiments_done_at_leader": True,
                "deadline_check_hours": 2},
    "run_defaults": {"max_active_runs": 6, "max_trials": 3,
                     "max_brain_reviews": 20, "max_run_minutes": 30,
                     "max_model_turns": 0, "max_jobs": 3, "max_submissions": 0,
                     "stall_seconds": 300, "max_brain_wait_seconds": 3600,
                     "brain_review_timeout_seconds": 900,
                     "rate_limit_max_seconds": 3600},
    "shadow": {"enabled": False, "min_interval_seconds": 60,
               "max_interval_seconds": 600, "max_reviews": 8},
    "mailbox": {"platform": "demo", "submission_limit": 10},
    "polling": {"disabled_challenges": [], "score_confirmation_seconds": 600,
                "confirmed_interval_seconds": 3600},
    "skills": {"always_on": []},
    "resources": {"provider_sessions": {"codex": 10, "deepseek": 10, "kimi": 10,
                                       "prime": 10},
                  "max_concurrent_jobs": None, "max_concurrent_sandboxes": None},
    "memory": {"root": str(EXPERIENCE_DIR), "max_global_entries": 20,
               "max_challenge_entries": 10, "max_injected_characters": 24000},
}


def ensure_dirs() -> None:
    for d in (DATA_DIR, WORKSPACE_DIR, WORKSPACE_DIR / "challenges",
              WORKSPACE_DIR / "runs", EXPERIENCE_DIR,
              EXPERIENCE_DIR / "global", DATA_DIR / "protocol_logs"):
        d.mkdir(parents=True, exist_ok=True)


def acquire_workspace_lock() -> None:
    """单进程工作区锁；第二个控制器进程拒绝启动。"""
    global _lock_file
    with _lock_guard:
        ensure_dirs()
        candidate = open(LOCK_PATH, "a+")
        candidate.seek(0)
        try:
            try:
                import msvcrt  # Windows
            except ImportError:
                import fcntl
                fcntl.flock(candidate.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                msvcrt.locking(candidate.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            candidate.close()
            raise RuntimeError(
                "另一个 CyberScientist 控制器已占用此工作区（controller.lock）"
            ) from exc
        # Only the owner may replace the PID. A failed second startup must not
        # truncate the live controller's recovery/diagnostic identity.
        _lock_file = candidate
        _lock_file.seek(0)
        _lock_file.truncate()
        _lock_file.write(str(os.getpid()))
        _lock_file.flush()


@serialized_mutation
def load_settings() -> dict[str, Any]:
    ensure_dirs()
    if not SETTINGS_PATH.exists():
        return json.loads(json.dumps(DEFAULT_SETTINGS))
    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    merged = merge_settings(DEFAULT_SETTINGS, data)
    # An explicitly stored price table is authoritative, including {}. Missing
    # prices remain unknown rather than silently reintroducing deleted defaults.
    if 'model_pricing' in data:
        merged['model_pricing'] = json.loads(json.dumps(data['model_pricing']))
    if merged['policy'].get('science_compute') == 'bohrium_only':
        merged['policy']['science_compute'] = 'local_seconds_remote_heavy'
    from .pi_policy import migrated
    merged['brain'] = migrated(merged['brain'])
    return merged


def merge_settings(current: dict, changes: dict) -> dict:
    """Partial writes preserve unrelated pages, including nested settings."""
    result = json.loads(json.dumps(current))
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = json.loads(json.dumps(value))
    return result


@serialized_mutation
def save_settings(settings: dict[str, Any]) -> None:
    ensure_dirs()
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)


@serialized_mutation
def load_secrets() -> dict[str, str]:
    ensure_dirs()
    if not SECRETS_PATH.exists():
        return {}
    return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))


@serialized_mutation
def save_secrets(secrets: dict[str, str]) -> None:
    ensure_dirs()
    tmp = SECRETS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(secrets, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, SECRETS_PATH)
    try:
        os.chmod(SECRETS_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def resolve_secret(secret_ref: str) -> str | None:
    """secret_ref 形式：env:VAR_NAME / local:<id>。keyring 暂不支持，返回 None。"""
    if not secret_ref:
        return None
    kind, _, rest = secret_ref.partition(":")
    if kind == "env":
        return os.environ.get(rest)
    if kind == "local":
        return load_secrets().get(rest)
    return None


def secret_configured(secret_ref: str) -> bool:
    return resolve_secret(secret_ref) is not None


def deepseek_key() -> str | None:
    """Read only the authorized env/root dotenv source; never persist the value."""
    value = os.environ.get("DEEPSEEK_API_KEY")
    if value:
        return value
    path = WORKSPACE_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, raw = line.strip().partition("=")
            if sep and name.removeprefix("export ").strip() == "DEEPSEEK_API_KEY":
                return raw.strip().strip('"').strip("'") or None
    return None


def sensitive_values() -> list[str]:
    return [v for v in [*load_secrets().values(), deepseek_key()]
            if isinstance(v, str) and v]
