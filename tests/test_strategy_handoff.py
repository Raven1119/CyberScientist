"""Two ordinary native-protocol fake Runs share current strategy revisions."""
import json

from httpx import ASGITransport, AsyncClient

from cyberscientist import api, collab, config, db, experiences, planning, strategies, local_scoring
from cyberscientist.brains.base import BrainEvent
from cyberscientist.controller import RunController
from test_collaboration import FakeExecutor, ScriptableBrain, _decision, _seed_challenge, _review_result


class RouteChoosingBrain(ScriptableBrain):
    async def review(self, session, packet):
        self.calls.append(packet)
        cards = packet['research_startup']['strategy_cards']
        route = 'B: exact method' if any('A: approximation' in c['body_md'] for c in cards) else 'A: approximation'
        decision = _decision([{'op': 'start_trial', 'goal': route, 'success_check': 'formal scorer'}],
                             rid=packet['run_id'], sv=packet['state_version'])
        decision['research_brief'] = {'environment_choice': {'mode': 'from_zero', 'reason_md': 'Synthetic empty environment'}, 'route_md': route,
            'ranked_methods': [{'name': route, 'reason_md': 'Compare prior method and test an alternative'}],
            'difference_md': 'Uses exact arithmetic instead of A' if cards else 'First recorded route',
            'advice_md': 'Verify units, then compute in authorized Bohrium'}
        yield BrainEvent('decision', {'decision': decision})


async def launch(c, brain, executor):
    rid = c.create_run('COLLAB_CH', mode='connected')['id']
    c.authorize(rid, 'fixture', True, 10, 60, 0, '')
    db.execute("UPDATE runs SET phase='running',started_at=? WHERE id=?", (db.utcnow(), rid))
    c._prime_sessions[rid] = await executor.start({})
    c._make_prime = lambda settings: executor
    reqid = c._enqueue_lifecycle(rid, 'run_start')
    await c._run_one_review_impl(rid, db.query_one('SELECT * FROM review_requests WHERE id=?', (reqid,)), brain, None)
    return rid


async def test_second_run_reads_all_same_topic_cards_chooses_other_route_and_reads_live_milestone():
    _seed_challenge()
    c1, c2 = RunController(), RunController()
    b1, b2 = RouteChoosingBrain(), RouteChoosingBrain()
    r1 = await launch(c1, b1, FakeExecutor())
    r2 = await launch(c2, b2, FakeExecutor())
    assert db.query_one('SELECT challenge_id FROM runs WHERE id=?', (r1,))[0] == db.query_one(
        'SELECT challenge_id FROM runs WHERE id=?', (r2,))[0]
    first = experiences.get_experience(strategies.card_id(r1))
    second = experiences.get_experience(strategies.card_id(r2))
    assert 'A: approximation' in first['body_md'] and 'B: exact method' in second['body_md']
    assert b2.calls[0]['research_startup']['strategy_cards'][0]['revision_id'] == first['revision_id']
    context_id = b2.calls[0]['research_startup']['strategy_context_id']
    delivered = json.loads(db.query_one('SELECT content_json FROM experience_contexts WHERE id=?', (context_id,))[0])
    assert delivered['items'][0]['body_md'] == first['body_md']
    token = None
    with db.transaction() as conn:
        token = collab.issue_token(conn, r2, 'brain', 'fixture-brain', 1)
    reqid = c1._enqueue_lifecycle(r1, 'fixture-milestone')
    db.execute("UPDATE review_requests SET status='running' WHERE id=?", (reqid,))
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (reqid,))
    result = _review_result('milestone')
    result['research_brief'] = {'route_md': 'A: approximation', 'advice_md': 'Avoid large k; use exact arithmetic'}
    c1._apply_review_result(r1, req, 'requested', {'frame_id': 'milestone'}, result)
    latest = experiences.get_experience(first['id'])
    assert latest['revision_id'] != first['revision_id']
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        response = await client.post('/api/v1/tools/experience', headers={'Authorization': 'Bearer ' + token},
                                     json={'action': 'read', 'experience_id': first['id']})
    assert response.status_code == 200
    assert response.json()['revision_id'] == latest['revision_id']
    assert 'Avoid large k' in response.json()['entry']['body_md']
    assert experiences.get_experience(first['id'])['frontmatter']['kind'] == 'strategy'
    assert len(planning.strategy_cards('COLLAB_CH')) == 2


