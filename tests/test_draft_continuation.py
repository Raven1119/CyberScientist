"""Known rejected drafts can be repaired by a new explicit submission, without another Attempt."""
from test_mailbox_platform import valid_arm_zip
import json
import asyncio
from datetime import datetime, timezone, timedelta
from threading import Event
from concurrent.futures import ThreadPoolExecutor

import pytest

from cyberscientist import db, mailboxes, arm_admission
from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform, DemoMailboxPlatform, PlatformError
from test_mailboxes import _seed_challenge, _make_run, _make_package


class DraftPlatform(DemoMailboxPlatform):
    calls = 0
    mode = 'ok'
    entered = None
    release = None

    def submit_package(self, email, secret, package_path, challenge_id='', meta=None):
        self.calls += 1
        if self.calls == 1:
            meta['on_stage']('bundle_blocked', 'draft-1')
            raise PlatformError('bundle_blocked')
        if not meta.get('resume_attempt_id'):
            return {'accepted': True, 'receipt': 'second-account-draft'}
        assert meta['resume_attempt_id'] == 'draft-1'
        if self.entered:
            self.entered.set()
            assert self.release.wait(5)
        if self.mode == 'unknown':
            meta['on_stage']('upload_sent', 'draft-1')
            raise PlatformError('upload response unknown')
        if self.mode == 'rejected':
            raise PlatformError('ownership not proven', no_side_effect=True)
        if self.mode == 'negative_receipt':
            return {'accepted': False, 'no_side_effect': True}
        return {'accepted': True, 'receipt': 'draft-1'}


def seed(monkeypatch, limit=1):
    _seed_challenge(); rid = _make_run(max_submissions=limit); _make_package(rid)
    mailboxes.register_experiment(1)
    platform = DraftPlatform()
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    original = mailboxes.submit_experiment(rid, 'trial_mb1', None, 'first')
    assert original['stage'] == 'bundle_blocked'
    _make_package(rid, 'trial_mb1', '{"repaired":true}')
    return rid, original, platform


def test_corrected_package_reuses_draft_and_budget_preserves_prior_bytes(monkeypatch):
    from cyberscientist import config
    rid, original, platform = seed(monkeypatch)
    old_bytes = (config.WORKSPACE_DIR / original['package_path']).read_bytes()
    # Ordinary non-JSON operation summaries must not break the alias lookup.
    db.record_operation('control-other', rid, 'control.pause', 'confirmed', request_summary='pause')
    repaired = mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')
    assert repaired['id'] == original['id'] and repaired['platform_ref'] == 'draft-1'
    assert repaired['status'] == 'submitted' and not repaired['reservation_released']
    assert repaired['package_sha256'] != original['package_sha256']
    assert (config.WORKSPACE_DIR / original['package_path']).read_bytes() == old_bytes
    assert db.query_one('SELECT COUNT(*) FROM submissions WHERE run_id=?', (rid,))[0] == 1
    assert mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')['deduplicated']
    assert platform.calls == 2
    with pytest.raises(mailboxes.MailboxError, match='授权已用尽'):
        mailboxes.submit_experiment(rid, 'trial_mb1', None, 'extra')


@pytest.mark.parametrize('mode', ['unknown', 'rejected', 'negative_receipt'])
def test_continuation_failure_retains_created_attempt_and_never_replays(monkeypatch, mode):
    rid, original, platform = seed(monkeypatch, limit=2); platform.mode = mode
    repaired = mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')
    assert repaired['status'] == 'unknown' and not repaired['reservation_released']
    assert mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')['deduplicated']
    with pytest.raises(mailboxes.MailboxError, match='续提正在进行或状态未知'):
        mailboxes.submit_experiment(rid, 'trial_mb1', None, 'another')
    assert platform.calls == 2 and db.query_one('SELECT COUNT(*) FROM submissions')[0] == 1


def test_concurrent_new_intents_cannot_create_second_attempt(monkeypatch):
    rid, original, platform = seed(monkeypatch, limit=2)
    platform.entered = Event(); platform.release = Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        task = pool.submit(mailboxes.submit_experiment, rid, 'trial_mb1', None, 'repair')
        assert platform.entered.wait(5)
        try:
            with pytest.raises(mailboxes.MailboxError, match='续提正在进行或状态未知'):
                mailboxes.submit_experiment(rid, 'trial_mb1', None, 'parallel')
        finally:
            platform.release.set()
        assert task.result()['status'] == 'submitted'
    assert platform.calls == 2 and db.query_one('SELECT COUNT(*) FROM submissions')[0] == 1


