"""One persistent sandbox per Run, chosen by the PI, with same-image Job fallback."""
from __future__ import annotations

import json

from . import compute, db, environment_catalog, sandboxes


def enabled(run_id: str) -> bool:
    row = compute._run(run_id)
    return json.loads(row['config_snapshot']).get('sandbox_first_version') == 1


def current(run_id: str) -> dict:
    row = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='topic.workspace' ORDER BY seq DESC LIMIT 1", (run_id,))
    return json.loads(row['payload']) if row else {'mode': 'not_selected'}


def ensure(run_id: str) -> dict:
    prior = current(run_id)
    if prior['mode'] != 'not_selected':
        if prior.get('sandbox_id'):
            box = sandboxes._owned(run_id, prior['sandbox_id'])
            if box['status'] != 'active' or sandboxes._seconds_left(box) < 30:
                return prior | {'mode': 'job', 'reason': '沙箱到期或不可用；原生CLI尚无已确认续期协议，不伪造远程续期'}
        return prior
    run = compute._run(run_id)
    choice = environment_catalog.current(run_id)
    if choice['mode'] != 'catalog':
        return {'mode': 'not_selected', 'reason': 'PI须先选择包含镜像的环境目录起点'}
    entry = environment_catalog.get(choice['entry_id'])
    image = entry.get('image')
    if not image:
        return {'mode': 'not_selected', 'reason': '所选环境未提供镜像'}
    operation_id = 'topic_' + run_id
    try:
        auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],))
        if not auth:
            raise compute.ComputeError('NOT_AUTHORIZED', '本题没有有效的计算授权')
        from . import run_clock
        # Creation itself needs up to 240 seconds in addition to the lifetime.
        lifetime = sandboxes.bounded_lifetime(run_id, int(run_clock.remaining(run, auth)) - 300)
        result = sandboxes.create(run_id, operation_id, {'image': image, 'cpu': '2c4g', 'timeout': lifetime})
        fact = {'mode': 'sandbox' if result['status'] == 'active' else 'job', 'image': image,
                'sandbox_id': result.get('sandbox_id'), 'operation_id': operation_id,
                'create_status': result['status'], 'lifetime_seconds': lifetime,
                'renewal': 'unavailable_in_native_cli', 'reason': '创建状态=' + result['status']}
    except compute.ComputeError as exc:
        fact = {'mode': 'job', 'image': image, 'sandbox_id': None,
                'operation_id': operation_id, 'reason': exc.code + ': ' + str(exc)}
    db.append_event(run_id, 'controller', 'topic.workspace', fact, trial_id=run['current_trial_id'])
    return fact


def work(run_id: str, body: dict) -> dict:
    """A work request includes its Job spec/input so fallback needs no second call."""
    fact = ensure(run_id)
    if fact['mode'] == 'not_selected':
        return fact
    if fact['mode'] == 'sandbox':
        from . import sandbox_background
        return sandbox_background.start(run_id, fact['sandbox_id'], body.get('command'),
                                        body.get('timeout'), body.get('operation_id'))
    spec = body.get('spec')
    if not isinstance(spec, dict) or not body.get('input_directory'):
        raise compute.ComputeError('FALLBACK_SPEC_REQUIRED', '沙箱创建未确认；请为同镜像Job提供spec、input_directory，unknown沙箱保留预留')
    if spec.get('image_address') != fact['image'] or spec.get('command') != body.get('command'):
        raise compute.ComputeError('FALLBACK_IMAGE_MISMATCH', '自动回退必须使用PI选定的同镜像、同命令')
    result = compute.submit(run_id, body.get('operation_id'), spec, body['input_directory'], body.get('preflight'))
    db.append_event(run_id, 'controller', 'topic.job_fallback',
                    {'operation_id': body.get('operation_id'), 'image': fact['image'],
                     'reason': fact['reason'], 'sandbox_reservation_retained': fact.get('create_status') == 'unknown'})
    return result | {'fallback': 'job', 'fallback_reason': fact['reason']}
