"""Successful creates are observations, never guarantees of platform cache life."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from . import db


def record_success(image: str, operation_id: str, sandbox_id: str, receipt: dict,
                   *, observed_at: str | None = None) -> dict:
    """Backend maintenance callers must bind the image/request before this call."""
    from . import sandboxes
    body = sandboxes._body(receipt)
    if (not receipt.get('ok') or receipt.get('unknown') or receipt.get('truncated')
            or not isinstance(body, dict) or body.get('ok') is False
            or sandboxes._sandbox_id(body) != sandbox_id or not image or not operation_id):
        raise ValueError('需要绑定资源的成功创建回执，不能由构建完成或目录登记推断预热')
    observed_at = observed_at or db.utcnow()
    if not datetime.fromisoformat(observed_at).tzinfo:
        raise ValueError('创建观察时间需要时区')
    image_sha = hashlib.sha256(image.encode()).hexdigest()
    value = {'image_sha256': image_sha, 'operation_id': operation_id,
             'sandbox_id': sandbox_id, 'created_success_at': observed_at,
             'receipt_sha256': hashlib.sha256(json.dumps(sandboxes._receipt(receipt), sort_keys=True).encode()).hexdigest(),
             'cache_validity_seconds': None, 'rewarm_interval_seconds': None}
    # One immutable observation per operation; preserve old observations.
    kind = 'sandbox-create:' + image_sha + ':' + operation_id
    db.execute('INSERT OR IGNORE INTO runtime_observations VALUES(?,?,?)',
               (kind, json.dumps(value, sort_keys=True), observed_at))
    return value


def latest() -> list[dict]:
    from . import environment_catalog
    facts = {}
    for row in db.query("SELECT * FROM runtime_observations WHERE kind LIKE 'sandbox-create:%' ORDER BY observed_at"):
        value = json.loads(row['payload_json'])
        facts[value['image_sha256']] = value
    return [{'entry_id': entry['id'], 'image_sha256': hashlib.sha256(entry['image'].encode()).hexdigest(),
             'created_success_at': facts.get(hashlib.sha256(entry['image'].encode()).hexdigest(), {}).get('created_success_at'),
             'cache_validity_seconds': None, 'rewarm_interval_seconds': None}
            for entry in environment_catalog.items() if entry.get('image')]
