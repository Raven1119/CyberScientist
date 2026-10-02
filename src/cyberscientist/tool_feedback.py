"""Procedural failure facts; a failure never grants or replays an operation."""
from __future__ import annotations

from . import config, db
from .bohr_proxy import redact_value
from .observation import strip_secrets


def failure(tool: str, cause, *, code: str = 'TOOL_FAILED',
            remote_effect: str = 'unknown', operation_id=None) -> dict:
    safe_cause = redact_value(cause, list(config.load_secrets().values()))
    def strip(value):
        if isinstance(value, str):
            return strip_secrets(value)[:12000]
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items()}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value
    safe_cause = strip(safe_cause)
    return redact_value({
        'tool': tool, 'code': code, 'cause': safe_cause,
        'possible_remote_effect': remote_effect, 'operation_id': operation_id,
        'automatic_resend': False,
        'choices': ['查看原操作的回执与只读状态；unknown 不代表未执行',
                    '检查并自行修复输入或环境；在原授权内明确选择下一操作',
                    '使用其他已授权通道，或报告具体阻塞与检查点'],
        'authority': '沿用原 Run、Trial 和授权；此反馈不新增权限或额度'},
        list(config.load_secrets().values()))


def attach(run_id: str, tool: str, result: dict) -> dict:
    if (result.get('ok') is not False and result.get('status') not in
            ('unknown', 'not_started', 'failed') and not result.get('error')):
        return result
    receipt = result.get('receipt') or result
    effect = 'not_started' if receipt.get('not_started') or result.get('status') == 'not_started' else 'unknown'
    facts = failure(tool, receipt, remote_effect=effect,
                    operation_id=result.get('operation_id'))
    db.append_event(run_id, 'controller', 'tool.failure_returned', facts)
    return result | {'failure_feedback': facts}
