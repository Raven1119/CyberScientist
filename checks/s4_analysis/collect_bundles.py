"""Bound public ZIP downloads, sanitize in memory, publish inventories/docs only."""
import io
import json
import time
import zipfile
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import PurePosixPath

import httpx

from .common import DEFAULT_DATA,ORIGIN,PublicClient,atomic,sha,utcnow,write_json
from .dataset import read_table
from .tables import write_csv

LIMIT=50_000_000
_FETCH_LOCKS=defaultdict(threading.Lock)


def redact_member(original,redactor):
    try:text=original.decode('utf-8');encoding='utf-8'
    except UnicodeDecodeError:
        return redactor.text(original.decode('latin1')).encode('latin1'),'latin1'
    try:obj=json.loads(text)
    except ValueError:obj=None
    if isinstance(obj,(dict,list)):
        clean=redactor.obj(obj)
        return ((json.dumps(clean,ensure_ascii=False)+'\n').encode() if clean!=obj else original),encoding
    if text.lstrip().startswith('{'):
        lines=[]
        for line in text.splitlines(keepends=True):
            try:obj=json.loads(line)
            except ValueError:break
            clean=redactor.obj(obj)
            lines.append(json.dumps(clean,ensure_ascii=False)+'\n' if clean!=obj else line)
        else:return ''.join(lines).encode(),encoding
    return redactor.text(text).encode(),encoding


def download(client,aid):
    for retry in range(7):
        try:
            client.rate()
            with httpx.Client(timeout=120,follow_redirects=False) as connection:
                with connection.stream('GET',ORIGIN+'/api/attempts/'+aid+'/bundle') as response:
                    response.raise_for_status()
                    if int(response.headers.get('content-length') or 0)>LIMIT:
                        raise ValueError('bundle_over_50MB_content_length')
                    raw=bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw)>LIMIT:raise ValueError('bundle_over_50MB_stream')
            return bytes(raw)
        except (httpx.TransportError,httpx.HTTPStatusError) as exc:
            code=getattr(getattr(exc,'response',None),'status_code',None)
            if code==404 and retry==0:
                time.sleep(1)
                continue
            if retry==6 or code is not None and code<500 and code!=429:
                raise RuntimeError(f'bundle_GET_failed status={code} kind={type(exc).__name__} request_attempts={retry+1}') from None
            time.sleep(min(60,2**retry))


def sanitize_archive(raw,redactor):
    inventory=[];docs=[];target=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as output:
        members=source.infolist()
        if len(members)>10000 or sum(i.file_size for i in members)>1_000_000_000:
            raise ValueError('archive_expansion_safety_bound')
        seen=set()
        for info in members:
            path=PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename:
                raise ValueError('unsafe_archive_member_path')
            if info.is_dir():continue
            if info.file_size>100_000_000:raise ValueError('archive_member_over_100MB_expansion_bound')
            original=source.read(info)
            # Even binary members are scanned; modified members remain marked.
            clean,encoding=redact_member(original,redactor)
            clean_name=redactor.text(info.filename)
            if clean_name in seen:raise ValueError('redacted_archive_path_collision')
            seen.add(clean_name);output.writestr(clean_name,clean)
            entry={'path':clean_name,'bytes':len(original),'sha256':sha(original),
                   'sanitized_bytes':len(clean),'sanitized_sha256':sha(clean),'redacted':clean!=original}
            inventory.append(entry)
            name=path.name.lower()
            manifest=name in ('arm_manifest.json','manifest.json','manifest.yaml','manifest.yml')
            description=name.startswith('readme') or name in ('description.md','description.txt','notes.md','report.md')
            if (manifest or description) and len(clean)<20000 and encoding=='utf-8':
                docs.append({'path':clean_name,'text':clean.decode(),'kind':'manifest' if manifest else 'description'})
    return target.getvalue(),inventory,docs


def fetch_bundle(client,item):
    with _FETCH_LOCKS[item['attempt_id']]:
        return _fetch_bundle(client,item)


def _fetch_bundle(client,item):
    root=client.root
    aid=item['attempt_id'];base={'attempt_id':aid,'challenge_id':item['challenge_id'],
        'ours':item['ours'],'bundle_reason':item['bundle_reason'],'observed_at':utcnow()}
    metadata=root/'data/bundle_inventories'/(aid+'.json')
    if metadata.exists() and (root/'.raw/bundles'/(aid+'.zip')).exists():
        return json.loads(metadata.read_text())['index']
    try:
        raw=download(client,aid);local=client.redactor.fork()
        cleaned,inventory,docs=sanitize_archive(raw,local)
        base.update(status='ok',original_bytes=len(raw),original_sha256=sha(raw),
                    sanitized_bytes=len(cleaned),sanitized_sha256=sha(cleaned),
                    file_count=len(inventory),redactions=sum(local.counts.values()),
                    inventory_path=str(metadata.relative_to(root)),
                    local_archive_path='.raw/bundles/'+aid+'.zip')
        atomic(root/base['local_archive_path'],cleaned)
        write_json(metadata,{'index':base,'redactions':dict(local.counts),'files':inventory})
        write_json(root/'data/bundle_docs'/(aid+'.json'),{'attempt_id':aid,'ours':item['ours'],'documents':docs})
    except Exception as exc:base.update(status='skipped' if isinstance(exc,ValueError) else 'failed',reason=str(exc))
    return base

def main():
    root=DEFAULT_DATA;client=PublicClient();items=list(read_table('data/bundles_requested.csv'))
    rows=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(fetch_bundle,client,item) for item in items]
        for future in as_completed(futures):
            rows.append(future.result());write_csv(root/'data/bundles_index.csv',sorted(rows,key=lambda r:int(r['attempt_id'])))
            print(json.dumps({'completed':len(rows),'expected':len(items),
                              'downloaded':sum(r['status']=='ok' for r in rows),
                              'non_success':[{'id':r['attempt_id'],'status':r['status'],'reason':r.get('reason')}
                                             for r in rows if r['status']!='ok']}),flush=True)


if __name__=='__main__':main()
