"""Capability-scoped PI file reads; no shell, writes or arbitrary filesystem root."""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import re

from . import config, db, observation, skills

PAGE_BYTES = 12000
LIST_LIMIT = 100
_PRIVATE_NAMES = {'.env', 'secrets.json', 'auth.json', 'credentials.json', 'config.toml',
                  'id_rsa', 'id_ed25519', '.git', '.cyberscientist', 'sessions', 'brain'}


def _parts(value):
    if not isinstance(value, str) or '\\' in value or '\0' in value:
        raise ValueError('文件路径无效')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or observation.strip_secrets(value) != value:
        raise ValueError('文件路径越界或含密钥')
    if any(part.lower() in _PRIVATE_NAMES or part.lower().startswith('.env.')
           or part.lower().endswith(('.pem', '.key')) for part in path.parts):
        raise ValueError('密钥或内部状态文件不可读取')
    return path.parts


def _root(run, scope, parts):
    if scope == 'skills':
        catalog = skills.file_catalog()
        if not parts:
            return None, (), [{'name': s['id'], 'type': 'directory',
                               'source_path': s['source_path']} for s in catalog]
        entry = next((s for s in sorted(catalog, key=lambda item: len(item['id']), reverse=True)
                      if parts[:len(PurePosixPath(s['id']).parts)] == PurePosixPath(s['id']).parts), None)
        if not entry:
            raise ValueError('技能未登记')
        return Path(entry['source_path']), parts[len(PurePosixPath(entry['id']).parts):], None
    if scope == 'trials':
        trials = db.query('SELECT id FROM trials WHERE run_id=? ORDER BY rowid', (run['id'],))
        if not parts:
            return None, (), [{'name': row['id'], 'type': 'directory'} for row in trials]
        if not any(row['id'] == parts[0] for row in trials):
            raise ValueError('Trial不属于本Run')
        return config.WORKSPACE_DIR / 'runs' / run['id'] / 'trials' / parts[0], parts[1:], None
    if scope == 'facts':
        return config.WORKSPACE_DIR / 'runs' / run['id'] / 'facts', parts, None
    if scope == 'resources':
        # Dataset materialization copies files here; symlinks are never followed.
        return config.WORKSPACE_DIR / 'challenges' / run['challenge_id'], parts, None
    raise ValueError('只允许skills、trials、resources、facts读取范围')


