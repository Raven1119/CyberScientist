"""Scientific PI behavior with native-protocol fakes and backend-held cloud receipts."""
import asyncio
import json

import pytest

from cyberscientist import compute, config, db, experiences, planning, sandboxes
from cyberscientist.controller import RunController
from test_collaboration import _decision, _rig, _seed_challenge
from test_sandboxes import run


@pytest.mark.parametrize("native_root_work_package", [False, True])
async def test_first_pi_frame_reads_public_ranking_and_complete_cards_and_records_weak_work(monkeypatch, native_root_work_package):
    _seed_challenge()
    db.execute("UPDATE challenges SET origin='https://public.example/topic',resources_json='[]' WHERE id='COLLAB_CH'")
    c, brain, executor = _rig(shadow=False)
    rid = c.create_run('COLLAB_CH', mode='connected', model_config={'executor': {
        'runtime': 'codex', 'model_id': 'synthetic-mini', 'reasoning_effort': 'medium',
        'note': '便宜，适合写死的任务'}})['id']
    c.authorize(rid, 'synthetic', True, 10, 60, 0, '', max_jobs=2)
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    seen = []
    monkeypatch.setattr(planning.platform_scores, 'get', lambda run_id: seen.append(('ranking', run_id)) or {
        'status': 'observed', 'count': 2, 'best': 80})
    cards = [{'id': 'other', 'revision_id': 'r1', 'body_md': 'Use method A; it failed at large k.'}]
    monkeypatch.setattr(planning, 'strategy_cards', lambda cid: seen.append(('cards', cid)) or cards)
    request = c._enqueue_lifecycle(rid, 'run_start')
    brief = {'environment_choice': {'mode': 'from_zero', 'reason_md': 'Synthetic standalone environment'}, 'problem_md': 'Compute a converged quantity', 'science_md': 'Check its units',
        'ranked_methods': [{'name': 'B', 'reason_md': 'A failed at large k'}],
        'traps_md': 'Do not confuse eV and Hartree',
        'parallel_preparation': {'contract': 'result.json', 'verifier': 'finite units', 'environment': 'smoke'},
        'acceptance_md': 'Convergence within 1%',
        'work_package': {'algorithm_md': 'Sweep 10,20,40', 'formula_md': 'relative difference',
          'parameter_ranges_md': 'k=10..40', 'expected_intermediate_md': 'finite values',
          'test_cases_md': 'known limit=1', 'stop_conditions_md': '1% or grant exhausted'}}
    c._prime_sessions[rid] = await executor.start({})
    decision = _decision([{'op': 'start_trial', 'goal': 'method B', 'success_check': '1% convergence'}], rid=rid)
    decision['research_brief'] = dict(brief)
    if native_root_work_package:
        decision['work_package'] = decision['research_brief'].pop('work_package')
    await brain.results.put({'decision': decision})
    await c._run_one_review_impl(rid, db.query_one('SELECT * FROM review_requests WHERE id=?', (request,)), brain, None)
    assert seen == [('ranking', rid), ('cards', 'COLLAB_CH')]
    packet = brain.calls[0]['research_startup']
    assert packet['strategy_cards'] == cards and packet['public_score_distribution']['best'] == 80
    assert packet['guidance']['level'] == 'concrete_work_package'
    written = config.WORKSPACE_DIR / 'runs' / rid / 'research_brief.md'
    assert all(value in written.read_text() for value in brief['work_package'].values())
    assert all(value in executor.prompts[0][1] for value in brief['work_package'].values())
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='research.brief_written'", (rid,))


async def test_pi_pause_rejected_for_an_untried_authorized_channel_but_manual_pause_works():
    _seed_challenge()
    c, brain, _ = _rig(shadow=False)
    rid = c.create_run('COLLAB_CH', mode='connected')['id']
    c.authorize(rid, 'synthetic', True, 10, 60, 0, '', max_jobs=1)
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    await c._apply_decision(rid, _decision([{'op': 'pause', 'reason': 'one path unavailable'}], rid=rid), {}, brain, None)
    assert c.run_snapshot(rid)['phase'] == 'running'
    event = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='run.pause_advice'", (rid,))
    assert json.loads(event['payload'])['untried_authorized_channels'] == ['bohrium_job']
    c._signals[rid] = asyncio.Queue()
    assert (await c.control(rid, 'pause', None, 'manual-still-works'))['status'] == 'accepted'
    assert c.run_snapshot(rid)['phase'] == 'pausing'


async def test_review_stop_changes_route_instead_of_closing_unused_authorized_channels():
    from test_collaboration import _guidance, _review_result
    _seed_challenge()
    c, _, _ = _rig(shadow=False)
    rid = c.create_run('COLLAB_CH', mode='connected')['id']
    c.authorize(rid, 'synthetic', True, 10, 60, 0, '', max_jobs=1)
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    c._executor_busy[rid] = True
    reqid = c._enqueue_lifecycle(rid, 'fixture')
    db.execute("UPDATE review_requests SET status='running' WHERE id=?", (reqid,))
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (reqid,))
    c._apply_review_result(rid, req, 'requested', {'frame_id': 'fixture'},
        _review_result('fixture', 'intervene', _guidance(kind='stop', intent='reframe')))
    assert c.run_snapshot(rid)['gate'] == 'open'
    guidance = db.query_one('SELECT kind,text_md FROM guidance WHERE run_id=?', (rid,))
    assert guidance['kind'] == 'steer' and 'bohrium_job' in guidance['text_md']


