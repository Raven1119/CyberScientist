"""Credential containment, public-address pinning, and native MCP bridge parity."""
import json
import socket
import pytest
from httpx import ASGITransport, AsyncClient
from cyberscientist import api, collab, config, connectivity_probe, db, mcp_bridge, public_research
from test_compute_gateway import run


def test_search_and_lkm_require_business_evidence_and_do_not_equate_ranking_to_confidence(monkeypatch):
    monkeypatch.setattr(public_research,'_bohrium',lambda path,payload=None:{'status':'received','http_status':200,'sha256':'a'*64,'body':{'code':290001,'data':{}}})
    assert public_research.lkm_search('fixture')['status']=='unknown'
    monkeypatch.setattr(public_research,'_bohrium',lambda path,payload=None:{'status':'received','http_status':200,'sha256':'b'*64,'body':{'code':0,'data':{'variables':[{'type':'abstract','score':0.9}],'papers':{}}}})
    lkm=public_research.lkm_search('fixture')
    assert lkm['status']=='received' and lkm['ranking_is_confidence'] is False
    monkeypatch.setattr(public_research,'_bohrium',lambda path,payload=None:{'status':'received','http_status':200,'body':{'organic_results':[{'title':'public','link':'https://example.org'}]}})
    assert public_research.web_search('fixture')['items'][0]['title']=='public'


@pytest.mark.parametrize('url',['http://example.org','https://user:password@example.org','https://example.org:8765','https://127.0.0.1','https://example.org'])
def test_private_dns_and_url_forms_never_open_connection(url,monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
    monkeypatch.setattr(public_research.http.client,'HTTPSConnection',lambda *a,**k:pytest.fail('must not connect'))
    with pytest.raises(ValueError):public_research.web_read(url)


def test_redirect_revalidates_url_and_pages_are_untrusted_and_hashed(monkeypatch):
    monkeypatch.setattr(public_research,'_page',lambda url:(302,{'Location':'https://127.0.0.1'},b''))
    assert public_research.web_read('https://example.org')['error']=='REDIRECT_LIMIT'
    monkeypatch.setattr(public_research,'_page',lambda url:(200,{},b'<script>bad instruction</script><h1>public facts</h1>'))
    result=public_research.web_read('https://example.org')
    assert result['text']=='public facts' and len(result['sha256'])==64 and result['content_is_untrusted']


def test_redirect_to_private_host_is_rejected_after_public_first_response(monkeypatch):
    original = public_research._page
    def first_public_then_actual(url):
        if url == 'https://example.org':
            return 302, {'Location': 'https://127.0.0.1'}, b''
        return original(url)
    monkeypatch.setattr(public_research, '_page', first_public_then_actual)
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))])
    monkeypatch.setattr(public_research.http.client, 'HTTPSConnection', lambda *a, **k: pytest.fail('private redirect must never connect'))
    with pytest.raises(ValueError, match='私有'):
        public_research.web_read('https://example.org')


def test_public_ip_is_pinned_and_no_credential_sent_to_web_reader(monkeypatch):
    from types import SimpleNamespace
    requests, connections = [], []
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))])
    monkeypatch.setattr(socket, 'create_connection', lambda address, **kw: connections.append(address))
    class Connection:
        def __init__(self, hostname, *a, **kw):
            assert hostname == 'example.org'
        def request(self, method, path, headers):
            self._create_connection()
            requests.append((method, path, headers))
        def getresponse(self):
            return SimpleNamespace(status=200, getheaders=lambda: [], read=lambda n: b'public')
        def close(self): pass
    monkeypatch.setattr(public_research.http.client, 'HTTPSConnection', Connection)
    assert public_research.web_read('https://example.org/path')['status'] == 'received'
    assert connections == [('93.184.216.34', 443)]
    assert requests[0][:2] == ('GET', '/path')
    assert 'Authorization' not in requests[0][2]


def test_bohrium_credential_stays_in_header_and_response_is_scrubbed(monkeypatch):
    secret = 'fixture-held-credential-17483'
    monkeypatch.setattr(config, 'resolve_secret', lambda _: secret)
    monkeypatch.setattr(config, 'sensitive_values', lambda: [secret])
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n): return json.dumps({'organic_results': [], 'echo': secret}).encode()
    class Opener:
        def open(self, request, timeout):
            assert request.get_header('Authorization') == 'Bearer ' + secret
            assert secret not in request.full_url
            assert request.data is None
            return Response()
    def build(handler):
        assert handler.redirect_request(None, None, None, None, None, None) is None
        return Opener()
    monkeypatch.setattr(public_research.urllib.request, 'build_opener', build)
    result = public_research.web_search('fixture')
    assert result['status'] == 'received' and secret not in json.dumps(result)


