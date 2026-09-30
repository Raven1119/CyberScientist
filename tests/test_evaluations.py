"""Fake evaluation Runs exercise the persistent queue without models or Bohrium."""
from __future__ import annotations

import asyncio
import json
import sys

import pytest

from cyberscientist import cli, config, db, environment_facts, evaluations, experience_context, mailboxes
from cyberscientist.controller import RunController


MODELS = {role: {'runtime': 'codex', 'model_id': 'gpt-6-sol',
                 'reasoning_effort': 'xhigh'} for role in ('brain', 'executor')}


def _challenge(cid: str) -> None:
    db.execute('INSERT INTO challenges(id,platform_challenge_id,origin,title,content,'
               'content_hash,imported_at) VALUES(?,?,?,?,?,?,?)',
               (cid, cid, 'fixture', cid, 'fixture task', cid, db.utcnow()))


def _catalog(monkeypatch, tmp_path) -> None:
    path = tmp_path / 'catalog.json'
    path.write_text(json.dumps({'challenges': [
        {'challenge_id': cid, 'platform_challenge_id': cid,
         'tier': 'fast', 'included': True,
         'science_scorer': {'status': 'spec_validated'}}
        for cid in ('eval_a', 'eval_b')]}))
    monkeypatch.setattr(evaluations, 'CATALOG', path)
    for cid in ('eval_a', 'eval_b'):
        _challenge(cid)
    monkeypatch.setattr(experience_context, 'select', lambda *args, **kwargs: [])
    monkeypatch.setattr(evaluations.skills, 'effective_for', lambda *args, **kwargs: [])


class FakeController:
    def __init__(self):
        self.real = RunController()
        self.starts = []
        self.resumes = []

    def create_run(self, *args, **kwargs):
        return self.real.create_run(*args, **kwargs)

    def authorize(self, *args, **kwargs):
        return self.real.authorize(*args, **kwargs)

    async def start_async(self, run_id):
        self.starts.append(run_id)
        trial = 'trial_' + run_id
        db.execute('INSERT INTO trials(id,run_id,goal,success_check,created_at)'
                   ' VALUES(?,?,?,?,?)', (trial, run_id, 'fake', 'fake', db.utcnow()))
        db.execute("UPDATE runs SET phase='eval_scoring',gate='open',current_trial_id=?,"
                   'started_at=? WHERE id=?', (trial, db.utcnow(), run_id))

    async def control(self, run_id, action, text, operation_id):
        self.resumes.append(run_id)
        db.execute("UPDATE runs SET phase='eval_scoring' WHERE id=?", (run_id,))

    def _finalize_run(self, run_id, reason):
        db.execute("UPDATE runs SET phase='finished',ended_at=?,end_reason=? WHERE id=?",
                   (db.utcnow(), reason, run_id))


def _fake_score(run_id: str, result_id: str):
    run = db.query_one('SELECT challenge_id,current_trial_id FROM runs WHERE id=?', (run_id,))
    score = 100.0 if run['challenge_id'] == 'eval_a' else 40.0
    db.execute('INSERT INTO local_scores(id,challenge_id,run_id,trial_id,package_sha256,'
               'science_artifact_hashes_json,manifest_science_sha256,science_score,'
               'trace_prediction_json,scorer_version,scorer_file_hashes_json,feature_version,'
               'model_version,sandbox_operation_id,created_at)'
               ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               ('ls_' + result_id, run['challenge_id'], run_id, run['current_trial_id'],
                'package', '{}', 'manifest', score, '{}', 'fake-v1', '{}', 'v1', 'v1',
                'eval-score-' + result_id, db.utcnow()))
    db.append_event(run_id, 'controller', 'evaluation.trace_diagnosed',
                    {'status': 'ready', 'checklist_score': 75,
                     'qualified_codes': ['N09_NO_EXECUTION_EVIDENCE'], 'advisory_cap': 49})
    return 'scored', None


