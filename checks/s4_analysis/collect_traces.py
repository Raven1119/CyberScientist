"""Download every selected trace; keep over-budget traces in ignored storage."""
import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .common import DEFAULT_DATA, PublicClient, atomic, sha, utcnow, zstd
from .dataset import read_table, truth
from .tables import write_csv


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=12)
    parser.add_argument('--private-byte-budget',type=int,default=700_000_000)
    args=parser.parse_args();client=PublicClient();root=DEFAULT_DATA
    selected=list(read_table('data/selected.csv'))
    if (root/'data/selection_additions.csv').exists():
        selected+=list(read_table('data/selection_additions.csv'))
    selected=list({row['attempt_id']:row for row in selected}.values())
    selected.sort(key=lambda r:('calibration' not in r['selection_reasons'],
                               not truth(r['ours']),'head_top10' not in r['selection_reasons'],int(r['attempt_id'])))
    directory=root/'data/traces';directory.mkdir(parents=True,exist_ok=True)
    total=sum(p.stat().st_size for p in directory.glob('*.zst'));lock=threading.Lock()
    def fetch(item):
        nonlocal total
        aid=item['attempt_id'];row={'attempt_id':aid,'challenge_id':item['challenge_id'],
                                  'ours':item['ours'],'observed_at':utcnow()}
        try:
            body=client.get('/api/attempts/'+aid+'/trace')
            if not isinstance(body,list):raise ValueError('Unexpected trace schema; not a step list')
            for step in body:
                if not isinstance(step,dict):raise ValueError('Non-object trace step')
            raw=''.join(json.dumps(step,ensure_ascii=False)+'\n' for step in body).encode()
            compressed=zstd(raw);path=directory/(aid+'.jsonl.zst')
            with lock:
                previous=path.stat().st_size if path.exists() else 0
                private=len(compressed)<90_000_000 and total-previous+len(compressed)<args.private_byte_budget
                if private:total=total-previous+len(compressed)
            if not private:path=root/'.raw/traces'/(aid+'.jsonl.zst')
            atomic(path,compressed)
            row.update(status='ok',step_count=len(body),sanitized_sha256=sha(raw),
                       compressed_bytes=len(compressed),storage='private' if private else 'local_only',
                       path=str(path.relative_to(root)),reason=None if private else 'private_repository_size_budget')
        except Exception as exc:row.update(status='failed',reason=str(exc))
        return row
    rows=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(fetch,item):item['attempt_id'] for item in selected}
        for future in as_completed(futures):
            rows.append(future.result())
            if len(rows)%100==0 or len(rows)==len(selected):
                rows.sort(key=lambda r:int(r['attempt_id']))
                write_csv(root/'data/traces_index.csv',rows)
                print(json.dumps({'completed':len(rows),'expected':len(selected),
                                  'failures':sum(r['status']=='failed' for r in rows),
                                  'private_bytes':total,'time':utcnow()}),flush=True)


if __name__=='__main__':main()
