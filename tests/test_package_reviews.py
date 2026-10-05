import asyncio
import io
import json
import zipfile
import pytest
from cyberscientist import config, db, mailboxes, mcp_bridge, package_reviews
from cyberscientist.brains.base import BrainEvent, SessionRef
from cyberscientist.controller import RunController
from test_mailboxes import _seed_challenge, _make_run, _make_package


def seed():
    _seed_challenge()
    rid = _make_run()
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at) VALUES(?,?,?,'check','reported_complete',?)",
               ('trial_mb1', rid, 'Science evidence', db.utcnow()))
    _make_package(rid)
    return rid


class Reviewer:
    def __init__(self, calls): self.calls = calls
    async def open(self, spec):
        assert not {'mcp_servers', 'resume_thread_id', 'env'} & spec.keys()
        assert 'package_reviews' in spec['working_directory']
        self.calls.append(('open', spec))
        return SessionRef('fixture', f'fresh-{len(self.calls)}')
    async def close(self, session): self.calls.append(('close', session.session_id))
    async def review(self, session, packet):
        assert packet['task'] == 'package_review'
        assert set(packet) == {'protocol', 'task', 'instructions', 'challenge', 'delivery_contract',
                               'sealed_package', 'local_scores', 'local_score_status', 'scorer_source', 'trace_diagnostics', 'admission', 'output_contract'}
        assert packet['local_score_status'] == 'unknown'
        self.calls.append(('packet', packet))
        yield BrainEvent('task_result', {'result': {'verdict': 'issues', 'issues': ['契约路径不符；没有干净环境复跑证据'], 'summary_md': 'PI 决定修复或提交'}})


@pytest.mark.asyncio
async def test_fresh_review_returns_path_issue_pi_can_record_reason_and_submit(monkeypatch):
    rid = seed()
    calls = []
    ctl = RunController()
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: Reviewer(calls))
    result = await package_reviews.review(ctl, rid, 'trial_mb1', 'fresh-review')
    assert result['status'] == 'done' and result['result']['verdict'] == 'issues' and result['advisory_only']
    before = len(calls)
    assert await package_reviews.review(ctl, rid, 'trial_mb1', 'fresh-review') == result
    assert len(calls) == before
    await package_reviews.review(ctl, rid, 'trial_mb1', 'different-review')
    opens = [call for call in calls if call[0] == 'open']
    assert len(opens) == 2
    mailboxes.register_experiment(1)
    db.execute("INSERT INTO guidance(id,run_id,source,target_trial_id,kind,intent,text_md,status,created_at,updated_at) VALUES(?,?,'requested',?,'submit','continue',?,'sent',?,?)",
               ('review-guidance', rid, 'trial_mb1', '路径问题可接受，记录缺证后按原授权照常提交', db.utcnow(), db.utcnow()))
    await ctl._execute_submit(rid, 'review-guidance', 'trial_mb1')
    assert db.query_one('SELECT status FROM submissions WHERE run_id=?', (rid,))['status'] == 'submitted'
    event = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='package.review_pi_decision'", (rid,))
    decision = json.loads(event['payload'])
    assert decision['result']['verdict'] == 'issues'
    assert '照常提交' in decision['pi_reason'] and decision['source_matches_review']


@pytest.mark.asyncio
async def test_changed_bundle_and_foreign_trial_do_not_reuse_review(monkeypatch):
    rid = seed()
    ctl = RunController()
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: Reviewer([]))
    await package_reviews.review(ctl, rid, 'trial_mb1', 'bound-review')
    _make_package(rid, content='{"changed": true}')
    with pytest.raises(ValueError, match='冲突'):
        await package_reviews.review(ctl, rid, 'trial_mb1', 'bound-review')
    with pytest.raises(ValueError, match='不属于'):
        await package_reviews.review(ctl, rid, 'foreign-trial', 'foreign-review')


@pytest.mark.asyncio
async def test_interrupted_review_unknown_never_replays_and_provider_failure_advisory(monkeypatch):
    rid = seed()
    ctl = RunController()
    calls = []
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: Reviewer(calls))
    await package_reviews.review(ctl, rid, 'trial_mb1', 'old-review')
    db.execute("UPDATE package_reviews SET status='running',result_json=NULL WHERE operation_id='old-review'")
    package_reviews.reconcile_interrupted()
    before = len(calls)
    result = await package_reviews.review(ctl, rid, 'trial_mb1', 'old-review')
    assert result['status'] == 'unknown' and len(calls) == before
    class Broken(Reviewer):
        async def review(self, session, packet):
            yield BrainEvent('error', {'message': 'HTTP 429 Too Many Requests Retry-After: 60'})
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: Broken(calls))
    failed = await package_reviews.review(ctl, rid, 'trial_mb1', 'limited-review')
    assert failed['status'] == 'failed' and failed['advisory_only']
    assert db.query_one('SELECT provider FROM model_provider_backoff')['provider'] == 'codex'


