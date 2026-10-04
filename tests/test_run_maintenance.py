"""Durable end maintenance uses native-protocol fakes, not scientific fixtures."""
import asyncio
import json

import pytest

from cyberscientist import config, db, experiences, maintenance
from cyberscientist.brains.base import BrainEvent, SessionRef
from test_collaboration import _rig, _seed_challenge, _start, _wait


@pytest.mark.parametrize('ending', ['normal', 'authorization_expired', 'user_terminate', 'runtime_error', 'brain_review_limit'])
async def test_every_exit_curates_and_writes_fresh_three_part_review(ending, monkeypatch):
    _seed_challenge()
    ctl, brain, executor = _rig(shadow=False)
    rid = ctl.create_run('COLLAB_CH', shadow_enabled=False)['id']
    tid = await _start(ctl, brain, rid)
    research_used = ctl.run_snapshot(rid)['brain_reviews_used']
    if ending == 'normal':
        ctl._finalize_run(rid, ending)
    elif ending == 'user_terminate':
        await ctl.control(rid, 'terminate', None, 'fixture-terminate')
    elif ending == 'brain_review_limit':
        db.execute('UPDATE runs SET brain_reviews_used=? WHERE id=?',
                   (config.load_settings()['run_defaults']['max_brain_reviews'], rid))
        await ctl.control(rid, 'steer', 'research judgement', 'fixture-steer')
    else:
        db.execute('UPDATE authorizations SET max_run_minutes=1 WHERE run_id=?', (rid,))
        db.execute('UPDATE runs SET active_elapsed_seconds=61 WHERE id=?', (rid,))
        if ending == 'runtime_error':
            async def broken_abort(_):
                raise RuntimeError('fixture native connection lost')
            monkeypatch.setattr(executor, 'abort', broken_abort)
        await executor.turn_done()
    assert await _wait(lambda: ctl.run_snapshot(rid)['phase'] in ('finished', 'failed', 'cancelled'))
    assert await _wait(lambda: (db.query_one('SELECT status FROM run_post_reviews WHERE run_id=?', (rid,)) or {})['status'] == 'done')
    assert ctl.run_curation_status(rid)['state'] == 'done'
    calls = db.query('SELECT kind,status FROM maintenance_calls WHERE run_id=?', (rid,))
    assert {r['kind'] for r in calls} == {'curation', 'postreview'} and len(calls) == 2
    assert all(r['status'] == 'done' for r in calls)
    assert ctl.run_snapshot(rid)['brain_reviews_used'] == (config.load_settings()['run_defaults']['max_brain_reviews'] if ending == 'brain_review_limit' else research_used)
    note = experiences.get_experience('trial_note_' + tid)
    assert note['frontmatter']['scope'] == 'challenge' and '科学成功' in note['body_md']
    post = db.query_one('SELECT * FROM run_post_reviews WHERE run_id=?', (rid,))
    text = (config.WORKSPACE_DIR / post['report_path']).read_text()
    assert all(title in text for title in ('## 系统缺陷', '## 策略教训候选', '## 环境事实'))
    terminal = ctl.run_snapshot(rid)['phase']
    maintenance.queue_end(ctl, rid, ending)
    await maintenance.advance(ctl, rid)
    await asyncio.sleep(.01)
    assert len(db.query('SELECT * FROM maintenance_calls WHERE run_id=?', (rid,))) == 2
    assert ctl.run_snapshot(rid)['phase'] == terminal


async def test_failed_curation_still_reviews_and_shared_call_limit_never_replays(monkeypatch):
    _seed_challenge(); ctl, _, _ = _rig(shadow=False)
    rid = ctl.create_run('COLLAB_CH')['id']
    calls = []
    class Brain:
        async def open(self, spec): return SessionRef('fixture', 'fresh')
        async def close(self, session): pass
        async def review(self, session, packet):
            calls.append(packet['protocol'])
            if packet['protocol'] == 'experience_curation':
                yield BrainEvent('error', {'message': 'fixture 500'})
            else:
                yield BrainEvent('task_result', {'result': {'system_defects_md': 'Inspect the failure',
                    'strategy_lessons': [], 'environment_notes_md': 'No receipt'}})
    monkeypatch.setattr(ctl, '_make_brain', lambda _: Brain())
    ctl._finalize_run(rid, 'normal')
    assert await _wait(lambda: (db.query_one('SELECT status FROM run_post_reviews WHERE run_id=?', (rid,)) or {})['status'] == 'done')
    assert calls == ['experience_curation', 'role_task']
    assert ctl.run_snapshot(rid)['phase'] == 'finished'
    await ctl.curate_run_experience(rid, 'third-call')
    assert await _wait(lambda: ctl.run_curation_status(rid)['state'] == 'failed')
    assert len(calls) == 2
    maintenance.reconcile_interrupted()
    await maintenance.advance(ctl)
    assert len(calls) == 2


