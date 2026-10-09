"""Synthetic native inputs prove early alerts without reading credential files."""
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cyberscientist import alerts, config, credential_watch, db
from cyberscientist.prime.codex_exec import CodexExecutor, _Session
from test_codex_runtime import FakeRpc
from test_sandboxes import run


@pytest.mark.parametrize('item', [
    {'type': 'commandExecution', 'command': 'cat .runtime/codex/auth.json'},
    {'type': 'commandExecution', 'command': 'python3 -c "open(\"$CODEX_HOME/auth.json\").read()"'},
    {'type': 'mcpToolCall', 'tool': 'read_file', 'arguments': {'path': '.cyberscientist/secrets.json'}},
    {'type': 'dynamicToolCall', 'tool': 'exec', 'arguments': {'code': 'await tools.exec_command({cmd:"cat .env"})'}},
])
def test_explicit_native_read_inputs_are_detected_without_opening_credentials(monkeypatch, tmp_path, item):
    root = tmp_path / 'CyberScientist-comp'
    monkeypatch.setattr(config, 'WORKSPACE_ROOT', root)
    # Any content read would fail this test; only inputs may be inspected.
    monkeypatch.setattr(Path, 'read_text', lambda *a, **k: (_ for _ in ()).throw(AssertionError('No credential reads')))
    assert credential_watch.referenced_paths(item, cwd=str(root), home=str(root / '.runtime/home'),
        codex_home=str(root / '.runtime/codex'))


@pytest.mark.parametrize('item', [
    {'type': 'agentMessage', 'text': 'cat .env'},
    {'type': 'commandExecution', 'command': 'pwd', 'aggregatedOutput': 'cat .env'},
    {'type': 'commandExecution', 'command': 'cat .env.example'},
    {'type': 'commandExecution', 'command': 'ls -l .env'},
    {'type': 'commandExecution', 'command': 'cat outputs/report.md'},
])
def test_assistant_output_metadata_and_unrelated_files_do_not_alert(tmp_path, monkeypatch, item):
    monkeypatch.setattr(config, 'WORKSPACE_ROOT', tmp_path / 'CyberScientist-comp')
    assert not credential_watch.referenced_paths(item, cwd=str(config.WORKSPACE_ROOT))


@pytest.mark.parametrize('relative', ['.codex/auth.json', '.playground/config.json',
    '.config/playground/agents/test.env', '.config/playground/credentials.env',
    '.bohr/config.json', '.config/bohrium/config.json'])
def test_global_home_aliases_and_credential_directories_are_watched(tmp_path, monkeypatch, relative):
    home = tmp_path / 'global-home'
    monkeypatch.setattr(credential_watch.pwd, 'getpwuid', lambda _: SimpleNamespace(pw_dir=str(home)))
    item = {'type': 'commandExecution', 'command': 'cat ~/' + relative}
    paths = credential_watch.referenced_paths(item, home=str(home), cwd=str(tmp_path))
    assert paths and all(path.startswith(str(home) + '/') for path in paths)


@pytest.mark.parametrize('kind', ['native_cwd', 'direct_workdir', 'code_mode_workdir', 'code_mode_read_file', 'shell_cd'])
def test_tool_working_directory_overrides_initial_session_for_relative_reads(tmp_path, monkeypatch, kind):
    root = tmp_path/'CyberScientist-comp'
    monkeypatch.setattr(config,'WORKSPACE_ROOT',root)
    session = root/'workspace/runs/synthetic/trials/synthetic'
    if kind == 'native_cwd':
        item = {'type':'commandExecution','cwd':str(root),'command':'cat .env'}
    elif kind == 'direct_workdir':
        item = {'type':'dynamicToolCall','tool':'exec_command',
            'arguments':{'workdir':str(root),'cmd':'cat .env'}}
    elif kind == 'code_mode_workdir':
        item = {'type':'dynamicToolCall','tool':'exec',
            'arguments':{'code':f'await tools.exec_command({{workdir:"{root}",cmd:"cat .env"}})'}}
    elif kind == 'code_mode_read_file':
        item = {'type':'dynamicToolCall','tool':'exec',
            'arguments':{'code':f'await tools.mcp__filesystem__read_file({{path:"{root}/.env"}})'}}
    else:
        item = {'type':'commandExecution','command':f'cd "{root}" && cat .env'}
    assert credential_watch.referenced_paths(item,cwd=str(session)) == [str(root/'.env')]


async def test_started_native_call_alerts_before_result_and_preserves_original_log(run, tmp_path, monkeypatch):
    controller, rid, _, _, _ = run
    root = tmp_path / 'CyberScientist-comp'
    monkeypatch.setattr(config, 'WORKSPACE_ROOT', root)
    rpc = FakeRpc()
    session = _Session(rpc=rpc, thread_id='synthetic-native-session', cwd=str(root))
    executor = CodexExecutor('/bin/true')
    task = asyncio.create_task(executor._pump(session))
    frame = {'method': 'item/started', 'params': {'threadId': session.thread_id, 'turnId': 'synthetic-turn',
        'item': {'type': 'commandExecution', 'id': 'read-credentials',
                 'command': 'cat .env', 'status': 'inProgress'}}}
    native = tmp_path / 'native.jsonl'
    native.write_text(json.dumps(frame) + '\n')
    digest = hashlib.sha256(native.read_bytes()).hexdigest()
    try:
        await rpc.messages.put(frame)
        event = await asyncio.wait_for(session.queue.get(), 1)
        assert event['type'] == 'credentials_touched' and 'output' not in event
        assert not any(key in event for key in ('command', 'arguments'))
        for _ in range(2):
            await controller._handle_signal({'type': 'prime_event', 'event': event}, rid, asyncio.Queue())
        alerts.synchronize(); alerts.synchronize()
        rows = db.query("SELECT * FROM events WHERE run_id=? AND type='credentials_touched'", (rid,))
        assert len(rows) == 1
        assert json.loads(rows[0]['payload'])['paths'] == [str(root / '.env')]
        assert len(db.query("SELECT * FROM alerts WHERE run_id=? AND kind='credentials_touched'", (rid,))) == 1
        assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'running'
        assert hashlib.sha256(native.read_bytes()).hexdigest() == digest
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
