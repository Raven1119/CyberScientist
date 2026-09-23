"""Read-only, redacted audit capture for one real Run; never drives research.

Snapshots are content-addressed and an append-only index chains their hashes.
This detects local changes; it is not an external signature or tamper-proof store.
Private reasoning and credentials are deliberately excluded from exports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SENSITIVE_KEYS = re.compile(r'^(?:password|secret|secret_value|api_key|apikey|access_key|accesskey|authorization|bearer|token|cs_tool_token)$', re.I)
PRIVATE_TYPES = {'brain.raw_output', 'prime.reasoning', 'reasoning', 'agent_reasoning', 'reasoning_summary'}
PRIVATE_NORMALIZED = {re.sub(r'[^a-z]', '', t.lower()) for t in PRIVATE_TYPES}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def capture(run_id, out):
    from cyberscientist.bohr_proxy import redact
    secrets_path = ROOT / '.cyberscientist/secrets.json'
    values = list(json.loads(secrets_path.read_text()).values()) if secrets_path.exists() else []
    values += [v for k, v in os.environ.items() if SENSITIVE_KEYS.match(k) or k.endswith(('_API_KEY', '_ACCESS_TOKEN', '_ACCESS_KEY'))]
    values = [v for v in values if isinstance(v, str) and len(v) >= 8]

    def clean(obj):
        if isinstance(obj, dict):
            private_type=re.sub(r'[^a-z]', '', str(obj.get('type','')).lower()) in PRIVATE_NORMALIZED
            if private_type or (obj.get('role')=='assistant' and obj.get('channel')=='analysis'):
                envelope={k:obj[k] for k in ('type','seq','event_id','run_id','trial_id','occurred_at','recorded_at','timestamp','source') if k in obj}
                return {**envelope, 'excluded':'private reasoning or raw model output', 'original_sha256':digest(encoded(obj))}
            return {k:'[REDACTED]' if SENSITIVE_KEYS.match(k) else clean(v) for k,v in obj.items()}
        if isinstance(obj, list):
            return [clean(v) for v in obj]
        if isinstance(obj, str):
            return redact(obj, values)
        return obj

    out.mkdir(parents=True, exist_ok=True)
    objects = out / 'objects'
    objects.mkdir(exist_ok=True)

    def put(data):
        key=digest(data)
        dest=objects/key
        if not dest.exists():
            with dest.open('xb') as f:
                f.write(data)
        return key

    conn=sqlite3.connect(f'file:{ROOT}/.cyberscientist/cyberscientist.db?mode=ro', uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute('BEGIN')
    run=conn.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
    if not run:
        raise ValueError(f'Unknown Run {run_id}')
    run=dict(run)
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    state={}
    for table in tables:
        if not re.fullmatch(r'[a-z_]+',table) or table in {'capability_tokens','mailboxes'}:
            continue
        columns={r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
        if 'run_id' in columns:
            rows=conn.execute(f'SELECT * FROM {table} WHERE run_id=?',(run_id,)).fetchall()
        elif table=='runs':
            rows=[run]
        elif table=='challenges':
            rows=conn.execute('SELECT * FROM challenges WHERE id=?',(run['challenge_id'],)).fetchall()
        else:
            continue
        state[table]=[]
        for row in rows:
            item=dict(row)
            if table=='events' and item['type'] in PRIVATE_TYPES:
                item['payload']={'excluded':'private reasoning or raw model output','original_sha256':digest(item['payload'].encode())}
            for k,v in list(item.items()):
                if isinstance(v,str) and v[:1] in ('{','['):
                    try:item[k]=json.loads(v)
                    except ValueError:pass
            state[table].append(clean(item))
    conn.rollback()
    conn.close()
    stamp=datetime.now(timezone.utc).isoformat()
    entries={'database_state':put(encoded(state))}
    # Preserve evolving scripts and evidence, not just their current paths.
    # Large outputs are chunked so appending a log does not duplicate it in full.
    artifacts=[]
    skip_dirs={'.git','.venv','node_modules','__pycache__'}
    for base in (ROOT/'workspace/runs'/run_id/'trials', ROOT/'workspace/challenges'/run['challenge_id']):
        for directory, dirs, files in os.walk(base):
            dirs[:]=[d for d in dirs if d not in skip_dirs and not (Path(directory)/d).is_symlink()]
            for name in files:
                path=Path(directory)/name
                if path.is_symlink():
                    continue
                before=path.stat()
                item={'path':str(path.relative_to(ROOT)),'bytes':before.st_size,'mtime_ns':before.st_mtime_ns}
                if name in {'.env','secrets.json','auth.json'} or name.endswith(('.pem','.key')):
                    item['excluded']='credential-bearing filename'
                else:
                    original=hashlib.sha256()
                    chunks=[]
                    with path.open('rb') as f:
                        while chunk:=f.read(4*1024*1024):
                            original.update(chunk)
                            if any(v.encode() in chunk for v in values):
                                item['excluded']='known secret value; source preserved in restricted workspace'
                                chunks=[]
                                break
                            try:
                                value=chunk.decode('utf-8')
                            except UnicodeDecodeError:
                                safe=chunk
                            else:
                                safe=redact(value,values).encode()
                            chunks.append(put(safe))
                    if 'excluded' not in item:
                        item.update(original_sha256=original.hexdigest(),chunks=chunks)
                after=path.stat()
                item['stable_during_read']=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
                artifacts.append(item)
    entries['workspace_artifacts']=put(encoded(artifacts))
    entries['collector_sha256']=COLLECTOR_SOURCE_SHA256
    source_before=out.parent/'source-before.json'
    if source_before.exists():
        baseline=json.loads(source_before.read_text())['files']
        current={p:digest((ROOT/p).read_bytes()) if (ROOT/p).is_file() else None for p in baseline}
        entries['runtime_source_hashes']=put(encoded(current))
        changes=[p for p in baseline if baseline[p]!=current[p]]
    else:
        changes=[]
    # Only inspect native sessions belonging to this Run/this fresh challenge.
    allowed={str(ROOT/'workspace/runs'/run_id/'brain_view'),str(ROOT/'workspace/challenges'/run['challenge_id'])}
    session_root=Path.home()/'.codex/sessions'
    sessions=[]
    for path in session_root.glob('*/*/*/*.jsonl'):
        if path.stat().st_mtime < datetime.fromisoformat(run['created_at']).timestamp()-2:
            continue
        with path.open() as f:
            first=f.readline()
            try:meta=json.loads(first)
            except ValueError:continue
            payload=meta.get('payload') or {}
            if meta.get('type')!='session_meta' or payload.get('cwd') not in allowed:
                continue
            records=[clean(meta)]
            partial=0
            for line in f:
                if not line.endswith('\n'):
                    partial+=1
                    continue
                try:records.append(clean(json.loads(line)))
                except ValueError:partial+=1
        sessions.append({'session_id':payload.get('id'),'cwd':payload.get('cwd'),'source_path':str(path),'records':len(records),'incomplete_lines':partial,'object':put(b'\n'.join(encoded(r) for r in records)+b'\n')})
    entries['native_public_sessions']=sessions
    index=out/'index.jsonl'
    previous=None
    if index.exists():
        with index.open('rb') as f:
            lines=f.read().splitlines()
        if lines:previous=json.loads(lines[-1])['record_sha256']
    record={'captured_at':stamp,'run_id':run_id,'phase':run['phase'],'latest_seq':max((e['seq'] for e in state.get('events',[])),default=0),'entries':entries,'runtime_source_changes':changes,'previous_record_sha256':previous}
    record['record_sha256']=digest(encoded(record))
    with index.open('ab') as f:
        f.write(encoded(record)+b'\n')
        f.flush()
        os.fsync(f.fileno())
    (out/'latest.json').write_bytes(encoded(record)+b'\n')
    print(json.dumps({k:record[k] for k in ['captured_at','run_id','phase','latest_seq','runtime_source_changes']},ensure_ascii=False),flush=True)
    return run['phase']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run_id')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--watch',action='store_true')
    p.add_argument('--interval',type=float,default=60)
    args=p.parse_args()
    while True:
        try:
            phase=capture(args.run_id,args.output)
        except Exception as exc:
            if not args.watch:
                raise
            error={'captured_at':datetime.now(timezone.utc).isoformat(),'run_id':args.run_id,'error_type':type(exc).__name__,'capture_complete':False}
            args.output.mkdir(parents=True,exist_ok=True)
            with (args.output/'capture-errors.jsonl').open('a') as f:
                f.write(json.dumps(error)+'\n')
            print(json.dumps(error),flush=True)
            time.sleep(max(10,args.interval))
            continue
        if not args.watch or phase in {'finished','failed','cancelled'}:
            break
        time.sleep(max(10,args.interval))


if __name__=='__main__':
    main()
