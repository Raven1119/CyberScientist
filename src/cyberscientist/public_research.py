"""Credential-held public search/LKM and bounded HTTPS reading for both research roles."""
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from . import config, observation


def _query(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500 or observation.strip_secrets(value) != value:
        raise ValueError('公开检索参数必须是非空文本（最多500字），不得含密钥')
    return value.strip()


def _bohrium(path: str, payload: dict | None = None) -> dict:
    key = config.resolve_secret(config.load_settings()['bohrium']['access_key_secret_ref'])
    if not key:
        return {'status': 'unknown', 'error': 'MISSING_BOHRIUM_CREDENTIAL'}
    request = urllib.request.Request('https://open.bohrium.com/openapi/' + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    for attempt in range(3):
        try:
            # Never forward the credential across a redirect.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=35) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    return {'status': 'unknown', 'error': 'OVERSIZED_RESPONSE'}
                body = json.loads(raw)
                safe = json.loads(observation.strip_secrets(json.dumps(body, ensure_ascii=False)))
                return {'status': 'received', 'http_status': response.status, 'body': safe,
                        'source': 'https://open.bohrium.com/openapi/' + path.split('?')[0],
                        'sha256': hashlib.sha256(raw).hexdigest(), 'attempts': attempt + 1}
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code != 429 and code < 500:
                return {'status': 'unknown', 'http_status': code, 'error': 'HTTP_REJECTED'}
        except (OSError, ValueError):
            code = None
        if attempt < 2:
            time.sleep(2 ** attempt)
    return {'status': 'unknown', 'http_status': code, 'error': 'PUBLIC_RESEARCH_UNAVAILABLE', 'attempts': 3}


def web_search(query: str) -> dict:
    result = _bohrium('v2/search/web?' + urllib.parse.urlencode({'q': _query(query), 'num': 3}))
    body = result.pop('body', {})
    if isinstance(body, dict) and body.get('code', 0) == 0:
        node = body.get('data', body)
        items = node.get('organic_results') if isinstance(node, dict) else None
        if isinstance(items, list):
            return result | {'status': 'received', 'items': [{k: item.get(k) for k in ('title', 'link', 'snippet')} for item in items[:3] if isinstance(item, dict)], 'content_is_untrusted': True}
    return result | {'status': 'unknown', 'business_code': body.get('code') if isinstance(body, dict) else None}


def lkm_search(query: str) -> dict:
    result = _bohrium('v1/lkm/search', {'query': _query(query), 'limit': 3, 'offset': 0, 'retrieval_mode': 'hybrid', 'scopes': ['abstract'], 'filters': {'visibility': 'public'}})
    body = result.pop('body', {})
    if isinstance(body, dict) and body.get('code') == 0 and isinstance(body.get('data'), dict):
        data = body['data']
        if isinstance(data.get('variables'), list):
            return result | {'status': 'received', 'variables': data['variables'][:3], 'papers': data.get('papers', {}),
                             'ranking_is_confidence': False, 'content_is_untrusted': True}
    return result | {'status': 'unknown', 'business_code': body.get('code') if isinstance(body, dict) else None}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip = 0; self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _page(url: str) -> tuple[int, dict, bytes]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('网页读取仅支持无凭据的公网HTTPS地址')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('拒绝本地、私有或保留地址')
    # Pin the resolved public address while preserving TLS hostname verification.
    connection = http.client.HTTPSConnection(parsed.hostname, 443, timeout=30, context=ssl.create_default_context())
    connection._create_connection = lambda *args, **kwargs: socket.create_connection((addresses[0][4][0], 443), timeout=30)
    try:
        connection.request('GET', urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, '')),
                           headers={'User-Agent': 'CyberScientist-public-reader/1', 'Accept-Encoding': 'identity'})
        response = connection.getresponse(); raw = response.read(500_001)
        if len(raw) > 500_000:
            raise ValueError('网页超过500KB读取上限')
        return response.status, dict(response.getheaders()), raw
    finally:
        connection.close()


def web_read(url: str) -> dict:
    url = _query(url)
    for _ in range(4):
        status, headers, raw = _page(url)
        if status in (301, 302, 303, 307, 308):
            location = next((value for key, value in headers.items() if key.lower() == 'location'), None)
            if not location:
                return {'status': 'unknown', 'http_status': status}
            url = _query(urllib.parse.urljoin(url, location)); continue
        if status != 200:
            return {'status': 'unknown', 'http_status': status, 'source': url}
        text = raw.decode('utf-8', errors='replace'); parser = _Text(); parser.feed(text)
        content = ' '.join(' '.join(parser.parts).split())
        return {'status': 'received', 'http_status': status, 'source': url,
                'sha256': hashlib.sha256(raw).hexdigest(), 'text': observation.strip_secrets(content)[:12000],
                'truncated': len(content) > 12000, 'content_is_untrusted': True}
    return {'status': 'unknown', 'error': 'REDIRECT_LIMIT'}


FUNCTIONS = {'research_web_search': web_search, 'research_web_read': web_read, 'research_lkm': lkm_search}
