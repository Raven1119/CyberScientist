"""Public GETs, bounded downloads, and redaction before any persistence."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

MAIN = Path('/home/wmywb/CyberScientist')
DEFAULT_DATA = Path('/home/wmywb/cs-s4-analysis')
ORIGIN = 'https://play.bohrium.com'
ZSTD = shutil.which('zstd') or '/home/wmywb/miniforge3/bin/zstd'


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def credentials():
    """Read existing files directly: no backend initialization or DB access."""
    secrets_path = MAIN / '.cyberscientist/secrets.json'
    secrets = json.loads(secrets_path.read_text()) if secrets_path.exists() else {}
    key = os.environ.get('DEEPSEEK_API_KEY', '')
    dotenv = MAIN / '.env'
    if not key and dotenv.exists():
        for line in dotenv.read_text().splitlines():
            name, sep, value = line.strip().partition('=')
            if sep and name.removeprefix('export ').strip() == 'DEEPSEEK_API_KEY':
                key = value.strip().strip('"').strip("'")
    settings_path = MAIN / '.cyberscientist/settings.json'
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    return secrets, key, settings


class Redactor:
    def __init__(self):
        secrets, key, settings = credentials()
        self.known = sorted({v for v in [*secrets.values(), key]
                             if isinstance(v, str) and len(v) >= 8}, key=len, reverse=True)
        self.ours = set()
        def emails(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    if k.lower() in ('email', 'account_email') and isinstance(v, str) and '@' in v:
                        self.ours.add(v.strip().lower())
                    elif isinstance(v, (list, dict)): emails(v)
            elif isinstance(value, list):
                for v in value: emails(v)
        emails(settings)
        # Use an already-existing immutable maintenance snapshot, never the
        # production ledger, to read mailbox configuration stored outside JSON.
        snapshot = MAIN / '.package-checks/cs-up-12/preflight-warmup-final/current.sqlite'
        if snapshot.exists():
            with sqlite3.connect('file:' + str(snapshot) + '?mode=ro&immutable=1', uri=True) as conn:
                for (email,) in conn.execute('SELECT email FROM mailboxes WHERE is_demo=0'):
                    if isinstance(email, str) and '@' in email:
                        self.ours.add(email.strip().lower())
        self.counts = Counter()
        self.patterns = [
            ('pem', re.compile(r'-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)-----.*?(?:-----END [A-Z ]+-----|\Z)', re.S)),
            ('provider_key', re.compile(r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|(?:AKIA|ASIA)[A-Z0-9]{16})\b')),
            ('bearer', re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}')),
            ('jwt', re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b')),
            ('credential_assignment', re.compile(r'(?i)(?:(?<![A-Za-z0-9])(?:api[_-]?key|access[_-]?(?:key(?:[_-]?id)?|token)|refresh[_-]?token|id[_-]?token|session[_-]?(?:id|token)|private[_-]?key|secret|password|passwd|token|key|cookie|sig|Signature|X-Amz-Credential)["\x27]?\s*[:=]\s*["\x27]?)[A-Za-z0-9_./+%~=-]{12,}')),
            ('email', re.compile(r'\b[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')),
        ]

    def fork(self):
        result = object.__new__(Redactor)
        result.known, result.ours, result.patterns = self.known, self.ours, self.patterns
        result.counts = Counter()
        return result

    def text(self, value):
        for secret in self.known:
            count = value.count(secret)
            if count:
                self.counts['known_secret'] += count
                value = value.replace(secret, '[REDACTED]')
        for label, pattern in self.patterns:
            value, count = pattern.subn('[REDACTED]', value)
            self.counts[label] += count
        return value

    def obj(self, value, path=()):
        if isinstance(value, str): return self.text(value)
        if isinstance(value, list): return [self.obj(v, path+('[]',)) for v in value]
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                normal = re.sub(r'[^a-z]', '', k.lower())
                sensitive = normal in {'apikey','accesstoken','envdaccesstoken','authorization',
                    'password','passwd','secret','secretkey','accesskey','accesskeysecret','refreshtoken','idtoken',
                    'cookie','setcookie','sessiontoken','credential','credentials','pass'} or normal.endswith(
                    ('apikey','secretaccesskey','privatekey','password','accesstoken','refreshtoken','accesskeyid'))
                location = path+(k,)
                public_scientific_field = location[-3:] in (
                    ('answers','[]','token'), ('datasets','[]','key'), ('resources','[]','key'))
                sensitive = sensitive or normal in ('key','token') and isinstance(v,str) and len(v)>=16 and not public_scientific_field
                if sensitive and isinstance(v, str) and v and v != '[REDACTED]':
                    self.counts['credential_field'] += 1
                    out[k] = '[REDACTED]'
                else: out[k] = self.obj(v,location)
            return out
        return value

    def identify_ours(self, value):
        if not isinstance(value, dict): return False
        owner = {k: v for k, v in value.items() if k.lower() in {
            'author','author_name','user','owner','submitter','createdby','email','useremail','authoremail'}}
        return any(email in json.dumps(owner, ensure_ascii=False).lower() for email in self.ours)


def atomic(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(raw)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def write_json(path, value):
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def zstd(raw):
    return subprocess.run([ZSTD, '-q', '-c', '-3'], input=raw,
                          stdout=subprocess.PIPE, check=True).stdout


def unzstd(raw):
    return subprocess.run([ZSTD, '-q', '-d', '-c'], input=raw,
                          stdout=subprocess.PIPE, check=True).stdout


class PublicClient:
    def __init__(self, root=DEFAULT_DATA):
        self.root = Path(root)
        self.cache = self.root / '.raw/http'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.redactor = Redactor()

    def rate(self):
        with (self.root / '.raw/rate.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            lock.seek(0)
            previous = float(lock.read() or 0)
            time.sleep(max(0, .36 - (time.time() - previous)))
            lock.seek(0); lock.truncate(); lock.write(str(time.time())); lock.flush()

    def get(self, path, *, refresh=False, limit=100_000_000):
        url = ORIGIN + path if path.startswith('/') else path
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'play.bohrium.com' or parsed.username:
            raise ValueError('Only the authorized public platform origin is allowed')
        cache_id = sha(url.encode())
        target = self.cache / (cache_id + '.json.zst')
        meta_path = self.cache / (cache_id + '.meta.json')
        if target.exists() and meta_path.exists() and not refresh:
            previous = json.loads(unzstd(target.read_bytes()))
            redactor = self.redactor.fork()
            clean = redactor.obj(previous)
            if clean != previous:
                clean_raw = (json.dumps(clean,ensure_ascii=False)+'\n').encode()
                atomic(target,zstd(clean_raw))
                metadata=json.loads(meta_path.read_text())
                metadata['sanitized_sha256']=sha(clean_raw)
                counts=Counter(metadata.get('redactions',{}));counts.update(redactor.counts)
                metadata.update(redactions=dict(counts),redaction_revision=2,rescrubbed_at=utcnow())
                write_json(meta_path,metadata)
            return clean
        redactor = self.redactor.fork()
        for retry in range(7):
            try:
                self.rate()
                with httpx.Client(timeout=60, follow_redirects=False) as client:
                    with client.stream('GET', url, headers={'Accept':'application/json'}) as response:
                        status = response.status_code
                        if status == 429 or status >= 500:
                            raise httpx.HTTPStatusError('Transient public GET', request=response.request, response=response)
                        response.raise_for_status()
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            raw.extend(chunk)
                            if len(raw) > limit: raise ValueError('Public response exceeds byte limit')
                original_sha = sha(raw)
                value = json.loads(raw)
                def mark(v):
                    if isinstance(v, dict):
                        if 'id' in v and redactor.identify_ours(v): v['_ours'] = True
                        for x in v.values():
                            if isinstance(x, (dict, list)): mark(x)
                    elif isinstance(v, list):
                        for x in v: mark(x)
                mark(value)
                clean = redactor.obj(value)
                clean_raw = (json.dumps(clean, ensure_ascii=False) + '\n').encode()
                atomic(target, zstd(clean_raw))
                write_json(self.cache / (cache_id + '.meta.json'), {
                    'url': redactor.text(url), 'http_status': status,
                    'original_sha256': original_sha, 'sanitized_sha256': sha(clean_raw),
                    'fetched_at': utcnow(), 'original_bytes': len(raw),
                    'redactions': dict(redactor.counts)})
                return clean
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                if retry == 6 or status is not None and status < 500 and status != 429:
                    raise RuntimeError(f'Public GET failed: {parsed.path}, status={status}, kind={type(exc).__name__}') from None
                time.sleep(min(60, 2 ** retry))
        raise AssertionError('unreachable')
