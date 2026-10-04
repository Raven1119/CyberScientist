"""One authorized native turn; success requires a completed tool receipt."""
from __future__ import annotations
import asyncio
import json
import uuid
from tempfile import TemporaryDirectory
from . import challenge_models, config, observation, resource_coordinator


async def run(controller, role: str, choice: dict | None = None) -> dict:
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
            session = await brain.open({'working_directory': cwd})
            packet = {'protocol': 'role_task', 'task': 'native_tool_probe',
                      'instructions': '必须实际用 shell 工具读取当前目录 probe.txt，只读此文件。不要打印环境变量。'
                                      '把读取的全文作为 probe_token。不要计算或调用其他 API。',
                      'output_contract': {'probe_token': 'string'}}
            receipt = result = usage = None
            async with asyncio.timeout(300):
                async for event in brain.review(session, packet):
                    if event.type == 'progress' and event.payload.get('exit_code') == 0 and nonce in event.payload.get('output', ''):
                        receipt = {k: event.payload.get(k) for k in ('item_id', 'status', 'exit_code')}
                    elif event.type == 'task_result':
                        result = event.payload.get('result')
                    elif event.type == 'usage':
                        usage = event.payload
                    elif event.type == 'error':
                        raise ValueError(observation.strip_secrets(str(event.payload.get('message', '原生探针失败'))))
            return {'status': 'ok' if receipt and result and result.get('probe_token') == nonce else 'unknown',
                    'role': role, 'model_choice': selected, 'tool_receipt': receipt,
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
