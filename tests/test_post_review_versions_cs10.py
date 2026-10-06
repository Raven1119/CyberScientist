import asyncio
import hashlib
import json
import pytest
from cyberscientist import config, curation, db, maintenance, resource_coordinator
from cyberscientist.brains.base import BrainEvent, SessionRef
from test_collaboration import _rig, _seed_challenge, _proposal


def terminal_run():
    _seed_challenge(); ctl, _, _ = _rig(shadow=False)
    rid = ctl.create_run('COLLAB_CH')['id']
    db.execute("UPDATE runs SET phase='finished',ended_at=? WHERE id=?", (db.utcnow(), rid))
    return ctl, rid


def fake_brain(result, calls):
    class Brain:
        async def open(self, spec): return SessionRef('fixture', 'fresh')
        async def close(self, session): pass
        async def review(self, session, packet):
            calls.append(packet)
            assert packet['full_public_trace_jsonl'] == open(packet['public_trace']['path']).read()
            yield BrainEvent('task_result', {'result': result})
    return Brain()


async def test_visible_hash_reference_previously_outside_snapshot_is_accepted_as_candidate(monkeypatch):
    ctl, rid = terminal_run(); digest = hashlib.sha256(b'old artifact').hexdigest()
    event = db.append_event(rid, 'prime', 'prime.execution.progress', {'sha256': digest, 'exit_code': 0})
    packet = maintenance.snapshot(ctl, rid)
    assert 'sha256:' + digest in packet['full_evidence_refs']
    assert packet['hash_reference_sources']['sha256:' + digest] == [f"event:{rid}:{event['seq']}"]
    proposal = _proposal('challenge', 'Hash backed lesson'); proposal['evidence_refs'] = ['sha256:' + digest]
    from test_review_defects_cs12 import reviewed
    proposal = reviewed(proposal)
    calls = []; monkeypatch.setattr(ctl, '_make_brain', lambda settings: fake_brain({'system_defects_md': 'ok', 'strategy_lessons': [proposal], 'environment_notes_md': 'unknown'}, calls))
    maintenance.grant_post_review(ctl, rid, 'repeat-one', allow_model_calls=True, reason='Explicit single-call review')
    await maintenance.run_post_review(ctl, rid, review_id='repeat-one')
    row = db.query_one('SELECT * FROM run_post_review_versions WHERE id=?', ('repeat-one',))
    assert row['status'] == 'done' and row['calls_used'] == 1 and len(calls) == 1
    assert not db.query('SELECT * FROM maintenance_calls')
    revision = db.query_one('SELECT frontmatter FROM experience_revisions WHERE experience_id=?', (json.loads(row['result_json'])['experience_ids'][0],))
    assert json.loads(revision['frontmatter'])['evidence_status'] == 'hypothesis'


async def test_new_grant_preserves_legacy_review_authorization_and_deduplicates(monkeypatch):
    ctl, rid = terminal_run(); now = db.utcnow()
    db.execute("INSERT INTO run_post_reviews(run_id,status,reason,error,created_at,updated_at) VALUES(?,'failed','old','out-of-snapshot',?,?)", (rid, now, now))
    for n in range(2): maintenance.claim_call(rid, 'old-' + str(n), 'postreview'); maintenance.complete_call('old-' + str(n), 'failed')
    old_review = dict(db.query_one('SELECT * FROM run_post_reviews WHERE run_id=?', (rid,)))
    old_calls = [dict(r) for r in db.query('SELECT * FROM maintenance_calls')]
    old_run = dict(ctl._require_run(rid))
    calls = []; monkeypatch.setattr(ctl, '_make_brain', lambda settings: fake_brain({'system_defects_md': 'ok', 'strategy_lessons': [], 'environment_notes_md': 'unknown'}, calls))
    first = maintenance.grant_post_review(ctl, rid, 'explicit-new', allow_model_calls=True, reason='new grant')
    assert maintenance.grant_post_review(ctl, rid, 'explicit-new', allow_model_calls=True, reason='new grant')['id'] == first['id']
    await maintenance.run_post_review(ctl, rid, review_id='explicit-new')
    await maintenance.run_post_review(ctl, rid, review_id='explicit-new')
    assert len(calls) == 1 and dict(ctl._require_run(rid)) == old_run
    assert dict(db.query_one('SELECT * FROM run_post_reviews WHERE run_id=?', (rid,))) == old_review
    assert [dict(r) for r in db.query('SELECT * FROM maintenance_calls')] == old_calls
    assert db.query_one('SELECT version FROM run_post_review_versions')[0] == 1
    db.init_db(); db.init_db()
    assert db.query_one('SELECT status FROM run_post_review_versions')[0] == 'done'


