"""Append-only challenge exchange; provenance never implies scientific correctness."""
from __future__ import annotations
import hashlib
import json
import re
import uuid
import io
import zipfile
from pathlib import Path
from . import config, db, local_scoring, observation, package_reviews

MAX_BYTES = 16_000_000
NAME = re.compile(r'[A-Za-z0-9_.-]{1,100}\Z')


def enabled():
    return config.load_settings().get('features', {}).get('shared_area', True)


def _root(challenge_id):
    if not db.query_one('SELECT 1 FROM challenges WHERE id=?', (challenge_id,)):
        raise ValueError('题目不存在')
    base = config.WORKSPACE_DIR.resolve()
    root = base / 'challenges' / challenge_id / 'shared'
    if not root.resolve().is_relative_to(base / 'challenges') or any(p.is_symlink() for p in [root, root.parent, root.parent.parent]):
        raise ValueError('共享区路径越界或含符号链接')
    return root


def _trial(run_id, trial_id, *, write=False):
    row = db.query_one('SELECT r.challenge_id,r.phase,r.gate,r.current_trial_id,t.status FROM runs r JOIN trials t ON t.run_id=r.id WHERE r.id=? AND t.id=?', (run_id, trial_id))
    if not row:
        raise ValueError('Trial不属于本Run')
    if write and (not enabled() or row['phase'] != 'running' or row['gate'] != 'open' or row['status'] != 'active' or row['current_trial_id'] != trial_id):
        raise ValueError('共享区关闭或Run/Trial未在运行')
    base = config.WORKSPACE_DIR.resolve() / 'runs' / run_id / 'trials' / trial_id
    if not base.resolve().is_relative_to(config.WORKSPACE_DIR.resolve() / 'runs') or any(p.is_symlink() for p in [base, base.parent, base.parent.parent]):
        raise ValueError('Trial路径越界或含符号链接')
    return row, base


def _clean(raw):
    secrets = [value.encode() for value in config.sensitive_values() if isinstance(value, str) and len(value) > 7]
    budget = {'bytes': MAX_BYTES, 'members': 100}
    def inspect(content, depth=0):
        if len(content) > MAX_BYTES or depth > 4:
            raise ValueError('共享文件/嵌套ZIP超过限制')
        if content.startswith((b'\x1f\x8b', b'BZh', b'\xfd7zXZ')):
            raise ValueError('共享压缩格式无法安全检查，请先展开文件')
        archive = None
        if content.startswith(b'PK'):
            archive = zipfile.ZipFile(io.BytesIO(content))
            items = archive.infolist()
            size = sum(item.file_size for item in items)
            if size > budget['bytes'] or len(items) > budget['members'] or any(item.flag_bits & 1 for item in items):
                archive.close()
                raise ValueError('共享ZIP累计展开超过限制或已加密')
            budget['bytes'] -= size; budget['members'] -= len(items)
        text = content.decode('utf-8', errors='replace')
        if any(secret in content for secret in secrets) or observation.strip_secrets(text) != text:
            if archive: archive.close()
            raise ValueError('共享文件含密钥，拒绝复制')
        if archive:
            with archive:
                for item in archive.infolist(): inspect(archive.read(item), depth + 1)
    inspect(raw)


def _immutable(path, raw):
    base = config.WORKSPACE_DIR.resolve()
    if not path.resolve().is_relative_to(base) or any(p.is_symlink() for p in [path, *path.parents] if p != base and p.is_relative_to(base)):
        raise ValueError('目标路径越界或含符号链接')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
            raise ValueError('不可覆盖已存在的共享文件')
        return
    with path.open('xb') as stream:
        stream.write(raw)
    path.chmod(0o444)


def validator(challenge_id):
    """Only the configured backend grader may become a formal validator version."""
    root = _root(challenge_id)
    try:
        manifest = local_scoring.scorer_manifest(challenge_id)
    except local_scoring.LocalScoreError as exc:
        return {'status': 'unknown', 'code': exc.code, 'detail': '未配置正式科学验证器，研究产物不能自称已验证'}
    version = manifest['scorer_version']
    target = root / 'validators' / version
    if any(p.is_symlink() for p in (target, target.parent, target / 'scorer')):
        raise ValueError('正式验证器路径含符号链接')
    old = db.query_one('SELECT descriptor_json FROM challenge_validator_versions WHERE challenge_id=? AND version=?', (challenge_id, version))
    if old:
        descriptor = json.loads(old['descriptor_json'])
        for name, raw in manifest['files'].items():
            frozen = root / 'validators' / version / 'scorer' / name
            if frozen.is_symlink() or not frozen.is_file() or frozen.read_bytes() != raw:
                raise ValueError('正式验证器冻结文件哈希不一致')
        return descriptor
    for raw in manifest['files'].values(): _clean(raw)
    for name, raw in manifest['files'].items(): _immutable(target / 'scorer' / name, raw)
    descriptor = {'status': 'observed', 'scorer_version': version, 'entrypoint': manifest['entrypoint'],
        'snapshot_root': str(target / 'scorer'), 'file_hashes': manifest['file_hashes']}
    descriptor['source'] = 'backend configured scorer; frozen source, not an execution receipt'
    db.execute('INSERT OR IGNORE INTO challenge_validator_versions VALUES(?,?,?,?)', (challenge_id, version, json.dumps(descriptor, ensure_ascii=False), db.utcnow()))
    return descriptor


