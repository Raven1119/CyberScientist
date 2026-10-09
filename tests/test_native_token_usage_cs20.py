"""Native cumulative accounting, duplicates, hours, resets, and read-only scope."""
import importlib.util
import json
from pathlib import Path
import sqlite3

spec = importlib.util.spec_from_file_location('native_token_usage', Path(__file__).resolve().parents[1] / 'scripts/native_token_usage.py')
usage = importlib.util.module_from_spec(spec);spec.loader.exec_module(usage)


def write(path, frames):
    path.write_text('\n'.join(json.dumps(row) for row in frames) + '\n')
    return path


def event(kind, time, **fields):
    return {'timestamp': time, 'type': 'event_msg', 'payload': {'type': kind, **fields}}


def tokens(time, input, output, reasoning, last_input):
    return event('token_count', time, info={'total_token_usage': {'input_tokens':input,
        'output_tokens':output,'reasoning_output_tokens':reasoning,'cached_input_tokens':0},
        'last_token_usage':{'input_tokens':last_input}})


def test_hour_deltas_pi_turn_inputs_and_duplicate_notifications(tmp_path):
    one = tokens('2026-10-09T01:58:00Z', 100, 10, 4, 100)
    path = write(tmp_path/'native.jsonl', [
        {'type':'session_meta','payload':{'id':'synthetic-pi'}},
        event('task_started','2026-10-09T01:57:00Z',turn_id='first'),one,one,
        tokens('2026-10-09T02:01:00Z',250,30,9,150),
        event('task_complete','2026-10-09T02:02:00Z',turn_id='first'),
        event('task_started','2026-10-09T02:03:00Z',turn_id='second'),
        tokens('2026-10-09T02:04:00Z',450,35,10,200)])
    before = path.read_bytes()
    data = usage.summarize([('pi',path),('pi',path)])
    assert data['by_role'][0]['input_tokens'] == 450
    assert data['by_role'][0]['output_tokens'] == 35
    assert data['by_role'][0]['reasoning_output_tokens'] == 10
    assert [row['input_tokens'] for row in data['by_role_hour']] == [100,350]
    assert [row['hour'] for row in data['by_role_hour']] == ['2026-10-09T09:00:00+08:00','2026-10-09T10:00:00+08:00']
    assert data['pi_turn_count'] == 2
    assert data['pi_turns'][0]['first_request_input_tokens'] == 100
    assert data['pi_turns'][0]['last_request_input_tokens'] == 150
    assert data['pi_turns'][0]['tokens']['input_tokens'] == 250
    assert data['pi_turns'][0]['usage_events'] == 2
    assert not data['unknown_observations']
    assert path.read_bytes() == before


def test_since_uses_earlier_baseline_instead_of_counting_whole_session(tmp_path):
    path = write(tmp_path/'native.jsonl',[tokens('2026-10-09T01:00:00Z',100,10,1,100),
        tokens('2026-10-09T02:00:00Z',150,15,2,50)])
    data = usage.summarize([('executor',path)], since='2026-10-09T01:30:00Z')
    assert data['by_role'][0]['input_tokens'] == 50
    assert data['by_role'][0]['output_tokens'] == 5


def test_compaction_reset_and_missing_fields_are_unknown_without_guessing_cost(tmp_path):
    path = write(tmp_path/'native.jsonl', [tokens('2026-10-09T01:00:00Z',100,10,3,100),
        {'timestamp':'2026-10-09T01:30:00Z','type':'compacted','payload':{}},
        tokens('2026-10-09T01:31:00Z',20,2,1,20),
        tokens('2026-10-09T01:32:00Z',30,5,2,10)])
    data = usage.summarize([('pi',path)])
    assert data['sessions'][0]['compaction_events_seen'] == 1
    assert data['by_role'][0]['input_tokens'] == 110
    assert data['unknown_observations'][0]['reason'] == 'cumulative_counter_regressed'
    missing = write(tmp_path/'missing.jsonl', [event('token_count','2026-10-09T02:00:00Z',
        info={'total_token_usage':{'input_tokens':11,'output_tokens':5}})])
    data = usage.summarize([('executor',missing)])
    assert data['by_role'][0]['reasoning_output_tokens'] is None
    assert 'missing_metrics' in data['unknown_observations'][0]['reason']


def test_absent_usage_and_partial_row_do_not_become_zero_or_leak_text(tmp_path):
    path = tmp_path/'native.jsonl';path.write_text('{"PRIVATE_TEXT_NOT_LOGGED"')
    data = usage.summarize([('pi',path)])
    assert data['by_role'][0]['input_tokens'] is None
    assert 'PRIVATE_TEXT_NOT_LOGGED' not in json.dumps(data)
    assert len(data['unknown_observations']) == 2


def test_controller_bound_paths_discovery_does_not_write_database(tmp_path):
    root = tmp_path / 'runtime'
    directory = root/'.cyberscientist';directory.mkdir(parents=True)
    database = directory/'cyberscientist.db'
    with sqlite3.connect(database) as conn:
        conn.execute('CREATE TABLE events(run_id TEXT,type TEXT,payload TEXT)')
        for rid in ('wanted','other'):
            conn.execute('INSERT INTO events VALUES(?,?,?)',(rid,'session.configuration',
                json.dumps({'role':'brain','native_log_path':'/synthetic/'+rid+'.jsonl'})))
    before = database.read_bytes()
    assert usage.native_sessions(root,'wanted') == [('pi',Path('/synthetic/wanted.jsonl'))]
    assert database.read_bytes() == before


def test_newly_reported_metric_without_prior_baseline_is_not_invented_delta(tmp_path):
    path = write(tmp_path/'native.jsonl', [event('token_count','2026-10-09T01:00:00Z',
        info={'total_token_usage':{'input_tokens':100,'output_tokens':30}}),
        tokens('2026-10-09T02:00:00Z',200,60,40,100),
        tokens('2026-10-09T03:00:00Z',300,90,50,100)])
    data = usage.summarize([('pi',path)])
    assert data['by_role'][0]['input_tokens'] == 300
    assert data['by_role'][0]['reasoning_output_tokens'] == 10
    assert 'missing_prior_metrics' in data['unknown_observations'][1]['reason']
    assert data['pi_turn_count'] is None