@pytest.mark.parametrize('state', ['paused', 'expired', 'mailbox_changed'])
def test_draft_continuation_keeps_authority_and_mailbox_boundaries(monkeypatch, state):
    rid, original, platform = seed(monkeypatch)
    if state == 'paused':
        db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
    elif state == 'expired':
        db.execute("UPDATE runs SET phase='running',started_at=?,clock_version=1,active_elapsed_seconds=99999 WHERE id=?", (db.utcnow(), rid))
    else:
        db.execute("UPDATE mailboxes SET status='inactive' WHERE id=?", (original['mailbox_id'],))
    with pytest.raises(mailboxes.MailboxError):
        mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')
    assert platform.calls == 1 and db.query_one('SELECT COUNT(*) FROM submissions')[0] == 1


@pytest.mark.parametrize('change', [None, 'owner', 'challenge', 'id', 'submitted', 'pending_bundle'])
def test_native_adapter_checks_owned_unsubmitted_target_before_any_post(tmp_path, change):
    pkg = tmp_path / 'sealed.zip'; pkg.write_bytes(valid_arm_zip())
    draft = {'id': 17, 'authorId': 'owner', 'challengeId': 'old', 'status': 'draft', 'bundleStatus': 'incomplete'}
    if change == 'owner': draft['authorId'] = 'other'
    if change == 'challenge': draft['challengeId'] = 'other'
    if change == 'id': draft['id'] = 18
    if change == 'submitted': draft['status'] = 'submitted'
    if change == 'pending_bundle': draft['bundleStatus'] = 'processing'
    calls = []
    def http(method, path, **kwargs):
        calls.append((method, path))
        if path == '/auth/me': return {'id': 'owner'}
        if method == 'GET': return draft
        if path.endswith('/bundle'): return {'bundleStatus': 'complete'}
        return {'accepted': True}
    platform = BohriumPlaygroundPlatform('https://play.bohrium.com/api'); platform._http = http
    if change:
        with pytest.raises(PlatformError, match='未确认'):
            platform.submit_package('fixture', 'fixture-token', str(pkg), 'old', {'resume_attempt_id': '17'})
        assert not any(method == 'POST' for method, _ in calls)
    else:
        assert platform.submit_package('fixture', 'fixture-token', str(pkg), 'old', {'resume_attempt_id': '17'})['receipt'] == '17'
        assert [path for method, path in calls if method == 'POST'] == ['/attempts/17/bundle', '/attempts/17/submit']


def test_platform_observed_manifest_shape_is_visible_before_upload():
    errors = arm_admission.manifest_shape_errors({'execution': {'artifacts': ['result.json']},
        'expected_outputs': [{'name': 'result'}]})
    assert errors == ['execution.artifacts[0]: expected object', 'expected_outputs[0].type: required string missing']
    assert not arm_admission.manifest_shape_errors({'execution': {'artifacts': [
        {'id': 'result', 'path': 'result.json', 'type': 'data'}]},
        'expected_outputs': [{'name': 'result', 'type': 'data'}]})


def test_poll_started_before_package_repair_cannot_bind_new_score_to_old_hash(monkeypatch):
    rid, original, platform = seed(monkeypatch, limit=2)
    platform.mode = 'unknown'
    def fetch_score(*args):
        repaired = mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')
        assert repaired['package_sha256'] != original['package_sha256']
        return 100.0
    platform.fetch_score = fetch_score
    mailboxes.poll_scores(rid, manual=True)
    current = db.query_one('SELECT * FROM submissions WHERE id=?', (original['id'],))
    assert current['score'] is None and current['score_status'] == 'unknown'
    assert not db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='submission.scored'", (rid,))


def test_startup_marks_lost_continuation_unknown_without_reposting(monkeypatch):
    rid, original, platform = seed(monkeypatch)
    platform.mode = 'unknown'
    mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')
    db.execute("UPDATE operations SET status='accepted' WHERE operation_id='repair'")
    db.execute("UPDATE submissions SET stage='bundle_blocked' WHERE id=?", (original['id'],))
    calls = platform.calls
    mailboxes.reconcile_draft_continuations()
    assert platform.calls == calls
    assert db.query_one("SELECT status FROM operations WHERE operation_id='repair'")[0] == 'unknown'
    assert mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')['deduplicated']
    platform.mode = 'ok'
    assert mailboxes.submit_experiment(rid, 'trial_mb1', None, 'new-explicit-intent')['status'] == 'submitted'
    assert db.query_one('SELECT COUNT(*) FROM submissions')[0] == 1


