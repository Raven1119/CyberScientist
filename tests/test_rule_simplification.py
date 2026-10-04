"""D40 regression probes use synthetic credentials and ordinary Run grants."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cyberscientist import api, config, db, mailboxes
from test_mailboxes import _make_package, _make_run, _seed_challenge


async def test_settings_and_secret_changes_never_write_global_prime_configuration(monkeypatch, tmp_path):
    # Changing a usable profile previously wrote a raw key into global models.json.
    home = tmp_path / 'native-home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    settings = config.load_settings()
    settings['llm_profiles'] = [{'id': 'fake', 'protocol': 'openai_chat_completions',
        'secret_ref': 'local:fixture', 'model_id': 'synthetic', 'base_url': 'https://invalid.example'}]
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        written = await client.post('/api/v1/secrets', json={'secret_id': 'fixture', 'value': 'SYNTHETIC_TEST_SECRET'})
        assert written.status_code == 200
        changed = await client.put('/api/v1/settings', json={'settings': settings, 'base_revision': settings['revision']})
        assert changed.status_code == 200
        status = (await client.get('/api/v1/settings')).json()['_status']
        assert status['prime_authentication'] == 'native_unknown'
        assert 'SYNTHETIC_TEST_SECRET' not in json.dumps(status)
        assert not (home / '.prime').exists()
        deleted = await client.delete('/api/v1/secrets/fixture')
        assert deleted.status_code == 200
        assert not (home / '.prime').exists()


def test_legacy_report_marker_does_not_override_ordinary_submission_permission():
    _seed_challenge()
    rid = _make_run(max_submissions=1)
    _make_package(rid)
    snapshot = json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (rid,))['config_snapshot'])
    snapshot['eval_mode'] = {'enabled': True, 'experience_manifests': {'both': []}}
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?', (json.dumps(snapshot), rid))
    mailboxes.register_experiment(1)
    sent = mailboxes.submit_experiment(rid, 'trial_mb1', None, 'ordinary-with-marker')
    assert sent['id']
    with pytest.raises(mailboxes.MailboxError) as exc:
        mailboxes.submit_experiment(rid, 'trial_mb1', None, 'exceeded-budget')
    assert exc.value.code == 'NEEDS_AUTHORIZATION'


def test_submission_uses_active_clock_and_still_rejects_exhausted_time():
    _seed_challenge()
    rid = _make_run()
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    db.execute("UPDATE runs SET phase='running',clock_version=1,started_at=?,active_elapsed_seconds=20 WHERE id=?", (old, rid))
    with db.transaction() as conn:
        mailboxes._check_budget(conn, rid)
    db.execute('UPDATE runs SET active_elapsed_seconds=1800 WHERE id=?', (rid,))
    with pytest.raises(mailboxes.MailboxError, match='时长'), db.transaction() as conn:
        mailboxes._check_budget(conn, rid)


def test_observation_watchlist_is_advice_without_three_item_cap():
    from cyberscientist import collab, observation
    from test_collaboration import _review_result
    watches = [{'id': str(i), 'hypothesis_md': 'fixture hypothesis',
        'evidence_needed_md': 'fixture evidence', 'intervene_when_md': 'fixture condition', 'evidence_refs': []} for i in range(4)]
    result = _review_result('frame-fixture')
    result['watchlist'] = watches
    collab._validate(result, 'ReviewResult')
    _seed_challenge()
    rid = _make_run()
    db.execute('INSERT INTO supervision(run_id,watchlist,updated_at) VALUES(?,?,?)', (rid, json.dumps(watches), db.utcnow()))
    frame = observation.build_frame(rid, mode='shadow', frame_id='fixture', from_seq=1,
                                    through_seq=1, shadow_cfg={'max_reviews': 8})
    assert frame['watchlist'] == watches
