"""Fail delivery on configured credentials, ignored raw data, or size excess."""
import csv
import io
import json
import argparse
import subprocess
import tempfile
from pathlib import Path

from .common import DEFAULT_DATA,Redactor,unzstd
from .dataset import duckdb_module


def audit_value(value):
    """Restore two typed public JSON columns before signature checking.

    Resource keys and scientific answer tokens are public identifiers. Flattening
    them into strings must not erase the existing narrowly scoped exceptions.
    Provider-key/Bearer/JWT patterns inside their values remain checked.
    """
    if isinstance(value,list):return [audit_value(v) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        if key in ('resources','raw.resultsJson.answers') and isinstance(item,str):
            try:parsed=json.loads(item)
            except ValueError:parsed=None
            if isinstance(parsed,list):
                item={'resources':parsed} if key=='resources' else {'resultsJson':{'answers':parsed}}
        result[key]=audit_value(item)
    return result


def index_snapshot(root):
    """Freeze the index object IDs once; later working-tree writes cannot pass audit."""
    result={}
    for entry in subprocess.check_output(['git','ls-files','--stage','-z'],cwd=root).split(b'\0'):
        if not entry:continue
        metadata,name=entry.split(b'\t',1);mode,digest,stage=metadata.split()
        if mode not in [b'100644',b'100755'] or stage!=b'0':raise ValueError('Unexpected index entry')
        path=root/name.decode()
        if any(part in ['.raw','.local','.git'] for part in path.relative_to(root).parts):
            raise ValueError('Ignored raw path in Git index')
        result[path]=digest.decode()
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--index',action='store_true');args=parser.parse_args()
    root=DEFAULT_DATA;redactor=Redactor();total=0;files=0;issues=[]
    paths=[p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts
           and '.raw' not in p.relative_to(root).parts and '.local' not in p.relative_to(root).parts] if not args.index else []
    staged={}
    if args.index:
        staged=index_snapshot(root);paths=list(staged)
    def inspect(value,path):
        value=audit_value(value)
        text=json.dumps(value,ensure_ascii=False)
        if any(s in text for s in redactor.known) or any(e in text.lower() for e in redactor.ours):
            issues.append({'path':str(path.relative_to(root)),'kind':'configured_credential_or_mailbox'})
        local=redactor.fork()
        if local.obj(value)!=value:
            issues.append({'path':str(path.relative_to(root)),'kind':'redaction_signature_survived','counts':dict(local.counts)})
    for path in paths:
        data=subprocess.check_output(['git','cat-file','blob',staged[path]],cwd=root) if args.index else path.read_bytes()
        size=len(data);total+=size;files+=1
        if size>=90_000_000:issues.append({'path':str(path.relative_to(root)),'kind':'file_size'})
        if path.suffix=='.parquet':
            with tempfile.TemporaryDirectory(dir=root/'.local') as temp:
                copy=Path(temp)/'staged.parquet';copy.write_bytes(data);copy.chmod(0o600)
                with duckdb_module().connect() as connection:
                    result=connection.execute('SELECT * FROM read_parquet(?)',[str(copy)])
                    fields=[r[0] for r in result.description]
                    inspect(fields,path)
                    while rows:=result.fetchmany(500):
                        inspect([{key:value for key,value in zip(fields,row) if value is not None} for row in rows],path)
        else:
            raw=unzstd(data) if path.suffix=='.zst' else data
            text=raw.decode('utf-8',errors='replace')
            if path.suffix=='.csv':inspect(list(csv.DictReader(io.StringIO(text))),path)
            elif path.name.endswith(('.jsonl','.jsonl.zst')):inspect([json.loads(line) for line in text.splitlines() if line.strip()],path)
            else:
                try:value=json.loads(text)
                except ValueError:value=text
                inspect(value,path)
    if total>=1_000_000_000:issues.append({'kind':'repository_size'})
    print(json.dumps({'files':files,'bytes':total,'issues':issues,'audit_scope':'staged_git_blobs' if args.index else 'current_tree'}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
