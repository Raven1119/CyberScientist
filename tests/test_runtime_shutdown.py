"""Owned async readers and polling tasks must finish before shutdown returns."""
import asyncio

import pytest

from cyberscientist.prime import with_stall_watchdog


@pytest.mark.parametrize("close_after_stall", [False, True])
async def test_watchdog_closes_pending_reader(close_after_stall):
    entered, closed = asyncio.Event(), asyncio.Event()

    async def events():
        try:
            entered.set()
            await asyncio.Event().wait()
            yield {"type": "never"}
        finally:
            closed.set()

    before = asyncio.all_tasks()
    stream = with_stall_watchdog(events(), 0.01 if close_after_stall else 60)
    reader = asyncio.create_task(anext(stream))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if close_after_stall:
            assert (await reader)["type"] == "trial.stalled"
            await stream.aclose()
        else:
            reader.cancel()
            with pytest.raises(asyncio.CancelledError):
                await reader
        assert closed.is_set(), "watchdog leaked its shielded __anext__ task"
    finally:
        # Reap the old implementation's leaked reader so a failing test is isolated.
        remaining = asyncio.all_tasks() - before
        for task in remaining:
            task.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)
        await stream.aclose()


async def test_app_lifespan_awaits_cancelled_poller(monkeypatch):
    from cyberscientist.api import create_app

    entered, closed = asyncio.Event(), asyncio.Event()

    startup_reconciled = False
    async def pending_thread_call(*args, **kwargs):
        nonlocal startup_reconciled
        from cyberscientist import topic_workspace
        if args and args[0] is topic_workspace.maintain_due:
            return []  # Independent workspace worker finishes; poller blocks below.
        if not startup_reconciled:
            startup_reconciled = True
            return {'changed_run_ids': []}
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(asyncio, "to_thread", pending_thread_call)
    app = create_app()
    try:
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(entered.wait(), 1)
        assert closed.is_set(), "lifespan returned before its poller completed cancellation"
    finally:
        await asyncio.sleep(0)


async def test_startup_reconciles_submissions_before_native_auto_recovery(monkeypatch):
    from cyberscientist import api,compute,mailboxes,power
    order=[]
    monkeypatch.setattr(compute,'recover_pending',lambda:order.append('jobs'))
    monkeypatch.setattr(mailboxes,'poll_pending_by_challenge',lambda:order.append('submissions') or {'changed_run_ids':[]})
    async def recover(controller):
        assert order[:2]==['jobs','submissions']
        order.append('native_recovery');return []
    monkeypatch.setattr(power,'recover',recover)
    app=api.create_app()
    async with app.router.lifespan_context(app):
        assert order[:3]==['jobs','submissions','native_recovery']
