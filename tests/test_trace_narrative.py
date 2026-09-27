"""W1 narrative facts must be backed by durable, cutoff-bounded Run events."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from cyberscientist import collab, config, db, mailboxes, mcp_bridge, package_seal, trace_narrative
from test_mailboxes import _make_run, _seed_challenge, _set_scored


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buf.getvalue()


def _fixture():
    _seed_challenge()
    rid = _make_run(prediction_required=True)
    tid = 'trial_narrative'
    db.execute("INSERT INTO trials(id,run_id,goal,success_check,status,created_at)"
               " VALUES(?,?,'test','test','active',?)", (tid, rid, db.utcnow()))
    db.execute('UPDATE runs SET current_trial_id=? WHERE id=?', (tid, rid))
    first = db.append_event(rid, 'prime', 'prime.execution.progress',
                            {'item_id': 'tool-1', 'status': 'started',
                             'detail': 'run science'}, trial_id=tid)
    second = db.append_event(rid, 'prime', 'prime.execution.progress',
                             {'item_id': 'tool-1', 'status': 'completed',
                              'detail': 'complete', 'output': 'answer=42',
                              'exit_code': 0}, trial_id=tid)
    extra = db.append_event(rid, 'controller', 'job.accepted',
                            {'operation_id': 'job-evidence'}, trial_id=tid)
    files = {
        'arm_manifest.json': json.dumps({
            'arm_version': '1.1', 'entrypoint': 'run.py',
            'trace': 'traces/trace.jsonl',
            'execution': {'log_path': 'run.log', 'artifacts': [{'path': 'result.txt'}]}
        }).encode(),
        'run.py': b'print(42)\n', 'run.log': b'answer=42\n',
        'result.txt': b'42\n',
        'traces/trace.jsonl': b'{"step_type":"observation","title":"original"}\n',
    }
    package = _zip(files)
    trial_dir = config.WORKSPACE_DIR / 'runs' / rid / 'trials' / tid
    trial_dir.mkdir(parents=True, exist_ok=True)
    (trial_dir / 'result_package.zip').write_bytes(package)
    rows = [{"step_type": "tool_call", "title": "run science",
             "tool_call_id": "tool-1", "timestamp": first['recorded_at'],
             "cs_refs": [f"{rid}#{first['seq']}"]},
            {"step_type": "tool_result", "title": "output",
             "tool_call_id": "tool-1", "tool_output": "answer=42", "exit_code": 0,
             "timestamp": second['recorded_at'],
             "cs_refs": [f"{rid}#{second['seq']}"]},
            {"step_type": "artifact", "title": "saved result",
             "artifact_path": "result.txt",
             "sha256": hashlib.sha256(files['result.txt']).hexdigest(),
             "timestamp": second['recorded_at'],
             "cs_refs": [f"{rid}#{second['seq']}"]}]
    return rid, tid, package, files, rows, first, second, extra, trial_dir


def _raw(rows):
    return ('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n').encode()


@pytest.mark.parametrize('mutate,expected', [
    (lambda rows, ctx: rows[0].update(tool_call_id='invented'), 'tool_call_id'),
    (lambda rows, ctx: rows[1].update(tool_output='answer=99'), 'tool_output'),
    (lambda rows, ctx: rows[0].update(timestamp='2000-01-01T00:00:00Z'), 'timestamp'),
    (lambda rows, ctx: rows[0].update(annotation=True), '事后注释'),
    (lambda rows, ctx: rows[0].update(cs_refs=[f'{ctx[0]}#999999']), '超过封存'),
    (lambda rows, ctx: rows[0].update(cs_refs=['other-run#1']), '引用不存在'),
    (lambda rows, ctx: rows[0].pop('cs_refs'), 'cs_refs'),
    (lambda rows, ctx: rows[2].update(artifact_path='missing.txt'), 'artifact_path'),
    (lambda rows, ctx: rows[0].update(cost_usd=12.0), 'cost_usd'),
])
def test_invalid_narrative_reason_is_line_specific(mutate, expected):
    ctx = _fixture()
    rid, tid, package, files, rows, first, second, extra, trial_dir = ctx
    mutate(rows, ctx)
    with pytest.raises(trace_narrative.InvalidTraceNarrative) as error:
        package_seal.seal(package, rid, tid, second['seq'],
                          narrative_bytes=_raw(rows))
    assert any(expected in reason and '第 ' in reason for reason in error.value.reasons)


def test_valid_narrative_is_deterministic_and_keeps_uncovered_projection():
    rid, tid, package, files, rows, first, second, extra, trial_dir = _fixture()
    written_at = datetime.now(timezone.utc).isoformat()
    rows.append({'step_type': 'observation', 'title': '事后说明',
                 'annotation': True, 'timestamp': written_at,
                 'cs_refs': [f"{rid}#{second['seq']}"]})
    raw = _raw(rows)
    first_bytes, merged = package_seal.seal(
        package, rid, tid, extra['seq'], narrative_bytes=raw,
        narrative_written_at=written_at)
    second_bytes, again = package_seal.seal(
        package, rid, tid, extra['seq'], narrative_bytes=raw,
        narrative_written_at=written_at)
    assert first_bytes == second_bytes and merged == again
    assert merged[:len(rows)] == rows
    assert any(row.get('tool_call_id') == 'job:job-evidence' for row in merged)
    assert not any(row.get('title') == 'original' for row in merged)
    with zipfile.ZipFile(io.BytesIO(first_bytes)) as archive:
        assert archive.read('traces/trace_narrative.jsonl') == raw


def test_preflight_uses_same_narrative_validation_and_read_only_preview():
    rid, tid, package, files, rows, first, second, extra, trial_dir = _fixture()
    narrative = trial_dir / 'trace_narrative.jsonl'
    rows[1]['tool_output'] = 'fabricated'
    narrative.write_bytes(_raw(rows))
    preview = mailboxes.inspect_trace_narrative(rid, tid, None)
    assert preview['error_code'] == 'INVALID_TRACE_NARRATIVE'
    assert any('tool_output' in reason for reason in preview['reasons'])
    assert not db.query_one("SELECT 1 FROM events WHERE run_id=?"
                            " AND type='submission.preflight_failed'", (rid,))
    with pytest.raises(mailboxes.MailboxError) as error:
        mailboxes.preflight_submission(rid, tid, None)
    assert error.value.code == 'INVALID_TRACE_NARRATIVE'
    rows[1]['tool_output'] = 'answer=42'
    narrative.write_bytes(_raw(rows))
    preview = mailboxes.inspect_trace_narrative(rid, tid, None)
    assert preview['valid'] is True
    assert preview['sealed_package_sha256']
    assert any(row['step_type'] == 'tool_result' for row in preview['merged_trace'])


def test_trace_variant_preserves_science_bytes_and_records_provenance(monkeypatch):
    rid, tid, package, files, rows, first, second, extra, trial_dir = _fixture()
    mailboxes.register_experiment(1)
    monkeypatch.setattr(mailboxes.arm_admission, 'check',
                        lambda *_: {'verdict': 'admitted', 'signals': {}})
    source = mailboxes.submit_experiment(rid, tid, None, 'source-baseline',
                                         prediction_md='预计基线总分为 20')
    _set_scored(source['id'], 20)
    (trial_dir / 'trace_narrative.jsonl').write_bytes(_raw(rows))
    variant = mailboxes.submit_trace_variant(source['id'], 'variant-one',
                                             '增加真实工具叙述，预计轨迹分上升')
    assert variant['source_submission_id'] == source['id']
    assert variant['variant_of'] == source['id']
    assert variant['science_artifact_match'] == 1
    assert json.loads(variant['science_artifact_hashes_json']) == mailboxes._science_artifact_hashes(
        (config.WORKSPACE_DIR / source['package_path']).read_bytes())
    source_bytes = (config.WORKSPACE_DIR / source['package_path']).read_bytes()
    variant_bytes = (config.WORKSPACE_DIR / variant['package_path']).read_bytes()
    assert source_bytes != variant_bytes
    assert mailboxes._science_artifact_hashes(source_bytes) == mailboxes._science_artifact_hashes(variant_bytes)
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as original, zipfile.ZipFile(io.BytesIO(variant_bytes)) as changed:
        science_names = set(original.namelist()) - {
            'arm_manifest.json', package_seal.TRACE}
        science_names = {name for name in science_names
                         if not name.startswith('traces/') and not name.startswith('trace/')}
        assert all(original.read(name) == changed.read(name) for name in science_names)
    assert mailboxes.submit_trace_variant(source['id'], 'variant-one',
        '增加真实工具叙述，预计轨迹分上升')['deduplicated'] is True
    rows[0]['title'] = 'different factual wording'
    (trial_dir / 'trace_narrative.jsonl').write_bytes(_raw(rows))
    with pytest.raises(mailboxes.MailboxError) as error:
        mailboxes.submit_trace_variant(source['id'], 'variant-one',
                                       '增加真实工具叙述，预计轨迹分上升')
    assert error.value.code == 'CONFLICT'


async def test_narrative_preview_tool_is_read_only_for_brain_and_executor(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app

    rid, tid, package, files, rows, first, second, extra, trial_dir = _fixture()
    (trial_dir / 'trace_narrative.jsonl').write_bytes(_raw(rows))
    with db.transaction() as conn:
        tokens = [collab.issue_token(conn, rid, role, role, 1)
                  for role in ('brain', 'executor')]
    for role in ('brain', 'executor'):
        monkeypatch.setenv('CS_TOOL_ROLE', role)
        listing = mcp_bridge._handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        assert 'research_trace_narrative_check' in [
            tool['name'] for tool in listing['result']['tools']]
    before = db.query_one('SELECT COUNT(*) AS n FROM submissions')['n']
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://t') as client:
        for token in tokens:
            response = await client.post('/api/v1/tools/trace_narrative_check',
                json={'trial_id': tid}, headers={'Authorization': f'Bearer {token}'})
            assert response.status_code == 200
            assert response.json()['valid'] is True
    assert db.query_one('SELECT COUNT(*) AS n FROM submissions')['n'] == before
