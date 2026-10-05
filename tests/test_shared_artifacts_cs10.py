import io
import json
import zipfile
import pytest
from httpx import ASGITransport, AsyncClient
from cyberscientist import api, collab, config, db, shared_artifacts as shared, package_seal
from test_trace_narrative import _fixture
from test_mailboxes import _make_run
from test_local_scoring import _scorer


def two_runs():
    rid, tid, *_ = _fixture(); other = _make_run()
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at) VALUES('recipient',?,'import','fixture','active',?)", (other, db.utcnow()))
    for run_id, trial_id in ((rid, tid), (other, 'recipient')):
        db.execute("UPDATE runs SET phase='running',current_trial_id=? WHERE id=?", (trial_id, run_id))
    source = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / tid / 'answer.txt'
    source.write_bytes(b'answer=42\n')
    evidence = db.append_event(rid, 'prime', 'artifact.created', {'path': 'answer.txt'}, trial_id=tid)
    return rid, tid, other, source, evidence['seq']


async def test_two_runs_publish_import_versions_trace_and_backend_formal_validator(monkeypatch):
    rid, tid, other, source, seq = two_runs(); _scorer()
    # Exercise capability routes, not just service helpers.
    monkeypatch.setattr(collab, 'validate_token', lambda token: {'run_id': rid if token == 'publisher' else other, 'role': 'executor'})
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        response = await client.post('/api/v1/tools/shared', headers={'authorization': 'Bearer publisher'}, json={
            'action': 'publish', 'trial_id': tid, 'name': 'answer.txt', 'source_path': 'answer.txt', 'source_event_seq': seq})
        assert response.status_code == 200, response.text
        first = response.json()
        source.write_bytes(b'new revision\n')
        second = shared.publish(rid, tid, 'answer.txt', 'answer.txt', seq)
        assert first['version'] == 1 and second['version'] == 2 and first['sha256'] != second['sha256']
        response = await client.post('/api/v1/tools/shared', headers={'authorization': 'Bearer recipient'},
            json={'action': 'import', 'trial_id': 'recipient', 'artifact_id': first['id']})
        assert response.status_code == 200, response.text
        imported = response.json()
        destination = config.WORKSPACE_DIR / 'runs' / other / 'trials' / 'recipient' / imported['path']
        assert destination.read_bytes() == b'answer=42\n'
        event = next(e for e in db.events_after(other, 0) if e['seq'] == imported['event_seq'])
        assert event['type'] == 'shared.imported' and event['trial_id'] == 'recipient'
        assert event['payload']['source_run_id'] == rid and event['payload']['source_event_seq'] == seq
        package = io.BytesIO()
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('arm_manifest.json', json.dumps({'arm_version': '1.1', 'entrypoint': 'run.py', 'trace': 'traces/trace.jsonl'}))
            archive.writestr('run.py', 'print(42)')
            archive.writestr('traces/trace.jsonl', '')
        sealed, projected = package_seal.seal(package.getvalue(), other, 'recipient', imported['event_seq'])
        with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
            trace = [json.loads(line) for line in archive.read(package_seal.TRACE).splitlines()]
        step = next(row for row in trace if row.get('title') == 'shared.imported')
        assert step['cs_ref'] == f"{other}#{imported['event_seq']}"
        assert rid in step['body'] and first['sha256'] in step['body'] and 'false' in step['body']
        result = await client.get('/api/v1/challenges/MB_CH/shared')
        assert result.status_code == 200
        assert result.json()['validator']['status'] == 'observed'
        assert len(result.json()['items']) == 2
    db.init_db(); db.init_db()
    assert len(db.query('SELECT * FROM challenge_shared_versions')) == 2
    assert len(db.query('SELECT * FROM challenge_validator_versions')) == 1
    assert not db.query('SELECT * FROM compute_jobs') and not db.query('SELECT * FROM compute_sandboxes')


