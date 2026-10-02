"""Controlled tools return failure facts to the caller, without pausing/replaying."""
import io
import json
import urllib.error

import pytest

from cyberscientist import collab, compute, db, mcp_bridge, sandboxes, tool_feedback
from cyberscientist.api import create_app
from test_final_candidate_integrity import _run_with_scorer


@pytest.mark.parametrize('tool,method,payload', [
    ('job', 'submit', {'action': 'submit', 'operation_id': 'uncertain-job', 'spec': {}}),
    ('bohr', 'cli', {'args': ['job', 'download', '-j', '1', '-o', 'out']}),
    ('sandbox', 'dispatch', {'action': 'files.write', 'operation_id': 'uncertain-transfer'})])
async def test_failed_tool_facts_reach_executor_and_run_remains_running(monkeypatch, tool, method, payload):
    from httpx import ASGITransport, AsyncClient
    rid, tid, *_ = _run_with_scorer()
    app = create_app()
    with db.transaction() as conn:
        token = collab.issue_token(conn, rid, 'executor', 'test-session', 1)
    calls = []
    def failed(*args, **kwargs):
        calls.append(args)
        return {'status': 'unknown' if tool != 'bohr' else 'failed', 'ok': False,
                'operation_id': 'uncertain', 'receipt': {'ok': False, 'unknown': True,
                    'stderr': 'original transport timeout'}}
    monkeypatch.setattr(sandboxes if tool == 'sandbox' else compute, method, failed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://local') as client:
        response = await client.post('/api/v1/tools/' + tool, json=payload,
                                     headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 200 and len(calls) == 1
    facts = response.json()['failure_feedback']
    assert facts['possible_remote_effect'] == 'unknown' and facts['automatic_resend'] is False
    assert facts['choices'] and 'transport timeout' in str(facts['cause'])
    assert db.query_one('SELECT phase FROM runs WHERE id=?', (rid,))['phase'] == 'running'
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='tool.failure_returned'", (rid,))


def test_bridge_preserves_full_structured_failure_without_replay(monkeypatch):
    facts = tool_feedback.failure('sandbox.files.write', 'x'*1000 + 'specific cause', operation_id='stable')
    body = {'detail': {'code': 'TRANSFER_FAILED'}, 'failure_feedback': facts}
    calls = []
    def failed(*a, **k):
        calls.append(1)
        raise urllib.error.HTTPError('http://local', 409, 'failure', {}, io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(mcp_bridge.urllib.request, 'urlopen', failed)
    result = mcp_bridge._post('/api/v1/tools/sandbox', {}, retry_transient=False)
    assert result['failure_feedback'] == facts and result['detail']['code'] == 'TRANSFER_FAILED'
    assert calls == [1] and mcp_bridge._tool_result(result)['isError']


def test_unknown_sandbox_dispatch_exception_is_recorded_without_reexecution(monkeypatch):
    from test_executor_scoring import _setup
    rid, tid, sid, prepared, _ = _setup(monkeypatch)
    calls = []
    def lost(*args, **kwargs):
        calls.append(args)
        raise RuntimeError('unknown dispatch outcome')
    monkeypatch.setattr(compute, '_native', lost)
    result = sandboxes.execute(rid, sid, prepared['command'], 120, 'unknown-exec')
    assert result['status'] == 'unknown' and len(calls) == 1
    with pytest.raises(compute.ComputeError, match='不自动重复执行'):
        sandboxes.execute(rid, sid, prepared['command'], 120, 'unknown-exec')
    assert len(calls) == 1
    row = db.query_one("SELECT * FROM compute_sandbox_operations WHERE operation_id='unknown-exec'")
    assert row['status'] == 'unknown' and row['receipt_sha256']
