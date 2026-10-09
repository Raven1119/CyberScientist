"""Receipt-backed starting environments, with per-Run choices and smoke evidence.

Catalog maintenance is a backend administrative action. Research tools can select
and restore a starting point, but cannot publish another environment version.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import config, db, observation

LEGACY_IDS = {
    'cs10-private-python-v1':'python-minimal-private-v1',
    'cs10-public-python-v1':'python-3-10-public-v1',
    'cs12-lean-mathlib-v1':'lean-mathlib-v1',
    'cs12-pyscf-v1':'pyscf-v1',
    'cs12-sci-py-v1':'sci-python-v1',
    'cs12-torch-cpu-v1':'pytorch-cpu-v1',
    'cs12-torch-cuda-v1':'pytorch-cuda-v1',
    'cs13-abacus-v1':'abacus-plane-wave-v1',
    'cs13-abacus-v2':'abacus-plane-wave-v2',
    'cs13-materials-v1':'materials-python-v1',
}


def migrate_legacy_ids(conn):
    """Administrative migration; immutable old descriptors and receipts stay."""
    for alias,canonical in LEGACY_IDS.items():
        old=conn.execute('SELECT * FROM environment_catalog_entries WHERE id=?',(alias,)).fetchone()
        if old is None:continue
        descriptor=json.loads(old['descriptor_json']);descriptor['id']=canonical
        raw=json.dumps(descriptor,ensure_ascii=False,sort_keys=True)
        digest=hashlib.sha256(raw.encode()).hexdigest()
        existing=conn.execute('SELECT sha256 FROM environment_catalog_entries WHERE id=?',(canonical,)).fetchone()
        if existing and existing['sha256']!=digest:
            raise ValueError('环境目录新标识已被不同内容占用：'+canonical)
        prior_alias=conn.execute('SELECT entry_id FROM environment_catalog_aliases WHERE alias=?',(alias,)).fetchone()
        if prior_alias and prior_alias['entry_id']!=canonical:
            raise ValueError('环境目录旧标识已指向不同起点：'+alias)
        conn.execute('INSERT OR IGNORE INTO environment_catalog_entries VALUES(?,?,?,?)',
            (canonical,raw,digest,db.utcnow()))
        conn.execute('INSERT OR IGNORE INTO environment_catalog_aliases VALUES(?,?,?)',
            (alias,canonical,db.utcnow()))


def enabled() -> bool:
    value = config.load_settings().get('features', {}).get('environment_catalog', True)
    if type(value) is not bool:
        raise ValueError('环境目录开关必须是布尔值')
    return value


def register_verified(entry: dict, receipts: list[dict]) -> dict:
    """Called only after backend verification of native smoke/output receipts."""
    required = {'id', 'topic_types', 'type', 'image', 'restore_command', 'contents',
                'smoke_command', 'reproduction_md', 'known_issues'}
    if not isinstance(entry, dict) or set(entry) != required:
        raise ValueError('环境目录字段不完整')
    if (not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', entry['id'])
            or entry['type'] not in ('public_image', 'private_image', 'environment_bundle')
            or not isinstance(entry['contents'], dict) or not entry['contents']
            or not isinstance(entry['topic_types'], list)
            or not isinstance(entry['known_issues'], list)
            or not entry['smoke_command'] or not entry['reproduction_md']
            or not (entry['image'] if entry['type'] != 'environment_bundle' else entry['restore_command'])):
        raise ValueError('环境目录标识、起点或复现信息不符')
    if not receipts or any(
            item.get('status') != 'verified' or item.get('exit_code') != 0
            or item.get('channel') not in ('job', 'sandbox')
            or not item.get('source') or not item.get('observed_at')
            or type(item.get('elapsed_seconds')) not in (float, int) or item['elapsed_seconds'] < 0
            or any(not re.fullmatch('[a-f0-9]{64}', item.get(key, '')) for key in ('receipt_sha256', 'output_sha256'))
            for item in receipts):
        raise ValueError('配方不是冒烟证据；需要核实命令、退出码、输出哈希和实测耗时')
    data = entry | {'status': 'verified', 'receipts': receipts,
                    'last_verified_at': max(item['observed_at'] for item in receipts),
                    'restore_seconds': {item['channel']: item['elapsed_seconds'] for item in receipts}}
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if observation.strip_secrets(raw) != raw:
        raise ValueError('环境目录不得含密钥')
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with db.transaction() as conn:
        prior = conn.execute('SELECT sha256 FROM environment_catalog_entries WHERE id=?', (entry['id'],)).fetchone()
        if prior and prior['sha256'] != digest:
            raise ValueError('目录起点不可覆盖；维护时使用新标识，Run不能保存新版本')
        conn.execute('INSERT OR IGNORE INTO environment_catalog_entries VALUES(?,?,?,?)',
                     (entry['id'], raw, digest, db.utcnow()))
        migrate_legacy_ids(conn)
    return get(entry['id'])


def items() -> list[dict]:
    return [json.loads(row['descriptor_json']) | {'sha256': row['sha256']}
            for row in db.query('SELECT * FROM environment_catalog_entries e WHERE NOT EXISTS '
                '(SELECT 1 FROM environment_catalog_aliases a WHERE a.alias=e.id) ORDER BY id')]


def get(entry_id: str) -> dict:
    alias=db.query_one('SELECT entry_id FROM environment_catalog_aliases WHERE alias=?',(entry_id,))
    if alias:entry_id=alias['entry_id']
    entry = next((item for item in items() if item['id'] == entry_id), None)
    if not entry:
        raise ValueError('环境目录起点不存在：' + str(entry_id))
    return entry


def current(run_id: str) -> dict:
    row = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='environment.choice' ORDER BY seq DESC LIMIT 1", (run_id,))
    return json.loads(row['payload']) if row else {'mode': 'unknown', 'reason_md': 'PI尚未明确选择起点或从零开始'}


def choose(run_id: str, choice: dict, *, source: str = 'brain') -> dict:
    if (not isinstance(choice, dict) or set(choice) - {'mode', 'entry_id', 'reason_md'}
            or choice.get('mode') not in ('catalog', 'from_zero')
            or not isinstance(choice.get('reason_md'), str) or not choice['reason_md'].strip()
            or len(choice['reason_md']) > 2000):
        raise ValueError('environment_choice需要mode、reason_md；catalog还需要entry_id')
    safe = json.loads(observation.strip_secrets(json.dumps(choice, ensure_ascii=False)))
    if safe['mode'] == 'catalog':
        entry = get(safe.get('entry_id'))
        safe['entry_id']=entry['id']
        safe['catalog_sha256'] = entry['sha256']
    elif safe.get('entry_id'):
        raise ValueError('from_zero不能同时指定目录条目')
    if current(run_id) != safe:
        db.append_event(run_id, source, 'environment.choice', safe)
    return safe


def prepare(run_id: str, entry_id: str | None = None, reason_md: str = '') -> dict:
    if entry_id is not None:
        choose(run_id, {'mode': 'catalog', 'entry_id': entry_id, 'reason_md': reason_md}, source='prime')
    choice = current(run_id)
    if choice['mode'] == 'unknown':
        raise ValueError('PI尚未明确选择环境目录起点或from_zero；请先补研究简报')
    entry = get(choice['entry_id']) if choice['mode'] == 'catalog' else None
    plan = {'choice': choice, 'entry': entry, 'status': 'planned', 'not_executed': True,
            'execution_command': execution_command(entry) if entry else None,
            'instructions': '先恢复所选起点并运行smoke_command；安装依赖或换基础镜像均可。失败则换条目或从零搭建，不保存环境新版本。'}
    db.append_event(run_id, 'controller', 'environment.restore_plan', plan)
    return plan


def execution_command(entry: dict) -> str:
    return (entry['restore_command'] + ' && ' if entry['type'] == 'environment_bundle' else '') + entry['smoke_command']


def observe_smoke(run_id: str, operation_id: str) -> dict:
    """Read backend-tracked sandbox command evidence; never accept an agent boolean."""
    row = db.query_one('SELECT * FROM compute_sandbox_operations WHERE operation_id=? AND run_id=?', (operation_id, run_id))
    if not row:
        raise ValueError('冒烟操作不属于本Run')
    box = db.query_one('SELECT * FROM compute_sandboxes WHERE sandbox_id=? AND run_id=?', (row['sandbox_id'], run_id))
    started = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='sandbox.exec_started' AND json_extract(payload,'$.operation_id')=?", (run_id, operation_id))
    command = json.loads(started['payload']).get('command') if started else None
    raw = row['receipt_json'] or '{}'
    from . import sandboxes
    receipt = json.loads(raw); body = sandboxes._body(receipt); data = sandboxes._data(body) or {}
    choice = current(run_id)
    if choice['mode'] != 'catalog':
        raise ValueError('需要先选择目录起点')
    entry = get(choice['entry_id'])
    if (row['action'] != 'exec' or row['status'] not in ('completed', 'failed', 'unknown')
            or not box or not isinstance(command, str) or command != execution_command(entry)
            or (json.loads(box['request_json']).get('image') or None) != (entry['image'] or None)
            or row['command_sha256'] != hashlib.sha256(command.encode()).hexdigest()
            or row['receipt_sha256'] != hashlib.sha256(raw.encode()).hexdigest()
            or receipt.get('truncated')):
        raise ValueError('冒烟回执身份、命令、镜像或哈希未核实')
    passed = (row['status'] == 'completed' and receipt.get('ok') is True
              and isinstance(body, dict) and body.get('ok') is not False and not data.get('error')
              and type(data.get('exit_code')) is int and data['exit_code'] == 0)
    status = 'passed' if passed else 'failed' if row['status'] == 'failed' else 'unknown'
    payload = {'entry_id': entry['id'], 'operation_id': operation_id,
               'catalog_sha256': entry['sha256'], 'receipt_sha256': row['receipt_sha256'],
               'status': status,
               'exit_code': data.get('exit_code'), 'stdout': data.get('stdout', ''),
               'stderr': data.get('stderr', '')}
    payload = json.loads(observation.strip_secrets(json.dumps(payload, ensure_ascii=False)))
    db.append_event(run_id, 'controller', 'environment.smoke_result', payload, trial_id=box['trial_id'])
    return payload


def executor_instructions(run_id: str) -> str:
    if not enabled(): return ''
    return '\n环境目录起点：' + json.dumps(current(run_id), ensure_ascii=False) + '\n第一步调用research_environment(action="restore")获得恢复计划，再用已授权计算工具实际恢复并冒烟；失败可换条目或从零搭建。运行中禁止保存新环境版本。\n'
