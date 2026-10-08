"""Controller-bound native log snapshots; never edit a provider's record."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote
from . import config, db, observation, bohr_proxy


_TOKEN = re.compile(r'(?<![A-Za-z0-9_-])(?:sk-|AKIA|ghp_|gho_|xoxb-|AIza)[A-Za-z0-9_.-]+')
_BEARER = re.compile(r'(?i)\bBearer\s+([A-Za-z0-9_.~+/=-]+)')
_ENV = re.compile(r'(?i)\b(?:BOHR_ACCESS_KEY|ACCESS_KEY|CS_TOOL_TOKEN|API_KEY)\s*=\s*([^\s"\']+)')
_JSON_CREDENTIAL = re.compile(r'(?i)"(?:' + bohr_proxy._CREDENTIAL_FIELD + r')"\s*:\s*"([^"]*)"')
_PLACEHOLDERS = {'...', '***', '[redacted]', 'your_api_key', 'your_access_key', 'your_token'}


def _placeholder(value):
    if value.startswith('<') and value.endswith('>'):
        return _placeholder(value[1:-1])
    if value.casefold().startswith('bearer '):
        value = value[7:].strip()
    return (not value or value.casefold() in _PLACEHOLDERS or
            re.fullmatch(r'[A-Za-z_]{1,16}\.\.\.', value) is not None or
            re.fullmatch(r'YOUR_(?:(?:BOHR|BOHRIUM|PLAYGROUND|OPENAI)_)?(?:API_|ACCESS_)?(?:KEY|TOKEN)', value, re.I) is not None or
            re.fullmatch(r'\$\{[A-Z_][A-Z0-9_]*\}|\$[A-Z_][A-Z0-9_]*', value) is not None)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)


def contains_secrets(text):
    """Classify semantic plaintext; never transform the bytes to be submitted.

    Presentation redaction intentionally matches substrings and examples. A
    provider-owned reasoning ciphertext is opaque, while exact stored secrets
    are checked everywhere, including that ciphertext and encoded variants.
    """
    secrets = {variant for value in config.sensitive_values() if value
               for variant in (value, quote(value, safe=''), quote_plus(value))}
    if any(value in text for value in secrets):
        return True
    for line in text.splitlines():
        row = json.loads(line)
        if (isinstance(row, dict) and row.get('type') == 'response_item'
                and isinstance(row.get('payload'), dict)
                and row['payload'].get('type') == 'reasoning'):
            row = row | {'payload': {k: v for k, v in row['payload'].items()
                                     if k != 'encrypted_content'}}
        for value in _strings(row):
            # Two decoding levels cover URL-encoded signed links in JSON text.
            for candidate in (value, unquote(value), unquote(unquote(value))):
                if (any(secret in candidate for secret in secrets)
                        or observation._SECRET_BLOCK_RE.search(candidate)
                        or _TOKEN.search(candidate)):
                    return True
                for pattern in (_BEARER, _ENV, _JSON_CREDENTIAL):
                    if any(not _placeholder(m.group(1)) for m in pattern.finditer(candidate)):
                        return True
                for match in bohr_proxy._ACCESS_KEY_QUERY.finditer(candidate):
                    if not _placeholder(match.group(0)[len(match.group(1)):]):
                        return True
    return False


def bind_trial(run_id, trial_id, session_id):
    rows = db.query("SELECT payload FROM events WHERE run_id=? AND type='session.configuration' ORDER BY seq DESC", (run_id,))
    for row in rows:
        value = json.loads(row['payload'])
        if value.get('role') == 'executor' and value.get('session_id') == session_id:
            if value.get('native_log_path'):
                db.append_event(run_id, 'controller', 'trial.native_session_bound', value, trial_id=trial_id)
            return


def snapshot(run_id, trial_id):
    if not trial_id:
        return None
    row = db.query_one("SELECT payload FROM events WHERE run_id=? AND trial_id=? AND source='controller' AND type='trial.native_session_bound' ORDER BY seq DESC LIMIT 1", (run_id, trial_id))
    if not row:
        return None
    value = json.loads(row['payload'])
    path = Path(value['native_log_path'])
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024**2:
        raise ValueError('原生会话日志不存在、为链接或超过128MiB')
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    if contains_secrets(text):
        raise ValueError('原始会话包含需脱敏内容；不得改写，须使用无密钥的干净会话')
    first = json.loads(text.splitlines()[0])
    if (first.get('type') != 'session_meta'
            or first.get('payload', {}).get('id') != value['session_id']):
        raise ValueError('原生会话身份与最终Trial绑定不符')
    return {'bytes': raw, 'session_id': value['session_id'],
            'sha256': hashlib.sha256(raw).hexdigest(), 'model': value.get('model'),
            'provider': value.get('provider'), 'trial_id': trial_id}
