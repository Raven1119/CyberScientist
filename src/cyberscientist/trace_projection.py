"""Project durable run events into auditable ARM steps, without inventing actions."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import config, db
from .bohr_proxy import redact
from .mailbox_platform import public_feedback


def _safe(value: Any) -> str:
    raw = str(value or "")[:4000]
    secrets = list(config.load_secrets().values())
    return redact(public_feedback(raw, *secrets), secrets)


def project(run_id: str, trial_id: str | None, through_seq: int,
            package_files: dict[str, bytes]) -> list[dict[str, Any]]:
    """Only rows at or before through_seq from this Run can become steps."""
    rows = db.query("SELECT seq,recorded_at,type,payload,trial_id FROM events"
                    " WHERE run_id=? AND seq<=? ORDER BY seq", (run_id, through_seq))
    calls: set[str] = set()
    results: set[str] = set()
    steps: list[dict[str, Any]] = []
    for row in rows:
        if trial_id and row["trial_id"] not in (None, trial_id):
            continue
        payload = json.loads(row["payload"])
        kind = row["type"]
        base = {"timestamp": row["recorded_at"], "cs_ref": f"{run_id}#{row['seq']}"}
        if kind == "prime.execution.progress" and payload.get("item_id"):
            item = _safe(payload["item_id"])
            status = str(payload.get("status", "")).lower()
            if status in ("started", "running", "in_progress", "inprogress", "in-progress") and item not in calls:
                calls.add(item)
                steps.append(base | {"step_type": "tool_call", "tool_call_id": item,
                                     "title": _safe(payload.get("detail"))})
            elif status in ("completed", "failed") and item not in results:
                results.add(item)
                steps.append(base | {"step_type": "tool_result", "tool_call_id": item,
                                     "title": _safe(payload.get("detail")),
                                     "tool_output": _safe(payload.get("output")),
                                     "exit_code": payload.get("exit_code")
                                     if type(payload.get("exit_code")) is int else None})
                if status == "failed":
                    steps.append(base | {"step_type": "error", "title": "Tool failed",
                                         "body": _safe(payload.get("detail"))})
        elif kind == "job.accepted" and payload.get("operation_id"):
            op = str(payload["operation_id"])
            job = db.query_one("SELECT spec_json FROM compute_jobs WHERE run_id=? AND operation_id=?",
                               (run_id, op))
            spec = json.loads(job["spec_json"]) if job else {}
            steps.append(base | {"step_type": "tool_call", "tool_call_id": "job:" + op,
                                 "title": "Bohrium Job accepted", "code": _safe(spec.get("command"))})
        elif kind == "job.observed" and payload.get("status") in ("Finished", "Failed", "Stopped"):
            op = str(payload.get("operation_id") or "")
            steps.append(base | {"step_type": "tool_result", "tool_call_id": "job:" + op,
                                 "title": "Bohrium Job terminal state",
                                 "tool_output": _safe(f"Job {payload.get('platform_job_id')} status {payload.get('status')}; Finished does not prove scientific success")})
        elif kind in ("job.not_started", "job.unknown"):
            steps.append(base | {"step_type": "error" if kind == "job.not_started" else "observation",
                                 "title": kind, "body": _safe(payload.get("error") or payload.get("reason"))})
        elif kind == "checkpoint.created":
            steps.append(base | {"step_type": "observation", "title": "Checkpoint " + _safe(payload.get("checkpoint_id")),
                                 "body": _safe(payload.get("report_excerpt"))})
        elif kind in ("trial.created", "brain.decision", "guidance.delivered"):
            steps.append(base | {"step_type": "decision", "title": kind,
                                 "body": _safe(payload.get("goal") or payload.get("summary") or payload.get("reason"))})
        elif kind == "prime.reasoning.summary":
            steps.append(base | {"step_type": "thought", "title": "Recorded reasoning summary",
                                 "body": _safe(payload.get("summary"))})
    # Artifact steps require an actual file and an actual manifest declaration.
    try:
        manifest = json.loads(package_files["arm_manifest.json"])
        artifacts = manifest.get("execution", {}).get("artifacts", [])
    except (KeyError, ValueError, TypeError):
        artifacts = []
    for artifact in artifacts:
        path = artifact.get("path") if isinstance(artifact, dict) else None
        if isinstance(path, str) and path in package_files:
            steps.append({"step_type": "artifact", "title": path, "artifact_path": path,
                          "sha256": hashlib.sha256(package_files[path]).hexdigest(),
                          "cs_ref": f"{run_id}#{through_seq}"})
    return steps
