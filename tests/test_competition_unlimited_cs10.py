"""Before/after admission with synthetic native protocols; no paid work."""
import json
import pytest
from cyberscientist import compute, config, db, competition, maintenance, sandboxes, collab, observation
from cyberscientist.controller import RunController
from cyberscientist.brains.base import BrainEvent, SessionRef
from test_compute_gateway import run, spec, receipt
from test_collaboration import _decision, FakeExecutor


def grant(rid):
    db.execute('UPDATE authorizations SET unlimited_resources=1,max_compute_cost_cny=NULL WHERE run_id=?', (rid,))


def test_c8_m32_and_arbitrary_disk_no_longer_hit_old_resource_cap(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('JobId: 123'))
    request = dict(spec(), machine_type='c8_m32_cpu', disk_size=1000)
    with pytest.raises(compute.ComputeError) as err: compute.submit(rid, 'wide-machine', request, str(source))
    assert err.value.code == 'RESOURCE_LIMIT' and not compute.list_jobs(rid)['items']
    grant(rid)
    assert compute.submit(rid, 'wide-machine', request, str(source))['status'] == 'accepted'
    facts = observation.authority_facts(rid)
    assert facts['authorization']['job_limits']['max_memory_gb'] is None
    assert facts['operating_facts']['effective_job_limits']['max_disk_gb'] is None


def test_third_and_fourth_jobs_bypass_run_count_concurrency_and_global_cap(run, monkeypatch):
    rid, source = run
    calls = []
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt(f'JobId: {123+len(calls)}'))
    for op in ('first', 'second'): compute.submit(rid, op, spec(), str(source))
    with pytest.raises(compute.ComputeError) as err: compute.submit(rid, 'third', spec(), str(source))
    assert err.value.code == 'CONCURRENCY_LIMIT'
    settings = config.load_settings(); settings['resources']['max_concurrent_jobs'] = 1; config.save_settings(settings)
    grant(rid)
    for op in ('third', 'fourth'): assert compute.submit(rid, op, spec(), str(source))['status'] == 'accepted'
    assert len(calls) == 4 and compute.list_jobs(rid)['reserved_jobs'] == 4
    budget = RunController().run_snapshot(rid)['budget']
    assert budget['max_jobs'] is None and budget['max_submissions'] == 0


def test_unknown_unit_price_does_not_block_explicit_unlimited_grant(run, monkeypatch):
    rid, source = run
    db.execute("UPDATE authorizations SET max_compute_cost_cny='1' WHERE run_id=?", (rid,))
    calls = []
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt('{}'))
    with pytest.raises(compute.ComputeError) as err: compute.submit(rid, 'unpriced', spec(), str(source))
    assert err.value.code == 'COMPUTE_PRICE_UNKNOWN'
    grant(rid); calls.clear()
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt('JobId: 123'))
    assert compute.submit(rid, 'unpriced', spec(), str(source))['status'] == 'accepted'
    assert len(calls) == 1


def test_third_maintenance_call_is_allowed_but_same_identity_never_replayed(run):
    rid, _ = run
    for op in ('m1', 'm2'): maintenance.claim_call(rid, op, 'postreview')
    with pytest.raises(ValueError, match='额度已用尽'): maintenance.claim_call(rid, 'm3', 'postreview')
    grant(rid); maintenance.claim_call(rid, 'm3', 'postreview')
    assert len(db.query('SELECT * FROM maintenance_calls WHERE run_id=?', (rid,))) == 3
    with pytest.raises(ValueError, match='已开始过'): maintenance.claim_call(rid, 'm3', 'postreview')
    payload = json.loads(db.query_one("SELECT payload FROM events WHERE type='maintenance.call_started' ORDER BY seq DESC")['payload'])
    assert payload['limit'] is None and payload['used'] == 3