def _open(root, parts, directory):
    """Walk from / with directory descriptors: symlink swaps cannot widen scope."""
    names = (*root.absolute().parts[1:], *parts)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for index, name in enumerate(names):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(names) - 1 or directory:
                flags |= os.O_DIRECTORY
            next_fd = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def access(run_id, args):
    allowed = {'action', 'scope', 'path', 'offset', 'limit', 'expected_sha256'}
    if not isinstance(args, dict) or set(args) - allowed:
        raise ValueError('只读文件参数无效')
    action, scope = args.get('action'), args.get('scope')
    if action not in ('list', 'read'):
        raise ValueError('只允许列目录或读文件')
    offset, limit = args.get('offset', 0), args.get('limit', PAGE_BYTES if action == 'read' else LIST_LIMIT)
    maximum = PAGE_BYTES if action == 'read' else LIST_LIMIT
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= maximum:
        raise ValueError('分页参数超出范围')
    parts = _parts(args.get('path', ''))
    run = db.query_one('SELECT id,challenge_id FROM runs WHERE id=?', (run_id,))
    if not run:
        raise ValueError('Run不存在')
    root, relative, virtual = _root(run, scope, parts)
    if virtual is not None:
        if action != 'list':
            raise ValueError('请选择一个文件')
        return {'scope': scope, 'path': '', 'entries': virtual[offset:offset+limit],
                'next_offset': offset+limit if offset+limit < len(virtual) else None}
    source = root.joinpath(*relative)
    try:
        fd = _open(root, relative, action == 'list')
        with os.fdopen(fd, 'rb') if action == 'read' else _Directory(fd) as handle:
            if action == 'list':
                entries = []
                for name in sorted(os.listdir(handle.fd)):
                    try:
                        _parts(name)
                        info = os.stat(name, dir_fd=handle.fd, follow_symlinks=False)
                        if not stat.S_ISLNK(info.st_mode):
                            entries.append({'name': name, 'type': 'directory' if stat.S_ISDIR(info.st_mode) else 'file'})
                    except (OSError, ValueError):
                        continue
                return {'scope': scope, 'path': '/'.join(parts), 'source_path': str(source),
                        'entries': entries[offset:offset+limit],
                        'next_offset': offset+limit if offset+limit < len(entries) else None}
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('只允许读取普通文件')
            digest = hashlib.sha256()
            secrets = [value.encode() for value in config.sensitive_values()
                       if isinstance(value, str) and len(value) > 7]
            overlap = max([4096, *(len(value) for value in secrets)])
            tail, page, position, archive = b'', b'', 0, b''
            while position < before.st_size:
                chunk = handle.read(min(1024 * 1024, before.st_size-position))
                if not chunk:
                    raise ValueError('文件读取期间已变化，请重新分页')
                digest.update(chunk)
                window = tail + chunk
                text = window.decode('utf-8', errors='replace')
                if (any(value in window for value in secrets) or observation.strip_secrets(text) != text
                        or re.search(rb'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----', window)):
                    raise ValueError('文件含密钥，拒绝读取')
                if position == 0 and chunk.startswith((b'PK', b'\x1f\x8b', b'BZh', b'\xfd7zXZ')):
                    if before.st_size > 16 * 1024 * 1024:
                        raise ValueError('压缩文件过大，无法安全检查密钥；请读取已展开产物')
                    archive = chunk
                elif archive:
                    archive += chunk
                if len(archive) > 16 * 1024 * 1024:
                    raise ValueError('压缩文件过大，无法安全检查密钥')
                lo, hi = max(0, offset-position), min(len(chunk), offset+limit-position)
                if lo < hi:
                    page += chunk[lo:hi]
                position += len(chunk)
                tail = window[-overlap:]
                current = os.fstat(handle.fileno())
                if (current.st_size, current.st_mtime_ns, current.st_ctime_ns) != (
                        before.st_size, before.st_mtime_ns, before.st_ctime_ns):
                    raise ValueError('文件读取期间已变化，请重新分页')
            if archive:
                from .shared_artifacts import _clean
                import zipfile
                try:
                    _clean(archive)
                except (zipfile.BadZipFile, RuntimeError) as exc:
                    raise ValueError('压缩文件无法安全检查密钥，请读取已展开产物') from exc
            after = os.fstat(handle.fileno())
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('文件读取期间已变化，请重新分页')
            sha = digest.hexdigest()
            if args.get('expected_sha256') and args['expected_sha256'] != sha:
                raise ValueError('文件版本已变化，分页哈希不一致')
            try:
                content, encoding = page.decode('utf-8'), 'utf-8'
            except UnicodeDecodeError:
                content, encoding = base64.b64encode(page).decode(), 'base64'
            result = {'scope': scope, 'path': '/'.join(parts), 'source_path': str(source),
                      'sha256': sha, 'size': position, 'offset': offset, 'bytes': len(page),
                      'next_offset': offset+len(page) if offset+len(page) < position else None,
                      'content': content, 'encoding': encoding, 'content_is_untrusted': True}
    except OSError as exc:
        raise ValueError('文件不可读，或路径包含符号链接/越界') from exc
    db.append_event(run_id, 'brain', 'brain.file_read',
                    {key: value for key, value in result.items() if key not in ('content', 'encoding')})
    return result


async def tracked_access(run_id,args):
    from . import resource_coordinator
    return await resource_coordinator.tracked_thread(access,run_id,args,owner_prefix='pi-file-')


async def drain():
    from . import resource_coordinator
    await resource_coordinator.drain_threads(prefix='pi-file-')


class _Directory:
    def __init__(self, fd): self.fd = fd
    def __enter__(self): return self
    def __exit__(self, *_): os.close(self.fd)