def test_disabled_shared_area_keeps_versions_and_no_write():
    rid, tid, other, source, seq = two_runs(); item = shared.publish(rid, tid, 'answer.txt', 'answer.txt', seq)
    settings = config.load_settings(); settings['features']['shared_area'] = False; config.save_settings(settings)
    assert shared.catalog('MB_CH')['items'][0]['id'] == item['id']
    with pytest.raises(ValueError, match='关闭'): shared.import_artifact(other, 'recipient', item['id'])
    with pytest.raises(ValueError, match='关闭'): shared.publish(rid, tid, 'new', 'answer.txt', seq)


@pytest.mark.parametrize('case', ['bad_event', 'outside', 'secret', 'zip_secret', 'symlink_import', 'tampered'])
def test_exchange_rejects_wrong_provenance_secrets_and_filesystem_escape(case):
    rid, tid, other, source, seq = two_runs()
    if case == 'bad_event':
        with pytest.raises(ValueError, match='来源事件'): shared.publish(rid, tid, 'answer', 'answer.txt', seq + 10000)
    elif case == 'outside':
        with pytest.raises(ValueError, match='相对路径'): shared.publish(rid, tid, 'answer', '../answer.txt', seq)
    elif case in ('secret', 'zip_secret'):
        raw = ('sk-' + 'Q' * 48).encode()
        if case == 'zip_secret':
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive: archive.writestr('data.txt', raw)
            raw = stream.getvalue()
        source.write_bytes(raw)
        with pytest.raises(ValueError, match='密钥'): shared.publish(rid, tid, 'answer', 'answer.txt', seq)
        assert not db.query('SELECT * FROM challenge_shared_versions')
    else:
        item = shared.publish(rid, tid, 'answer', 'answer.txt', seq)
        if case == 'tampered':
            path = config.WORKSPACE_DIR / item['path']; path.chmod(0o644); path.write_bytes(b'tampered')
            assert shared.catalog('MB_CH')['items'][0]['integrity'] == 'unknown'
            with pytest.raises(ValueError, match='哈希'): shared.import_artifact(other, 'recipient', item['id'])
        else:
            recipient = config.WORKSPACE_DIR / 'runs' / other / 'trials' / 'recipient'; recipient.mkdir(parents=True, exist_ok=True)
            outside = config.DATA_DIR / 'outside'; outside.mkdir(); (recipient / 'imports').symlink_to(outside, target_is_directory=True)
            with pytest.raises(ValueError, match='符号链接'): shared.import_artifact(other, 'recipient', item['id'])
            assert not list(outside.iterdir())


async def test_pi_may_list_but_cannot_publish_or_modify_validator(monkeypatch):
    rid, tid, *_ = _fixture(); monkeypatch.setattr(collab, 'validate_token', lambda _: {'run_id': rid, 'role': 'brain'})
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        headers = {'authorization': 'Bearer brain'}
        assert (await client.post('/api/v1/tools/shared', headers=headers, json={'action': 'list'})).status_code == 200
        assert (await client.post('/api/v1/tools/shared', headers=headers, json={'action': 'publish', 'trial_id': tid})).status_code == 403
        assert (await client.post('/api/v1/tools/shared', headers=headers, json={'action': 'publish_validator'})).status_code == 403


def test_nested_unknown_token_is_rejected_and_zip_budget_checked_before_read(monkeypatch):
    def zip_one(name, raw):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive: archive.writestr(name, raw)
        return stream.getvalue()
    nested = zip_one('inner.zip', zip_one('key.txt', ('sk-' + 'Q' * 48).encode()))
    with pytest.raises(ValueError, match='密钥'): shared._clean(nested)
    bomb = zip_one('large.bin', b'0' * (shared.MAX_BYTES + 1))
    monkeypatch.setattr(config, 'sensitive_values', lambda: ['registered-fixture-token'])
    monkeypatch.setattr(zipfile.ZipFile, 'read', lambda *a, **k: pytest.fail('budget must reject before member reading'))
    with pytest.raises(ValueError, match='展开超过限制'): shared._clean(bomb)