@pytest.mark.asyncio
async def test_twenty_first_pi_review_is_answered_and_usage_preserved(run):
    rid, _ = run
    db.execute('UPDATE runs SET brain_reviews_used=20 WHERE id=?', (rid,))
    db.execute('INSERT INTO supervision(run_id,enabled,updated_at) VALUES(?,0,?)', (rid, db.utcnow()))
    controller = RunController(); calls = []
    class Brain:
        async def review(self, session, packet):
            calls.append(packet)
            yield BrainEvent('question_answer', {'answer_md': 'Synthetic evidence only', 'evidence_refs': []})
    def request():
        with db.transaction() as conn:
            req = collab._enqueue_request_tx(conn, rid, source='executor', blocking=False, trigger='executor_question')
            conn.execute('UPDATE review_requests SET frame_json=? WHERE id=?', (json.dumps({'question': {'message': 'Explain synthetic facts'}}), req))
        return db.query_one('SELECT * FROM review_requests WHERE id=?', (req,))
    original = request()
    await controller._run_question_review(rid, original, Brain(), SessionRef('fake', 'same-session'))
    assert not calls and db.query_one('SELECT status FROM review_requests WHERE id=?', (original['id'],))['status'] == 'error'
    grant(rid)
    await controller._run_question_review(rid, request(), Brain(), SessionRef('fake', 'same-session'))
    assert len(calls) == 1 and calls[0]['budget_remaining']['brain_reviews'] is None
    assert db.query_one('SELECT brain_reviews_used FROM runs WHERE id=?', (rid,))[0] == 21
    assert db.query_one("SELECT 1 FROM events WHERE type='brain.question_answered'")


@pytest.mark.asyncio
async def test_fourth_trial_is_delivered_instead_of_budget_gate(run):
    rid, _ = run
    for tid in ('trial_fixture', 'trial_second', 'trial_third'):
        db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at) VALUES(?,?,'synthetic','fixture','done',?)", (tid, rid, db.utcnow()))
    controller = RunController(); executor = FakeExecutor()
    controller._prime_instances[rid] = executor
    controller._prime_sessions[rid] = 'fixture'
    action = {'op': 'start_trial', 'goal': 'fourth synthetic trial', 'success_check': 'fixture evidence'}
    await controller._apply_decision(rid, _decision([action], rid=rid), {}, None, None)
    assert db.query_one('SELECT gate FROM runs WHERE id=?', (rid,))[0] == 'awaiting_budget'
    assert not executor.prompts
    grant(rid)
    db.execute("UPDATE runs SET gate='open',pending_action_json=NULL WHERE id=?", (rid,))
    await controller._apply_decision(rid, _decision([action], rid=rid), {}, None, None)
    assert len(db.query('SELECT * FROM trials WHERE run_id=?', (rid,))) == 4
    assert len(executor.prompts) == 1 and 'fourth synthetic trial' in executor.prompts[0][1]


def test_sandbox_cpu_concurrency_and_cumulative_minutes_are_unlimited(run, monkeypatch):
    rid, _ = run
    db.execute('UPDATE authorizations SET max_sandboxes=1,max_sandbox_minutes=1 WHERE run_id=?', (rid,))
    request = {'cpu': '32c128g', 'timeout': 600}
    with pytest.raises(compute.ComputeError): sandboxes.create(rid, 'sb1', request)
    grant(rid); calls = []
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt(json.dumps({'ok': True, 'data': {'sandboxID': f'sb-unlimited-{len(calls)}'}})))
    for op in ('sb1', 'sb2', 'sb3'): assert sandboxes.create(rid, op, request)['status'] == 'active'
    assert len(calls) == 3 and sandboxes.bounded_lifetime(rid, 600) == 600


def test_new_round_confirmation_flags_unlimited_and_old_frozen_template_stays_bounded():
    from test_competition import challenges, template
    challenges(1)
    round = competition.import_round(['c0'], mode='demo')
    confirmed = competition.confirm(round['id'], template())
    assert confirmed['items'][0]['template']['authorization']['unlimited_resources'] is True
    frozen_old = competition._template(template(), 'demo', frozen=True)
    assert frozen_old['authorization']['unlimited_resources'] is False
    db.init_db(); db.init_db()


def test_unlimited_remaining_and_channels_preserve_explicit_gpu_denial(run):
    from cyberscientist import runtime_facts, planning
    rid, _ = run
    db.execute('UPDATE authorizations SET max_jobs=0,max_sandboxes=0,max_sandbox_minutes=0 WHERE run_id=?', (rid,))
    before = runtime_facts.facts(rid)
    assert before['remaining']['jobs'] == 0
    assert planning.untried_channels(rid) == []
    grant(rid)
    after = runtime_facts.facts(rid)
    assert all(after['remaining'][key] is None for key in ('jobs', 'sandbox_minutes', 'sandbox_concurrent_slots'))
    assert after['remaining']['run_seconds'] > 0
    assert after['effective_job_limits']['allow_gpu'] is False
    assert observation.authority_facts(rid)['authorization']['job_limits']['allow_gpu'] is False
    assert planning.untried_channels(rid) == ['bohrium_job', 'bohrium_sandbox']