@pytest.mark.parametrize('phase', ['created', 'running', 'pausing', 'paused', 'waiting_score', 'recovering'])
def test_nonterminal_state_never_queues_or_grants_post_review(phase):
    ctl, rid = terminal_run(); db.execute('UPDATE runs SET phase=? WHERE id=?', (phase, rid))
    maintenance.queue_end(ctl, rid, 'pause')
    with db.transaction() as conn: maintenance.persist_end_tx(conn, rid, 'pause')
    assert not db.query('SELECT * FROM run_post_reviews')
    with pytest.raises(ValueError, match='真正结束'): maintenance.grant_post_review(ctl, rid, 'repeat', allow_model_calls=True, reason='new')


def test_full_snapshot_is_immutable_cutoff_bounded_and_scrubbed(monkeypatch):
    ctl, rid = terminal_run(); config.save_secrets({'key': 'fixture-secret-full-trace'})
    first = db.append_event(rid, 'prime', 'prime.execution.progress', {'output': 'fixture-secret-full-trace'})
    packet = maintenance.snapshot(ctl, rid)
    assert 'fixture-secret-full-trace' not in json.dumps(packet)
    assert packet['public_trace']['through_seq'] == first['seq']
    db.append_event(rid, 'controller', 'job.unknown', {'late': True})
    assert curation.run_evidence(rid, through_seq=first['seq'])['through_seq'] == first['seq']
    new = maintenance.snapshot(ctl, rid)
    assert new['public_trace']['path'] != packet['public_trace']['path']
    assert open(packet['public_trace']['path']).read() == packet['full_public_trace_jsonl']


def test_interrupted_single_call_grant_is_unknown_and_never_replayed():
    ctl, rid = terminal_run(); maintenance.grant_post_review(ctl, rid, 'unknown', allow_model_calls=True, reason='new')
    db.execute("UPDATE run_post_review_versions SET status='running',calls_used=1")
    maintenance.reconcile_interrupted()
    row = db.query_one('SELECT * FROM run_post_review_versions')
    assert row['status'] == 'unknown' and row['calls_used'] == 1


async def test_duplicate_inflight_review_cannot_release_first_session_lease(monkeypatch):
    ctl, rid = terminal_run(); entered = asyncio.Event(); release = asyncio.Event()
    db.execute("UPDATE runs SET mode='connected' WHERE id=?", (rid,))
    class Brain:
        async def open(self, spec): return SessionRef('fixture', 'fresh')
        async def close(self, session): pass
        async def review(self, session, packet):
            entered.set(); await release.wait()
            yield BrainEvent('task_result', {'result': {'system_defects_md': 'ok', 'strategy_lessons': [], 'environment_notes_md': 'unknown'}})
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: Brain())
    maintenance.grant_post_review(ctl, rid, 'inflight', allow_model_calls=True, reason='new')
    task = asyncio.create_task(maintenance.run_post_review(ctl, rid, review_id='inflight')); await entered.wait()
    await maintenance.run_post_review(ctl, rid, review_id='inflight')
    assert db.query('SELECT * FROM model_session_leases WHERE owner=?', ('repeat-postreview-inflight',))
    release.set(); await task


