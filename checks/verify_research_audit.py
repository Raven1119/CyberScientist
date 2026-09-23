"""Verify a frozen prefix of a research audit without modifying its contents."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def verify(root: Path):
    lines = (root / 'index.jsonl').read_bytes().splitlines(keepends=True)
    # A concurrent append can be incomplete; verify the complete prefix only.
    incomplete_tail = bool(lines and not lines[-1].endswith(b'\n'))
    if incomplete_tail:
        lines.pop()
    records = [json.loads(line) for line in lines]
    if not records:
        raise ValueError('No complete audit records')
    previous = None
    referenced = set()
    bytes_checked = 0

    def object_bytes(key):
        nonlocal bytes_checked
        if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid content-addressed object key')
        path = root / 'objects' / key
        if path.is_symlink():
            raise ValueError(f'Unexpected object symlink: {key}')
        data = path.read_bytes()
        if key not in referenced:
            if hashlib.sha256(data).hexdigest() != key:
                raise ValueError(f'Object checksum mismatch: {key}')
            referenced.add(key)
            bytes_checked += len(data)
        return data

    for record in records:
        payload = {k: v for k, v in record.items() if k != 'record_sha256'}
        if hashlib.sha256(encoded(payload)).hexdigest() != record['record_sha256']:
            raise ValueError('Index record checksum mismatch')
        if record['previous_record_sha256'] != previous:
            raise ValueError('Broken audit index chain')
        if record['run_id'] != records[0]['run_id']:
            raise ValueError('Mixed Run IDs in audit index')
        entries = record['entries']
        database = json.loads(object_bytes(entries['database_state']))
        events = database.get('events', [])
        if sorted(e['seq'] for e in events) != list(range(1, record['latest_seq'] + 1)):
            raise ValueError(f'Event sequence gap at {record["captured_at"]}')
        if any(e['run_id'] != record['run_id'] for e in events):
            raise ValueError('Wrong Run ID in events')
        if 'runtime_source_hashes' in entries:
            object_bytes(entries['runtime_source_hashes'])
        for session in entries.get('native_public_sessions', []):
            object_bytes(session['object'])
        if 'workspace_artifacts' in entries:
            artifacts = json.loads(object_bytes(entries['workspace_artifacts']))
            for artifact in artifacts:
                for chunk in artifact.get('chunks', []):
                    if chunk not in referenced:
                        object_bytes(chunk)
        previous = record['record_sha256']
    latest = records[-1]
    result = {'run_id': latest['run_id'], 'through': latest['captured_at'],
              'records_verified': len(records), 'objects_verified': len(referenced),
              'object_bytes_verified': bytes_checked, 'events_through': latest['latest_seq'],
              'incomplete_index_tail_excluded': incomplete_tail,
              'runtime_source_changes': latest['runtime_source_changes'],
              'last_record_sha256': latest['record_sha256'],
              'scope': 'Local content hashes and event continuity; no external signature or scientific validation'}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit_directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.audit_directory), ensure_ascii=False, indent=2))
