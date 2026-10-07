"""Audit an added embedded-token rule across persisted, already-sanitized data."""
import io
import json
import re
import zipfile
from collections import Counter

from .collect_bundles import redact_member
from .common import DEFAULT_DATA,Redactor,atomic,sha,unzstd,utcnow,write_json,zstd
from .dataset import duckdb_module

MARKER=re.compile(rb'envd[_-]?(?:access[_-]?)?token',re.I)


def main():
    root=DEFAULT_DATA;redactor=Redactor();scanned=0;changes=[];failures=[];counts=Counter()
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '.git' in path.relative_to(root).parts:continue
        scanned+=1
        try:
            if path.suffix=='.parquet':
                with duckdb_module().connect() as c:
                    result=c.execute('SELECT * FROM read_parquet(?)',[str(path)])
                    while rows:=result.fetchmany(100):
                        if any(MARKER.search(str(value).encode()) for row in rows for value in row if value is not None):
                            # Do not alter a table without preserving its schema/types.
                            # Source regeneration is required if a real token survives.
                            for row in rows:
                                for value in row:
                                    if isinstance(value,str) and MARKER.search(value.encode()) and redactor.fork().text(value)!=value:
                                        failures.append({'path':str(path.relative_to(root)),'kind':'parquet_requires_source_regeneration'})
                continue
            if path.suffix=='.zip':
                output=io.BytesIO();changed=False;local=redactor.fork();members=[]
                with zipfile.ZipFile(path) as source,zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as target:
                    for info in source.infolist():
                        data=source.read(info);clean=data
                        if MARKER.search(data):clean,_=redact_member(data,local)
                        changed|=clean!=data;target.writestr(info,clean)
                        members.append({'path':info.filename,'sanitized_bytes':len(clean),'sanitized_sha256':sha(clean),'newly_redacted':clean!=data})
                if changed:
                    cleaned=output.getvalue();atomic(path,cleaned)
                    inventory=root/'data/bundle_inventories'/(path.stem+'.json')
                    if inventory.exists():
                        value=json.loads(inventory.read_text());by_path={m['path']:m for m in members}
                        for member in value['files']:
                            fresh=by_path[member['path']];member.update(sanitized_bytes=fresh['sanitized_bytes'],sanitized_sha256=fresh['sanitized_sha256'],redacted=member['redacted'] or fresh['newly_redacted'])
                        value['index'].update(sanitized_bytes=len(cleaned),sanitized_sha256=sha(cleaned),redactions=value['index']['redactions']+sum(local.counts.values()))
                        tally=Counter(value.get('redactions',{}));tally.update(local.counts);value['redactions']=dict(tally);write_json(inventory,value)
                    changes.append({'path':str(path.relative_to(root)),'kind':'zip_rescrubbed'});counts.update(local.counts)
                continue
            raw=path.read_bytes();decoded=unzstd(raw) if path.suffix=='.zst' else raw
            if not MARKER.search(decoded):continue
            local=redactor.fork();clean,_=redact_member(decoded,local)
            if clean!=decoded:
                atomic(path,zstd(clean) if path.suffix=='.zst' else clean)
                if path.parent==root/'.raw/http' and path.name.endswith('.json.zst'):
                    meta=path.with_name(path.name.removesuffix('.json.zst')+'.meta.json')
                    if meta.exists():
                        value=json.loads(meta.read_text());tally=Counter(value.get('redactions',{}));tally.update(local.counts)
                        value.update(sanitized_sha256=sha(clean),redactions=dict(tally),redaction_revision=3,rescrubbed_at=utcnow());write_json(meta,value)
                changes.append({'path':str(path.relative_to(root)),'kind':'rescrubbed'});counts.update(local.counts)
        except Exception as exc:failures.append({'path':redactor.text(str(path.relative_to(root))),'kind':type(exc).__name__})
        if scanned%2000==0:print(json.dumps({'scanned':scanned,'changed':len(changes),'failures':len(failures)}),flush=True)
    report={'scanned_files':scanned,'changed_files':len(changes),'changes':changes,'redactions':dict(counts),'failures':failures,'observed_at':utcnow(),
       'scope':'Added envd embedded-text signature; full configured/pattern audit remains separate'}
    write_json(root/'data/privacy_rescan_revision3.json',report);print(json.dumps(report),flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
