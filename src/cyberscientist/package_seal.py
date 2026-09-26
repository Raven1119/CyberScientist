"""Deterministically seal the exact ARM bytes used by local admission and upload."""
from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from . import trace_projection, trace_selection

TRACE = "traces/cyberscientist_merged.jsonl"
DATA = "provenance/data_inputs.json"


def seal(source: bytes, run_id: str, trial_id: str | None, through_seq: int,
         data_inputs: dict[str, Any] | None = None) -> tuple[bytes, list[dict[str, Any]]]:
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive member")
        files = {name: archive.read(name) for name in names}
    root = trace_selection.bundle_root(files)
    trace_name = root + TRACE
    data_name = root + DATA
    manifest_name = root + "arm_manifest.json"
    if trace_name in files or data_name in files:
        raise ValueError("sealed package reserved path collision")
    selected = trace_selection.select(files)
    if not selected.readable:
        raise ValueError("selected trace unreadable")
    manifest = json.loads(files[manifest_name])
    relative_files = {name[len(selected.bundle_root):]: raw for name, raw in files.items()
                      if name.startswith(selected.bundle_root)}
    steps = trace_projection.project(run_id, trial_id, through_seq, relative_files)
    merged = [*selected.rows, *steps]
    files[trace_name] = ("\n".join(json.dumps(s, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) for s in merged) + "\n").encode()
    files[data_name] = json.dumps(data_inputs or {"evidence_class": "unknown", "materializations": []},
                             ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    manifest["trace"] = TRACE
    files[manifest_name] = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                              separators=(",", ":")).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name.endswith('/') else zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if name.endswith('/') else 0o644) << 16
            archive.writestr(info, files[name])
    return output.getvalue(), steps