def test_two_by_two_evaluation_and_resume(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(evaluations, '_score_run', _fake_score)
    settings = config.load_settings()
    settings['run_defaults']['max_active_runs'] = 2
    config.save_settings(settings)
    created = evaluations.create_evaluation('fast', 2, 'fake')
    assert len(created['results']) == 4
    assert evaluations.create_evaluation('fast', 2, 'fake')['id'] == created['id']
    first = FakeController()
    asyncio.run(evaluations.advance(first))
    assert len(first.starts) == 2  # capacity; no fourth Run created yet
    second = FakeController()       # process restart: persisted queue, new controller
    for _ in range(4):
        asyncio.run(evaluations.advance(second))
    result = evaluations.report(created['id'])
    assert result['evaluation']['status'] == 'complete'
    assert result['suite_summary']['completed_count'] == 4
    assert result['suite_summary']['science_mean'] == 70
    assert all(row['result']['scorer_version'] == 'fake-v1' for row in result['evaluation']['results'])
    assert all(row['result']['display_interval']['upper'] == row['result']['science_score'] * .49
               for row in result['evaluation']['results'])
    assert len(first.starts + second.starts) == 4
    assert len({row['run_id'] for row in result['evaluation']['results']}) == 4
    assert db.query_one('SELECT 1 FROM submissions') is None
    assert db.query_one('SELECT 1 FROM experience_revisions') is None
    markdown, structured = evaluations.write_report(created['id'])
    assert 'eval_a' in markdown.read_text() and structured.is_file()


def test_recovering_run_resumes_once(monkeypatch, tmp_path):
    _catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(evaluations, '_score_run', _fake_score)
    created = evaluations.create_evaluation('fast', 1)
    first = FakeController()
    asyncio.run(evaluations.advance(first))
    rid = created['results'][0]['run_id'] or first.starts[0]
    db.execute("UPDATE runs SET phase='recovering' WHERE id=?", (rid,))
    second = FakeController()
    asyncio.run(evaluations.advance(second))
    assert rid in second.resumes
    assert rid not in second.starts


@pytest.mark.parametrize(('cap', 'expected'), [
    (20, (0, 0)), (29, (0, 0)), (30, (0, 24)), (69, (0, 55.2)),
    (None, (24, 80)),
])
def test_display_interval_branches(cap, expected):
    result = evaluations.display_interval(80, cap)
    assert (result['lower'], result['upper']) == expected
    if cap is None:
        assert result['basis'] == '裁判部分未复刻'
    assert evaluations.display_interval(None, cap)['lower'] is None


def test_eval_submission_and_experience_writes_are_rejected():
    _challenge('eval_guard')
    controller = RunController()
    run = controller.create_run('eval_guard', 'connected', eval_mode={
        'enabled': True, 'models': MODELS,
        'experience_manifests': {'brain': [], 'executor': [], 'both': []}})
    rid = run['id']
    with pytest.raises(mailboxes.MailboxError) as error:
        mailboxes.submit_experiment(rid, None, None, 'fake-op')
    assert error.value.code == 'EVAL_SUBMISSION_FORBIDDEN'
    controller._apply_experience_proposal(rid, 'fake-decision',
                                           {'body_md': 'must not write'})
    with db.transaction() as conn:
        experience_context.adopt_tx(conn, rid, None,
                                    [{'context_id': 'none'}], 'brain', 'fake')
    event = {'run_id': rid, 'source': 'controller', 'type': 'image_facts.observed'}
    assert environment_facts.record('fake-key', 'fake', {}, event)['status'] == 'rejected'
    assert db.query_one('SELECT 1 FROM experience_revisions') is None
    assert db.query_one('SELECT 1 FROM submissions WHERE run_id=?', (rid,)) is None
    kinds = {row['type'] for row in db.query('SELECT type FROM events WHERE run_id=?', (rid,))}
    assert 'evaluation.submission_rejected' in kinds
    assert 'evaluation.experience_write_rejected' in kinds


async def test_eval_finish_enters_scoring_with_open_gate(monkeypatch):
    _challenge('eval_finish')
    controller = RunController()
    rid = controller.create_run('eval_finish', 'connected', eval_mode={
        'enabled': True, 'models': MODELS,
        'experience_manifests': {'brain': [], 'executor': [], 'both': []}})['id']
    controller.authorize(rid, 'connected', True, 0, 60, 0, 'fake')
    trial = 'trial_eval_finish'
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,status,created_at)'
               ' VALUES(?,?,?,?,?,?)',
               (trial, rid, 'fake', 'fake', 'reported_complete', db.utcnow()))
    db.execute("UPDATE runs SET phase='running',gate='waiting_brain',current_trial_id=?,"
               'started_at=? WHERE id=?', (trial, db.utcnow(), rid))
    monkeypatch.setattr(controller, '_make_prime', lambda _: object())
    decision = {'schema_version': 2, 'decision_id': 'finish-eval', 'run_id': rid,
                'observed_state_version': 0, 'summary': 'done', 'evidence_refs': [],
                'experience_proposals': [], 'actions': [{
                    'op': 'finish', 'reason': 'done',
                    'objective_assessment': {'status': 'partial', 'evidence_refs': [],
                                             'remaining_md': ''}}]}
    await controller._apply_decision(rid, decision, {}, None, None)
    run = db.query_one('SELECT phase,gate FROM runs WHERE id=?', (rid,))
    assert (run['phase'], run['gate']) == ('eval_scoring', 'open')
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='evaluation.scoring_started'",
                        (rid,))


