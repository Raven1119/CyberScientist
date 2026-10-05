import copy
import hashlib
import json
from httpx import ASGITransport, AsyncClient
from cyberscientist import alerts, api, competition, config, db, protocol_drift, runtime_facts
from test_competition import challenges
from test_mailboxes import _make_run, _seed_challenge
REAL_FETCH = protocol_drift.fetch_documents


def fetch_fixture(monkeypatch, changed=False):
    docs, meta = protocol_drift._baseline(config.load_settings()['playground']['base_url'])
    docs, meta = copy.deepcopy(docs), copy.deepcopy(meta)
    if changed:
        docs['protocol']['version'] = 'new-public-version'
        meta['protocol']['sha256'] = hashlib.sha256(json.dumps(docs['protocol']).encode()).hexdigest()
    calls = []
    def fetch(): calls.append(True); return docs, meta
    monkeypatch.setattr(protocol_drift, 'fetch_documents', fetch)
    return calls


def test_changed_protocol_field_is_persisted_popup_and_all_pi_operating_facts(monkeypatch):
    calls = fetch_fixture(monkeypatch, True)
    result = protocol_drift.check()
    assert result['status'] == 'changed' and result['changes'][0]['changed_paths'] == ['version']
    _seed_challenge(); rid = _make_run()
    assert runtime_facts.facts(rid)['platform_protocol_drift'] == result
    assert alerts.pending()[0]['kind'] == 'platform.protocol_changed'
    result = protocol_drift.check(); assert len(alerts.pending()) == 1
    db.init_db(); assert protocol_drift.facts() == result
    assert len(calls) == 2


def test_unchanged_does_not_popup_and_off_preserves_previous_observation(monkeypatch):
    calls = fetch_fixture(monkeypatch)
    result = protocol_drift.check(); assert result['status'] == 'unchanged' and not alerts.pending()
    settings = config.load_settings(); settings['features']['protocol_drift'] = False; config.save_settings(settings)
    disabled = protocol_drift.check(); assert disabled['status'] == 'disabled' and disabled['last_observation'] == result
    assert len(calls) == 1


def test_unknown_never_claims_no_change_or_discards_pending_alert(monkeypatch):
    fetch_fixture(monkeypatch, True); protocol_drift.check()
    def fail(): raise TimeoutError('public fetch timeout')
    monkeypatch.setattr(protocol_drift, 'fetch_documents', fail)
    result = protocol_drift.check()
    assert result['status'] == 'unknown' and result['last_verified']['changes'][0]['changed_paths'] == ['version']
    assert alerts.pending()[0]['kind'] == 'platform.protocol_changed'


def test_import_round_checks_fresh_contracts_without_starting_run(monkeypatch):
    calls = fetch_fixture(monkeypatch, True); ids = challenges(10)
    round_value = competition.import_round(ids, mode='connected')
    assert calls == [True] and round_value['protocol_drift']['status'] == 'changed'
    assert not db.query('SELECT * FROM runs') and not db.query('SELECT * FROM authorizations')


async def test_frontend_real_routes_and_off_do_not_fetch(monkeypatch):
    calls = fetch_fixture(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        response = await client.post('/api/v1/protocol-drift/check')
        assert response.status_code == 200 and response.json()['status'] == 'unchanged'
        assert (await client.get('/api/v1/protocol-drift')).json()['status'] == 'unchanged'
    assert calls == [True]


def test_changed_schema_reference_404_still_reports_observed_protocol_change(monkeypatch):
    import io
    import urllib.error
    from urllib.parse import urlsplit
    docs, _ = protocol_drift._baseline(config.load_settings()['playground']['base_url'])
    protocol = copy.deepcopy(docs['protocol']); protocol['schemas']['arm_manifest'] = '/api/schemas/new-unavailable'
    requests = []
    class Response(io.BytesIO):
        status = 200
        def __init__(self, url, raw): super().__init__(raw); self.url = url
        def geturl(self): return self.url
    def opening(request, timeout):
        requests.append(request)
        path = urlsplit(request.full_url).path
        if path == '/api/schemas/new-unavailable': raise urllib.error.HTTPError(request.full_url, 404, 'missing', {}, None)
        if path == '/api/protocol': return Response(request.full_url, json.dumps(protocol).encode())
        name = next((name for name, ref in protocol['schemas'].items() if ref == path), None)
        if name: return Response(request.full_url, json.dumps(docs[name]).encode())
        name = next(name for name, ref in protocol_drift.DOCS.items() if ref == path)
        return Response(request.full_url, docs[name].encode())
    monkeypatch.setattr(protocol_drift.urllib.request, 'urlopen', opening)
    # Restore the real per-document fetch; no live external requests.
    monkeypatch.setattr(protocol_drift, 'fetch_documents', REAL_FETCH)
    result = protocol_drift.check()
    assert result['status'] == 'changed' and result['complete'] is False
    assert any(change['document'] == 'protocol' and 'schemas.arm_manifest' in change['changed_paths'] for change in result['changes'])
    assert result['documents']['arm_manifest']['status'] == 'unknown'
    assert alerts.pending()[0]['payload']['changes'] == result['changes']
    assert all('Authorization' not in request.headers for request in requests)
    assert list((config.DATA_DIR / 'platform_drift').glob('*/protocol.txt'))


def test_switching_platform_marks_old_observation_historical_not_current(monkeypatch):
    fetch_fixture(monkeypatch); protocol_drift.check()
    settings = config.load_settings(); settings['playground']['base_url'] = 'https://other.invalid/api'; config.save_settings(settings)
    result = protocol_drift.facts()
    assert result['status'] == 'unknown' and result['platform_origin'] == 'https://other.invalid'
    assert result['historical_observation']['platform_origin'] == 'https://play.bohrium.com'


def test_per_document_timeouts_preserve_latest_confirmed_change(monkeypatch):
    fetch_fixture(monkeypatch, True); previous = protocol_drift.check()
    monkeypatch.setattr(protocol_drift, 'fetch_documents', REAL_FETCH)
    def fail(*args, **kwargs): raise TimeoutError('public document timeout')
    monkeypatch.setattr(protocol_drift, '_read_public', fail)
    result = protocol_drift.check()
    assert result['status'] == 'unknown' and result['last_verified'] == previous
    assert len(result['errors']) == 6
