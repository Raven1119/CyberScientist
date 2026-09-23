"""Synthetic Codex protocol regressions; not evidence of a model round trip."""
import asyncio
import json
import os

import pytest

from cyberscientist.brains.codex import CodexBrain
from cyberscientist.codex_protocol import process_environment, thread_params, verify_thread_config
from cyberscientist.prime.codex_exec import CodexExecutor, _Session


class FakeRpc:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.messages = asyncio.Queue()
        self.requests = asyncio.Queue()
        self.initialized = False
        self.stopped = False

    async def start(self):
        pass

    async def stop(self):
        self.stopped = True

    async def notify(self, method, params=None):
        assert method == 'initialized'
        self.initialized = True

    async def request(self, method, params=None, **kwargs):
        self.calls.append((method, params))
        if method == 'initialize':
            return {}
        assert self.initialized
        if method == 'thread/start':
            assert params['sandbox'] in ('read-only', 'workspace-write')
            assert 'effort' not in params and 'sandboxPolicy' not in params
            return {'thread': {'id': 'thread-1'}, 'model': params['model'],
                    'reasoningEffort': params['config']['model_reasoning_effort']}
        if method == 'turn/start':
            assert params['effort'] in ('xhigh', 'medium')
            await self.requests.put({'id': 777, 'method': 'item/commandExecution/requestApproval'})
            return {'turn': {'id': 'turn-1'}}
        return {}

    async def respond(self, req_id, result=None, error=None):
        # The turn cannot finish until the adapter handles its approval request.
        assert req_id == 777
        assert result == {'decision': 'decline'}
        for method, item in [
            ('item/started', {'type': 'commandExecution', 'id': 'cmd-1', 'command': 'pwd', 'status': 'inProgress'}),
            ('item/completed', {'type': 'commandExecution', 'id': 'cmd-1', 'command': 'pwd', 'status': 'completed', 'exitCode': 0, 'aggregatedOutput': '/research'}),
            ('item/completed', {'type': 'reasoning', 'summary': ['PRIVATE_REASONING_FIXTURE']}),
            ('item/completed', {'type': 'agentMessage', 'id': 'msg-progress', 'phase': 'commentary', 'text': 'Reading public evidence.'}),
        ]:
            await self.messages.put({'method': method, 'params': {'threadId': 'thread-1', 'item': item}})
        await self.messages.put({'method': 'item/completed', 'params': {
            'threadId': 'thread-1', 'item': {'type': 'agentMessage',
            'text': json.dumps({'schema_version': 1, 'actions': [{'op': 'wait', 'reason': 'probe'}]})}}})
        await self.messages.put({'method': 'turn/completed', 'params': {
            'threadId': 'thread-1', 'turn': {'id': 'turn-1', 'status': 'completed'}}})

    async def notifications(self):
        while True:
            yield await self.messages.get()

    async def server_requests(self):
        while True:
            yield await self.requests.get()


async def test_brain_native_fields_and_concurrent_approval(monkeypatch, tmp_path):
    monkeypatch.setattr('cyberscientist.brains.codex.JsonRpcStdio', FakeRpc)
    brain = CodexBrain('/bin/true', 'gpt-6-astra', 'xhigh')
    session = await brain.open({'working_directory': str(tmp_path), 'instructions': 'test'})
    try:
        async def collect():
            return [e async for e in brain.review(session, {'run_id': 'run-1'})]
        events = await asyncio.wait_for(collect(), 1)
        assert any(e.type == 'decision' for e in events)
        assert any(e.type == 'approval_request' for e in events)
        progress = [e.payload for e in events if e.type == 'progress']
        assert any(p.get('exit_code') == 0 and p.get('output') == '/research' for p in progress)
        assert any(p['detail'] == 'Reading public evidence.' for p in progress)
        assert 'PRIVATE_REASONING_FIXTURE' not in repr(events)
        params = next(p for m, p in brain.rpc.calls if m == 'thread/start')
        assert params['developerInstructions'] == 'test'
        assert params['sandbox'] == 'read-only'
    finally:
        await brain.close(session)