def test_hex_secret_cannot_reenter_snapshot_through_hash_alias():
    ctl, rid = terminal_run(); key = 'a' * 64
    config.save_secrets({'fixture': key})
    db.append_event(rid, 'prime', 'prime.execution.progress', {'sha256': key, 'output': key})
    packet = maintenance.snapshot(ctl, rid)
    assert key not in json.dumps(packet)
    assert 'sha256:' + key not in packet['full_evidence_refs']
    row = maintenance.grant_post_review(ctl, rid, 'secret-safe', allow_model_calls=True, reason='new')
    assert key not in row['packet_json']


async def test_operation_id_cannot_overwrite_legacy_report_or_release_other_owner(monkeypatch):
    ctl, rid = terminal_run()
    report = config.WORKSPACE_DIR / 'reviews' / (rid + '.md'); report.parent.mkdir(exist_ok=True); report.write_text('old immutable report')
    with db.transaction() as conn:
        conn.execute('INSERT INTO model_session_leases(owner,role,provider,created_at) VALUES(?,?,?,?)', (rid, 'brain', 'codex', db.utcnow()))
    calls = []; monkeypatch.setattr(ctl, '_make_brain', lambda settings: fake_brain({'system_defects_md': 'ok', 'strategy_lessons': [], 'environment_notes_md': 'unknown'}, calls))
    maintenance.grant_post_review(ctl, rid, rid, allow_model_calls=True, reason='new')
    await maintenance.run_post_review(ctl, rid, review_id=rid)
    assert report.read_text() == 'old immutable report'
    assert db.query_one('SELECT 1 FROM model_session_leases WHERE owner=?', (rid,))
    assert db.query_one('SELECT report_path FROM run_post_review_versions')['report_path'] != str(report.relative_to(config.WORKSPACE_DIR))


async def test_result_and_legacy_call_terminal_status_commit_atomically(monkeypatch):
    ctl, rid = terminal_run(); now = db.utcnow()
    db.execute("INSERT INTO run_post_reviews(run_id,status,reason,created_at,updated_at) VALUES(?,'running','old',?,?)", (rid, now, now))
    calls = []; monkeypatch.setattr(ctl, '_make_brain', lambda settings: fake_brain({'system_defects_md': 'ok', 'strategy_lessons': [], 'environment_notes_md': 'unknown'}, calls))
    original = maintenance._update_review
    def fail_result(*args, **kwargs):
        if 'result_json' in kwargs: raise RuntimeError('simulated crash before result update')
        return original(*args, **kwargs)
    monkeypatch.setattr(maintenance, '_update_review', fail_result)
    with pytest.raises(RuntimeError, match='simulated crash'): await maintenance.run_post_review(ctl, rid)
    assert db.query_one('SELECT status FROM maintenance_calls')[0] == 'running'
    maintenance.reconcile_interrupted()
    assert db.query_one('SELECT status FROM maintenance_calls')[0] == 'unknown'
    assert db.query_one('SELECT status FROM run_post_reviews')[0] == 'unknown'


