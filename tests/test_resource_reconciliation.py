"""Observed old Job API shape, synthetic names/costs only."""
import json

import pytest

from cyberscientist import compute, config, db
from test_compute_gateway import run, spec, receipt


def _api_credentials():
    settings = config.load_settings()
    settings['bohrium']['access_key_secret_ref'] = 'local:fixture-api'
    config.save_settings(settings)
    config.update_secret('fixture-api', 'synthetic-key-never-in-receipts')


def test_query_uses_verified_paging_and_projects_account_fields(monkeypatch):
    _api_credentials()
    def get(url, **kwargs):
        assert url.endswith('/openapi/v1/job/list')
        assert kwargs['params']['pageSize'] == 100 and 'perPage' not in kwargs['params']
        assert kwargs['params']['accessKey'] == 'synthetic-key-never-in-receipts'
        class Response:
            def raise_for_status(self): pass
            def json(self):
                return {'code': 0, 'data': {'page': 1, 'totalPage': 2,
                    'items': [{'id': 123, 'jobName': 'synthetic', 'status': 2,
                               'cost': '0.12', 'spendTime': 30,
                               'userName': 'private account', 'userId': 99}]}}
        return Response()
    import httpx
    monkeypatch.setattr(httpx, 'get', get)
    projected = compute._job_page(1)
    assert projected['items'][0]['cost'] == '0.12'
    assert 'userId' not in json.dumps(projected) and 'private account' not in json.dumps(projected)
    assert 'synthetic-key' not in json.dumps(projected)


def test_partial_page_failure_preserves_exact_match_and_does_not_release_absence(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *args, **kwargs: receipt('', False))
    compute.submit(rid, 'uncertain-reservation', spec(), str(source))
    row = compute.list_jobs(rid)['items'][0]
    _api_credentials()
    calls = []
    def page(number):
        calls.append(number)
        if number == 1:
            return {'page': 1, 'total_pages': 2, 'items': [{
                'id': 123, 'jobName': row['spec']['job_name'], 'status': 2,
                'cost': '0.12', 'spendTime': 30}]}
        raise compute.ComputeError('JOB_OBSERVATION_UNKNOWN', 'synthetic timeout')
    monkeypatch.setattr(compute, '_job_page', page)
    # A second wanted name forces page 2; page 1's successful observation survives.
    unknown = dict(row['spec'], job_name='cs-unresolved-synthetic')
    db.execute("INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,spec_json,"
               "input_directory,status,created_at,updated_at) VALUES(?,?,?,?,?,?,'unknown',?,?)",
               ('unresolved', rid, row['trial_id'], 'hash', json.dumps(unknown),
                str(source), db.utcnow(), db.utcnow()))
    result = compute.reconcile(rid)
    by_id = {item['operation_id']: item for item in result['items']}
    assert by_id['uncertain-reservation']['platform_job_id'] == 123
    assert by_id['uncertain-reservation']['status'] == 'Finished'
    assert by_id['unresolved']['status'] == 'unknown'
    assert by_id['unresolved']['platform_job_id'] is None
    assert calls == [1, 2]
    billing = by_id['uncertain-reservation']['receipt']['billing']
    assert billing['native_amount'] == '0.12' and billing['currency'] is None
    assert compute.costs(rid)['total_amount'] is None
    assert compute.costs(rid)['job_native_amount_total'] == '0.12'
    assert 'synthetic-key' not in json.dumps(result)
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='job.reservation_unresolved'", (rid,))


def test_unverified_numeric_status_cannot_resolve_unknown(run, monkeypatch):
    rid, source = run
    monkeypatch.setattr(compute, '_native', lambda *args, **kwargs: receipt('', False))
    compute.submit(rid, 'unknown-state', spec(), str(source))
    row = compute.list_jobs(rid)['items'][0]
    _api_credentials()
    monkeypatch.setattr(compute, '_job_page', lambda page: {
        'page': 1, 'total_pages': 1, 'items': [{'id': 123,
            'jobName': row['spec']['job_name'], 'status': 999}]})
    compute.reconcile(rid)
    job = compute.list_jobs(rid)['items'][0]
    assert job['platform_job_id'] is None and job['status'] == 'unknown'
