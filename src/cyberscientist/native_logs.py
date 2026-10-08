"""Controller-bound native log snapshots; never edit a provider's record."""
import hashlib
import json
from pathlib import Path
from . import config, db, observation


def bind_trial(run_id, trial_id, session_id):
    rows = db.query("SELECT payload FROM events WHERE run_id=? AND type='session.configuration' ORDER BY seq DESC", (run_id,))
    for row in rows:
        value = json.loads(row['payload'])
        if value.get('role') == 'executor' and value.get('session_id') == session_id:
            if value.get('native_log_path'):
                db.append_event(run_id, 'controller', 'trial.native_session_bound', value, trial_id=trial_id)
            return


def snapshot(run_id, trial_id):
    if not trial_id:
        return None
    row = db.query_one("SELECT payload FROM events WHERE run_id=? AND trial_id=? AND source='controller' AND type='trial.native_session_bound' ORDER BY seq DESC LIMIT 1", (run_id, trial_id))
    if not row:
        return None
    value = json.loads(row['payload'])
    path = Path(value['native_log_path'])
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024**2:
        raise ValueError('原生会话日志不存在、为链接或超过128MiB')
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    if observation.strip_secrets(text) != text:
        raise ValueError('原始会话包含需脱敏内容；不得改写，须使用无密钥的干净会话')
    first = json.loads(text.splitlines()[0])
    if (first.get('type') != 'session_meta'
            or first.get('payload', {}).get('id') != value['session_id']):
        raise ValueError('原生会话身份与最终Trial绑定不符')
    return {'bytes': raw, 'session_id': value['session_id'],
            'sha256': hashlib.sha256(raw).hexdigest(), 'model': value.get('model'),
            'provider': value.get('provider'), 'trial_id': trial_id}