def test_late_event_and_checkpoint_writer_cannot_enter_pinned_snapshot(monkeypatch):
    import threading
    ctl, rid = terminal_run(); first = db.append_event(rid, 'prime', 'prime.execution.progress', {'output': 'before'})
    started = threading.Event(); threads = []
    original = curation.run_evidence
    def late_writer():
        started.set()
        db.append_event(rid, 'controller', 'environment.smoke_observed', {'late': True})
        db.execute('INSERT INTO checkpoints(id,run_id,report,evidence_refs,created_at) VALUES(?,?,?,?,?)', ('late-cp', rid, 'late', '[]', db.utcnow()))
        db.execute('INSERT INTO local_scores(id,challenge_id,run_id,trial_id,package_sha256,science_artifact_hashes_json,manifest_science_sha256,trace_prediction_json,scorer_version,scorer_file_hashes_json,feature_version,model_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('late-score', 'COLLAB_CH', rid, 'late-trial', 'late-package', '{}', 'late-manifest', '{}', 'fixture', '{}', 'fixture', 'fixture', db.utcnow()))
    def during_snapshot(*args, **kwargs):
        thread = threading.Thread(target=late_writer); threads.append(thread); thread.start(); assert started.wait(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(curation, 'run_evidence', during_snapshot)
    packet = maintenance.snapshot(ctl, rid)
    threads[0].join(5); assert not threads[0].is_alive()
    assert packet['public_trace']['through_seq'] == first['seq']
    assert 'checkpoint:late-cp' not in packet['full_evidence_refs']
    assert 'local_score:late-score' not in packet['full_evidence_refs']
    assert not packet['environment_receipts'] and 'late' not in packet['full_public_trace_jsonl']


def test_native_character_limit_uses_complete_verified_chunks_not_truncation():
    from cyberscientist.role_tasks import prompt
    ctl, rid = terminal_run()
    db.append_event(rid, 'prime', 'prime.execution.progress', {'output': 'public data ' * 100_000})
    packet = maintenance.snapshot(ctl, rid)
    assert len(prompt(packet)) > 1_048_576  # Real native RPC rejects this before model dispatch.
    native, chunks = maintenance.native_materials(packet)
    assert len(prompt(native)) < 900_000 and 'full_public_trace_jsonl' not in native
    assert ''.join(chunks.values()) == packet['full_public_trace_jsonl']
    assert hashlib.sha256(''.join(chunks.values()).encode()).hexdigest() == packet['public_trace']['sha256']
    path, content = next(iter(chunks.items()))
    payload = {'command': 'cat ' + path, 'status': 'completed', 'exit_code': 0, 'output': content}
    assert maintenance.observed_chunk(payload, chunks) == path
    assert maintenance.observed_chunk({**payload, 'output': content[-10:]}, chunks) is None
    assert maintenance.observed_chunk({**payload, 'command': 'echo ' + path}, chunks) is None


async def test_large_review_requires_actual_complete_native_chunk_receipts(monkeypatch):
    ctl, rid = terminal_run()
    db.append_event(rid, 'prime', 'prime.execution.progress', {'output': 'public data ' * 100_000})
    maintenance.grant_post_review(ctl, rid, 'chunk-review', allow_model_calls=True, reason='new')
    class Brain:
        async def open(self, spec): return SessionRef('fixture', 'fresh')
        async def close(self, session): pass
        async def review(self, session, packet):
            assert packet['trace_delivery']['mode'] == 'verified_file_chunks'
            for chunk in packet['trace_delivery']['chunks']:
                yield BrainEvent('progress', {'command': 'cat ' + chunk['path'], 'status': 'completed', 'exit_code': 0, 'output': open(chunk['path']).read()})
            yield BrainEvent('task_result', {'result': {'system_defects_md': 'ok', 'strategy_lessons': [], 'environment_notes_md': 'unknown'}})
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: Brain())
    await maintenance.run_post_review(ctl, rid, review_id='chunk-review')
    row = db.query_one('SELECT status,result_json FROM run_post_review_versions WHERE id=?', ('chunk-review',))
    assert row['status'] == 'done'
    proof = json.loads(row['result_json'])['trace_delivery_evidence']
    assert proof['chunks_read'] == proof['chunks_required'] > 100


@pytest.mark.parametrize('content,output', [(' ' * 10000, ''), ('\n full trace \n', 'full trace')])
def test_chunk_receipt_cannot_hide_whitespace_truncation(content, output):
    path = '/frozen/chunk.txt'
    payload = {'command': 'cat ' + path, 'status': 'completed', 'exit_code': 0, 'output': output}
    assert maintenance.observed_chunk(payload, {path: content}) is None
    assert maintenance.observed_chunk({**payload, 'output': content}, {path: content}) == path


async def test_large_kimi_review_rejected_before_consuming_model_grant(monkeypatch):
    ctl, rid = terminal_run()
    db.append_event(rid, 'prime', 'prime.execution.progress', {'output': 'public data ' * 100_000})
    maintenance.grant_post_review(ctl, rid, 'unsupported-chunks', allow_model_calls=True, reason='new')
    original = ctl._runtime_settings
    def settings(run_id):
        value = original(run_id); value['post_review'] = {**value['post_review'], 'runtime': 'kimi'}
        return value
    monkeypatch.setattr(ctl, '_runtime_settings', settings)
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: pytest.fail('No native process before runtime capability rejection'))
    await maintenance.run_post_review(ctl, rid, review_id='unsupported-chunks')
    row = db.query_one('SELECT status,calls_used,error FROM run_post_review_versions WHERE id=?', ('unsupported-chunks',))
    assert row['status'] == 'failed' and row['calls_used'] == 0 and '未调用模型' in row['error']