def catalog(challenge_id):
    _root(challenge_id)
    items = []
    for row in db.query('SELECT * FROM challenge_shared_versions WHERE challenge_id=? ORDER BY name,version DESC', (challenge_id,)):
        item = dict(row)
        path = config.WORKSPACE_DIR / item['path']
        item['integrity'] = 'confirmed' if path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'] else 'unknown'
        items.append(item)
    formal = validator(challenge_id) if enabled() else {'status': 'disabled'}
    return {'enabled': enabled(), 'items': items, 'validator': formal}


def publish(run_id, trial_id, name, source_path, source_event_seq):
    row, base = _trial(run_id, trial_id, write=True)
    if not isinstance(name, str) or not NAME.fullmatch(name) or name in ('.', '..') or observation.strip_secrets(name) != name:
        raise ValueError('共享名称必须是普通文件名')
    if not isinstance(source_path, str) or not source_path or Path(source_path).is_absolute() or '..' in Path(source_path).parts:
        raise ValueError('来源必须是当前Trial内相对路径')
    path = base / source_path
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(base.resolve()):
        raise ValueError('来源文件不存在或越界')
    if path.stat().st_size > MAX_BYTES: raise ValueError('共享文件超过16MB')
    if type(source_event_seq) is not int or not db.query_one('SELECT 1 FROM events WHERE run_id=? AND trial_id=? AND seq=?', (run_id, trial_id, source_event_seq)):
        raise ValueError('来源事件不属于本Run/Trial')
    raw = path.read_bytes(); _clean(raw); digest = hashlib.sha256(raw).hexdigest()
    root = _root(row['challenge_id'])
    with db.transaction() as conn:
        version = conn.execute('SELECT COALESCE(MAX(version),0)+1 FROM challenge_shared_versions WHERE challenge_id=? AND name=?', (row['challenge_id'], name)).fetchone()[0]
        destination = root / 'artifacts' / name / f'v{version}-{digest[:16]}'
        _immutable(destination, raw)
        identity = 'shared_' + uuid.uuid4().hex[:16]
        conn.execute('INSERT INTO challenge_shared_versions VALUES(?,?,?,?,?,?,?,?,?,?)',
            (identity, row['challenge_id'], name, version, destination.relative_to(config.WORKSPACE_DIR).as_posix(), digest, run_id, trial_id, source_event_seq, db.utcnow()))
        db.append_event_tx(conn, run_id, 'executor', 'shared.published', {
            'id': identity, 'name': name, 'version': version, 'sha256': digest, 'source_event_seq': source_event_seq}, trial_id=trial_id)
    return dict(db.query_one('SELECT * FROM challenge_shared_versions WHERE id=?', (identity,)))


def import_artifact(run_id, trial_id, artifact_id):
    row, base = _trial(run_id, trial_id, write=True)
    source = db.query_one('SELECT * FROM challenge_shared_versions WHERE id=? AND challenge_id=?', (artifact_id, row['challenge_id']))
    if not source:
        raise ValueError('共享版本不属于本题')
    path = config.WORKSPACE_DIR / source['path']
    root = _root(row['challenge_id'])
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('共享文件越界或不存在')
    raw = path.read_bytes(); _clean(raw)
    if hashlib.sha256(raw).hexdigest() != source['sha256']:
        raise ValueError('共享版本哈希不一致')
    destination = base / 'imports' / (artifact_id + '-' + source['name'])
    _immutable(destination, raw)
    event = db.append_event(run_id, 'executor', 'shared.imported', {
        'id': artifact_id, 'version': source['version'], 'sha256': source['sha256'],
        'source_run_id': source['source_run_id'], 'source_trial_id': source['source_trial_id'],
        'source_event_seq': source['source_event_seq'], 'path': destination.relative_to(base).as_posix(),
        'science_verified': False}, trial_id=trial_id)
    return {'path': destination.relative_to(base).as_posix(), 'sha256': source['sha256'], 'event_seq': event['seq']}
