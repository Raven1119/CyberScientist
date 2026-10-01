"""Candidate-independent prebuilt environments, promoted by backend receipts.

Recipes declare requirements; a recipe is never evidence of a built image.
No agent tool can register or publish an environment.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import config, db


class EnvironmentUnavailable(ValueError):
    pass


def recipe(environment_id: str) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', environment_id):
        raise EnvironmentUnavailable('无效环境标识')
    root = config.WORKSPACE_ROOT / 'environments' / environment_id
    descriptor = root / 'environment.json'
    if root.is_symlink() or descriptor.is_symlink() or not descriptor.is_file():
        raise EnvironmentUnavailable('预置环境配方缺失')
    data = json.loads(descriptor.read_text())
    dockerfile = root / 'Dockerfile'
    if dockerfile.is_symlink() or not dockerfile.is_file():
        raise EnvironmentUnavailable('预置环境 Dockerfile 缺失')
    data['dockerfile_sha256'] = hashlib.sha256(dockerfile.read_bytes()).hexdigest()
    data['recipe_sha256'] = hashlib.sha256(descriptor.read_bytes()).hexdigest()
    return data


def resolve(environment_id: str) -> dict:
    expected = recipe(environment_id)
    row = db.query_one('SELECT * FROM runtime_environments WHERE id=?', (environment_id,))
    if (not row or row['status'] != 'verified'
            or row['recipe_sha256'] != expected['recipe_sha256']
            or row['dockerfile_sha256'] != expected['dockerfile_sha256']):
        raise EnvironmentUnavailable('预置环境尚无可验证的镜像回执：' + environment_id)
    return expected | {'image': row['image_address'],
                       'platform_image_id': row['platform_image_id'], 'status': 'verified'}


def facts() -> list[dict]:
    root = config.WORKSPACE_ROOT / 'environments'
    result = []
    for path in sorted(root.glob('*/environment.json')):
        try:
            data = recipe(path.parent.name)
            try:
                data = resolve(path.parent.name)
            except EnvironmentUnavailable:
                data = data | {'image': None, 'status': 'unverified'}
            result.append(data)
        except (EnvironmentUnavailable, ValueError, OSError):
            continue
    return result


def register_verified(environment_id: str, *, image_address: str, platform_image_id: str,
                      observed_descriptor: dict, receipt_sha256: str) -> None:
    """Backend acceptance only; fail closed on identity or observed version mismatch."""
    data = recipe(environment_id)
    if (not re.fullmatch(r'registry\.[A-Za-z0-9./:_-]+', image_address)
            or not platform_image_id or not re.fullmatch(r'[a-f0-9]{64}', receipt_sha256)
            or any(observed_descriptor.get(key) != value for key, value in data['identity'].items())):
        raise EnvironmentUnavailable('环境回执与固定版本要求不符')
    db.execute('INSERT INTO runtime_environments(id,recipe_sha256,dockerfile_sha256,'
               'image_address,platform_image_id,status,receipt_sha256,observed_at)'
               " VALUES(?,?,?,?,?,'verified',?,?) ON CONFLICT(id) DO UPDATE SET"
               ' recipe_sha256=excluded.recipe_sha256,dockerfile_sha256=excluded.dockerfile_sha256,'
               'image_address=excluded.image_address,platform_image_id=excluded.platform_image_id,'
               'status=excluded.status,receipt_sha256=excluded.receipt_sha256,observed_at=excluded.observed_at',
               (environment_id, data['recipe_sha256'], data['dockerfile_sha256'], image_address,
                platform_image_id, receipt_sha256, db.utcnow()))