async def test_verified_score_registration_immediately_updates_card_without_checkpoint():
    _seed_challenge()
    c = RunController()
    rid = await launch(c, RouteChoosingBrain(), FakeExecutor())
    tid = db.query_one('SELECT current_trial_id FROM runs WHERE id=?', (rid,))[0]
    from test_trace_narrative import _zip
    package = _zip({'arm_manifest.json': json.dumps({'trace': 'traces/trace.jsonl'}).encode(),
                    'traces/trace.jsonl': (json.dumps({'step_type': 'decision', 'body': 'synthetic trace',
                                               'timestamp': db.utcnow()}) + '\n').encode(),
                    'outputs/result.json': b'{"synthetic":true}'})
    scored = local_scoring._record_score('COLLAB_CH', rid, tid, 'fixture-score', package,
        {'scorer_version': 'synthetic', 'file_hashes': {'score.py': 'a'*64}},
        {'score': 73, 'components': {}, 'confidence': 'high', 'notes': 'fixture', 'scorer_version': 'synthetic'})
    assert str(scored['science_score']) in experiences.get_experience(strategies.card_id(rid))['body_md']
    next_id = RunController().create_run('COLLAB_CH', mode='connected')['id']
    context = planning.startup(next_id, c._challenge_for_run(c._require_run(next_id)))
    assert scored['id'] in context['strategy_cards'][0]['body_md']


async def test_foreign_strategy_proposal_cannot_replace_card_and_bad_card_does_not_block_trial():
    _seed_challenge()
    c = RunController()
    r1 = await launch(c, RouteChoosingBrain(), FakeExecutor())
    original = experiences.get_experience(strategies.card_id(r1))
    r2 = c.create_run('COLLAB_CH')['id']
    c._apply_experience_proposal(r2, 'foreign', {'scope': 'challenge', 'title': 'replace',
        'body_md': 'Unverified score=100', 'kind': 'heuristic', 'applicability': 'same topic',
        'target_id': original['id']})
    assert experiences.get_experience(original['id'])['revision_id'] == original['revision_id']
    fm = dict(original['frontmatter'], plan=None)
    experiences.save_experience(original['id'], fm, original['body_md'], 'user', 'invalid plan fixture', original['current_hash'])
    c.notify_run_change(r1)
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='strategy.update_unknown'", (r1,))
    assert c.run_snapshot(r1)['phase'] == 'running'


async def test_milestone_brief_is_redacted_before_review_record_and_experience_writes():
    _seed_challenge()
    c = RunController()
    rid = await launch(c, RouteChoosingBrain(), FakeExecutor())
    config.update_secret('synthetic', 'SYNTHETIC_STRATEGY_SECRET')
    reqid = c._enqueue_lifecycle(rid, 'milestone')
    db.execute("UPDATE review_requests SET status='running' WHERE id=?", (reqid,))
    req = db.query_one('SELECT * FROM review_requests WHERE id=?', (reqid,))
    result = _review_result('milestone')
    result['research_brief'] = {'advice_md': 'SYNTHETIC_STRATEGY_SECRET',
                                'ranked_methods': [{'name': 'A', 'reason_md': 'SYNTHETIC_STRATEGY_SECRET'}]}
    c._apply_review_result(rid, req, 'requested', {'frame_id': 'milestone'}, result)
    stored = db.query_one('SELECT result_json FROM review_requests WHERE id=?', (reqid,))[0]
    assert 'SYNTHETIC_STRATEGY_SECRET' not in stored
    assert 'SYNTHETIC_STRATEGY_SECRET' not in experiences.get_experience(strategies.card_id(rid))['body_md']


async def test_interrupted_startup_uses_exact_frozen_cards():
    _seed_challenge()
    c = RunController()
    first = await launch(c, RouteChoosingBrain(), FakeExecutor())
    rid = c.create_run('COLLAB_CH', mode='connected')['id']
    from cyberscientist import experience_context
    frozen = experience_context.freeze(rid, None, 'startup:strategies', items=planning.strategy_cards('COLLAB_CH'), role='brain')
    planning.record_brief(first, {'advice_md': 'A later update'}, 'later')
    context = planning.startup(rid, c._challenge_for_run(c._require_run(rid)))
    assert context['strategy_cards'] == frozen['items']
    assert context['strategy_context_id'] == frozen['id']


def test_strategy_cannot_be_a_global_experience_and_cannot_claim_an_unregistered_score():
    import pytest
    with pytest.raises(experiences.ExperienceError, match='策略卡'):
        experiences.save_experience('wrong', {'title': 'wrong', 'scope': 'global', 'status': 'candidate',
            'kind': 'strategy', 'evidence_status': 'hypothesis'}, 'wrong', 'fixture', '', None)
    _seed_challenge()
    rid = RunController().create_run('COLLAB_CH')['id']
    strategies.update(rid, brief={'route_md': 'A: approximation', 'advice_md': 'Claimed score=100 is a hypothesis'})
    card = experiences.get_experience(strategies.card_id(rid))
    assert 'unknown；尚无正式本地评分' in card['body_md']
    assert card['frontmatter']['evidence_status'] == 'hypothesis'