def test_science_score_still_runs_when_trace_admission_blocks(monkeypatch):
    _challenge('eval_soft_admission')
    controller = RunController()
    rid = controller.create_run('eval_soft_admission', 'connected', eval_mode={
        'enabled': True, 'models': MODELS,
        'experience_manifests': {'brain': [], 'executor': [], 'both': []}})['id']
    trial = 'trial_soft_admission'
    now = db.utcnow()
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,created_at)'
               ' VALUES(?,?,?,?,?)', (trial, rid, 'fake', 'fake', now))
    db.execute("UPDATE runs SET phase='eval_scoring',gate='open',current_trial_id=? WHERE id=?",
               (trial, rid))
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,'
               'request_json,status,created_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
               ('sx_soft', rid, trial, 'sandbox_soft', '{"image":"fake-image"}',
                'active', now, now, now))
    monkeypatch.setattr(mailboxes, 'preflight_submission', lambda *args, **kwargs: {
        'sealed_bytes': b'fake-sealed', 'sealed_package_sha256': 'fake-sha',
        'data_inputs': {'evidence_class': 'proxy'},
        'trace_diagnostics': {'status': 'ready', 'checklist_score': 0,
                              'advisories': [], 'advisory_cap': None},
        'error_code': 'TRACE_ADMISSION_BLOCKED'})
    monkeypatch.setattr(evaluations.local_scoring, 'scorer_manifest', lambda _: {'image': 'fake-image'})
    seen = []
    def fake_evaluate(*args, **kwargs):
        seen.append(kwargs['preflight']['error_code'])
        return {'id': 'ls_fake', 'science_score': 80}
    monkeypatch.setattr(evaluations.local_scoring, 'evaluate', fake_evaluate)
    assert evaluations._score_run(rid, 'er_soft') == ('scored', None)
    assert seen == [None]
    event = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='evaluation.sealed'",
                         (rid,))
    assert json.loads(event['payload'])['admission_error_code'] == 'TRACE_ADMISSION_BLOCKED'


def test_eval_tables_are_idempotent():
    db.init_db()
    db.init_db()
    assert db.query_one("SELECT name FROM sqlite_master WHERE name='eval_results'")


def test_one_command_eval_launches_existing_backend(monkeypatch, capsys):
    seen = []

    class Response:
        def __init__(self, body):
            self.body = body
        def close(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    def urlopen(request, timeout):
        seen.append(request)
        return Response(None) if isinstance(request, str) else Response({'id': 'eval_fake',
                                                                          'status': 'running'})

    monkeypatch.setattr(cli.urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(cli.json, 'load', lambda response: response.body)
    monkeypatch.setattr(sys, 'argv', ['cyberscientist', 'eval', 'run', '--suite', 'fast',
                                     '--repeats', '2'])
    cli.main()
    assert len(seen) == 2
    assert json.loads(seen[1].data)['suite'] == 'fast'
    assert 'eval_fake' in capsys.readouterr().out
