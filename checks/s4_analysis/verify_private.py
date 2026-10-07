"""Fail delivery on configured credentials, ignored raw data, or size excess."""
import csv
import io
import json
from pathlib import Path

from .common import DEFAULT_DATA,Redactor,unzstd
from .dataset import duckdb_module


def main():
    root=DEFAULT_DATA;redactor=Redactor();total=0;files=0;issues=[]
    paths=[p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts
           and '.raw' not in p.relative_to(root).parts and '.local' not in p.relative_to(root).parts]
    def inspect(value,path):
        text=json.dumps(value,ensure_ascii=False)
        if any(s in text for s in redactor.known) or any(e in text.lower() for e in redactor.ours):
            issues.append({'path':str(path.relative_to(root)),'kind':'configured_credential_or_mailbox'})
        local=redactor.fork()
        if local.obj(value)!=value:
            issues.append({'path':str(path.relative_to(root)),'kind':'redaction_signature_survived','counts':dict(local.counts)})
    for path in paths:
        size=path.stat().st_size;total+=size;files+=1
        if size>=90_000_000:issues.append({'path':str(path.relative_to(root)),'kind':'file_size'})
        if path.suffix=='.parquet':
            with duckdb_module().connect() as connection:
                result=connection.execute('SELECT * FROM read_parquet(?)',[str(path)])
                while rows:=result.fetchmany(500):
                    fields=[r[0] for r in result.description]
                    inspect([dict(zip(fields,row)) for row in rows],path)
        else:
            raw=unzstd(path.read_bytes()) if path.suffix=='.zst' else path.read_bytes()
            text=raw.decode('utf-8',errors='replace')
            if path.suffix=='.csv':inspect(list(csv.DictReader(io.StringIO(text))),path)
            elif path.name.endswith(('.jsonl','.jsonl.zst')):inspect([json.loads(line) for line in text.splitlines() if line.strip()],path)
            else:
                try:value=json.loads(text)
                except ValueError:value=text
                inspect(value,path)
    if total>=1_000_000_000:issues.append({'kind':'repository_size'})
    print(json.dumps({'files':files,'bytes':total,'issues':issues}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