def test_full_public_trace_has_no_clipping_private_notes_or_secret_values():
    _seed_challenge(); ctl, _, _ = _rig(shadow=False)
    rid = ctl.create_run('COLLAB_CH')['id']
    config.save_secrets({'fixture_key': 'fixture-secret-never-export'})
    detail = 'public output ' * 1000
    db.append_event(rid, 'prime', 'prime.execution.progress', {'detail': detail, 'private_note_md': 'private scratch', 'output': 'fixture-secret-never-export'})
    db.append_event(rid, 'brain', 'brain.raw_output', {'text': json.dumps({'private_note_md': 'encoded scratch'})})
    packet = maintenance.snapshot(ctl, rid)
    raw = open(packet['public_trace']['path']).read()
    assert detail in raw and 'private scratch' not in raw and 'encoded scratch' not in raw and 'fixture-secret-never-export' not in raw
    assert not packet['public_trace']['truncated']


def test_restart_marks_started_calls_unknown_but_unstarted_requests_retry():
    _seed_challenge(); ctl, _, _ = _rig(shadow=False)
    rid = ctl.create_run('COLLAB_CH')['id']
    now = db.utcnow()
    packet = maintenance.snapshot(ctl, rid)
    db.execute("INSERT INTO run_post_reviews(run_id,status,reason,packet_json,created_at,updated_at) VALUES(?,'running','normal',?,?,?)",
               (rid, json.dumps(packet), now, now))
    maintenance.claim_call(rid, 'postreview-' + rid, 'postreview')
    maintenance.reconcile_interrupted()
    assert db.query_one('SELECT status FROM run_post_reviews WHERE run_id=?', (rid,))['status'] == 'unknown'
    with pytest.raises(ValueError, match='已开始'):
        maintenance.claim_call(rid, 'postreview-' + rid, 'postreview')
    assert db.query_one('SELECT status FROM maintenance_calls WHERE run_id=?', (rid,))['status'] == 'unknown'


async def test_post_review_accepts_complete_trace_refs_but_saves_only_candidate(monkeypatch):
    from test_collaboration import _proposal
    _seed_challenge(); ctl, _, _ = _rig(shadow=False)
    rid = ctl.create_run('COLLAB_CH')['id']
    for n in range(80):
        event = db.append_event(rid, 'controller', 'job.unknown', {'fixture': n})
        if n == 25:
            middle = f"event:{rid}:{event['seq']}"
    class Brain:
        async def open(self, spec): return SessionRef('fixture', 'fresh')
        async def close(self, session): pass
        async def review(self, session, packet):
            if packet['protocol'] == 'experience_curation':
                yield BrainEvent('curation_result', {'result': {'schema_version': 1,
                    'message_type': 'curation_result', 'summary': 'No proposals', 'experience_proposals': []}})
            else:
                trace = open(packet['public_trace']['path']).read()
                assert '"fixture": 25' in trace
                assert middle not in packet['run_evidence']['evidence_refs']
                p = _proposal('challenge', '独立复盘候选')
                p['evidence_refs'] = [middle]
                yield BrainEvent('task_result', {'result': {'system_defects_md': 'Full public trace read in fake',
                    'strategy_lessons': [p], 'environment_notes_md': 'No actual receipt'}})
    monkeypatch.setattr(ctl, '_make_brain', lambda _: Brain())
    ctl._finalize_run(rid, 'normal')
    assert await _wait(lambda: dict(db.query_one('SELECT status FROM run_post_reviews WHERE run_id=?', (rid,)) or {}).get('status') == 'done')
    item = next(i for i in experiences.list_experiences()['items'] if i['title'] == '独立复盘候选')
    assert item['status'] == 'candidate' and item['evidence_status'] == 'hypothesis'


async def test_unknown_abort_closes_local_runtime_before_end_maintenance(monkeypatch):
    from cyberscientist.prime import ActionReceipt
    _seed_challenge(); ctl, brain, executor = _rig(shadow=False)
    rid = ctl.create_run('COLLAB_CH')['id']; await _start(ctl, brain, rid)
    closed = []
    async def unknown_abort(_): return ActionReceipt(status='unknown', detail='No native acknowledgement')
    async def close(sid): closed.append(sid)
    monkeypatch.setattr(executor, 'abort', unknown_abort)
    monkeypatch.setattr(executor, 'close', close)
    db.execute('UPDATE authorizations SET max_run_minutes=1 WHERE run_id=?', (rid,))
    db.execute('UPDATE runs SET active_elapsed_seconds=61 WHERE id=?', (rid,))
    await executor.turn_done()
    assert await _wait(lambda: ctl.run_snapshot(rid)['phase'] == 'finished'), (ctl.run_snapshot(rid)['phase'], db.events_after(rid, 0)[-12:])
    assert closed and db.query_one("SELECT seq FROM events WHERE run_id=? AND type='run.native_session_closed'", (rid,))
    assert await _wait(lambda: ctl.run_curation_status(rid)['state'] == 'done')
