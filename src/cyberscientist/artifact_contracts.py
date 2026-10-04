"""Advisory task paths and explicitly verified scorer paths, for any task."""
from __future__ import annotations

import io
import re
import zipfile
from typing import Any

from . import db

_PATH = re.compile(r'`([^`\s]+\.(?:txt|json|jsonl|lean|csv|npz|npy|zip|pdf|png))`')
_OUTPUT = re.compile(r'output|artifact|deliver|submission|answer|产物|输出|答案|交付|提交', re.I)


def for_run(run_id: str) -> dict:
    row = db.query_one('SELECT c.title,c.content,c.resources_json,c.platform_snapshot_json,r.config_snapshot'
                       ' FROM runs r JOIN challenges c ON c.id=r.challenge_id WHERE r.id=?', (run_id,))
    if not row:
        raise ValueError('Run 不存在')
    import json
    result = dict(row)
    frozen = json.loads(row['config_snapshot']).get('competition', {}).get('challenge_snapshot')
    if frozen:
        result.update(title=frozen['title'], content=frozen['content'],
                      resources_json=json.dumps(frozen['resources']), platform_snapshot_json=json.dumps(frozen['platform']))
    result.pop('config_snapshot', None)
    return result


def inspect(challenge_id: str, sealed: bytes | None = None, *, task_content: str | None = None) -> dict[str, Any]:
    from . import local_scoring
    row = db.query_one('SELECT content FROM challenges WHERE id=?', (challenge_id,))
    content = task_content if task_content is not None else (row['content'] if row else '')
    paths = sorted({match.group(1) for line in content.splitlines()
                    if _OUTPUT.search(line) for match in _PATH.finditer(line)})
    result: dict[str, Any] = {
        'task_paths': paths, 'task_paths_source': 'output-related task text; extraction may be incomplete',
        'scorer_paths': [], 'status': 'unavailable', 'missing': [],
        'duplicate': [], 'warnings': [], 'scorer_version': None,
    }
    try:
        manifest = local_scoring.scorer_manifest(challenge_id)
    except local_scoring.LocalScoreError as exc:
        result['reason'] = exc.code
        return result
    result['scorer_version'] = manifest.get('scorer_version')
    contract = manifest.get('input_contract')
    if not contract:
        result['reason'] = 'scorer has no verified input-path declaration'
        return result
    accepted = contract['artifact_paths']
    result.update(scorer_paths=accepted, verification=contract['verification'],
                  required=contract['required'], status='declared')
    if paths and set(paths) != set(accepted):
        result['warnings'].append('题面输出相关路径与已验证评分器路径不同；请自行决定产物布局。')
    if sealed is None:
        return result
    try:
        with zipfile.ZipFile(io.BytesIO(sealed)) as archive:
            names = [name for name in archive.namelist() if not name.endswith('/')]
    except zipfile.BadZipFile:
        result.update(status='unavailable', reason='not a readable ZIP')
        return result
    for path in accepted:
        count = sum(name == path or name.endswith('/' + path) for name in names)
        if count == 0:
            result['missing'].append(path)
        elif count > 1:
            result['duplicate'].append(path)
    result['status'] = 'mismatch' if result['missing'] or result['duplicate'] else 'ready'
    if result['status'] == 'mismatch':
        result['warnings'].append('评分器路径缺少或重复；预检不替代理移动或补写产物。')
    result['package_paths'] = names[:100]
    return result


def require_supported(challenge_id: str, sealed: bytes) -> dict[str, Any]:
    """Avoid spending on a scorer whose declared required inputs are absent."""
    from .local_scoring import LocalScoreError
    result = inspect(challenge_id, sealed)
    if result['status'] == 'mismatch' and result.get('required'):
        roots = [path for path in result.get('package_paths', []) if '/' not in path]
        raise LocalScoreError('SCORER_INPUT_PATH_MISMATCH',
            '评分器路径缺少或重复：' + ', '.join(result['missing'] + result['duplicate'])
            + ('；包中根目录 ' + ', '.join(roots) if roots else ''))
    return result
