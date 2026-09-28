"""Isolated, model-free analysis context for an explicitly authorized replay.

Uses the production sandbox gateway and ledger. Does not start a controller loop,
copy credentials, change the live application database, or create a Job/Attempt.
The task card supplies the 1 CPU sandbox / 180 cumulative minute authorization;
running this utility in another task requires its own authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path

from cyberscientist import config, db, sandboxes
from cyberscientist.controller import RunController


def open_context(root: Path) -> dict | None:
    settings = config.load_settings()
    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn
    root = root.resolve()
    config.DATA_DIR = root / "state"
    config.DB_PATH = config.DATA_DIR / "analysis.db"
    config.SETTINGS_PATH = config.DATA_DIR / "settings.json"
    config.WORKSPACE_DIR = root / "workspace"
    config.EXPERIENCE_DIR = root / "experience"
    config.LOCK_PATH = config.DATA_DIR / "controller.lock"
    # SECRETS_PATH remains the configured backend vault. Values never get copied.
    config.ensure_dirs()
    if not config.SETTINGS_PATH.exists():
        config.save_settings(settings)
    db.init_db()
    session = root / "session.json"
    return json.loads(session.read_text()) if session.exists() else None


def initialize(root: Path, challenge_file: Path, *, max_minutes: int = 180) -> dict:
    if type(max_minutes) is not int or not 1 <= max_minutes <= 180:
        raise ValueError("analysis budget must be within the task's 180-minute cap")
    existing = open_context(root)
    if existing:
        return existing
    snapshot = json.loads(challenge_file.read_text())
    raw = snapshot["raw"]
    challenge_id = snapshot["challenge_id"]
    content = raw["content"]
    db.execute("INSERT INTO challenges(id,platform_challenge_id,origin,title,content,content_hash,imported_at) "
               "VALUES(?,?,?,?,?,?,?)", (challenge_id, challenge_id, "historical_analysis",
               snapshot["title"], content, hashlib.sha256(content.encode()).hexdigest(), db.utcnow()))
    controller = RunController()
    run = controller.create_run(challenge_id, mode="connected", shadow_enabled=False)
    rid = run["id"]
    controller.authorize(rid, scope="historical_scorer_analysis", allow_model_calls=False,
                         max_model_turns=0, max_run_minutes=max_minutes, max_submissions=0,
                         max_jobs=0, max_sandboxes=1, max_sandbox_minutes=max_minutes,
                         allow_sandbox_gpu=False,
                         note="CS-UP-03R: replay existing own artifacts; CPU sandbox only; no models, Jobs or Attempts")
    tid = "trial_" + uuid.uuid4().hex[:10]
    now = db.utcnow()
    with db.transaction() as conn:
        conn.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at) VALUES(?,?,?,?,?,?)",
                     (tid, rid, "Historical scorer replay", "Compare independent scores against frozen receipts", "active", now))
        frozen = json.loads(conn.execute("SELECT config_snapshot FROM runs WHERE id=?", (rid,)).fetchone()[0])
        frozen["analysis_only"] = True
        conn.execute("UPDATE runs SET phase='running',gate='open',current_trial_id=?,started_at=?,config_snapshot=? WHERE id=?",
                     (tid, now, json.dumps(frozen), rid))
        db.append_event_tx(conn, rid, "controller", "analysis.started",
                           {"models_started": False, "purpose": "historical_scorer_replay"}, trial_id=tid)
    trial_dir = config.WORKSPACE_DIR / "runs" / rid / "trials" / tid
    trial_dir.mkdir(parents=True)
    result = {"run_id": rid, "trial_id": tid, "trial_dir": str(trial_dir),
              "challenge_id": challenge_id, "authorization_max_minutes": max_minutes}
    (root / "session.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init")
    init.add_argument("--challenge", required=True, type=Path)
    init.add_argument("--budget-minutes", type=int, default=180)
    create = sub.add_parser("create")
    create.add_argument("--seconds", type=int, default=3600)
    execute = sub.add_parser("exec")
    execute.add_argument("--command", required=True)
    execute.add_argument("--timeout", type=int, default=60)
    for kind in ("write", "read"):
        transfer = sub.add_parser(kind)
        transfer.add_argument("--local", required=True)
        transfer.add_argument("--remote", required=True)
    sub.add_parser("close")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == "init":
        print(json.dumps(initialize(root, args.challenge, max_minutes=args.budget_minutes)))
        return
    context = open_context(root)
    if not context:
        raise SystemExit("initialize an authorized analysis context first")
    rid = context["run_id"]
    op = "analysis_" + uuid.uuid4().hex[:12]
    if args.action == "create":
        result = sandboxes.create(rid, op, {"image": "registry.dp.tech/dptech/ubuntu:20.04-py3.10",
                                           "cpu": "4c8g", "timeout": args.seconds})
        if result["status"] == "active":
            context["sandbox_id"] = result["sandbox_id"]
            (root / "session.json").write_text(json.dumps(context, indent=2) + "\n")
    elif args.action == "exec":
        result = sandboxes.execute(rid, context["sandbox_id"], args.command, args.timeout, op)
    elif args.action in ("write", "read"):
        result = sandboxes.transfer(rid, args.action, context["sandbox_id"], args.remote,
                                    local_path=args.local, operation_id=op)
    else:
        result = {"sandboxes": sandboxes.cleanup_run(rid)}
        if not sandboxes.list_run(rid)["active_or_unknown"]:
            db.execute("UPDATE runs SET phase='finished',ended_at=? WHERE id=?", (db.utcnow(), rid))
            db.execute("UPDATE trials SET status='completed' WHERE id=?", (context["trial_id"],))
            db.append_event(rid, "controller", "analysis.finished", {"models_started": False})
    receipts = root / "receipts"
    receipts.mkdir(exist_ok=True)
    (receipts / (op + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    summary = {key: value for key, value in result.items() if key != "receipt"}
    try:
        payload = json.loads(result["receipt"]["stdout"])
        data = payload.get("data", payload)
        summary.update({key: data[key] for key in ("stdout", "stderr", "exit_code") if key in data})
    except (KeyError, ValueError, TypeError):
        pass
    summary["receipt_path"] = str(receipts / (op + ".json"))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
