"""The built-in Demo adapter must obey the same close contract as real adapters."""
import asyncio

import pytest

from cyberscientist.prime import DemoPrime


async def test_completed_demo_keeps_its_events_then_closes_cleanly():
    prime = DemoPrime()
    sid = await prime.start({})
    events = prime.events(sid)
    await prime.prompt(sid, "offline lifecycle acceptance")

    async def completed():
        seen = []
        async for event in events:
            seen.append(event["type"])
            if event["type"] == "trial.completed":
                return seen

    seen = await asyncio.wait_for(completed(), timeout=5)
    assert seen == ["trial.started", "execution.progress",
                    "checkpoint.created", "trial.completed"]
    await prime.close(sid)
    await prime.close(sid)
    with pytest.raises(StopAsyncIteration):
        await anext(events)
    assert not prime._queues and not prime._scripts


async def test_early_close_cancels_scripts_and_finishes_a_pending_event_read():
    prime = DemoPrime()
    sid = await prime.start({})
    events = prime.events(sid)
    await prime.prompt(sid, "stop before the delayed progress event")
    assert (await anext(events))["type"] == "trial.started"
    scripts = tuple(prime._scripts[sid])
    await prime.steer(sid, "pending guidance must be released")
    waiting = asyncio.create_task(anext(events))
    await asyncio.sleep(0)

    await prime.close(sid)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(waiting, timeout=1)
    assert all(task.done() and task.cancelled() for task in scripts)
    assert not prime._queues and not prime._scripts and not prime._steer_pending
    await prime.close(sid)
    with pytest.raises(ValueError, match="已关闭"):
        await prime.prompt(sid, "must not resurrect the session")
    with pytest.raises(StopAsyncIteration):
        await anext(prime.events(sid))


async def test_close_is_idempotent_and_does_not_close_another_session():
    prime = DemoPrime()
    first = await prime.start({})
    second = await prime.start({})
    await prime.prompt(first, "first")
    await asyncio.gather(prime.close(first), prime.close(first))
    await prime.close("missing-session")
    receipt = await prime.prompt(second, "second remains usable")
    assert receipt.status == "accepted"
    events = prime.events(second)
    assert (await anext(events))["type"] == "trial.started"
    await prime.close(second)
    with pytest.raises(StopAsyncIteration):
        await anext(events)
