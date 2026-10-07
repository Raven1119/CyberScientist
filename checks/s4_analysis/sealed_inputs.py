"""Reuse existing pure trace_diagnostics input/selection, never backend imports.

Only declared execution.artifacts are submission evidence. Trace conversion uses
the hash-pinned official CLI and its existing deterministic precedence patch.
No downloaded scientific code is run and all network primitives are disabled.
"""
import importlib.util
import io
import json
import sys
import tempfile
import types
import zipfile
from pathlib import Path,PurePosixPath

from .common import DEFAULT_DATA,atomic,sha,utcnow,write_json,zstd


def pure_diagnostics():
    name='_s4_readonly_pure'
    if name+'.trace_diagnostics' in sys.modules:return sys.modules[name+'.trace_diagnostics']
    source=Path(__file__).resolve().parents[2]/'src/cyberscientist'
    package=types.ModuleType(name);package.__path__=[str(source)];sys.modules[name]=package
    for module in ['trace_selection','trace_diagnostics']:
        spec=importlib.util.spec_from_file_location(name+'.'+module,source/(module+'.py'))
        result=importlib.util.module_from_spec(spec);sys.modules[spec.name]=result;spec.loader.exec_module(result)
    return sys.modules[name+'.trace_diagnostics']


def prepare(root,aid,trace_override=None,metadata=None):
    root=Path(root);archive=root/'.raw/bundles'/(aid+'.zip');buffer=archive.read_bytes();digest=sha(buffer)
    diag=pure_diagnostics()
    with zipfile.ZipFile(io.BytesIO(buffer)) as z:
        if len(z.namelist())!=len(set(z.namelist())):raise ValueError('duplicate_sanitized_zip_member')
        files={i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}
    prefix=diag.trace_selection.bundle_root(files);manifest_source=prefix+'arm_manifest.json';alias=False
    if manifest_source not in files and prefix+'manifest.json' in files:
        legacy=json.loads(files[prefix+'manifest.json'])
        if not isinstance(legacy,dict) or legacy.get('arm_version') not in ('1.0','1.1') or not isinstance(legacy.get('execution'),dict):
            raise ValueError('legacy_manifest_not_verified_arm_structure')
        # Read-only normalized view. The original ZIP/file name is untouched.
        # Public bundle/manifest for calibration 23535 exposes this legacy ARM's
        # modality coverage; it has a valid manifest.json, not arm_manifest.json.
        manifest_source=prefix+'manifest.json';files[prefix+'arm_manifest.json']=files[manifest_source];alias=True
    selected=diag.trace_selection.select(files)
    if trace_override is None and (not selected.readable or not selected.rows or selected.unresolved_claims):
        raise ValueError('sealed_selected_trace_missing_unreadable_or_unresolved')
    rows=trace_override if trace_override is not None else list(selected.rows)
    adapted=diag._adapter_fields(rows)
    normalized=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in adapted).encode()
    identity=sha(normalized+digest.encode()+b'sealed-inputs-v2')
    directory=root/'.raw/sealed_v6_inputs'/aid/identity;directory.mkdir(parents=True,exist_ok=True)
    receipt=directory/'receipt.json'
    if receipt.exists():
        cached=json.loads(receipt.read_text())
        if metadata:
            cached.update({k:metadata.get(k) for k in ['challenge_id','ours']});write_json(receipt,cached)
            write_json(root/'scorer/sealed_input_provenance'/(aid+'.json'),cached)
        return cached
    original=directory/'selected.jsonl';converted=directory/'converted.jsonl';atomic(original,normalized)
    node=diag._binary('node')
    with tempfile.TemporaryDirectory(prefix='converter-',dir=directory) as temporary:
        isolated=Path(temporary);cli=diag._patched_cli(isolated);env=diag._env(isolated,node)
        diag._run([str(node),str(cli),'trace','convert','--trace',str(original),'--out',str(converted)],env,timeout=120)
    converted_rows=[json.loads(line) for line in converted.read_text().splitlines() if line.strip()]
    if not converted_rows:raise ValueError('official_converter_returned_no_events')
    arm_input=all(isinstance(row.get('step_type'),str) for row in rows)
    if arm_input and diag._tool_counts(converted_rows)!=diag._tool_counts(rows):
        raise ValueError('official_conversion_changed_arm_rows_or_tool_pair_counts')
    manifest=json.loads(files[selected.bundle_root+'arm_manifest.json'])
    execution=manifest.get('execution');execution=execution if isinstance(execution,dict) else {}
    declared=execution.get('artifacts');declared=declared if isinstance(declared,list) else []
    outputs={};missing=[]
    for item in declared:
        path=item.get('path') if isinstance(item,dict) else None
        if not isinstance(path,str):continue
        parts=PurePosixPath(path)
        if parts.is_absolute() or '..' in parts.parts or '\\' in path:raise ValueError('unsafe_declared_artifact_path')
        member=selected.bundle_root+path
        if member not in files:missing.append(path);continue
        outputs[path]=files[member]
    if len(outputs)>500 or sum(map(len,outputs.values()))>diag.MAX_OUTPUT_EVIDENCE_BYTES:
        raise ValueError('declared_output_evidence_limit')
    out=directory/'outputs';out.mkdir(exist_ok=True)
    for path,data in outputs.items():atomic(out/path,data)
    rawtrace=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows).encode()
    atomic(root/'.raw/bundle_selected_traces'/(aid+'.jsonl.zst'),zstd(rawtrace))
    provenance={'attempt_id':aid,'input_revision':'sealed-protocol-v2','source':'sanitized_downloaded_archive',
       'archive_sanitized_sha256':digest,'selected_members':list(selected.selected_members),'selection_rule':selected.rule,
       'manifest_source_path':manifest_source,'manifest_source_sha256':sha(files[manifest_source]),'virtual_legacy_manifest_alias':alias,
       'selected_trace_sha256':sha(rawtrace),'selected_rows':len(rows),'converted_rows':len(converted_rows),
       'converted_trace_sha256':sha(converted.read_bytes()),'official_cli_sha256':diag.CLI_SHA,'patched_cli_sha256':diag.PATCHED_SHA,
       'adapter_labels_added':sum(a!=b for a,b in zip(adapted,rows)),'arm_count_preservation_checked':arm_input,
       'provided_trace_override':trace_override is not None,
       'declared_output_files':len(outputs),'declared_output_bytes':sum(map(len,outputs.values())),
       'missing_declared_artifact_paths':missing,'outputs_source':'execution.artifacts only; no synthetic outputs',
       'converted_path':str(converted),'output_directory':str(out),'observed_at':utcnow(),
       'platform_worker_input_parity':'unknown; public archive and worker normalized input are not equated'}
    if metadata:provenance.update({k:metadata.get(k) for k in ['challenge_id','ours']})
    write_json(receipt,provenance);write_json(root/'scorer/sealed_input_provenance'/(aid+'.json'),provenance)
    return provenance


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('attempt_id');args=parser.parse_args()
    result=prepare(DEFAULT_DATA,args.attempt_id)
    print(json.dumps({k:result[k] for k in ['attempt_id','selected_rows','converted_rows','declared_output_files']}))
