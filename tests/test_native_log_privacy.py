"""Native records stay byte-exact; presentation redaction is not a classifier."""
import json
import hashlib
import io
import zipfile

import pytest

from cyberscientist import config, db, native_logs
from test_trace_narrative import _fixture


def _snapshot(tmp_path, content, monkeypatch, secrets=()):
    rid, tid, *_ = _fixture()
    monkeypatch.setattr(config, 'sensitive_values', lambda: list(secrets))
    rows = [{'type': 'session_meta', 'payload': {'id': 'native-privacy',
             'developer_instructions': 'Use a task-specific variable name.'}}, *content]
    raw = ('\n'.join(json.dumps(r) for r in rows) + '\n').encode()
    path = tmp_path / 'native.jsonl'
    path.write_bytes(raw)
    db.append_event(rid, 'controller', 'trial.native_session_bound',
        {'session_id': 'native-privacy', 'native_log_path': str(path)}, trial_id=tid)
    result = native_logs.snapshot(rid, tid)
    assert path.read_bytes() == raw
    assert result['bytes'] == raw
    return result


def test_public_examples_and_native_ciphertext_are_not_credentials(tmp_path, monkeypatch):
    result = _snapshot(tmp_path, [
        {'type': 'response_item', 'payload': {'type': 'reasoning',
            'encrypted_content': 'opaque-sk-random_gho_fragment-sk-random',
            'summary': [{'text': 'task-specific public-task-contract-v1'}]}},
        {'type': 'response_item', 'payload': {'type': 'function_call_output',
            'output': 'curl -H "Authorization: Bearer YOUR_API_KEY"; export BOHR_ACCESS_KEY=... python sdbx.py'}},
        {'type': 'event_msg', 'payload': {'text': '{"access_key":"YOUR_BOHR_ACCESS_KEY", "authorization":"Bearer YOUR_PLAYGROUND_API_KEY"}'}},
        {'type': 'event_msg', 'payload': {'text': 'export BOHR_ACCESS_KEY=<YOUR_BOHR_ACCESS_KEY>'}},
        {'type': 'event_msg', 'payload': {'text': 'curl -H "Authorization: Bearer abc_..."'}},
        {'type': 'event_msg', 'payload': {'text': r'export BOHR_ACCESS_KEY=...\npython3 sdbx.py doctor --json'}},
        {'type': 'event_msg', 'payload': {'text': r'export BOHR_ACCESS_KEY=<YOUR_BOHR_ACCESS_KEY>\npython3 sdbx.py doctor --json'}},
    ], monkeypatch)
    from cyberscientist import cli_submission
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('arm_manifest.json', json.dumps({'raw_messages': 'raw_messages.jsonl'}))
        archive.writestr('raw_messages.jsonl', result['bytes'])
        archive.writestr('provenance/native_session.json', json.dumps({
            'session_id': 'native-privacy', 'sha256': hashlib.sha256(result['bytes']).hexdigest()}))
    assert cli_submission._files(output.getvalue())[1] == result['bytes']


@pytest.mark.parametrize('text', [
    'sk-private-test-value-that-is-long', 'Bearer actual-unknown-token-that-is-long',
    'export BOHR_ACCESS_KEY=actual-unknown-value-that-is-long python run.py',
    r'export BOHR_ACCESS_KEY=actual-unknown-value-that-is-long\npython run.py',
    '{"api_key":"actual-unknown-value-that-is-long"}',
    'https://files.example/data?access_key=actual-unknown-value-that-is-long',
    'https%3A%2F%2Ffiles.example%2Fdata%3Faccess_key%3Dactual-unknown-value-that-is-long',
    '-----BEGIN PRIVATE KEY-----\nprivate material\n-----END PRIVATE KEY-----',
])
def test_real_credential_shapes_still_block(tmp_path, monkeypatch, text):
    with pytest.raises(ValueError, match='不得改写'):
        _snapshot(tmp_path, [{'type': 'event_msg', 'payload': {'message': text}}], monkeypatch)


def test_known_secret_is_blocked_even_inside_opaque_provider_field(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='不得改写'):
        _snapshot(tmp_path, [{'type': 'response_item', 'payload': {'type': 'reasoning',
            'encrypted_content': 'known-test-credential'}}], monkeypatch,
            secrets=('known-test-credential',))


def test_user_text_cannot_claim_the_provider_ciphertext_exception(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='不得改写'):
        _snapshot(tmp_path, [{'type': 'event_msg', 'payload': {
            'encrypted_content': 'sk-real-unknown-value-that-is-long'}}], monkeypatch)


def test_placeholder_exception_does_not_bypass_a_known_secret(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='不得改写'):
        _snapshot(tmp_path, [{'type': 'event_msg', 'payload': {'message': 'YOUR_API_KEY'}}],
                  monkeypatch, secrets=('YOUR_API_KEY',))


def test_seal_failure_exposes_a_bounded_redacted_reason(monkeypatch):
    from cyberscientist import mailboxes, package_seal
    rid, tid, _, _, rows, _, _, _, trial_dir = _fixture()
    (trial_dir / 'trace_narrative.jsonl').write_text(
        '\n'.join(json.dumps(row) for row in rows) + '\n')
    secret = 'fixture-diagnostic-credential'
    monkeypatch.setattr(config, 'sensitive_values', lambda: [secret])
    def broken(*args, **kwargs):
        raise ValueError('specific seal cause ' + secret)
    monkeypatch.setattr(package_seal, 'seal', broken)
    with pytest.raises(mailboxes.MailboxError) as error:
        mailboxes.preflight_submission(rid, tid, None)
    assert 'specific seal cause' in str(error.value)
    assert secret not in str(error.value)
    preview = mailboxes.inspect_trace_narrative(rid, tid, None)
    assert 'specific seal cause' in preview['reasons'][0]
    assert secret not in preview['reasons'][0]
    row = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='submission.preflight_failed' ORDER BY seq DESC LIMIT 1", (rid,))
    assert secret not in row['payload']
