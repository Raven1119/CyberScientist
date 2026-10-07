"""Lossless nullable field projections and small deterministic table operations."""
import csv
import io
import json
import math
from datetime import datetime

from .common import atomic


def number(value):
    if isinstance(value, bool): return None
    try: result = float(value)
    except (TypeError, ValueError): return None
    return result if math.isfinite(result) else None


def timestamp(value):
    if not isinstance(value, str): return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except ValueError: return None


def flatten(value, prefix=''):
    out = {}
    for key, val in value.items():
        name = prefix + key
        if isinstance(val, dict): out.update(flatten(val, name + '.'))
        elif isinstance(val, list): out[name] = json.dumps(val, ensure_ascii=False)
        else: out[name] = val
    return out


def write_csv(path, rows, fields=None):
    if fields is None: fields = sorted({key for row in rows for key in row})
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n', extrasaction='raise')
    writer.writeheader(); writer.writerows(rows)
    atomic(path, output.getvalue().encode())


def attempt_row(attempt, topic, ownership):
    results = attempt.get('resultsJson') or {}
    card = attempt.get('scorecard') or {}
    state = attempt.get('scoringState') or {}
    if not isinstance(results, dict): results = {}
    if not isinstance(card, dict): card = {}
    if not isinstance(state, dict): state = {}
    aid, author = str(attempt['id']), str(attempt.get('authorId') or '')
    score = number(state.get('displayScore'))
    if score is None: score = number(attempt.get('score'))
    science = number(results.get('harbor_score'))
    science_source = 'resultsJson.harbor_score'
    if science is None:
        science = number(card.get('harbor_score')); science_source = 'scorecard.harbor_score'
    trace = number(results.get('trace_score'))
    if trace is None: trace = number(card.get('trace_score'))
    created, start, end = map(timestamp, [attempt.get('createdAt'), topic.get('roundStartAt'), topic.get('roundEndAt')])
    row = {'attempt_id': aid, 'challenge_id': topic['id'], 'round_seq': topic.get('roundSeq'),
        'author_id': author, 'author_name': attempt.get('author_name'),
        'ours': author in ownership or attempt.get('_ours') is True,
        'ours_source': ownership.get(author, 'email_match' if attempt.get('_ours') else None),
        'display_score': score, 'science_score': science,
        'science_score_source': science_source if science is not None else None,
        'trace_score': trace, 'trace_decision': results.get('trace_decision'),
        'trace_engine': results.get('trace_score_engine'),
        'trace_quality_class': results.get('trace_quality_class'),
        'score_is_final': state.get('scoreIsFinal'), 'status': attempt.get('status'),
        'created_at': attempt.get('createdAt'), 'updated_at': attempt.get('updatedAt'),
        'minutes_since_round_start': (created-start).total_seconds()/60 if created and start else None,
        'is_within_round': start <= created < end if created and start and end else None,
        'topic_type': topic.get('disc'), 'trace_count': attempt.get('traceCount'),
        'snapshot_observed_at': attempt.get('_observed_at'),
        'detail_fetch_status': attempt.get('_detail_status'),
        'snapshot_path': attempt.get('_snapshot_path')}
    for key in ('method','detail','execLog','changelog'):
        row[key + '_chars'] = len(attempt[key]) if isinstance(attempt.get(key), str) else None
    for key, value in attempt.items():
        if key.startswith('_') or key in ('method','detail','execLog','changelog'): continue
        if isinstance(value, dict): row.update(flatten(value, 'raw.' + key + '.'))
        elif isinstance(value, list): row['raw.' + key] = json.dumps(value, ensure_ascii=False)
        else: row['raw.' + key] = value
    return row