def test_no_silent_model_or_effort_downgrade():
    with pytest.raises(RuntimeError, match='模型'):
        verify_thread_config({'model': 'other'}, 'gpt-6-astra', 'xhigh')
    with pytest.raises(RuntimeError, match='思考强度'):
        verify_thread_config({'model': 'gpt-6-astra', 'reasoningEffort': 'medium'},
                             'gpt-6-astra', 'xhigh')


def test_mcp_capability_only_in_environment():
    spec = {'env': {'PATH': '/bin', 'BOHR_ACCESS_KEY': 'bohr-test-secret'},
            'network_access': True,
            'writable_roots': ['/research/run-1/trials'],
            'mcp_servers': [{'name': 'cyberscientist', 'command': '/bin/python',
                             'args': ['-m', 'cyberscientist.mcp_bridge'],
                             'env': [{'name': 'CS_TOOL_TOKEN', 'value': 'test-secret'}]}]}
    params = thread_params(spec, 'gpt-6-astra', 'medium', writable=True)
    cfg = params['config']
    assert 'test-secret' not in json.dumps(params)
    assert cfg['mcp_servers']['cyberscientist']['env_vars'] == ['CS_TOOL_TOKEN']
    assert 'CS_TOOL_TOKEN' not in cfg['shell_environment_policy.include_only']
    assert cfg['sandbox_workspace_write.network_access'] is True
    assert cfg['sandbox_workspace_write.writable_roots'] == ['/research/run-1/trials']
    assert cfg['features.apps'] is False
    assert cfg['features.memories'] is False
    assert cfg['memories.use_memories'] is False
    assert cfg['memories.generate_memories'] is False
    bridge = cfg['mcp_servers']['cyberscientist']
    assert bridge['enabled_tools'] == ['research_checkpoint', 'ack_guidance', 'research_job']
    assert bridge['tools'] == {name: {'approval_mode': 'approve'}
                               for name in ('research_checkpoint', 'ack_guidance', 'research_job')}
    assert 'default_tools_approval_mode' not in bridge
    assert process_environment(spec)['CS_TOOL_TOKEN'] == 'test-secret'
    assert 'CS_TOOL_TOKEN' not in spec['env']


def test_other_mcp_server_does_not_inherit_bridge_approval():
    params = thread_params({'mcp_servers': [{'name': 'other', 'command': '/bin/true'}]},
                           'gpt-6-astra', 'medium', writable=True)
    assert params['approvalPolicy'] == 'never'
    assert params['sandbox'] == 'workspace-write'
    assert 'tools' not in params['config']['mcp_servers']['other']
    assert 'default_tools_approval_mode' not in params['config']['mcp_servers']['other']


async def test_executor_turn_is_not_trial_delivery(monkeypatch, tmp_path):
    monkeypatch.setattr('cyberscientist.prime.codex_exec.JsonRpcStdio', FakeRpc)
    exe = CodexExecutor('/bin/true', 'gpt-6-astra', 'medium')
    sid = await exe.start({'working_directory': str(tmp_path)})
    try:
        assert (await exe.prompt(sid, 'probe')).status == 'accepted'
        async def collect():
            out = []
            while True:
                event = await exe._sessions[sid].queue.get()
                out.append(event)
                if event['type'] == 'executor.turn_completed':
                    return out
        events = await asyncio.wait_for(collect(), 1)
        assert not any(e['type'] == 'trial.completed' for e in events)
        assert (await exe.state(sid))['status'] == 'idle'
    finally:
        await exe.close(sid)


async def test_interrupt_and_steer_use_current_turn():
    exe = CodexExecutor('/bin/true', 'gpt-6-astra', 'medium')
    rpc = FakeRpc()
    rpc.initialized = True
    exe._sessions['thread-1'] = _Session(rpc, 'thread-1', turn_id='turn-2', busy=True)
    assert (await exe.abort('thread-1')).status == 'accepted'
    assert rpc.calls[-1] == ('turn/interrupt', {'threadId': 'thread-1', 'turnId': 'turn-2'})
    assert (await exe.steer('thread-1', 'guidance')).status == 'accepted'
    assert rpc.calls[-1][1]['expectedTurnId'] == 'turn-2'
