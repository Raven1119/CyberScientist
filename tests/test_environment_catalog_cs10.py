"""Catalog choices, real gateway evidence and failure-driven restoration plans."""
import hashlib
import json
import pytest
from httpx import ASGITransport, AsyncClient
from cyberscientist import api, collab, compute, config, db, environment_catalog as catalog, environment_saves, planning, sandboxes
from test_sandboxes import run
from test_collaboration import FakeExecutor, _decision, _rig, _seed_challenge, _review_result


def descriptor(name='public-start'):
    return {'id': name, 'type': 'public_image', 'topic_types': ['infrastructure'],
            'image': 'registry.example/python:fixed', 'restore_command': '',
            'contents': {'python': '3.10.6'}, 'smoke_command': 'python3 --version',
            'reproduction_md': 'FROM registry.example/python:fixed\nRUN python3 --version',
            'known_issues': ['This is a synthetic test entry']}


def proof():
    return [{'channel': 'sandbox', 'status': 'verified', 'exit_code': 0,
             'source': 'fixture://native-smoke', 'observed_at': db.utcnow(), 'elapsed_seconds': 1.0,
             'receipt_sha256': 'a'*64, 'output_sha256': 'b'*64}]


def test_recipe_cannot_become_verified_without_receipts_and_catalog_cannot_be_overwritten():
    with pytest.raises(ValueError, match='配方不是'): catalog.register_verified(descriptor(), [])
    item = catalog.register_verified(descriptor(), proof())
    changed = descriptor(); changed['contents']['python'] = '3.11'
    with pytest.raises(ValueError, match='不可覆盖'): catalog.register_verified(changed, proof())
    db.init_db(); db.init_db()
    assert catalog.items()[0]['sha256'] == item['sha256']


async def test_pi_choice_restore_smoke_failure_switch_and_actual_executor_prompt(run, monkeypatch):
    controller, rid, _, _, _ = run
    for name in ('public-start', 'other-start'): catalog.register_verified(descriptor(name), proof())
    with pytest.raises(ValueError, match='首份研究'): planning.record_brief(rid, {'problem_md': 'fixture'}, 'bad')
    brief = {'problem_md': 'fixture', 'environment_choice': {'mode': 'catalog', 'entry_id': 'public-start', 'reason_md': 'Known starting Python'}}
    planning.record_brief(rid, brief, 'selected')
    assert planning.startup(rid, controller._challenge_for_run(controller._require_run(rid)))['environment_catalog'][0]['contents']['python'] == '3.10.6'
    plan = catalog.prepare(rid)
    assert plan['not_executed'] and plan['entry']['id'] == 'public-start'
    sid = sandboxes.create(rid, 'restore-start', {'image': descriptor()['image'], 'timeout': 600})['sandbox_id']
    original = compute._native
    def fail_smoke(args, **kwargs):
        if args[:2] == ['sandbox', 'exec']:
            return {'ok': True, 'exit_code': 0, 'stdout': json.dumps({'data': {'exit_code': 1, 'stderr': 'missing dependency'}}), 'stderr': ''}
        return original(args, **kwargs)
    monkeypatch.setattr(compute, '_native', fail_smoke)
    sandboxes.execute(rid, sid, descriptor()['smoke_command'], 30, 'failed-smoke')
    failed = catalog.observe_smoke(rid, 'failed-smoke')
    assert failed['status'] == 'failed' and failed['exit_code'] == 1
    replacement = catalog.prepare(rid, 'other-start', 'First entry smoke failed; choose another starting point')
    assert replacement['entry']['id'] == 'other-start'
    monkeypatch.setattr(compute, '_native', lambda args, **kw: {'ok': True, 'exit_code': 0, 'stdout': json.dumps({'data': {'exit_code': 0, 'stdout': 'Python 3.10.6'}}), 'stderr': ''})
    sandboxes.execute(rid, sid, descriptor()['smoke_command'], 30, 'passed-smoke')
    assert catalog.observe_smoke(rid, 'passed-smoke')['status'] == 'passed'
    db.execute('UPDATE compute_sandbox_operations SET receipt_sha256=? WHERE operation_id=?', ('c'*64, 'passed-smoke'))
    with pytest.raises(ValueError, match='哈希'): catalog.observe_smoke(rid, 'passed-smoke')
    executor = FakeExecutor(); controller._prime_instances[rid] = executor; controller._prime_sessions[rid] = 'fixture'
    db.execute('UPDATE runs SET current_trial_id=NULL WHERE id=?', (rid,))
    await controller._apply_decision(rid, _decision([{'op': 'start_trial', 'goal': 'Synthetic next trial', 'success_check': 'smoke'}], rid=rid), {}, None, None)
    assert '第一步调用research_environment' in executor.prompts[0][1] and 'other-start' in executor.prompts[0][1]
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='environment.smoke_result' AND json_extract(payload,'$.status')='failed'", (rid,))


