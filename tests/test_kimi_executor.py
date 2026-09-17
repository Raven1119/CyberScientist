"""KimiExecutor / 共享看门狗：纯映射与超时语义（不起真实进程）。"""
from __future__ import annotations

import asyncio

import pytest

from cyberscientist.prime import with_stall_watchdog
from cyberscientist.prime.kimi_acp import _EFFORT_MAP, map_update


def test_map_update_tool_call():
    ev = map_update({"sessionUpdate": "tool_call", "title": "Write",
                     "kind": "edit", "status": "pending"})
    assert ev and ev["type"] == "execution.progress" and "Write" in ev["detail"]


def test_map_update_tool_completed_extracts_text():
    ev = map_update({
        "sessionUpdate": "tool_call_update", "status": "completed",
        "title": "Writing a.txt",
        "content": [{"type": "content",
                     "content": {"type": "text", "text": "done"}}]})
    assert ev and "工具完成" in ev["detail"] and "done" in ev["detail"]


def test_map_update_tool_failed():
    ev = map_update({"sessionUpdate": "tool_call_update", "status": "failed",
                     "content": []})
    assert ev and "工具失败" in ev["detail"]


def test_map_update_ignores_chunk_and_meta():
    assert map_update({"sessionUpdate": "agent_message_chunk"}) is None
    assert map_update({"sessionUpdate": "tool_call_update",
                       "status": "in_progress"}) is None
    assert map_update({"sessionUpdate": "config_option_update"}) is None


def test_effort_map_covers_ui_levels():
    assert _EFFORT_MAP["low"] == "low"
    assert _EFFORT_MAP["high"] == "high"
    assert _EFFORT_MAP["xhigh"] == "max"


async def test_watchdog_passthrough():
    async def gen():
        yield {"type": "execution.progress", "detail": "x"}
        yield {"type": "trial.completed", "detail": "y"}

    seen = [ev async for ev in with_stall_watchdog(gen(), 5.0)]
    assert [e["type"] for e in seen] == ["execution.progress", "trial.completed"]


async def test_watchdog_stall():
    async def gen():
        yield {"type": "execution.progress", "detail": "x"}
        await asyncio.sleep(10)

    seen = []
    async for ev in with_stall_watchdog(gen(), 0.2):
        seen.append(ev)
    assert [e["type"] for e in seen] == ["execution.progress", "trial.stalled"]
    assert "挂起" in seen[-1]["detail"]
