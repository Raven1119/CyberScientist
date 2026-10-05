"""PI startup context and receipt-backed environment recipes, without extra compute."""
from __future__ import annotations

import hashlib
import json

from . import config, db, environment_facts, experience_context, platform_scores
from .bohr_proxy import redact


def strategy_cards(challenge_id: str) -> list[dict]:
    # Read complete current cards, independently of the ordinary injection budget.
    return [entry for entry in experience_context.effective(challenge_id)
            if entry['scope'] == 'challenge' and entry.get('kind') == 'strategy']


def guidance_level(run_id: str) -> dict:
    run = db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (run_id,))
    snapshot = json.loads(run['config_snapshot'])
    solver = dict(snapshot.get('settings', {}).get('executor', {}))
    solver['note'] = '\n'.join(filter(None, (solver.get('note'), snapshot.get('competition', {}).get('solver_note'))))
    solver['note'] = redact(solver['note'], config.sensitive_values())
    description = ' '.join(str(solver.get(k, '')) for k in ('model_id', 'note')).lower()
    concrete = any(word in description for word in
                   ('deepseek', 'flash', 'mini', '便宜', '写死', '弱', '具体'))
    return {'solver': {k: solver.get(k) for k in ('model_id', 'note', 'provider')},
            'level': 'concrete_work_package' if concrete else 'goal_constraints_acceptance',
            'work_package_fields': ['algorithm_md', 'formula_md', 'parameter_ranges_md',
                                    'expected_intermediate_md', 'test_cases_md', 'stop_conditions_md']}


def startup(run_id: str, challenge: dict) -> dict:
    """Only read public rankings for actual imported platform topics; failures stay unknown."""
    key = 'research_startup:' + run_id
    cached = db.query_one('SELECT value FROM system_state WHERE key=?', (key,))
    if cached:
        return json.loads(cached['value'])
    run = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    origin = db.query_one('SELECT origin FROM challenges WHERE id=?', (run['challenge_id'],))['origin']
    platform = json.loads(challenge.get('platform_snapshot_json') or '{}')
    scores = (platform_scores.get(run_id) if run['mode'] != 'demo' and
              (platform.get('fetched_at') or origin.startswith(('https://', 'pinned-public-snapshot://'))) else
              {'status': 'unknown', 'reason': 'No live platform provenance for this topic'})
    cards = strategy_cards(run['challenge_id'])
    delivered = experience_context.freeze(run_id, None, 'startup:strategies', items=cards, role='brain')
    context = {'title': challenge['title'], 'problem_md': challenge['content'],
               'resources': json.loads(challenge.get('resources_json') or '[]'),
               'public_score_distribution': scores,
               'strategy_cards': delivered['items'], 'strategy_context_id': delivered['id'],
               'guidance': guidance_level(run_id),
               'brief_fields': ['problem_md', 'science_md', 'ranked_methods', 'traps_md',
                                'parallel_preparation', 'acceptance_md'],
               'preparation_tracks': ['delivery_contract', 'verifier', 'environment_smoke']}
    db.execute('INSERT OR IGNORE INTO system_state(key,value) VALUES(?,?)',
               (key, json.dumps(context, ensure_ascii=False)))
    db.append_event(run_id, 'controller', 'research.startup_read', {
        'strategy_revisions': [c['revision_id'] for c in context['strategy_cards']],
        'public_score_status': scores.get('status', 'unknown'), 'guidance': context['guidance']})
    return context


def record_brief(run_id: str, brief: dict, decision_id: str) -> dict:
    safe = json.loads(redact(json.dumps(brief, ensure_ascii=False), config.sensitive_values()))
    body = '# PI 研究简报\n\n' + '\n\n'.join(
        f"## {key}\n\n" + (value if isinstance(value, str) else
                              json.dumps(value, ensure_ascii=False, indent=2))
        for key, value in safe.items()) + '\n'
    root = config.WORKSPACE_DIR / 'runs' / run_id
    root.mkdir(parents=True, exist_ok=True)
    target = root / 'research_brief.md'
    target.write_text(body, encoding='utf-8')
    event = db.append_event(run_id, 'brain', 'research.brief_written', {
        'decision_id': decision_id, 'brief': safe,
        'path': str(target.relative_to(config.WORKSPACE_DIR)),
        'sha256': hashlib.sha256(body.encode()).hexdigest()})
    from . import strategies
    strategies.maintain(run_id, brief=safe, event=event)
    return event


def brief_for_run(run_id: str) -> str:
    row = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='research.brief_written'"
                       ' ORDER BY seq DESC LIMIT 1', (run_id,))
    return ('\nPI 科学简报及具体工作包：\n' + json.dumps(json.loads(row['payload'])['brief'], ensure_ascii=False)
            if row else '')


