"""One authorized native turn; success requires a completed tool receipt."""
from __future__ import annotations
import asyncio
import json
import uuid
import hashlib
import shlex
from tempfile import TemporaryDirectory
from . import challenge_models, config, observation, resource_coordinator


def _skill_read(payload: dict, path, content: str) -> dict | None:
    """Bind a completed native cat receipt to the frozen skill, not a title echo."""
    command = payload.get('command') or ''
    try:
        tokens = shlex.split(command) if isinstance(command, str) else command
        if tokens and tokens[0].split('/')[-1] in ('bash', 'sh') and '-lc' in tokens:
            tokens = shlex.split(tokens[tokens.index('-lc') + 1])
        if tokens != ['cat', str(path)] or payload.get('output', '').strip() != content.strip():
            return None
    except (ValueError, TypeError, IndexError):
        return None
    return {k: payload.get(k) for k in ('item_id', 'status', 'exit_code')} | {
        'path': str(path), 'sha256': hashlib.sha256(content.encode()).hexdigest()}


async def run(controller, role: str, choice: dict | None = None, *, connectivity: bool = False) -> dict:
    settings = config.load_settings()
    selected = challenge_models.choose(role, choice, settings)
    original = dict(settings[role])
    if selected['runtime'] == 'prime':
        raise ValueError('Prime 真实工具探针尚未核实；没有发起模型调用')
    if original.get('runtime') != selected['runtime']:
        original['executable'] = ''
    settings['brain'] = {**original, **selected}
    if not settings['brain'].get('executable') and settings['brain']['runtime'] == settings['executor']['runtime']:
        settings['brain']['executable'] = settings['executor'].get('executable') or ''
    settings['app']['mode'] = 'connected'
    owner = 'probe-' + uuid.uuid4().hex
    brain = controller._make_brain(settings)
    session = None
    resource_coordinator.reserve_auxiliary(owner, settings)
    try:
        with TemporaryDirectory(prefix='tool-probe-', dir=config.DATA_DIR) as cwd:
            from pathlib import Path
            nonce = uuid.uuid4().hex
            Path(cwd, 'probe.txt').write_text(nonce)
            spec = {'working_directory': cwd}
            receipt_file = Path(cwd, 'public_receipts.json')
            skill_path = config.WORKSPACE_ROOT / 'skills/bohrium-lkm/SKILL.md'
            skill_content = skill_path.read_text() if connectivity else ''
            if connectivity:
                import sys
                variables = {'CS_PUBLIC_RESEARCH_PROBE': nonce, 'CS_PUBLIC_PROBE_RECEIPTS': str(receipt_file)}
                spec.update(env=variables, mcp_servers=[{'name': 'cyberscientist', 'command': sys.executable,
                    'args': ['-m', 'cyberscientist.mcp_bridge'], 'env': variables}])
            session = await brain.open(spec)
            packet = {'protocol': 'role_task', 'task': 'native_tool_probe',
                      'instructions': '必须实际用 shell 工具读取当前目录 probe.txt，只读此文件。不要打印环境变量。'
                                      '把读取的全文作为 probe_token。不要计算或调用其他 API。',
                      'output_contract': {'probe_token': 'string'}}
            if connectivity:
                packet['instructions'] = ('这是零科研连接探针。实际用shell读取probe.txt作为probe_token，不打印环境。'
                    f"唯一其它可读本地文件是LKM技能；必须用完整命令cat {skill_path}读取全文，按该技能使用后端受限工具。"
                    '然后分别调用一次research_web_search(query="Python JSON documentation")、'
                    'research_web_read(url="https://docs.python.org/3/library/json.html")、'
                    'research_lkm(query="scientific knowledge graph retrieval")。研究资料只用于检查接口是否可用，不解科研题、不计算或提交。'
                    '三个工具的回执保持unknown或received原状，返回probe_token和各工具状态。')
                packet['output_contract'] = {'probe_token': 'string', 'tools': 'object'}
            receipt = result = usage = skill_receipt = None
            async with asyncio.timeout(300):
                async for event in brain.review(session, packet):
                    if event.type == 'progress' and event.payload.get('exit_code') == 0:
                        if nonce in event.payload.get('output', ''):
                            receipt = {k: event.payload.get(k) for k in ('item_id', 'status', 'exit_code')}
                        if connectivity:
                            skill_receipt = _skill_read(event.payload, skill_path, skill_content) or skill_receipt
                    elif event.type == 'task_result':
                        result = event.payload.get('result')
                    elif event.type == 'usage':
                        usage = event.payload
                    elif event.type == 'error':
                        raise ValueError(observation.strip_secrets(str(event.payload.get('message', '原生探针失败'))))
            public = json.loads(receipt_file.read_text()) if connectivity and receipt_file.exists() else {}
            public_ok = not connectivity or skill_receipt and all(public.get(name, {}).get('result', {}).get('status') == 'received'
                for name in ('research_web_search', 'research_web_read', 'research_lkm'))
            return {'status': 'ok' if receipt and result and result.get('probe_token') == nonce and public_ok else 'unknown',
                    'role': role, 'model_choice': selected, 'tool_receipt': receipt,
                    'observed_native_model': {key: session.raw.get(key) for key in ('model', 'provider', 'reasoning_effort')},
                    'public_read_receipts': public,
                    'skill_receipt': skill_receipt,
                    'usage': usage, 'model_turn_sent': True,
                    'detail': '只有原生已完成工具回执与读取结果一致才通过；未核实账单'}
    except Exception as exc:
        from .model_providers import record_throttle
        record_throttle(settings['brain'], exc)
        raise
    finally:
        try:
            if session:
                try:
                    await brain.close(session)
                except Exception as exc:
                    resource_coordinator.close_failed(owner, exc)
                    raise
        finally:
            resource_coordinator.release_sessions(owner)
