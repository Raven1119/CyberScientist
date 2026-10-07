"""Re-audit structured receipts after redaction changes, never log their text."""
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .common import DEFAULT_DATA, Redactor, atomic, sha, unzstd, utcnow, write_json, zstd


def main():
    root=DEFAULT_DATA; redactor=Redactor()
    paths=[p for p in root.rglob('*') if p.is_file() and '.git' not in p.parts
           and (p.suffix=='.json' or p.name.endswith('.json.zst'))]
    def check(path):
        compressed=path.name.endswith('.zst')
        raw=unzstd(path.read_bytes()) if compressed else path.read_bytes()
        try:value=json.loads(raw)
        except (ValueError,UnicodeError):return {'path':str(path.relative_to(root)),'status':'unparsed'}
        local=redactor.fork();clean=local.obj(value)
        result={'path':str(path.relative_to(root)),'changed':clean!=value,'counts':dict(local.counts)}
        if clean!=value:
            encoded=(json.dumps(clean,ensure_ascii=False)+'\n').encode()
            atomic(path,zstd(encoded) if compressed else encoded)
            if compressed and path.parent==root/'.raw/http':
                meta=path.with_name(path.name.removesuffix('.json.zst')+'.meta.json')
                if meta.exists():
                    metadata=json.loads(meta.read_text());counts=Counter(metadata.get('redactions',{}))
                    counts.update(local.counts)
                    metadata.update(sanitized_sha256=sha(encoded),redactions=dict(counts),rescrubbed_at=utcnow())
                    write_json(meta,metadata)
        return result
    # Cache metadata is updated together with its receipt, never concurrently.
    ordinary=[p for p in paths if not p.name.endswith('.meta.json')]
    metadata=[p for p in paths if p.name.endswith('.meta.json')]
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(check,ordinary))
    results.extend(check(p) for p in metadata)
    report={'audited_at':utcnow(),'structured_files':len(results),
            'changed_files':sum(r.get('changed',False) for r in results),
            'unparsed_files':[r['path'] for r in results if r.get('status')=='unparsed'],
            'changed':[r for r in results if r.get('changed')]}
    write_json(root/'data/redaction_audit_latest.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='changed'}))


if __name__=='__main__':main()