@pytest.mark.parametrize('rewrites,expected', [(0, 'failed'), (2, 'done')])
async def test_post_review_explicit_format_budget_repairs_same_native_session(monkeypatch, rewrites, expected):
    from cyberscientist.brains.codex import CodexBrain
    from test_structured_rewrite_cs10 import NativeRPC
    ctl, rid = terminal_run()
    valid = {'system_defects_md': 'ok', 'strategy_lessons': [], 'environment_notes_md': 'unknown'}
    invalid = {**valid, 'system_defects_md_extra_placeholder_note': 'unexpected'}
    rpc = NativeRPC([json.dumps(invalid), json.dumps(valid)], 'codex')
    brain = CodexBrain('fixture'); brain.rpc = rpc
    async def opened(spec): return SessionRef('codex', 'same-session')
    async def closed(session): pass
    monkeypatch.setattr(brain, 'open', opened); monkeypatch.setattr(brain, 'close', closed)
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: brain)
    maintenance.grant_post_review(ctl, rid, 'format-budget', allow_model_calls=True, reason='explicit budget', max_format_rewrites=rewrites)
    await maintenance.run_post_review(ctl, rid, review_id='format-budget')
    row = db.query_one('SELECT * FROM run_post_review_versions WHERE id=?', ('format-budget',))
    assert row['status'] == expected and row['calls_used'] == (2 if rewrites else 1)
    assert len(rpc.calls) == row['calls_used'] and not db.query('SELECT * FROM maintenance_calls')
    assert all(params['threadId'] == 'same-session' for _, params in rpc.calls)
    with pytest.raises(ValueError, match='幂等'):
        maintenance.grant_post_review(ctl, rid, 'format-budget', allow_model_calls=True, reason='explicit budget', max_format_rewrites=1)
    if rewrites:
        db.execute("UPDATE run_post_review_versions SET status='running'")
        maintenance.reconcile_interrupted()
        assert db.query_one('SELECT status FROM run_post_review_versions')[0] == 'unknown'


async def test_missing_native_terminal_receipt_stays_unknown_and_not_replayed(monkeypatch):
    ctl, rid = terminal_run(); calls = []
    class Brain:
        async def open(self, spec): return SessionRef('fixture', 'unknown')
        async def close(self, session): pass
        async def review(self, session, packet):
            calls.append(1)
            yield BrainEvent('error', {'code': 'NATIVE_TURN_UNKNOWN', 'message': '等待 turn 终态失败'})
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: Brain())
    maintenance.grant_post_review(ctl, rid, 'lost-terminal', allow_model_calls=True, reason='explicit')
    await maintenance.run_post_review(ctl, rid, review_id='lost-terminal')
    assert db.query_one('SELECT status,calls_used FROM run_post_review_versions')[0] == 'unknown'
    maintenance.reconcile_interrupted(); await maintenance.run_post_review(ctl, rid, review_id='lost-terminal')
    assert calls == [1]


