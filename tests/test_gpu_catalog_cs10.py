"""Native public observations are admission facts, not implicit GPU grants."""
import json
import pytest
from cyberscientist import compute, db, machine_catalog, runtime_facts, sandboxes
from test_compute_gateway import run, spec, receipt

NAME = 'c4_m15_1 * NVIDIA T4'

def catalog():
    return machine_catalog.record('job', receipt(json.dumps({'ok': True, 'data': {'items': [{'chooseType':'gpu','skuEnName':NAME,'skuId':235,'cpuCoreNum':4,'memory':15,'gpuCoreNum':1,'gpu':'NVIDIA T4','price':2.5,'hasStock':True}], 'pagination':{'has_more':False}}})))

def test_gpu_job_old_denial_then_explicit_permission_and_observed_machine(run, monkeypatch):
    rid, source = run; catalog()
    monkeypatch.setattr(compute, '_native', lambda *a, **k: receipt('JobId: 123'))
    request = spec(); request['machine_type'] = NAME
    with pytest.raises(compute.ComputeError, match='未授权 GPU'): compute.submit(rid, 'gpu', request, str(source))
    limits = dict(compute.DEFAULT_LIMITS, allow_gpu=True)
    db.execute('UPDATE authorizations SET job_limits_json=? WHERE run_id=?', (json.dumps(limits), rid))
    assert compute.submit(rid, 'gpu', request, str(source))['status'] == 'accepted'
    assert runtime_facts.facts(rid)['gpu_machine_catalog']['job']['items'][0]['skuEnName'] == NAME
    request['machine_type'] = 'invented-gpu'
    with pytest.raises(compute.ComputeError, match='目录'): compute.submit(rid, 'unknown-gpu', request, str(source))


def test_gpu_catalog_incomplete_or_failed_cannot_overwrite_observation(run):
    catalog(); original = machine_catalog.facts()
    assert machine_catalog.record('job', receipt('{"ok":false}'))['status'] == 'unknown'
    assert machine_catalog.record('job', receipt('{"ok":true,"data":{"items":[],"pagination":{"has_more":true}}}'))['status'] == 'unknown'
    for pagination in ({}, {'total':0}, {'has_more':False,'total':-1}, {'has_more':False,'total':True}):
        assert machine_catalog.record('job', receipt(json.dumps({'ok':True,'data':{'items':[],'pagination':pagination}})))['status'] == 'unknown'
    assert machine_catalog.facts() == original


def test_gpu_sandbox_shortcut_preserves_permission_and_rejects_cpu_mix_before_reservation(run, monkeypatch):
    rid, _ = run
    db.execute('UPDATE authorizations SET unlimited_resources=1,allow_sandbox_gpu=1 WHERE run_id=?', (rid,))
    calls=[]
    monkeypatch.setattr(compute, '_native', lambda a, **k: calls.append(a) or receipt('{"ok":true,"data":{"sandboxID":"gpu-fixture"}}'))
    with pytest.raises(compute.ComputeError, match='显式镜像'): sandboxes.create(rid, 'bad', {'timeout':60,'gpu':'4090','cpu':'8c32g'})
    assert not calls and not db.query('SELECT * FROM compute_sandboxes')
    assert sandboxes.create(rid, 'good', {'timeout':60,'gpu':'4090'})['status'] == 'active'
    assert '--gpu' in calls[0] and '--cpu' not in calls[0]


def test_new_competition_template_defaults_gpu_on_but_explicit_and_frozen_denial_survive():
    from cyberscientist import competition
    from test_competition import template
    new = competition._template(template(), 'demo')['authorization']
    assert new['job_limits']['allow_gpu'] is True and new['allow_sandbox_gpu'] is True
    partial = template(); partial['authorization']['job_limits'] = {'max_cpu': 8}
    assert competition._template(partial, 'demo')['authorization']['job_limits'] == {'max_cpu': 8, 'allow_gpu': True}
    old = competition._template(template(), 'demo', frozen=True)['authorization']
    assert not old.get('allow_sandbox_gpu', False) and not old.get('job_limits', {}).get('allow_gpu', False)
    explicit = template(); explicit['authorization']['job_limits'] = {'allow_gpu': False}
    explicit['authorization']['allow_sandbox_gpu'] = False
    preserved = competition._template(explicit, 'demo')['authorization']
    assert preserved['job_limits']['allow_gpu'] is False and preserved['allow_sandbox_gpu'] is False
