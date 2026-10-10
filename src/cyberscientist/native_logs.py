"""Controller-bound native log snapshots; never edit a provider's record."""
import hashlib
import base64
import json
import re
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote
from . import config, db, observation, bohr_proxy


_TOKEN = re.compile(r'(?<![A-Za-z0-9_-])(?:asp_|sk-|AKIA|ghp_|gho_|xoxb-|AIza)[A-Za-z0-9_.-]{20,}')
_BEARER = re.compile(r'(?i)\bBearer\s+([A-Za-z0-9_.~+/=-]+)')
_ENV = re.compile(r'(?i)\b(?:BOHR_ACCESS_KEY|ACCESS_KEY|CS_TOOL_TOKEN|API_KEY)\s*=\s*([^\s"\'\\]+)')
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


def secret_findings(text):
    """Classify semantic plaintext; never transform the bytes to be submitted.

    Presentation redaction intentionally matches substrings and examples. A
    provider-owned reasoning ciphertext is opaque, while exact stored secrets
    are checked everywhere, including that ciphertext and encoded variants.
    """
    secrets = {variant for value in config.sensitive_values() if value
               for variant in (value, quote(value, safe=''), quote_plus(value),
                               json.dumps(value)[1:-1], base64.b64encode(value.encode()).decode(),
                               base64.urlsafe_b64encode(value.encode()).decode().rstrip('='))}
    if any(value in text for value in secrets):
        return [{'rule': 'stored_credential', 'line': None, 'exact_stored': True,
                 'context': '[redacted stored credential]', 'risk': 'critical'}]
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        row = json.loads(line)
        if (isinstance(row, dict) and row.get('type') == 'response_item'
                and isinstance(row.get('payload'), dict)
                and row['payload'].get('type') == 'reasoning'):
            row = row | {'payload': {k: v for k, v in row['payload'].items()
                                     if k != 'encrypted_content'}}
        for value in _strings(row):
            # Two decoding levels cover URL-encoded signed links in JSON text.
            for candidate in (value, unquote(value), unquote(unquote(value))):
                if any(secret in candidate for secret in secrets):
                    return [{'rule': 'stored_credential', 'line': number, 'exact_stored': True,
                             'context': '[redacted stored credential]', 'risk': 'critical'}]
                matches = []
                for rule, pattern in (('private_key', observation._SECRET_BLOCK_RE), ('token_prefix', _TOKEN)):
                    matches.extend((rule, m) for m in pattern.finditer(candidate))
                for rule, pattern in (('bearer_token', _BEARER), ('credential_assignment', _ENV), ('credential_field', _JSON_CREDENTIAL)):
                    matches.extend((rule, m) for m in pattern.finditer(candidate)
                                   if len(m.group(1)) >= 20 and not _placeholder(m.group(1)))
                for match in bohr_proxy._ACCESS_KEY_QUERY.finditer(candidate):
                    value = match.group(0)[len(match.group(1)):]
                    if len(value) >= 20 and not _placeholder(value):
                        matches.append(('credential_query', match))
                for rule, match in matches:
                    # No token material is persisted, even for a false positive.
                    context = candidate[max(0, match.start()-80):match.start()] + '[redacted]' + candidate[match.end():match.end()+80]
                    findings.append({'rule': rule, 'line': number, 'exact_stored': False,
                                     'context': observation.strip_secrets(context), 'risk': 'high'})
    return [json.loads(item) for item in sorted({json.dumps(f, sort_keys=True) for f in findings})]


def contains_secrets(text):
    return bool(secret_findings(text))


def assert_safe(text, *, run_id=None, trial_id=None, source='native_session'):
    """Exact secrets never pass; unknown shapes require a content-scoped review."""
    from . import gate_reviews
    digest = hashlib.sha256(text.encode()).hexdigest()
    blocked = []
    for finding in secret_findings(text):
        item = gate_reviews.record(finding['rule'], digest, source=source,
                                   run_id=run_id, trial_id=trial_id, **{
                                       k: finding[k] for k in ('line', 'exact_stored', 'context', 'risk')})
        if item['exact_stored'] or item['status'] != 'false_positive':
            blocked.append(item['id'])
    if blocked:
        raise ValueError('原始内容凭据检查待复核；不得改写原生记录；gate=' + ','.join(blocked))


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
    assert_safe(text, run_id=run_id, trial_id=trial_id, source=str(path))
    first = json.loads(text.splitlines()[0])
    if (first.get('type') != 'session_meta'
            or first.get('payload', {}).get('id') != value['session_id']):
        raise ValueError('原生会话身份与最终Trial绑定不符')
    return {'bytes': raw, 'session_id': value['session_id'], 'run_id': run_id,
            'sha256': hashlib.sha256(raw).hexdigest(), 'model': value.get('model'),
            'provider': value.get('provider'), 'trial_id': trial_id}