@pytest.mark.parametrize('fault,expected', [('start_timeout', 'unknown'), ('start_disconnect', 'unknown'), ('pipe_disconnect', 'unknown'), ('notification_eof', 'unknown'), ('known_rejection', 'failed')])
async def test_actual_codex_start_ack_and_terminal_loss_are_not_replayed(monkeypatch, fault, expected):
    from cyberscientist.brains.codex import CodexBrain
    from cyberscientist.jsonrpc_stdio import ProtocolError
    ctl, rid = terminal_run(); calls = []
    class RPC:
        async def request(self, method, params, **kwargs):
            calls.append(method)
            if fault == 'start_timeout': raise asyncio.TimeoutError()
            if fault == 'start_disconnect': raise ProtocolError('connection closed after sending')
            if fault == 'pipe_disconnect': raise ConnectionResetError('after write')
            if fault == 'known_rejection': raise ProtocolError(json.dumps({'code': -32602, 'data': {'input_error_code': 'input_too_large'}, 'message': 'Input exceeds maximum'}))
            return {'turn': {'id': 'accepted'}}
        async def notifications(self):
            if False: yield {}
    brain = CodexBrain('fixture'); brain.rpc = RPC()
    async def opened(spec): return SessionRef('codex', 'same-session')
    async def closed(session): pass
    monkeypatch.setattr(brain, 'open', opened); monkeypatch.setattr(brain, 'close', closed)
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: brain)
    maintenance.grant_post_review(ctl, rid, 'native-ack', allow_model_calls=True, reason='explicit', max_format_rewrites=2)
    await maintenance.run_post_review(ctl, rid, review_id='native-ack')
    row = db.query_one('SELECT status,calls_used FROM run_post_review_versions')
    assert row['status'] == expected and row['calls_used'] == 1
    maintenance.reconcile_interrupted(); await maintenance.run_post_review(ctl, rid, review_id='native-ack')
    assert calls == ['turn/start']


@pytest.mark.parametrize('rewrites,expected', [(0, 'failed'), (2, 'done')])
async def test_native_incomplete_trace_gets_missing_blocks_feedback_with_original_budget(monkeypatch, rewrites, expected):
    from cyberscientist.brains.codex import CodexBrain
    ctl, rid = terminal_run()
    db.append_event(rid, 'prime', 'prime.execution.progress', {'output': 'public data ' * 100_000})
    grant = maintenance.grant_post_review(ctl, rid, 'read-repair', allow_model_calls=True, reason='explicit', max_format_rewrites=rewrites)
    native, chunks = maintenance.native_materials(json.loads(grant['packet_json']))
    calls = []
    valid = {'system_defects_md': 'complete', 'strategy_lessons': [], 'environment_notes_md': 'unknown'}
    class RPC:
        async def request(self, method, params, **kwargs):
            calls.append(params); return {'turn': {'id': str(len(calls))}}
        async def notifications(self):
            items = list(chunks.items())[:1] if len(calls) == 1 else list(chunks.items())[1:]
            for path, content in items:
                yield {'method': 'item/completed', 'params': {'threadId': 'same-session', 'item': {
                    'type': 'commandExecution', 'command': 'cat ' + path, 'status': 'completed', 'exitCode': 0, 'aggregatedOutput': content}}}
            yield {'method': 'item/completed', 'params': {'threadId': 'same-session', 'item': {'type': 'agentMessage', 'text': json.dumps(valid)}}}
            yield {'method': 'turn/completed', 'params': {'threadId': 'same-session', 'turn': {'id': str(len(calls)), 'status': 'completed'}}}
    brain = CodexBrain('fixture'); brain.rpc = RPC()
    async def opened(spec): return SessionRef('codex', 'same-session')
    async def closed(session): pass
    monkeypatch.setattr(brain, 'open', opened); monkeypatch.setattr(brain, 'close', closed)
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: brain)
    await maintenance.run_post_review(ctl, rid, review_id='read-repair')
    row = db.query_one('SELECT * FROM run_post_review_versions')
    assert row['status'] == expected and row['calls_used'] == (2 if rewrites else 1)
    assert len(calls) == row['calls_used'] and all(p['threadId'] == 'same-session' for p in calls)
    assert all(len(p['input'][0]['text']) < 900_000 for p in calls)
    if rewrites:
        assert 'trace_delivery:' in calls[1]['input'][0]['text'] and '只补读' in calls[1]['input'][0]['text']
        proof = json.loads(row['result_json'])['trace_delivery_evidence']
        assert proof['chunks_read'] == proof['chunks_required'] == len(chunks)
    else:
        assert '未覆盖全部分块' in row['error']