async def test_submission_thread_stays_tracked_through_repeated_cancellation():
    from cyberscientist import resource_coordinator
    entered = Event(); release = Event()
    def http():
        entered.set(); assert release.wait(5); return 'receipt'
    caller = asyncio.create_task(mailboxes.submit_async(http))
    assert await asyncio.to_thread(entered.wait, 2)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError): await caller
    workers = resource_coordinator.auxiliary_tasks()
    assert len(workers) == 1
    try:
        workers[0].cancel(); await asyncio.sleep(.01)
        workers[0].cancel(); await asyncio.sleep(.01)
        assert resource_coordinator.auxiliary_tasks() and not workers[0].done()
    finally:
        release.set()
        assert await workers[0] == 'receipt'
    assert not resource_coordinator.auxiliary_tasks()


def test_shutdown_after_owned_draft_get_prevents_continuation_post(tmp_path):
    pkg = tmp_path / 'sealed.zip'; pkg.write_bytes(valid_arm_zip())
    posts = []
    def http(method, path, **kwargs):
        if method == 'POST': posts.append(path)
        if path == '/auth/me': return {'id': 'owner'}
        db.execute("INSERT OR REPLACE INTO system_state(key,value) VALUES('shutdown_requested','1')")
        return {'id': 17, 'authorId': 'owner', 'challengeId': 'old', 'status': 'draft', 'bundleStatus': 'incomplete'}
    platform = BohriumPlaygroundPlatform('https://play.bohrium.com/api'); platform._http = http
    with pytest.raises(PlatformError, match='安全关机'):
        platform.submit_package('fixture', 'fixture-token', str(pkg), 'old', {'resume_attempt_id': '17'})
    assert not posts


def test_repaired_experiment_leaves_second_total_attempt_for_same_package_harvest(monkeypatch):
    from cyberscientist import auto_harvest, config
    settings=config.load_settings();settings['features']['auto_harvest']=True;config.save_settings(settings)
    from test_mailboxes import _set_scored
    rid, original, platform = seed(monkeypatch, limit=2)
    mailboxes.add_harvest('fixture-harvest@example.com', 'fixture-harvest-secret')
    repaired = mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')
    _set_scored(repaired['id'], 100)
    db.execute("UPDATE runs SET phase='running' WHERE id=?", (rid,))
    auto_harvest.advance_sync()
    harvested = db.query_one('SELECT * FROM submissions WHERE is_harvest=1')
    assert harvested['source_submission_id'] == original['id']
    assert harvested['package_sha256'] == repaired['package_sha256']
    assert db.query_one('SELECT COUNT(*) FROM submissions WHERE run_id=?', (rid,))[0] == 2
    assert platform.calls == 3  # create, continue that draft, create for harvest


def test_new_late_old_topic_submission_keeps_own_seven_day_poll_window(monkeypatch):
    rid, original, platform = seed(monkeypatch)
    previous_stop = db.utcnow()
    db.execute('UPDATE submissions SET polling_stopped_at=? WHERE id=?', (previous_stop, original['id']))
    repaired = mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')
    assert not repaired['polling_stopped_at']
    evidence = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='submission.draft_continuation_requested'", (rid,))
    assert json.loads(evidence[0])['previous_polling_stopped_at'] == previous_stop
    past = datetime.now(timezone.utc) - timedelta(days=30)
    db.execute('UPDATE challenges SET platform_snapshot_json=? WHERE id=?',
               (json.dumps({'round': {'roundEndAt': past.isoformat()}}), 'MB_CH'))
    calls = []
    platform.fetch_score = lambda *args: calls.append(1) or 85.0
    mailboxes.poll_scores(rid)
    assert calls == [1]
    row = db.query_one('SELECT * FROM submissions WHERE id=?', (original['id'],))
    assert not row['polling_stopped_at'] and row['score'] == 85


def test_expired_old_poll_snapshot_cannot_stop_repaired_package_polling(monkeypatch):
    rid, original, platform = seed(monkeypatch)
    expired = datetime.now(timezone.utc) - timedelta(days=30)
    db.execute('UPDATE submissions SET submitted_at=? WHERE id=?', (expired.isoformat(), original['id']))
    deadline = mailboxes._poll_deadline
    def raced_deadline(row):
        result = deadline(row)
        mailboxes.submit_experiment(rid, 'trial_mb1', None, 'repair')
        return result
    monkeypatch.setattr(mailboxes, '_poll_deadline', raced_deadline)
    mailboxes.poll_scores(rid)
    current = db.query_one('SELECT * FROM submissions WHERE id=?', (original['id'],))
    assert current['package_sha256'] != original['package_sha256']
    assert not current['polling_stopped_at']