def untried_channels(run_id: str) -> list[str]:
    """Availability is based on remaining authority and actual attempted operations."""
    from . import run_clock
    run = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    auth = db.query_one('SELECT * FROM authorizations WHERE id=?', (run['authorization_id'],))
    if not auth or run_clock.remaining(run, auth) <= 0 or run['mode'] != 'connected':
        return []
    from . import compute_budget
    from decimal import Decimal
    cost = compute_budget.summary(run_id)
    compute_available = cost['remaining_cny'] is None or Decimal(cost['remaining_cny']) > 0
    result = []
    jobs = db.query_one('SELECT COUNT(*) AS n FROM compute_jobs WHERE run_id=?', (run_id,))['n']
    boxes = db.query_one('SELECT COUNT(*) AS n FROM compute_sandboxes WHERE run_id=?', (run_id,))['n']
    if (auth['unlimited_resources'] or auth['max_jobs'] > 0) and jobs == 0 and compute_available and run_clock.remaining(run, auth) >= 60:
        result.append('bohrium_job')
    if (auth['unlimited_resources'] or auth['max_sandboxes'] > 0 and auth['max_sandbox_minutes'] > 0) and boxes == 0 and compute_available:
        result.append('bohrium_sandbox')
    snapshot = json.loads(run['config_snapshot']).get('competition', {}).get('challenge_snapshot')
    topic = db.query_one('SELECT resources_json FROM challenges WHERE id=?', (run['challenge_id'],))
    resources = snapshot.get('resources', []) if snapshot else json.loads(topic['resources_json'] or '[]')
    if auth['allow_data_download'] and resources and not db.query_one(
            "SELECT 1 FROM events WHERE run_id=? AND type='data.materialize_requested'", (run_id,)):
        result.append('resource_download')
    return result


@config.serialized_mutation
def register_smoke(run_id: str, operation_id: str, recipe: str) -> dict:
    """A successful backend-held sandbox exec can register a reusable recipe, not an image."""
    from .compute import ComputeError
    operation = db.query_one('SELECT * FROM compute_sandbox_operations WHERE operation_id=? AND run_id=?',
                             (operation_id, run_id))
    if not operation or operation['action'] != 'exec' or operation['status'] != 'completed':
        raise ComputeError('INVALID_RECEIPT', '需要本 Run 已完成的冒烟执行回执')
    box = db.query_one('SELECT * FROM compute_sandboxes WHERE run_id=? AND sandbox_id=?',
                       (run_id, operation['sandbox_id']))
    raw = operation['receipt_json']
    receipt = json.loads(raw)
    from . import sandboxes
    data = sandboxes._data(sandboxes._body(receipt))
    started = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='sandbox.exec_started'"
                           " AND json_extract(payload,'$.operation_id')=?", (run_id, operation_id))
    command = json.loads(started['payload']).get('command') if started else None
    if (not box or not isinstance(data, dict) or not isinstance(command, str) or
            operation['command_sha256'] != hashlib.sha256(command.encode()).hexdigest() or
            operation['receipt_sha256'] != hashlib.sha256(raw.encode()).hexdigest() or
            receipt.get('ok') is not True or receipt.get('truncated') or
            type(data.get('exit_code')) is not int or data['exit_code'] != 0):
        raise ComputeError('INVALID_RECEIPT', '冒烟回执失败、截断、身份或哈希不符')
    if not isinstance(recipe, str) or not recipe.strip():
        raise ComputeError('INVALID_RECIPE', '请提供可以复用的软件安装和冒烟配方')
    payload = {'operation_id': operation_id, 'sandbox_id': box['sandbox_id'],
               'image_address': json.loads(box['request_json']).get('image'),
               'observed_command': command, 'recipe_proposal': recipe, 'recipe_status': 'unverified',
               'smoke_stdout': data.get('stdout', ''),
               'command_sha256': operation['command_sha256'],
               'receipt_sha256': operation['receipt_sha256'],
               'runtime_status': 'smoke_verified', 'persistent_image_status': 'unverified'}
    payload = json.loads(redact(json.dumps(payload, ensure_ascii=False), config.sensitive_values()))
    previous = db.query_one("SELECT * FROM events WHERE run_id=? AND type='environment.smoke_observed'"
                            " AND json_extract(payload,'$.operation_id')=?", (run_id, operation_id))
    if previous and json.loads(previous['payload']) != payload:
        raise ComputeError('OPERATION_CONFLICT', '同一冒烟回执已登记不同配方')
    event = (dict(previous) if previous else
             db.append_event(run_id, 'controller', 'environment.smoke_observed', payload,
                             trial_id=box['trial_id']))
    fact = environment_facts.record('smoke:' + operation_id, '冒烟命令回执与配方候选', payload, event)
    return {'status': 'smoke_verified', 'fact': fact, 'recipe_status': 'unverified',
            'persistent_image_status': 'unverified', 'deduplicated': bool(previous)}
