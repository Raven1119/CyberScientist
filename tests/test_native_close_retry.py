"""Unconfirmed process shutdown must retain the original native handles."""
import asyncio

import pytest

from cyberscientist.brains.base import SessionRef
from cyberscientist.brains.codex import CodexBrain
from cyberscientist.brains.kimi import KimiBrain
from cyberscientist.jsonrpc_stdio import JsonRpcStdio
from cyberscientist.prime.codex_exec import CodexExecutor, _Session as CodexSession
from cyberscientist.prime.kimi_acp import KimiExecutor, _Session as KimiSession
from cyberscientist.prime.rpc import PrimeJsonlClient, PrimeRpc


class ProcessFixture:
    returncode = None

    def __init__(self, failure):
        self.failure = failure
        self.waits = 0
        self.killed = False
        self.waiting = asyncio.Event()

    def terminate(self):
        pass

    def kill(self):
        self.killed = True

    async def wait(self):
        self.waits += 1
        if self.waits == 1:
            if self.failure == 'error':
                raise RuntimeError('process exit not confirmed')
            if self.failure == 'cancel':
                self.waiting.set()
                await asyncio.Event().wait()
            if self.failure == 'timeout':
                raise asyncio.TimeoutError
        self.returncode = 0
        return 0


@pytest.mark.parametrize('kind', ['codex_executor', 'kimi_executor', 'prime', 'codex_brain', 'kimi_brain'])
@pytest.mark.parametrize('failure', ['error', 'cancel', 'timeout'])
async def test_original_process_and_session_survive_unconfirmed_close(kind, failure):
    process = ProcessFixture(failure)
    rpc = PrimeJsonlClient([]) if kind == 'prime' else JsonRpcStdio([])
    rpc.proc = process
    async def request(*args, **kwargs):
        return {}
    if kind == 'prime':
        runtime = PrimeRpc('fixture')
        runtime._clients['original'] = rpc
        retained = lambda: runtime._clients.get('original') is rpc
        session = 'original'
    elif kind.endswith('_executor'):
        runtime = CodexExecutor('fixture') if kind == 'codex_executor' else KimiExecutor('fixture')
        native = CodexSession(rpc, 'original') if kind == 'codex_executor' else KimiSession(rpc, 'original')
        runtime._sessions['original'] = native
        retained = lambda: runtime._sessions.get('original') is native
        session = 'original'
        rpc.request = request
    else:
        runtime = CodexBrain('fixture') if kind == 'codex_brain' else KimiBrain('fixture')
        runtime.rpc = rpc
        runtime.session_id = 'original'
        retained = lambda: runtime.rpc is rpc
        session = SessionRef('fixture', 'original')
        rpc.request = request
    closing = asyncio.create_task(runtime.close(session))
    if failure == 'cancel':
        await asyncio.wait_for(process.waiting.wait(), 1)
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
    elif failure == 'error':
        with pytest.raises(RuntimeError, match='not confirmed'):
            await closing
    else:
        await closing
    if failure != 'timeout':
        assert retained() and rpc.proc is process and process.returncode is None
        await runtime.close(session)
    assert process.returncode == 0 and process.waits == 2
    assert not retained() and rpc.proc is None
    assert process.killed == (failure == 'timeout')
