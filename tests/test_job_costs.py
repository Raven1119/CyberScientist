"""Owned CPU Job pricing, unknown reservations and unverified duration units."""
import json

import pytest

from cyberscientist import compute, db, job_costs
from test_final_candidate_integrity import _run_with_scorer


def _receipt(**fields):
    item = dict(chooseType='cpu', cpuCoreNum=4, memory=8, gpuCoreNum=0,
                skuEnName='c4_m8_cpu', skuId=240, price=0.32)
    item.update(fields)
    return {'ok': True, 'stdout': json.dumps({'ok': True, 'data': {'items': [item]},
        'meta': {'timestamp': 1790894769}, 'notice': {'balance': 'private data'}})}


def _job(rid, tid, op='owned', **fields):
    values = dict(platform_job_id=1, status='Finished',
        spec_json=json.dumps({'machine_type': 'c4_m8_cpu', 'nnode': 2}),
        receipt_json=json.dumps({'billing': {'source': '/openapi/v1/job/list:cost',
                                  'spend_seconds': 1800, 'native_amount': '0.3', 'currency': None}}))
    values.update(fields)
    now = db.utcnow()
    db.execute('INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,'
        'spec_json,input_directory,platform_job_id,status,receipt_json,created_at,updated_at)'
        ' VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (op,rid,tid,'synthetic',values['spec_json'],'unused',values['platform_job_id'],
         values['status'],values['receipt_json'],now,now))


def test_job_quote_does_not_use_sandbox_rates_or_imply_a_bill(monkeypatch):
    rid, tid, *_ = _run_with_scorer()
    _job(rid, tid)
    assert job_costs.record_prices(rid, _receipt(), scene='job')['rate_count'] == 1
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('offline report'))
    cost = compute.costs(rid)
    assert cost['job_estimate']['amount'] == '0.3200'
    assert cost['job_estimate']['assumed_node_seconds'] == 3600
    assert cost['job_estimate']['duration_unit_verified'] is False
    assert cost['currency'] is None and cost['total_amount'] is None
    assert cost['job_native_amount_total'] == '0.3'
    assert cost['job_estimate']['rate_observed_at'] == '2026-10-01T22:46:09+00:00'
    payload = db.query_one("SELECT payload FROM events WHERE type='job.price_quote'")['payload']
    assert 'private data' not in payload and 'notice' not in payload


@pytest.mark.parametrize('fields', [
    {'price': True}, {'price': 'NaN'}, {'price': -1}, {'gpuCoreNum': 1},
    {'gpuCoreNum': False}, {'cpuCoreNum': True}, {'memory': None},
    {'skuEnName': 'wrong_cpu'}, {'skuId': True}, {'chooseType': 'gpu'}])
def test_invalid_quotes_do_not_fill_missing_cost_with_zero(fields):
    rid, tid, *_ = _run_with_scorer()
    _job(rid, tid)
    job_costs.record_prices(rid, _receipt(**fields), scene='job')
    result = job_costs.estimate(rid)
    assert result['amount'] is None and result['unpriced_count'] == 1


def test_wrong_scene_and_conflicting_quotes_are_rejected():
    rid, *_ = _run_with_scorer()
    assert job_costs.record_prices(rid, _receipt(), scene='sandbox')['status'] == 'unknown'
    receipt = _receipt()
    body = json.loads(receipt['stdout'])
    body['data']['items'].append(body['data']['items'][0] | {'price': 0.8})
    receipt['stdout'] = json.dumps(body)
    assert job_costs.record_prices(rid, receipt, scene='job')['status'] == 'unknown'
    assert not db.query("SELECT 1 FROM events WHERE type='job.price_quote'")


@pytest.mark.parametrize('duration', [True, None, -1, '1800', 1.5, 31536001])
def test_unverified_duration_value_is_unpriced(duration):
    rid, tid, *_ = _run_with_scorer()
    _job(rid, tid, receipt_json=json.dumps({'billing': {
        'source': '/openapi/v1/job/list:cost', 'spend_seconds': duration}}))
    job_costs.record_prices(rid, _receipt(), scene='job')
    assert job_costs.estimate(rid)['amount'] is None


def test_unknown_reservation_is_kept_in_partial_estimate():
    rid, tid, *_ = _run_with_scorer()
    _job(rid, tid)
    _job(rid, tid, op='unknown', status='unknown', platform_job_id=None)
    job_costs.record_prices(rid, _receipt(), scene='job')
    estimate = job_costs.estimate(rid)
    assert estimate['status'] == 'estimated_partial'
    assert estimate['priced_count'] == 1 and estimate['unpriced_count'] == 1
    assert estimate['amount'] == '0.3200'


def test_quote_refresh_reuses_received_quote_without_native_query(monkeypatch):
    rid, tid, *_ = _run_with_scorer()
    _job(rid, tid)
    job_costs.record_prices(rid, _receipt(), scene='job')
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('no duplicate query'))
    assert job_costs.refresh(rid)['status'] == 'recorded'
    assert len(db.query("SELECT 1 FROM events WHERE type='job.price_quote'")) == 1


def test_other_run_reuses_quote_preserving_observation_provenance(monkeypatch):
    from test_mailboxes import _make_run
    rid, tid, *_ = _run_with_scorer()
    job_costs.record_prices(rid, _receipt(), scene='job')
    db.execute("UPDATE runs SET phase='finished' WHERE id=?", (rid,))
    second = _make_run()
    _job(second, 'second-trial')
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('captured quote is reused'))
    assert job_costs.refresh(second)['status'] == 'recorded'
    quote = job_costs.estimate(second)
    assert quote['amount'] == '0.3200'
    assert quote['source_receipt_sha256'] == job_costs.estimate(rid)['source_receipt_sha256']


@pytest.mark.parametrize('phase', ['cancelled', 'finished', 'failed'])
def test_terminal_unknown_reservation_is_only_reconciled_at_startup(phase):
    rid, tid, *_ = _run_with_scorer()
    _job(rid, tid, status='unknown', platform_job_id=None)
    assert compute.reconciliation_runs() == [rid]
    db.execute('UPDATE runs SET phase=? WHERE id=?', (phase, rid))
    assert compute.reconciliation_runs() == []
    assert compute.reconciliation_runs(startup=True) == [rid]
    assert db.query_one('SELECT status FROM compute_jobs WHERE run_id=?', (rid,))['status'] == 'unknown'


@pytest.mark.parametrize('phase', ['cancelled', 'finished', 'failed'])
def test_known_nonterminal_job_keeps_polling_after_run_ends(phase):
    rid, tid, *_ = _run_with_scorer()
    _job(rid, tid, status='Running')
    db.execute('UPDATE runs SET phase=? WHERE id=?', (phase, rid))
    assert compute.reconciliation_runs() == [rid]
    db.execute("UPDATE compute_jobs SET status='Finished' WHERE run_id=?", (rid,))
    assert compute.reconciliation_runs() == []
