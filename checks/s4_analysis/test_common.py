import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from . import common


@pytest.fixture
def redactor(monkeypatch):
    monkeypatch.setattr(common, 'credentials', lambda: (
        {'key': 'fixture-' + 'k' * 40}, '', {'mailboxes': [{'email': 'our-person@example.test'}]}))
    return common.Redactor()


def test_known_and_pattern_secrets_never_survive(redactor):
    secret = 'fixture-' + 'k' * 40
    token = 'sk-' + 'a' * 40
    body = f'ordinary result 1.234; {secret}; {token}; Bearer ' + 'b' * 32
    cleaned = redactor.text(body)
    assert secret not in cleaned and token not in cleaned and 'b' * 32 not in cleaned
    assert 'ordinary result 1.234' in cleaned
    assert sum(redactor.counts.values()) == 3


def test_nested_credentials_and_emails_are_removed(redactor):
    obj = {'envdAccessToken': 'opaquevalue', 'steps': [{'body': 'Contact our-person@example.test'}],
           'author_name': 'Author kept', 'trace_score': 92.125}
    result = redactor.obj(obj)
    assert result['envdAccessToken'] == '[REDACTED]'
    assert '@' not in json.dumps(result)
    assert result['author_name'] == 'Author kept' and result['trace_score'] == 92.125


def test_multiline_pem_and_truncated_pem_are_redacted(redactor):
    for end in ['-----END PRIVATE KEY-----', '']:
        value = '-----BEGIN PRIVATE KEY-----\n' + 'c' * 200 + '\n' + end
        assert 'c' * 20 not in redactor.text(value)


def test_per_request_counts_do_not_mix_between_workers(redactor):
    def scrub(count):
        local = redactor.fork()
        local.text(('sk-' + 'a' * 32 + ' ') * count)
        return local.counts['provider_key']
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(scrub, range(1, 9))) == list(range(1, 9))
    assert not redactor.counts


def test_ours_is_identified_before_redaction_without_blank_matches(redactor):
    assert redactor.identify_ours({'author': {'email': 'our-person@example.test'}})
    assert not redactor.identify_ours({'author_name': 'other author'})


def test_compressed_persistence_roundtrip(tmp_path):
    raw = b'{"scientific_value":1.234}\n'
    path = tmp_path / 'receipt.json.zst'
    common.atomic(path, common.zstd(raw))
    assert common.unzstd(path.read_bytes()) == raw
    assert path.stat().st_mode & 0o777 == 0o600


def test_public_client_rejects_nonplatform_origins_before_request(tmp_path):
    client = common.PublicClient(tmp_path)
    for path in ['http://play.bohrium.com/api/protocol', 'https://localhost/api', 'https://evil.example/api']:
        with pytest.raises(ValueError, match='authorized public'):
            client.get(path)


def test_prefixed_credentials_in_objects_and_embedded_json_are_redacted(redactor):
    value = 'foreign-' + 'q' * 32
    data={'aws_secret_access_key':value,'BOHR_ACCESS_KEY':value,'CLOUD_ACCESS_KEY':value,'refresh_token':value,
          'body':'export CLOUD_ACCESS_KEY=' + value + '\n' + json.dumps({'refresh_token':value})}
    assert value not in json.dumps(redactor.obj(data))


def test_credentials_in_json_keys_are_removed_without_losing_colliding_values(redactor):
    first='fixture-'+'k'*40
    second='sk-'+'a'*40
    result=redactor.obj({first:1,second:2,'normal':3})
    assert first not in json.dumps(result) and second not in json.dumps(result)
    assert sorted(result.values())==[1,2,3]


def test_sensitive_containers_and_numeric_passwords_are_redacted(redactor):
    opaque='opaque-'+'q'*32
    data={'credentials':{'default':opaque},'access_token':[opaque],'password':123456789,'pass':True}
    result=redactor.obj(data)
    assert opaque not in json.dumps(result) and result['password']=='[REDACTED]'
    assert result['pass'] is True


def test_long_scientific_or_binary_runs_do_not_trigger_quadratic_email_search(redactor):
    import time
    value='a'*1_000_000+'@example.test'
    started=time.monotonic()
    assert redactor.text(value)==value
    assert time.monotonic()-started<10


@pytest.mark.parametrize('codes',[(404,200),(404,404)])
def test_public_404_is_retried_once_then_resolved_or_reported(tmp_path,monkeypatch,codes):
    import httpx
    calls=[];original=httpx.Client
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(codes[len(calls)-1],json={'ok':True},request=request)
    monkeypatch.setattr(common.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    monkeypatch.setattr(common.PublicClient,'rate',lambda self:None)
    monkeypatch.setattr(common.time,'sleep',lambda _:None)
    client=common.PublicClient(tmp_path)
    if codes[-1]==200:assert client.get('/api/protocol')=={'ok':True}
    else:
        with pytest.raises(RuntimeError,match='status=404'):client.get('/api/protocol')
    assert len(calls)==2


def test_atomic_concurrent_writers_leave_one_complete_value(tmp_path):
    p=tmp_path/'result.json'
    values=[json.dumps({'index':i,'value':'x'*1000}).encode() for i in range(20)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda raw:common.atomic(p,raw),values))
    assert p.read_bytes() in values
    assert not list(tmp_path.glob('*.tmp'))


def test_typed_public_scientific_tokens_and_resource_keys_are_not_credentials(redactor):
    value='scientific-answer-identifier'
    obj={'resultsJson':{'answers':[{'token':value}]},'datasets':[{'key':value}],
         'token':'opaque-'+'z'*32,'session_id':'session-identifier-kept'}
    result=redactor.obj(obj)
    assert result['resultsJson']['answers'][0]['token']==value
    assert result['datasets'][0]['key']==value
    assert result['token']=='[REDACTED]' and result['session_id']==obj['session_id']
