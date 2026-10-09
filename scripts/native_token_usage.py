#!/usr/bin/env python3
"""Read-only Codex native usage by role/hour and PI turn; stdlib only.

Usage: python scripts/native_token_usage.py --root /path/to/runtime --run-id run_ID
Or:    python scripts/native_token_usage.py --session pi=/path/to/native.jsonl
No credentials, model calls, application imports or database writes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

METRICS = ('input_tokens', 'output_tokens', 'reasoning_output_tokens', 'cached_input_tokens')


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def native_sessions(root: Path, run_id: str | None):
    """Use only controller-bound native paths, with SQLite mode=ro/query_only."""
    database = root / '.cyberscientist/cyberscientist.db'
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        rows = connection.execute("SELECT payload FROM events WHERE type='session.configuration'"
            + (' AND run_id=?' if run_id else '') + ' ORDER BY rowid', (run_id,) if run_id else ())
        result = []
        for (raw,) in rows:
            payload = json.loads(raw)
            if payload.get('native_log_path'):
                result.append(('pi' if payload.get('role') == 'brain' else payload.get('role') or 'unknown',
                    Path(payload['native_log_path'])))
        return result


def summarize(sessions, *, zone='Asia/Shanghai', since=None):
    tz = ZoneInfo(zone)
    after = timestamp(since) if since else None
    if since and after is None:
        raise ValueError('Invalid --since ISO timestamp')
    hours = {}
    totals = {}
    turns = []
    facts = []
    unknown = []
    seen = {}
    seen_ids = set()

    def issue(path, line, reason):
        unknown.append({'path': str(path), 'line': line, 'reason': reason})

    def bucket(mapping, key):
        return mapping.setdefault(key, {'observed': {name: 0 for name in METRICS}, 'seen_metrics': set()})

    def add(target, counts):
        for name, value in counts.items():
            target['observed'][name] += value
            target['seen_metrics'].add(name)

    def public(target):
        return {name: target['observed'][name] if name in target['seen_metrics'] else None for name in METRICS}

    for role, path in sessions:
        path = Path(path).resolve()
        if path in seen:
            if seen[path] != role:
                issue(path, 0, 'same_native_file_bound_to_multiple_roles')
            continue
        seen[path] = role
        counts_before = {}
        snapshots_seen = 0
        current = None
        usage_events = 0
        compactions = 0
        sid = None
        try:
            with path.open(encoding='utf-8') as stream:
                for line_number, line in enumerate(stream, 1):
                    try:
                        row = json.loads(line)
                    except (ValueError, UnicodeError):
                        issue(path, line_number, 'invalid_or_partial_native_json');continue
                    if not isinstance(row, dict):
                        issue(path, line_number, 'native_row_not_object');continue
                    body = row.get('payload') or {}
                    if not isinstance(body, dict):continue
                    time = timestamp(row.get('timestamp'))
                    selected = not after or time is not None and time >= after
                    if row.get('type') == 'session_meta':
                        sid = body.get('id')
                        if sid and sid in seen_ids:
                            issue(path, line_number, 'duplicate_native_session_id');break
                        if sid:seen_ids.add(sid)
                    kind = body.get('type') if row.get('type') == 'event_msg' else None
                    if row.get('type') == 'compacted' or kind == 'context_compacted':
                        if selected:compactions += 1
                    if kind == 'task_started':
                        current = {'session_id': sid, 'turn_id': body.get('turn_id'), 'role': role,
                            'started_at': row.get('timestamp'), 'completed_at': None,
                            'first_request_input_tokens': None, 'last_request_input_tokens': None,
                            'usage_events': 0, 'counts': bucket({}, 'turn'), 'selected': selected}
                        if role == 'pi':turns.append(current)
                    if kind == 'task_complete' and current and body.get('turn_id') == current['turn_id']:
                        current['completed_at'] = row.get('timestamp')
                    if kind != 'token_count' or not isinstance(body.get('info'), dict):continue
                    info = body['info']
                    cumulative = info.get('total_token_usage')
                    if not isinstance(cumulative, dict):
                        if selected:issue(path, line_number, 'missing_cumulative_usage')
                        continue
                    counts = {name: value for name in METRICS
                        if type(value := cumulative.get(name)) is int and value >= 0}
                    if not {'input_tokens', 'output_tokens'} <= counts.keys():
                        if selected:issue(path, line_number, 'missing_input_or_output_usage')
                        continue
                    regression = any(counts[name] < counts_before.get(name, 0) for name in counts)
                    unbased = set(counts) - counts_before.keys() if snapshots_seen else set()
                    delta = {name: value - counts_before.get(name, 0) for name, value in counts.items()
                        if name not in unbased}
                    # Resynchronize after a reset, but never guess its cost.
                    counts_before = counts
                    snapshots_seen += 1
                    if unbased and selected:issue(path, line_number, 'missing_prior_metrics:' + ','.join(sorted(unbased)))
                    if regression:
                        if selected:issue(path, line_number, 'cumulative_counter_regressed')
                        continue
                    if not any(delta.values()):continue  # Repeated notification, not another model request.
                    if selected:
                        usage_events += 1
                        hour = time.astimezone(tz).replace(minute=0, second=0, microsecond=0).isoformat() if time else 'unknown'
                        add(bucket(hours, (role, hour)), delta)
                        add(bucket(totals, role), delta)
                        if time is None:issue(path, line_number, 'usage_timestamp_unknown')
                        missing = set(METRICS) - counts.keys()
                        if missing:issue(path, line_number, 'missing_metrics:' + ','.join(sorted(missing)))
                    if current:
                        add(current['counts'], delta)
                        current['usage_events'] += 1
                        last = info.get('last_token_usage') or {}
                        input_size = last.get('input_tokens')
                        if type(input_size) is int and input_size >= 0:
                            if current['first_request_input_tokens'] is None:current['first_request_input_tokens'] = input_size
                            current['last_request_input_tokens'] = input_size
                        if selected:current['selected'] = True
            if not usage_events:
                # No observed usage is unknown, not a free session.
                bucket(totals, role)
                issue(path, 0, 'no_usage_observed_in_selected_interval')
            facts.append({'role': role, 'path': str(path), 'session_id': sid,
                'usage_events': usage_events, 'compaction_events_seen': compactions})
        except (OSError, UnicodeError):
            issue(path, 0, 'native_file_unavailable');bucket(totals, role)
    pi = []
    for turn in turns:
        if not turn['selected']:continue
        pi.append({key: value for key, value in turn.items() if key not in ('counts','selected')}
            | {'tokens': public(turn['counts'])})
    return {'source': 'native event_msg/token_count cumulative deltas', 'timezone': zone,
        'hour_assignment': 'timestamp of observed usage delta; crossing-hour requests are not split',
        'turn_assignment': 'full observed PI turns intersecting the selected interval',
        'reasoning_is_subset_of_output': True,
        'accounting': 'known observed deltas only; missing counters/intervals listed in unknown_observations',
        'sessions': facts,
        'by_role': [{'role': role, **public(value)} for role, value in sorted(totals.items())],
        'by_role_hour': [{'role': role, 'hour': hour, **public(value)} for (role, hour), value in sorted(hours.items())],
        'pi_turn_count': len(pi) if pi else None, 'pi_turns': pi, 'unknown_observations': unknown,
        'limits': 'unknown; read current native account/rateLimits/read separately'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--session', action='append', default=[], metavar='ROLE=FILE')
    parser.add_argument('--timezone', default='Asia/Shanghai')
    parser.add_argument('--since')
    args = parser.parse_args()
    if not args.root and not args.session:parser.error('Use --root or --session')
    sessions = native_sessions(args.root, args.run_id) if args.root else []
    for value in args.session:
        if '=' not in value:parser.error('--session requires ROLE=FILE')
        role, path = value.split('=', 1)
        if not role or not path:parser.error('--session requires ROLE=FILE')
        sessions.append((role, Path(path)))
    print(json.dumps(summarize(sessions, zone=args.timezone, since=args.since), ensure_ascii=False, indent=2))


if __name__ == '__main__':main()
