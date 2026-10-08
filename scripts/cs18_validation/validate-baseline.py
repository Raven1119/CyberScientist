import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cyberscientist import db
result={'experience_files':{p.relative_to(ROOT/'experience').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'experience').rglob('*') if p.is_file()},'secrets_sha256':hashlib.sha256((ROOT/'.cyberscientist/secrets.json').read_bytes()).hexdigest(),'counts':{table:db.query_one('SELECT COUNT(*) FROM '+table)[0] for table in ('runs','submissions','compute_jobs','mailboxes')}}
(ROOT/'.runtime/validation/hidden/baseline.json').write_text(json.dumps(result,indent=2))
