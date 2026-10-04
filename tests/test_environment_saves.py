"""Synthetic private builds account for unknowns and auto-register facts."""
import pytest
from cyberscientist import compute,db,environment_saves,experiences
from test_compute_gateway import run


def test_private_software_build_budget_and_smoke_receipt_register_fact(run,monkeypatch):
    rid,_=run
    db.execute('UPDATE authorizations SET max_environment_saves=1 WHERE run_id=?',(rid,))
    calls=[]
    def api(method,path,payload=None):
        calls.append((method,path,payload))
        return {'status':'received','http_status':200,'sha256':'a'*64,'body':{'code':0,'data':{'id':'fixture-id'} if method=='POST' else {'status':'available','url':'registry.dp.tech/fixture/public-software:1'}}}
    monkeypatch.setattr(environment_saves,'_api',api)
    result=environment_saves.save(rid,'public-env','FROM fixture/public:1','Public Python and fixed scorer wrapper','python3 --version')
    assert result['status']=='building' and result['cost_status']=='unknown'
    assert environment_saves.save(rid,'public-env','FROM fixture/public:1','Public Python and fixed scorer wrapper','python3 --version')['deduplicated']
    assert len(calls)==1
    with pytest.raises(compute.ComputeError,match='数量'):environment_saves.save(rid,'extra','FROM fixture/public:1','public software','true')
    assert environment_saves.reconcile('public-env')['status']=='verified'
    entries=experiences.active_experiences(None)
    assert entries[0]['kind']=='environment' and entries[0]['status']=='active'
    assert 'fixture-id' in entries[0]['body_md'] and 'python3 --version' in entries[0]['body_md']


def test_unknown_build_never_reissues_create_and_keeps_count(run,monkeypatch):
    rid,_=run
    db.execute('UPDATE authorizations SET max_environment_saves=1 WHERE run_id=?',(rid,))
    calls=[]
    def unknown(*args):calls.append(args);return {'status':'unknown'}
    monkeypatch.setattr(environment_saves,'_api',unknown)
    assert environment_saves.save(rid,'uncertain','FROM fixture/public:1','public software','true')['status']=='unknown'
    assert environment_saves.save(rid,'uncertain','FROM fixture/public:1','public software','true')['deduplicated']
    assert environment_saves.reconcile('uncertain')['status']=='unknown'
    assert len(calls)==2 and calls[1][0]=='GET'


def test_environment_authority_and_secret_boundary(run,monkeypatch):
    rid,_=run
    monkeypatch.setattr(environment_saves,'_api',lambda *a,**k:pytest.fail('no remote request'))
    with pytest.raises(compute.ComputeError,match='未授权'):environment_saves.save(rid,'unallowed','FROM fixture/public:1','public software','true')
    db.execute('UPDATE authorizations SET max_environment_saves=1,max_compute_cost_cny=\'1\' WHERE run_id=?',(rid,))
    with pytest.raises(compute.ComputeError,match='单价'):environment_saves.save(rid,'uncapped','FROM fixture/public:1','public software','true')
    with pytest.raises(compute.ComputeError,match='不复制'):environment_saves.save(rid,'copy','FROM fixture/public:1\nCOPY result_package.zip /tmp/','public software','true')
    assert not db.query('SELECT * FROM environment_saves')
