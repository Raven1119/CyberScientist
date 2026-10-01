"""Current sandbox SKU rates, never inferred from Node prices."""
import json

import pytest

from cyberscientist import db, compute
from test_final_candidate_integrity import _run_with_scorer


def _fixture():
    rid, tid, *_ = _run_with_scorer()
    now = db.utcnow()
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,'
               'request_json,status,created_at,deleted_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
               ('owned-synthetic',rid,tid,'synthetic-box','{"cpu":"4c8g"}', 'deleted',
                '2026-10-01T12:00:00+00:00','2026-10-01T12:30:00+00:00',now,now))
    return rid


def _receipt(price='0.80 RMB/h'):
    return {'ok':True,'stdout':json.dumps({'ok':True,'data':{'items':[
        {'class':'cpu','cpu':'4','memory':'8Gi','sku_id':4690,
         'sku_name':'c4_m8_cpu','price':price}]}})}


def test_exact_sandbox_rate_and_lifetime_generate_labelled_estimate_without_native_call(monkeypatch):
    from cyberscientist import sandbox_costs
    rid = _fixture()
    sandbox_costs.record_prices(rid, _receipt())
    monkeypatch.setattr(compute,'_native',lambda *args,**kwargs:pytest.fail('report is offline'))
    estimate = sandbox_costs.estimate(rid)
    assert estimate['amount'] == '0.4000'
    assert estimate['currency'] == 'CNY' and estimate['status'] == 'estimated'
    assert estimate['observed_seconds'] == 1800
    assert estimate['basis'] == 'current_sandbox_rate_times_observed_lifetime'
    assert estimate['source_receipt_sha256']
    assert compute.costs(rid)['sandbox_estimate']['amount'] == '0.4000'
    assert compute.costs(rid)['total_amount'] is None


@pytest.mark.parametrize('price',['unknown','0.80 USD/h'])
def test_unverified_rate_is_missing_not_zero(price):
    from cyberscientist import sandbox_costs
    rid = _fixture()
    sandbox_costs.record_prices(rid,_receipt(price))
    estimate = sandbox_costs.estimate(rid)
    assert estimate['amount'] is None and estimate['status'] == 'unknown'
    assert estimate['unpriced_count'] == 1


def test_missing_machine_layout_keeps_partial_estimate_and_reports_unpriced_resource():
    from cyberscientist import sandbox_costs
    rid = _fixture()
    sandbox_costs.record_prices(rid,_receipt())
    now=db.utcnow();tid=db.query_one('SELECT current_trial_id FROM runs WHERE id=?',(rid,))['current_trial_id']
    db.execute('INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,sandbox_id,request_json,'
               'status,created_at,deleted_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
               ('missing-machine',rid,tid,'missing-box','{}','deleted',now,now,now,now))
    estimate=sandbox_costs.estimate(rid)
    assert estimate['amount']=='0.4000' and estimate['status']=='estimated_partial'
    assert estimate['priced_count']==1 and estimate['unpriced_count']==1


def test_template_price_uses_observed_hardware_bound_to_owned_resource():
    from cyberscientist import sandbox_costs
    rid = _fixture()
    db.execute("UPDATE compute_sandboxes SET request_json='{}' WHERE run_id=?", (rid,))
    sandbox_costs.record_prices(rid, _receipt())
    db.append_event(rid, 'controller', 'sandbox.resources_observed', {
        'operation_id': 'owned-synthetic', 'sandbox_id': 'synthetic-box',
        'resources': {'cpu': '4c8g'}, 'source': 'create_receipt'})
    assert sandbox_costs.estimate(rid)['amount'] == '0.4000'
    db.execute("UPDATE compute_sandboxes SET sandbox_id='different-box' WHERE run_id=?", (rid,))
    assert sandbox_costs.estimate(rid)['amount'] is None


