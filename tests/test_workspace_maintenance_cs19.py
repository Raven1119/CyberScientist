"""Scheduler independence and explicit lifetime observations; no cloud calls."""
import asyncio
import json
import threading
import time

import pytest
from cyberscientist import api, db, preflight, topic_workspace
from test_sandboxes import run


def test_busy_run_lock_does_not_block_maintenance(run):
    _, rid, _, _, _ = run
    held, release = threading.Event(), threading.Event()
    def holder():
        with topic_workspace._locks[rid]:
            held.set(); release.wait(3)
    thread = threading.Thread(target=holder); thread.start()
    try:
        assert held.wait(1)
        started=time.monotonic()
        assert topic_workspace.maintain_due() == []
        assert time.monotonic()-started < 1
    finally:
        release.set(); thread.join(2)


async def test_submission_scheduler_advances_while_workspace_call_waits(monkeypatch):
    from cyberscientist import mailboxes, compute, submission_gate, power
    entered, release = threading.Event(), threading.Event()
    advanced=asyncio.Event()
    def workspace():
        entered.set(); release.wait(3)
    monkeypatch.setattr(topic_workspace, 'maintain_due', workspace)
    monkeypatch.setattr(compute, 'recover_pending', lambda: None)
    monkeypatch.setattr(mailboxes, 'poll_pending_by_challenge', lambda: {'changed_run_ids': []})
    async def recover(controller):return []
    monkeypatch.setattr(power, 'recover', recover)
    monkeypatch.setattr(submission_gate, 'advance_sync', lambda: advanced.set())
    async def submit(function):return function()
    monkeypatch.setattr(mailboxes, 'submit_async', submit)
    app=api.create_app()
    try:
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(asyncio.to_thread(entered.wait, 1), 1.5)
            await asyncio.wait_for(advanced.wait(), 1)
            assert not release.is_set()
            release.set()
    finally:
        release.set()


@pytest.mark.parametrize('payload',[None, '{}', '{broken', '{"effective_ceiling_seconds":true}',
                                    '{"effective_ceiling_seconds":0}'])
def test_missing_invalid_lifetime_fails_check_and_creates_frontend_alert(monkeypatch, payload):
    from cyberscientist import runtime_layout
    monkeypatch.setattr(runtime_layout, 'version', lambda: {'commit':'fixture'})
    if payload is not None:
        db.execute('INSERT INTO runtime_observations VALUES(?,?,?)',
                   ('sandbox-lifetime-ceiling',payload,db.utcnow()))
    with pytest.raises(ValueError, match='寿命实测记录'):
        topic_workspace.lifetime_ceiling()
    preflight.record_startup_checks()
    assert preflight.cached()['status']=='fail'
    alert=db.query_one("SELECT * FROM alerts WHERE kind='system.sandbox_lifetime_missing'")
    assert alert and alert['acknowledged_at'] is None
    assert '寿命实测记录' in json.loads(alert['payload'])['detail']


def test_real_observation_is_returned_without_hour_fallback():
    db.execute('INSERT INTO runtime_observations VALUES(?,?,?)',
               ('sandbox-lifetime-ceiling',json.dumps({'effective_ceiling_seconds':604800}),db.utcnow()))
    assert topic_workspace.lifetime_ceiling()==604800


def test_codex_code_mode_host_missing_fails_preflight(tmp_path, monkeypatch):
    from cyberscientist import config
    settings=config.load_settings()
    for role in ('brain','executor'):settings[role]['executable']=str(tmp_path/'codex')
    monkeypatch.setattr(config,'load_settings',lambda:settings)
    assert preflight.codex_helpers_check()['status']=='fail'
    host=tmp_path/'codex-code-mode-host';host.write_text('fixture');host.chmod(0o755)
    assert preflight.codex_helpers_check()['status']=='pass'