async def test_catalog_api_and_tool_paths_and_toggle_preserve_data(run):
    _, rid, _, _, _ = run
    catalog.register_verified(descriptor(), proof())
    with db.transaction() as conn: token = collab.issue_token(conn, rid, 'executor', 'fixture', 1)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        assert (await client.get('/api/v1/environment-catalog')).json()['items'][0]['id'] == 'public-start'
        headers = {'Authorization': 'Bearer ' + token}
        assert (await client.post('/api/v1/tools/environment', headers=headers, json={'action': 'restore'})).status_code == 422
        response = await client.post('/api/v1/tools/environment', headers=headers, json={'action': 'restore', 'entry_id': 'public-start', 'reason_md': 'fixture choice'})
        assert response.status_code == 200 and response.json()['not_executed']
    with pytest.raises(compute.ComputeError, match='不保存环境新版本'):
        environment_saves.save(rid, 'forbidden-version', 'FROM fixture', 'public', 'true')
    settings = config.load_settings(); settings['features']['environment_catalog'] = False; config.save_settings(settings)
    assert catalog.executor_instructions(rid) == '' and len(catalog.items()) == 1
    assert catalog.current(rid)['entry_id'] == 'public-start'


async def test_catalog_switch_rejects_text_in_settings_api():
    settings = config.load_settings(); settings['features']['environment_catalog'] = 'false'
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        response = await client.put('/api/v1/settings', json={'settings': settings, 'base_revision': settings['revision']})
    assert response.status_code == 422 and '布尔' in response.json()['detail']['message']


def test_from_zero_is_explicit_and_does_not_fabricate_verified_catalog(run):
    _, rid, _, _, _ = run
    selected = catalog.choose(rid, {'mode': 'from_zero', 'reason_md': 'Need a new base version'})
    assert selected['mode'] == 'from_zero' and catalog.prepare(rid)['entry'] is None
    assert not catalog.items()


async def test_startup_decision_and_milestone_review_both_persist_environment_choice():
    from cyberscientist.brains.codex import CodexBrain
    _seed_challenge(); controller, brain, executor = _rig(shadow=False)
    catalog.register_verified(descriptor(), proof())
    rid = controller.create_run('COLLAB_CH', mode='connected')['id']
    controller.authorize(rid, 'fixture', True, 10, 60, 0, '')
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    controller._prime_sessions[rid] = await executor.start({})
    request = controller._enqueue_lifecycle(rid, 'run_start')
    decision = _decision([{'op': 'start_trial', 'goal': 'fixture', 'success_check': 'smoke'}], rid=rid)
    decision['research_brief'] = {'environment_choice': {'mode': 'catalog', 'entry_id': 'public-start', 'reason_md': 'Verified starting image'}}
    await brain.results.put({'decision': decision})
    await controller._run_one_review_impl(rid, db.query_one('SELECT * FROM review_requests WHERE id=?', (request,)), brain, None)
    packet = brain.calls[0]
    assert 'environment_choice' in packet['research_startup']['brief_fields']
    assert '必须在research_brief内写environment_choice' in CodexBrain._render_prompt(packet)
    assert catalog.current(rid)['entry_id'] == 'public-start'
    assert '第一步调用research_environment' in executor.prompts[0][1]
    request = controller._enqueue_lifecycle(rid, 'milestone')
    db.execute("UPDATE review_requests SET status='running' WHERE id=?", (request,))
    result = _review_result('fixture-frame')
    result['research_brief'] = {'environment_choice': {'mode': 'from_zero', 'reason_md': 'Need a different base Python'}}
    controller._apply_review_result(rid, db.query_one('SELECT * FROM review_requests WHERE id=?', (request,)), 'requested', {'frame_id': 'fixture-frame'}, result)
    assert catalog.current(rid)['mode'] == 'from_zero'


@pytest.mark.parametrize('business_error', [{'ok': False, 'data': {'exit_code': 0}}, {'ok': True, 'data': {'exit_code': 0, 'error': 'business failed'}}])
def test_cli_exit_zero_cannot_override_failed_business_receipt(run, monkeypatch, business_error):
    _, rid, _, _, _ = run
    catalog.register_verified(descriptor(), proof())
    catalog.choose(rid, {'mode': 'catalog', 'entry_id': 'public-start', 'reason_md': 'fixture'})
    sid = sandboxes.create(rid, 'business-box', {'image': descriptor()['image'], 'timeout': 600})['sandbox_id']
    monkeypatch.setattr(compute, '_native', lambda *a, **k: {'ok': True, 'exit_code': 0, 'stdout': json.dumps(business_error), 'stderr': ''})
    sandboxes.execute(rid, sid, descriptor()['smoke_command'], 30, 'business-smoke')
    assert catalog.observe_smoke(rid, 'business-smoke')['status'] == 'failed'


def test_bundle_requires_actual_restore_and_smoke_command_in_same_receipt(run, monkeypatch):
    _, rid, _, _, _ = run
    entry = descriptor('public-bundle'); entry.update(type='environment_bundle', image='', restore_command='tar xf /public/env.tar -C /tmp')
    catalog.register_verified(entry, proof())
    plan = catalog.prepare(rid, entry['id'], 'Restore public locked bundle')
    assert plan['execution_command'] == entry['restore_command'] + ' && ' + entry['smoke_command']
    sid = sandboxes.create(rid, 'bundle-box', {'timeout': 600})['sandbox_id']
    monkeypatch.setattr(compute, '_native', lambda *a, **k: {'ok': True, 'exit_code': 0, 'stdout': json.dumps({'data': {'exit_code': 0, 'stdout': 'Python 3.10.6'}}), 'stderr': ''})
    sandboxes.execute(rid, sid, entry['smoke_command'], 30, 'missing-restore')
    with pytest.raises(ValueError, match='命令'): catalog.observe_smoke(rid, 'missing-restore')
    sandboxes.execute(rid, sid, plan['execution_command'], 30, 'restored-bundle')
    assert catalog.observe_smoke(rid, 'restored-bundle')['status'] == 'passed'
