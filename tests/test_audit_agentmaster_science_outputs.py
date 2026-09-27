import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "audit_agentmaster_science_outputs", Path(__file__).resolve().parents[1] /
    "checks/audit_agentmaster_science_outputs.py")
audit_module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit_module)


def test_audit_requires_same_bytes_in_submitted_and_sealed_outputs(tmp_path):
    iteration = tmp_path / "iteration"
    sealed = iteration / "workspace_snapshot/outputs"
    live = tmp_path / "live/outputs"
    sealed.mkdir(parents=True)
    live.mkdir(parents=True)
    (sealed / "answer.json").write_text('{"answer": 2}')
    (live / "answer.json").write_bytes((sealed / "answer.json").read_bytes())
    command = iteration / "submission/command.json"
    command.parent.mkdir(parents=True)
    command.write_text(json.dumps({"argv": ["playground", "submit", "--outputs", str(live)]}))
    pair = {"iteration": str(iteration), "attempt_id": "1", "challenge_id": "task",
            "score_is_final": True, "harbor_score": 42, "trace_score": 80,
            "command_record_sha256": hashlib.sha256(command.read_bytes()).hexdigest()}
    result = audit_module.audit(pair)
    assert result["file_count"] == 1
    assert result["harbor_score"] == 42
    assert '"answer": 2' not in json.dumps(result)
    (live / "answer.json").write_text('{"answer": 3}')
    with pytest.raises(ValueError, match="differ"):
        audit_module.audit(pair)


def test_audit_rejects_changed_command_and_symlink(tmp_path):
    iteration = tmp_path / "iteration"
    sealed = iteration / "workspace_snapshot/outputs"
    live = tmp_path / "live/outputs"
    sealed.mkdir(parents=True)
    live.mkdir(parents=True)
    command = iteration / "submission/command.json"
    command.parent.mkdir(parents=True)
    command.write_text(json.dumps({"argv": ["--outputs", str(live)]}))
    pair = {"iteration": str(iteration), "attempt_id": "1", "challenge_id": "task",
            "score_is_final": True, "harbor_score": 42, "trace_score": 80,
            "command_record_sha256": hashlib.sha256(command.read_bytes()).hexdigest()}
    (sealed / "linked").symlink_to(command)
    with pytest.raises(ValueError, match="symlink"):
        audit_module.audit(pair)
    command.write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        audit_module.audit(pair)
