import json
from datetime import datetime, timezone, timedelta
import pytest
from cyberscientist import auto_harvest, db, observation, config
from test_auto_harvest import seed
from test_deadline_harvest_cs12 import track, harvests

@pytest.mark.parametrize('window_score', [100, 60])
def test_unlimited_zero_count_harvests_confirmed_score(window_score):
    rid, source = seed(window_score)
    db.execute('UPDATE authorizations SET unlimited_resources=1,max_submissions=0 WHERE run_id=?', (rid,))
    track(rid, 'unlimited', datetime.now(timezone.utc)+timedelta(hours=1 if window_score<100 else 4))
    snapshot = json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (rid,))[0])
    snapshot['competition']['budget_policy'] = 'track-unlimited/v1'
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?', (json.dumps(snapshot), rid))
    auto_harvest.advance_sync()
    assert len(harvests()) == 1
    assert harvests()[0]['package_sha256'] == source['package_sha256']
    auto_harvest.advance_sync()
    assert len(harvests()) == 1


def test_structured_redaction_keeps_escaped_json_and_long_trace():
    value = [{'output': 'x'*1_000_000 + ' {"token": "secret\\\"quote", "more": "safe"}', 'nested': {'n': 42, 'token': 'sensitive'}}]
    safe = observation.redact_structure(value)
    assert json.loads(json.dumps(safe, ensure_ascii=False)) == safe
    assert safe[0]['nested'] == {'n': 42, 'token': '[REDACTED]'}
    assert 'sensitive' not in json.dumps(safe)


def test_expiry_only_file_difference_is_registered_without_rewriting_bytes():
    from pathlib import Path
    from datetime import timedelta
    from cyberscientist import experiences, environment_facts, config
    from test_environment_facts import _run
    rid = _run()
    event = db.append_event(rid, 'controller', 'sandbox.environment_observed', {'action': 'quota'})
    saved = environment_facts.record('expiry-repair', 'quota', {'available': 2}, event)
    current = experiences.get_experience(saved['id'])
    fm = dict(current['frontmatter']); fm['recheck_after'] = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    experiences.save_experience(saved['id'], fm, current['body_md'], 'system_environment', 'test old receipt', current['current_hash'])
    current = experiences.get_experience(saved['id']); old_revision = current['revision_id']
    fm = dict(current['frontmatter']); fm.update(status='candidate', review_note='待复核：真实回执超过 recheck_after；新回执到来前不注入')
    path = config.EXPERIENCE_DIR/'global'/(saved['id']+'.md')
    path.write_text(experiences._render(fm, current['body_md']))
    before = path.read_bytes()
    repaired = experiences.get_experience(saved['id'])
    assert repaired['revision_id'] != old_revision
    assert repaired['frontmatter']['status'] == 'candidate'
    assert path.read_bytes() == before
    assert saved['id'] not in {e['id'] for e in experiences.active_experiences()}
    path.write_text(path.read_text().replace('"available": 2', '"available": 99'))
    with pytest.raises(experiences.ExperienceError, match='环境事实'):
        experiences.get_experience(saved['id'])


def test_known_server_handoff_and_missing_characterization_preflight():
    from cyberscientist import package_seal
    assert 'handoff.status' in ' '.join(package_seal.preflight_files({'arm_manifest.json': json.dumps({'handoff': {'status': 'complete'}}).encode()}))
    assert 'characterization' in ' '.join(package_seal.preflight_files({'arm_manifest.json': json.dumps({'characterization': {'path': 'missing.json'}}).encode()}))
    assert package_seal.preflight_files({'arm_manifest.json': b'{"handoff":{"status":"partial"}}'}) == []


@pytest.mark.parametrize('score,remaining_hours', [(100,4),(60,1)])
async def test_one_click_confirmation_score_and_automatic_harvest(score,remaining_hours):
    settings=config.load_settings();settings['features']['auto_harvest']=True;config.save_settings(settings)
    from cyberscientist import competition, evaluations, mailboxes
    from test_competition import FakeController, template
    from test_mailboxes import _seed_challenge, _make_package, _set_scored, _legacy_prediction_run
    _seed_challenge()
    rnd=competition.import_round(['MB_CH'],mode='demo')
    value=template(); value['authorization']['unlimited_resources']=True
    competition.set_clock(rnd['id'],{'start':datetime.now(timezone.utc).isoformat(),'end':(datetime.now(timezone.utc)+timedelta(hours=remaining_hours)).isoformat()})
    competition.confirm(rnd['id'],value)
    ctl=FakeController();ctl.throttled=True
    await evaluations.advance(ctl)
    run=db.query_one('SELECT * FROM runs')
    auth=db.query_one('SELECT * FROM authorizations WHERE run_id=?',(run['id'],))
    assert auth['unlimited_resources'] and auth['max_submissions']==0
    _legacy_prediction_run(run['id']);_make_package(run['id'])
    mailboxes.register_experiment(1);mailboxes.add_harvest('owned@example.com','fixture-harvest')
    src=mailboxes.submit_experiment(run['id'],'trial_mb1',None,'one-click-exp')
    _set_scored(src['id'],score);auto_harvest.advance_sync()
    assert harvests()[0]['package_sha256']==src['package_sha256']