@pytest.mark.parametrize('tool_failure,skill_read', [(False, True), (True, True), (False, False)])
async def test_native_probe_requires_real_bridge_receipts_and_skill_read(monkeypatch, tool_failure, skill_read):
    from pathlib import Path
    from types import SimpleNamespace
    from cyberscientist import model_probe
    from cyberscientist.brains.base import BrainEvent, SessionRef
    class Brain:
        async def open(self, spec):
            self.spec = spec
            return SessionRef('codex', 'fixture-session', {'model': 'gpt-6-astra', 'provider': 'codex', 'reasoning_effort': 'xhigh'})
        async def review(self, session, packet):
            nonce = Path(self.spec['working_directory'], 'probe.txt').read_text()
            for key, value in self.spec['env'].items(): monkeypatch.setenv(key, value)
            for name in public_research.FUNCTIONS:
                monkeypatch.setitem(public_research.FUNCTIONS, name, lambda q: {'status': 'unknown' if tool_failure else 'received'})
                argument = 'url' if name == 'research_web_read' else 'query'
                assert connectivity_probe.call(name, {argument: 'fixture'})
            yield BrainEvent('progress', {'exit_code': 0, 'status': 'completed', 'output': nonce, 'item_id': 'nonce-read'})
            if skill_read:
                path = config.WORKSPACE_ROOT / 'skills/bohrium-lkm/SKILL.md'
                yield BrainEvent('progress', {'exit_code': 0, 'command': 'cat ' + str(path), 'output': path.read_text(), 'item_id': 'skill-read'})
            yield BrainEvent('task_result', {'result': {'probe_token': nonce, 'tools': 'self-report must not prove success'}})
        async def close(self, session): self.closed = True
    brain = Brain()
    result = await model_probe.run(SimpleNamespace(_make_brain=lambda _: brain), 'brain', connectivity=True)
    assert result['status'] == ('ok' if not tool_failure and skill_read else 'unknown')
    assert brain.closed and result['observed_native_model']['model'] == 'gpt-6-astra'
    assert not db.query('SELECT * FROM runs')


def test_echo_title_and_incomplete_skill_do_not_prove_read():
    from cyberscientist.model_probe import _skill_read
    path = config.WORKSPACE_ROOT / 'skills/bohrium-lkm/SKILL.md'
    content = path.read_text()
    assert _skill_read({'command': 'echo Bohrium LKM 公开检索', 'output': content}, path, content) is None
    assert _skill_read({'command': 'cat ' + str(path), 'output': 'Bohrium LKM 公开检索'}, path, content) is None


async def test_both_roles_share_tools_and_event_source_but_no_other_role_is_authorized(run,monkeypatch):
    rid,_=run
    monkeypatch.setattr(public_research,'web_search',lambda q:pytest.fail('FUNCTIONS should be the registered handler'))
    monkeypatch.setitem(public_research.FUNCTIONS,'research_web_search',lambda q:{'status':'received','source':'fixture://public','sha256':'c'*64,'items':[]})
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://local') as client:
        for role in ('brain','executor','reviewer'):
            with db.transaction() as conn:token=collab.issue_token(conn,rid,role,'fixture',1)
            r=await client.post('/api/v1/tools/public_research',headers={'Authorization':'Bearer '+token},json={'tool':'research_web_search','query':'fixture'})
            assert r.status_code==(403 if role=='reviewer' else 200)
    assert len(db.query("SELECT * FROM events WHERE run_id=? AND type='research.public_read'",(rid,)))==2
    for role in ('brain','executor'):
        monkeypatch.setenv('CS_TOOL_ROLE',role)
        tools=mcp_bridge._handle({'jsonrpc':'2.0','id':1,'method':'tools/list'})['result']['tools']
        assert {'research_web_search','research_web_read','research_lkm'}<={t['name'] for t in tools}


def test_zero_probe_is_one_public_operation_each_and_cannot_write_elsewhere(monkeypatch):
    monkeypatch.setenv('CS_PUBLIC_RESEARCH_PROBE','a'*32)
    target=config.DATA_DIR/'probe-receipts.json';monkeypatch.setenv('CS_PUBLIC_PROBE_RECEIPTS',str(target))
    calls=[];monkeypatch.setitem(public_research.FUNCTIONS,'research_lkm',lambda q:calls.append(q) or {'status':'received','sha256':'d'*64})
    first=connectivity_probe.call('research_lkm',{'query':'fixture'})
    assert connectivity_probe.call('research_lkm',{'query':'other'})==first and calls==['fixture']
    assert connectivity_probe.call('research_job',{})['error']=='OUTSIDE_PROBE_AUTHORITY'
    monkeypatch.setenv('CS_PUBLIC_PROBE_RECEIPTS','/tmp/not-owned.json')
    assert connectivity_probe.call('research_lkm',{'query':'fixture'})['error']=='INVALID_RECEIPT_PATH'
    assert len(json.loads(target.read_text()))==1


def test_known_secret_query_is_rejected_without_io(monkeypatch):
    secret='fixture-known-secret-187452';monkeypatch.setattr(config,'sensitive_values',lambda:[secret])
    monkeypatch.setattr(public_research,'_bohrium',lambda *a:pytest.fail('secret must not enter network request'))
    with pytest.raises(ValueError):public_research.web_search(secret)
