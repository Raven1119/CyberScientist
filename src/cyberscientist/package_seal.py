"""Deterministically seal the exact ARM bytes used by local admission and upload."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

from . import trace_projection

TRACE = "traces/cyberscientist_events.jsonl"
DATA = "provenance/data_inputs.json"


def seal(source: bytes, run_id: str, trial_id: str | None, through_seq: int,
         data_inputs: dict[str, Any] | None = None) -> tuple[bytes, list[dict[str, Any]]]:
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    if TRACE in files or DATA in files:
        raise ValueError("sealed package reserved path collision")
    manifest = json.loads(files["arm_manifest.json"])
    steps = trace_projection.project(run_id, trial_id, through_seq, files)
    files[TRACE] = ("\n".join(json.dumps(s, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for s in steps) + "\n").encode()
    files[DATA] = json.dumps(data_inputs or {"evidence_class": "unknown", "materializations": []},
                             ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    trace = manifest.setdefault("trace", {})
    trace["files"] = sorted(set(trace.get("files", [])) | {TRACE})
    trace["step_count"] = int(trace.get("step_count") or 0) + len(steps)
    files["arm_manifest.json"] = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                              separators=(",", ":")).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[name])
    return output.getvalue(), steps