@pytest.mark.parametrize('fault', ['start_timeout', 'terminal_disconnect'])
async def test_legacy_format_rewrite_native_unknown_marks_both_calls_and_never_replays(monkeypatch, fault):
    from cyberscientist.brains.codex import CodexBrain
    from cyberscientist.jsonrpc_stdio import ProtocolError
    ctl, rid = terminal_run(); now = db.utcnow(); calls = []
    db.execute("UPDATE runs SET phase='created' WHERE id=?", (rid,))
    ctl.authorize(rid, 'demo', True, 10, 30, 0, None)
    db.execute("UPDATE runs SET phase='finished' WHERE id=?", (rid,))
    db.execute("INSERT INTO run_post_reviews(run_id,status,reason,created_at,updated_at) VALUES(?,'running','old',?,?)", (rid, now, now))
    class RPC:
        async def request(self, method, params, **kwargs):
            calls.append(params)
            if len(calls) == 2 and fault == 'start_timeout': raise asyncio.TimeoutError()
            return {'turn': {'id': str(len(calls))}}
        async def notifications(self):
            if len(calls) == 2: raise ProtocolError('connection closed after accepted rewrite')
            yield {'method': 'item/completed', 'params': {'threadId': 'same-session', 'item': {'type': 'agentMessage', 'text': 'not JSON'}}}
            yield {'method': 'turn/completed', 'params': {'threadId': 'same-session', 'turn': {'id': '1', 'status': 'completed'}}}
    brain = CodexBrain('fixture'); brain.rpc = RPC()
    async def opened(spec): return SessionRef('codex', 'same-session')
    async def closed(session): pass
    monkeypatch.setattr(brain, 'open', opened); monkeypatch.setattr(brain, 'close', closed)
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: brain)
    await maintenance.run_post_review(ctl, rid)
    assert len(calls) == 2 and all(p['threadId'] == 'same-session' for p in calls)
    assert [r['status'] for r in db.query('SELECT status FROM maintenance_calls ORDER BY rowid')] == ['unknown', 'unknown']
    assert db.query_one('SELECT status FROM run_post_reviews')[0] == 'unknown'
    maintenance.reconcile_interrupted(); await maintenance.advance(ctl, rid); await maintenance.run_post_review(ctl, rid)
    assert len(calls) == 2


@pytest.mark.parametrize('explicit', [False, True])
async def test_post_review_resumed_run_cannot_reserve_material_repair(monkeypatch, explicit):
    ctl, rid = terminal_run(); calls = []; now = db.utcnow()
    db.execute("UPDATE runs SET phase='created' WHERE id=?", (rid,))
    ctl.authorize(rid, 'demo', True, 10, 30, 0, None)
    db.execute("UPDATE runs SET phase='finished' WHERE id=?", (rid,))
    db.append_event(rid, 'prime', 'prime.execution.progress', {'output': 'public data ' * 100_000})
    if explicit:
        maintenance.grant_post_review(ctl, rid, 'resume-boundary', allow_model_calls=True, reason='new', max_format_rewrites=2)
    else:
        db.execute("INSERT INTO run_post_reviews(run_id,status,reason,created_at,updated_at) VALUES(?,'running','old',?,?)", (rid, now, now))
    class Brain:
        async def open(self, spec): return SessionRef('fixture', 'same')
        async def close(self, session): pass
        async def review(self, session, packet):
            calls.append(1); db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
            yield BrainEvent('task_result', {'result': {'system_defects_md': 'partial', 'strategy_lessons': [], 'environment_notes_md': 'unknown'}})
    monkeypatch.setattr(ctl, '_make_brain', lambda settings: Brain())
    await maintenance.run_post_review(ctl, rid, **({'review_id': 'resume-boundary'} if explicit else {}))
    assert calls == [1]
    if explicit:
        assert db.query_one('SELECT calls_used,status FROM run_post_review_versions')[0] == 1
    else:
        assert len(db.query('SELECT * FROM maintenance_calls')) == 1