@pytest.mark.parametrize('payment,cost,photon,currency,expected', [
    (0, 0.08, None, 'CNY', '0.08'),
    (0, 0, None, 'CNY', '0'),
    (1, 0.03, 1.25, 'photons', '1.25'),
    (1, 0.03, None, 'photons', '0.03'),
])
def test_native_resource_costs_match_owned_id_and_keep_payment_units(payment, cost, photon, currency, expected, monkeypatch):
    from cyberscientist import sandbox_costs
    rid = _fixture()
    item = {'sandbox_id': 'synthetic-box', 'paymentType': payment, 'cost': cost}
    if photon is not None:
        item['photonCost'] = photon
    receipt = {'ok': True, 'stdout': json.dumps({'ok': True, 'data': {'items': [item,
        {'sandbox_id': 'another-account-resource', 'cost': 999, 'owner': 'private account info'}]}})}
    assert sandbox_costs.record_costs(rid, receipt)['matched_count'] == 1
    monkeypatch.setattr(compute, '_native', lambda *a, **k: pytest.fail('offline reports'))
    observed = compute.costs(rid)['sandbox_observed']
    assert observed['amounts'] == {currency: expected}
    assert observed['unmatched_count'] == 0
    assert observed['final_settlement_confirmed'] is False
    assert compute.costs(rid)['total_amount'] is None
    payload = db.query_one("SELECT payload FROM events WHERE run_id=? AND type='sandbox.cost_observed'", (rid,))['payload']
    assert 'private account info' not in payload and 'another-account-resource' not in payload
    assert observed['source_receipt_sha256']


@pytest.mark.parametrize('fields', [
    {}, {'cost': None}, {'cost': True}, {'cost': -1}, {'cost': 'NaN'},
    {'cost': 0.1, 'paymentType': True}, {'cost': 0.1, 'paymentType': 7},
])
def test_absent_or_unverified_native_cost_is_unknown_not_zero(fields):
    from cyberscientist import sandbox_costs
    rid = _fixture()
    receipt = {'ok': True, 'stdout': json.dumps({'ok': True, 'data': {'items': [
        {'sandbox_id': 'synthetic-box', **fields}]}})}
    sandbox_costs.record_costs(rid, receipt)
    observed = sandbox_costs.observed_costs(rid)
    assert observed['status'] == 'unknown' and observed['amounts'] == {}
    assert observed['unmatched_count'] == 1


def test_billing_snapshot_conflicts_and_changed_identity_cannot_leak_into_totals():
    from cyberscientist import sandbox_costs
    rid = _fixture()
    def receipt(values):
        return {'ok': True, 'stdout': json.dumps({'ok': True, 'data': {'items': [
            {'sandbox_id': 'synthetic-box', 'cost': value} for value in values]}})}
    sandbox_costs.record_costs(rid, receipt([0.08, 0.09]))
    assert sandbox_costs.observed_costs(rid)['amounts'] == {}
    sandbox_costs.record_costs(rid, receipt([0.08]))
    assert sandbox_costs.observed_costs(rid)['amounts'] == {'CNY': '0.08'}
    assert sandbox_costs.record_costs(rid, {'ok': False})['status'] == 'unknown'
    assert sandbox_costs.observed_costs(rid)['amounts'] == {'CNY': '0.08'}
    db.execute("UPDATE compute_sandboxes SET sandbox_id='changed-resource' WHERE run_id=?", (rid,))
    assert sandbox_costs.observed_costs(rid)['amounts'] == {}


def test_delayed_billing_projection_retains_original_cli_time():
    from cyberscientist import sandbox_costs
    rid = _fixture()
    receipt = {'ok': True, 'stdout': json.dumps({'ok': True,
        'meta': {'timestamp': 1790856000}, 'data': {'items': [
            {'sandbox_id': 'synthetic-box', 'cost': 0.08}]}})}
    sandbox_costs.record_costs(rid, receipt)
    observed = sandbox_costs.observed_costs(rid)
    assert observed['observed_at'] == '2026-10-01T12:00:00+00:00'
    assert observed['recorded_at'] != observed['observed_at']