def test_compressed_key_not_exported_and_migrations_idempotent(monkeypatch):
    secret = 'fixture-compressed-provider-key-812837'
    monkeypatch.setattr(config, 'deepseek_key', lambda: secret)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('science.txt', secret)
    assert secret.encode() not in buf.getvalue()
    assert package_reviews._contains_secret(buf.getvalue())
    db.init_db(); db.init_db()
    assert db.query_one("SELECT name FROM sqlite_master WHERE name='package_reviews'")


def test_mcp_review_only_pi_no_transport_replay(monkeypatch):
    monkeypatch.setenv('CS_TOOL_ROLE', 'brain')
    offered = mcp_bridge._handle({'id': 1, 'method': 'tools/list'})['result']['tools']
    assert 'research_review_package' in {tool['name'] for tool in offered}
    calls = []
    monkeypatch.setattr(mcp_bridge, '_post', lambda path, payload, **kwargs: calls.append((path, kwargs)) or {'status': 'unknown'})
    mcp_bridge._handle({'id': 2, 'method': 'tools/call', 'params': {'name': 'research_review_package', 'arguments': {'trial_id': 't', 'operation_id': 'op'}}})
    assert calls == [('/api/v1/tools/package_review', {'timeout': 960, 'retry_transient': False})]
    monkeypatch.setenv('CS_TOOL_ROLE', 'executor')
    result = mcp_bridge._handle({'id': 3, 'method': 'tools/call', 'params': {'name': 'research_review_package'}})
    assert result['result']['isError'] and len(calls) == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_has_one_turn_and_immutable_snapshot(monkeypatch):
    rid = seed()
    calls = []
    ctl = RunController()
    class Slow(Reviewer):
        async def review(self, session, packet):
            await asyncio.sleep(.02)
            async for event in super().review(session, packet): yield event
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: Slow(calls))
    results = await asyncio.gather(*(package_reviews.review(ctl, rid, 'trial_mb1', 'concurrent-review') for _ in range(2)))
    assert all(result['status'] in ('done', 'running') for result in results)
    assert len([call for call in calls if call[0] == 'open']) == 1
    assert package_reviews.get('concurrent-review', rid)['status'] == 'done'


@pytest.mark.asyncio
async def test_default_package_symlink_cannot_export_foreign_file(monkeypatch, tmp_path):
    rid = seed()
    source = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / 'trial_mb1' / 'result_package.json'
    source.unlink()
    foreign = tmp_path / 'foreign.json'
    foreign.write_text('{"private": "fixture"}')
    source.symlink_to(foreign)
    ctl = RunController()
    monkeypatch.setattr(ctl, '_make_brain', lambda _: pytest.fail('不应启动审查'))
    with pytest.raises(ValueError, match='本 Trial'):
        await package_reviews.review(ctl, rid, 'trial_mb1', 'symlink-review')
    assert not db.query('SELECT * FROM package_reviews')


@pytest.mark.asyncio
async def test_reimport_keeps_frozen_topic_contract_and_actual_submission_hash(monkeypatch):
    rid = seed()
    state = json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (rid,))[0])
    state['competition'] = {'challenge_snapshot': {'title': 'Frozen', 'content': 'Output `frozen.txt`', 'resources': [], 'platform': {}}}
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?', (json.dumps(state), rid))
    db.execute("UPDATE challenges SET content='Output `changed.json`' WHERE id='MB_CH'")
    calls = []
    ctl = RunController()
    monkeypatch.setattr(ctl, '_make_brain', lambda _: Reviewer(calls))
    await package_reviews.review(ctl, rid, 'trial_mb1', 'frozen-topic-review')
    packet = next(call[1] for call in calls if call[0] == 'packet')
    assert packet['challenge'] == 'Output `frozen.txt`'
    assert packet['delivery_contract']['task_paths'] == ['frozen.txt']
    mailboxes.register_experiment(1)
    db.execute("INSERT INTO guidance(id,run_id,source,target_trial_id,kind,intent,text_md,status,created_at,updated_at) VALUES(?,?,'requested',?,'submit','continue',?,'sent',?,?)",
               ('changed-guidance', rid, 'trial_mb1', '修正后仍按授权提交；旧审查仅参考', db.utcnow(), db.utcnow()))
    real_submit = mailboxes.submit_experiment
    def edit_then_submit(*args, **kwargs):
        _make_package(rid, content='{"new_bytes": true}')
        return real_submit(*args, **kwargs)
    monkeypatch.setattr(mailboxes, 'submit_experiment', edit_then_submit)
    await ctl._execute_submit(rid, 'changed-guidance', 'trial_mb1')
    payload = json.loads(db.query_one("SELECT payload FROM events WHERE type='package.review_pi_decision'")[0])
    assert payload['source_matches_review'] is False
    assert db.query_one('SELECT status FROM submissions')['status'] == 'submitted'
