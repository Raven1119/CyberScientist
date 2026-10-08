"""Future solver projection from observed throttling; never switches a PI or live Run."""
import json
from datetime import datetime, timezone
from . import challenge_models, config, db, model_limits, observation


def validate(value, settings):
    if not isinstance(value, dict) or set(value) - {'after_minutes', 'solver_id'}: raise ValueError('DeepSeek后备配置无效')
    minutes, ident = value.get('after_minutes', 5), value.get('solver_id', '')
    if type(minutes) not in (int, float) or not 0 <= minutes <= 1440: raise ValueError('后备等待分钟须为0–1440')
    if not isinstance(ident, str): raise ValueError('后备求解者ID无效')
    if ident and challenge_models.solver(ident, settings)['provider'] != 'deepseek': raise ValueError('后备条目必须使用DeepSeek')
    return {'after_minutes': minutes, 'solver_id': ident}


def _key(choice):
    return 'native_throttle:' + (choice.get('provider') or choice.get('runtime', 'codex')) + ':' + (choice.get('model_id') or 'unknown')


def ticket(choice):
    row = db.query_one('SELECT payload_json FROM runtime_observations WHERE kind=?', (_key(choice),))
    return json.loads(row['payload_json']).get('generation', 0) if row else 0


def _summarize(facts):
    waiting = [item for item in facts['requests'].values() if item['status'] == 'waiting']
    facts['status'] = 'waiting' if waiting else 'recovered'
    if waiting: facts['first_at'] = min(item['first_at'] for item in waiting)


def note(choice, error, *, will_retry=False, request_id='legacy'):
    info = model_limits.classify(error)
    if not info: return
    now = db.utcnow(); key = _key(choice)
    with db.transaction() as conn:
        row = conn.execute('SELECT payload_json FROM runtime_observations WHERE kind=?', (key,)).fetchone()
        facts = json.loads(row['payload_json']) if row else {}
        requests = facts.setdefault('requests', {})
        previous = requests.get(request_id, {})
        requests[request_id] = {'status': 'waiting', 'first_at': previous['first_at'] if previous.get('status') == 'waiting' else now, 'observed_at': now}
        facts.update(provider=choice.get('provider') or choice.get('runtime', 'codex'), model_id=choice.get('model_id'),
                     observed_at=now, will_retry=bool(will_retry), reason=info.reason, generation=facts.get('generation', 0) + 1,
                     detail=observation.strip_secrets(str(error))[:400], scope='request_model; provider-wide availability unverified')
        _summarize(facts)
        conn.execute('INSERT OR REPLACE INTO runtime_observations VALUES(?,?,?)', (key, json.dumps(facts, ensure_ascii=False), now))


def recovered(choice, *, request_id='legacy', started_generation=None):
    key = _key(choice)
    with db.transaction() as conn:
        row = conn.execute('SELECT payload_json FROM runtime_observations WHERE kind=?', (key,)).fetchone()
        if not row: return
        facts = json.loads(row['payload_json']);now = db.utcnow()
        request = facts.get('requests', {}).get(request_id)
        if request: request.update(status='recovered', observed_at=now)
        # A new request begun after the most recent fault confirms availability
        # for future Runs. Older concurrent completions cannot clear that fault.
        if started_generation == facts.get('generation'):
            facts['successful_generation'] = started_generation
        facts.update(last_success={'request_id': request_id, 'started_generation': started_generation, 'observed_at': now}, observed_at=now)
        _summarize(facts)
        conn.execute('UPDATE runtime_observations SET payload_json=?,observed_at=? WHERE kind=?', (json.dumps(facts, ensure_ascii=False), now, key))


def facts():
    return [json.loads(row['payload_json']) for row in db.query("SELECT payload_json FROM runtime_observations WHERE kind LIKE 'native_throttle:%' ORDER BY kind")]


def select(choice, settings):
    original = dict(choice)
    result = {'status': 'original', 'original': original}
    if settings.get('science_first_flow',True):
        result['status']='manual_only'
        return original,result
    if not settings.get('features', {}).get('deepseek_fallback', True) or settings['app']['mode'] != 'connected': return original, result
    if (choice.get('provider') or choice['runtime']) != 'codex': return original, result
    settings_value = validate(settings.get('deepseek_fallback', {}), settings)
    row = db.query_one('SELECT payload_json FROM runtime_observations WHERE kind=?', (_key(choice),))
    observed = json.loads(row['payload_json']) if row else None
    if not observed or observed.get('status') != 'waiting' or observed.get('successful_generation') == observed.get('generation'): return original, result
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(observed['first_at'])).total_seconds()
    result['rate_observation'] = observed
    if elapsed < settings_value['after_minutes'] * 60: return original, result
    entries = challenge_models.roster(settings)
    entry = next((item for item in entries if item['id'] == settings_value['solver_id']), None) if settings_value['solver_id'] else next((item for item in entries if item['provider'] == 'deepseek'), None)
    if not entry or not config.deepseek_key():
        result.update(status='unavailable', reason='缺少DeepSeek条目或DEEPSEEK_API_KEY；保持原选择并排队')
        return original, result
    selected = challenge_models.choose('executor', entry, settings)
    result.update(status='fallback', selected=selected, solver_entry=entry, after_minutes=settings_value['after_minutes'], reason='请求模型持续429，后备只用于新求解者；PI与提供方退避保持')
    return selected, result
