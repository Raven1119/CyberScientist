"""Deterministically seal the exact ARM bytes used by local admission and upload."""
from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from . import trace_narrative, trace_projection, trace_selection

TRACE = "traces/cyberscientist_merged.jsonl"
DATA = "provenance/data_inputs.json"
OUTPUT_PACKAGE_INSTRUCTION = ('结果包只放题面输出契约中的文件，包内路径与契约一致（去掉开头的 /app/）；'
                              '清单和轨迹由系统补齐，不要自己编写轨迹文件、叙述文件或 ARM 清单。')


def _supply_manifest(files: dict[str, bytes], run_id: str) -> dict[str, bytes]:
    root=trace_selection.bundle_root(files)
    if root+'arm_manifest.json' in files:
        return files
    # An outputs-only archive has no wrapper directory. Retain support for a
    # conventional single wrapper that contains outputs/, but never call
    # outputs/ itself the ARM bundle root.
    if root in ('outputs/','app/','traces/','trace/','provenance/') or not any(
            name.startswith(root+'outputs/') for name in files):
        root=''
    from . import artifact_contracts, submission_outputs
    facts=artifact_contracts.for_run(run_id)
    contract=submission_outputs.contract_for_run(run_id)
    paths=(contract or {}).get('paths') or [name[len(root):] for name in files
        if name.startswith(root+'outputs/') and not name.endswith('/')]
    paths=sorted({submission_outputs.source_path(path) for path in paths})
    if not paths:
        raise ValueError('缺少题面输出契约和 outputs 产物，无法生成结果清单')
    manifest={'arm_version':'1.1','paper':{'title':facts['title']},
              'entrypoint':'','expected_outputs':[
                  {'name':path,'path':path,'type':'data'} for path in paths]}
    return files | {root+'arm_manifest.json':json.dumps(
        manifest,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()}


def preflight_files(files: dict[str, bytes]) -> list[str]:
    """Check observed server constraints without changing scientific content."""
    root = trace_selection.bundle_root(files)
    manifest = json.loads(files[root + 'arm_manifest.json'])
    errors = []
    handoff = manifest.get('handoff')
    # Public schema permits complete, but the actual upload validator rejects
    # it (CS-RH-01); preserve the discrepancy and ask the author to resolve it.
    if isinstance(handoff, dict) and handoff.get('status') == 'complete':
        errors.append('handoff.status=complete 被真实上传校验拒绝；请省略该可选字段，或按实际交接状态填写 partial/stuck/failed')
    char = manifest.get('characterization')
    path = char.get('path') if isinstance(char, dict) else char if isinstance(char, str) else None
    if path is not None and (not isinstance(path, str) or path.startswith('/')
            or '..' in path.split('/') or '\\' in path or root + path not in files):
        errors.append('characterization.path 必须指向包内有效 JSON；否则缺少 characterization modality')
    elif path is not None:
        try:
            if not isinstance(json.loads(files[root + path]), dict): raise ValueError()
        except (ValueError, UnicodeDecodeError):
            errors.append('characterization modality 的文件须为 JSON 对象')
    return errors


def seal(source: bytes, run_id: str, trial_id: str | None, through_seq: int,
         data_inputs: dict[str, Any] | None = None, *,
         narrative_bytes: bytes | None = None,
         narrative_written_at: str | None = None) -> tuple[bytes, list[dict[str, Any]]]:
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive member")
        files = {name: archive.read(name) for name in names}
    files = _supply_manifest(files, run_id)
    errors = preflight_files(files)
    if errors:
        raise ValueError('; '.join(errors))
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
    from . import native_logs
    native = native_logs.snapshot(run_id, trial_id)
    if native is not None:
        raw_name = root + 'raw_messages.jsonl'
        if raw_name in files and files[raw_name] != native['bytes']:
            raise ValueError('提交包原生日志与最终Trial原始字节不符；不能重写或借用其他会话')
        files[raw_name] = native['bytes']
        manifest['raw_messages'] = 'raw_messages.jsonl'
        files[root + 'provenance/native_session.json'] = json.dumps(
            {key: value for key, value in native.items() if key != 'bytes'},
            ensure_ascii=False, sort_keys=True).encode()

    relative_files = {name[len(selected.bundle_root):]: raw for name, raw in files.items()
                      if name.startswith(selected.bundle_root)}
    steps = trace_projection.project(run_id, trial_id, through_seq, relative_files)
    if narrative_bytes is None:
        merged = [*selected.rows, *steps]
    else:
        narrative_name = root + "traces/trace_narrative.jsonl"
        if narrative_name in files:
            raise trace_narrative.InvalidTraceNarrative(
                ["提交包已包含保留的 traces/trace_narrative.jsonl 路径"])
        narrative_rows, uncovered = trace_narrative.validate(
            narrative_bytes, run_id, through_seq, relative_files, steps,
            narrative_written_at)
        merged = [*narrative_rows, *uncovered]
        files[narrative_name] = narrative_bytes
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
    return output.getvalue(), merged if narrative_bytes is not None else steps