def test_pi_can_pause_after_all_authorized_channels_were_attempted():
    _seed_challenge()
    c = RunController()
    rid = c.create_run('COLLAB_CH', mode='connected')['id']
    c.authorize(rid, 'synthetic', True, 10, 60, 0, '', max_jobs=0)
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    assert planning.untried_channels(rid) == []


def test_remaining_duration_and_shared_cost_cap_do_not_invent_an_authorized_route():
    _seed_challenge()
    c = RunController()
    rid = c.create_run('COLLAB_CH', mode='connected')['id']
    c.authorize(rid, 'synthetic', True, 10, 60, 0, '', max_jobs=1,
                max_compute_cost_cny='1')
    db.execute("UPDATE runs SET phase='running',clock_version=1,active_elapsed_seconds=3580,started_at=? WHERE id=?",
               (db.utcnow(), rid))
    assert planning.untried_channels(rid) == []
    db.execute('UPDATE runs SET active_elapsed_seconds=1 WHERE id=?', (rid,))
    db.execute('INSERT INTO compute_cost_reservations VALUES(?,?,?,?,?,?,?,?)',
               (rid, 'spent-fixture', 'sandbox', '60', 60, '1', 'fixture', db.utcnow()))
    assert planning.untried_channels(rid) == []


def test_real_competition_note_and_verified_slug_import_are_used(monkeypatch):
    _seed_challenge()
    c = RunController()
    rid = c.create_run('COLLAB_CH', mode='connected')['id']
    row = db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (rid,))
    snapshot = json.loads(row['config_snapshot'])
    snapshot['competition'] = {'solver_note': '弱，给写死任务'}
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?', (json.dumps(snapshot), rid))
    db.execute("UPDATE challenges SET origin='verified-slug',platform_snapshot_json=? WHERE id='COLLAB_CH'",
               (json.dumps({'fetched_at': db.utcnow()}),))
    calls = []
    monkeypatch.setattr(planning.platform_scores, 'get', lambda run_id: calls.append(run_id) or {'status': 'observed'})
    assert planning.startup(rid, c._challenge_for_run(c._require_run(rid)))['guidance']['level'] == 'concrete_work_package'
    assert calls == [rid]


def test_solver_note_rejects_known_secret_before_snapshot():
    _seed_challenge()
    config.update_secret('fixture', 'SYNTHETIC_PLANNING_SECRET')
    from cyberscientist.controller import ControllerError
    with pytest.raises(ControllerError, match='密钥'):
        RunController().create_run('COLLAB_CH', model_config={'executor': {
            'runtime': 'codex', 'model_id': 'synthetic', 'reasoning_effort': 'high',
            'note': 'SYNTHETIC_PLANNING_SECRET'}})


def test_pause_checks_frozen_resources_instead_of_a_later_topic_revision():
    _seed_challenge()
    c = RunController()
    rid = c.create_run('COLLAB_CH', mode='connected')['id']
    c.authorize(rid, 'synthetic', True, 10, 60, 0, '', allow_data_download=True)
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    snapshot = json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (rid,))[0])
    snapshot['competition'] = {'challenge_snapshot': {'resources': []}}
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?', (json.dumps(snapshot), rid))
    db.execute("UPDATE challenges SET resources_json='[{\"url\":\"later-revision\"}]' WHERE id='COLLAB_CH'")
    assert planning.untried_channels(rid) == []


def test_smoke_registers_recipe_only_from_owned_successful_untampered_receipt(run, monkeypatch):
    _, rid, _, _, _ = run
    sid = sandboxes.create(rid, 'smoke-box', {'timeout': 600})['sandbox_id']
    monkeypatch.setattr(compute, '_native', lambda *a, **k: {'ok': True, 'exit_code': 0,
        'stdout': json.dumps({'data': {'exit_code': 0, 'stdout': 'numpy 2.1 ready'}}), 'stderr': ''})
    sandboxes.execute(rid, sid, 'python3 smoke.py', 30, 'smoke-receipt')
    result = planning.register_smoke(rid, 'smoke-receipt', 'Install numpy==2.1; python3 smoke.py')
    assert result['status'] == 'smoke_verified' and result['persistent_image_status'] == 'unverified'
    entry = experiences.active_experiences(None)[0]
    assert entry['kind'] == 'environment' and 'numpy==2.1' in entry['body_md']
    assert 'unverified' in entry['body_md'] and 'python3 smoke.py' in entry['body_md']
    assert planning.register_smoke(rid, 'smoke-receipt', 'Install numpy==2.1; python3 smoke.py')['deduplicated']
    assert db.query_one("SELECT COUNT(*) FROM events WHERE run_id=? AND type='environment.smoke_observed'", (rid,))[0] == 1
    from concurrent.futures import ThreadPoolExecutor
    def retry(_):
        return planning.register_smoke(rid, 'smoke-receipt', 'Install numpy==2.1; python3 smoke.py')
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(item['deduplicated'] for item in pool.map(retry, range(2)))
    with pytest.raises(compute.ComputeError, match='不同配方'):
        planning.register_smoke(rid, 'smoke-receipt', 'unrelated changed recipe')
    with pytest.raises(compute.ComputeError):
        planning.register_smoke('another-run', 'smoke-receipt', 'foreign')
    db.execute("UPDATE compute_sandbox_operations SET receipt_json='{}' WHERE operation_id='smoke-receipt'")
    with pytest.raises(compute.ComputeError):
        planning.register_smoke(rid, 'smoke-receipt', 'tampered')
