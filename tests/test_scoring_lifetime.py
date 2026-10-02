"""Controller scoring fits existing grants; no real sandbox is created."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from cyberscientist import compute, db, local_scoring, mailboxes, sandboxes
from test_final_candidate_integrity import _run_with_scorer


def _fixture(seconds=900):
    rid, tid, _, _, manifest = _run_with_scorer()
    now = db.utcnow()
    expires = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,'
        'request_json,status,created_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
        ('synthetic-score-box',rid,tid,'synthetic-score-box',json.dumps({'image':manifest['image']}),
         'active',now,expires,now))
    return rid, tid, manifest


def test_score_timeout_exceeding_shortened_lifetime_is_bounded(monkeypatch):
    rid, tid, manifest = _fixture()
    monkeypatch.setattr(mailboxes.arm_admission, 'check',
                        lambda *_: {'verdict':'admitted','signals':{}})
    seconds = iter((800, 55))
    monkeypatch.setattr(sandboxes, '_seconds_left', lambda _: next(seconds))
    calls = []
    def execute(run_id, sid, command, timeout, operation_id):
        calls.append(timeout)
        if operation_id.endswith('-run'):
            if timeout > 55:
                raise compute.ComputeError('INVALID_COMMAND','timeout exceeds remaining lifetime')
            result = {'score':11,'components':{},'confidence':'medium',
                      'notes':'synthetic','scorer_version':manifest['scorer_version']}
            return {'status':'completed','receipt':{'stdout':json.dumps({'data':{'stdout':json.dumps(result)}})}}
        return {'status':'completed'}
    monkeypatch.setattr(sandboxes, 'execute', execute)
    monkeypatch.setattr(sandboxes, 'transfer', lambda *a,**k: {'status':'completed'})
    score = local_scoring.evaluate(rid,tid,'synthetic-score-box','bounded-score',score_timeout=1200)
    assert calls == [30, 50]
    assert score['science_score'] == 11
    assert db.query_one('SELECT count(*) AS n FROM compute_sandboxes WHERE run_id=?',(rid,))['n'] == 1


def test_command_is_also_bounded_by_remaining_run_grant():
    rid, _, _ = _fixture(3600)
    started = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
    db.execute('UPDATE runs SET started_at=? WHERE id=?',(started,rid))
    db.execute('UPDATE authorizations SET max_run_minutes=1 WHERE id=(SELECT authorization_id FROM runs WHERE id=?)',(rid,))
    assert 1 <= sandboxes.bounded_execution_timeout(rid,'synthetic-score-box',1200) <= 10


@pytest.mark.parametrize('state',['expired','run_expired','deleted','foreign'])
def test_exhausted_or_unowned_scoring_never_executes(state,monkeypatch):
    rid, _, _ = _fixture(0 if state=='expired' else 3600)
    if state=='run_expired':
        db.execute('UPDATE runs SET started_at=? WHERE id=?',
                   ((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),rid))
    if state=='deleted':
        db.execute("UPDATE compute_sandboxes SET status='deleted' WHERE run_id=?",(rid,))
    monkeypatch.setattr(compute,'_native',lambda *a,**k:pytest.fail('no external execution'))
    with pytest.raises(compute.ComputeError):
        sandboxes.bounded_execution_timeout(rid,'foreign-box' if state=='foreign' else 'synthetic-score-box',1200)
