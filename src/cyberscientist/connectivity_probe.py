"""Three public read operations in an explicitly authorized zero-research probe."""
import fcntl
import json
import os
from pathlib import Path
import re

from . import config, public_research


def call(name: str, arguments: dict) -> dict:
    marker = os.environ.get('CS_PUBLIC_RESEARCH_PROBE', '')
    if not re.fullmatch('[0-9a-f]{32}', marker) or name not in public_research.FUNCTIONS:
        return {'status': 'unknown', 'error': 'OUTSIDE_PROBE_AUTHORITY'}
    target = Path(os.environ['CS_PUBLIC_PROBE_RECEIPTS']).resolve()
    if not target.is_relative_to(config.DATA_DIR.resolve()):
        return {'status': 'unknown', 'error': 'INVALID_RECEIPT_PATH'}
    expected = 'url' if name == 'research_web_read' else 'query'
    if not isinstance(arguments, dict) or set(arguments) != {expected}:
        return {'status': 'unknown', 'error': 'INVALID_ARGUMENTS'}
    with target.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = json.loads(target.read_text()) if target.exists() else {}
        if name in previous:
            return previous[name].get('result') or {'status': 'unknown', 'error': 'ALREADY_STARTED_NOT_REPLAYED'}
        previous[name] = {'status': 'started'}
        target.write_text(json.dumps(previous))
        try:
            result = public_research.FUNCTIONS[name](arguments[expected])
        except (ValueError, OSError) as exc:
            result = {'status': 'unknown', 'error': type(exc).__name__}
        previous[name] = {'status': 'completed', 'result': result}
        target.write_text(json.dumps(previous, ensure_ascii=False))
        return result
