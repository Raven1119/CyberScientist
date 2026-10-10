import base64
import json
from urllib.parse import quote
import pytest
from cyberscientist import config, gate_reviews, native_logs


def test_rh02_public_bearer_phrase_passes(monkeypatch):
    monkeypatch.setattr(config, 'sensitive_values', lambda: [])
    for phrase in ('normal Playground user bearer token', 'token bearer password', 'Bearer short'):
        assert not native_logs.contains_secrets(json.dumps({'text': phrase}))


@pytest.mark.parametrize('encode', [lambda s: s, quote, lambda s: quote(quote(s, safe=''), safe=''), lambda s: base64.b64encode(s.encode()).decode(), lambda s: json.dumps(s)[1:-1]])
def test_stored_credential_cannot_be_released(monkeypatch, encode):
    secret = 'fixture /private+credential"value'
    monkeypatch.setattr(config, 'sensitive_values', lambda: [secret])
    text = json.dumps({'text': encode(secret)})
    with pytest.raises(ValueError, match='不得改写'):
        native_logs.assert_safe(text)
    item = gate_reviews.pending()['items'][0]
    assert item['exact_stored'] == 1
    with pytest.raises(ValueError, match='禁止人工放行'):
        gate_reviews.resolve(item['id'], false_positive=True, reason='test')


def test_shape_release_is_scoped_to_unchanged_content(monkeypatch):
    monkeypatch.setattr(config, 'sensitive_values', lambda: [])
    text = json.dumps({'text': 'public fixture Bearer ' + 'q'*25})
    with pytest.raises(ValueError):
        native_logs.assert_safe(text)
    item = gate_reviews.pending()['items'][0]
    assert 'q'*25 not in item['context']
    gate_reviews.resolve(item['id'], false_positive=True, reason='public synthetic example')
    native_logs.assert_safe(text)
    with pytest.raises(ValueError):
        native_logs.assert_safe(json.dumps({'text': 'different Bearer ' + 'q'*25}))
