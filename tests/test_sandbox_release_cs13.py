import json
from datetime import datetime, timedelta, timezone
import pytest
from cyberscientist import compute, db, sandboxes
from test_sandboxes import run

@pytest.mark.parametrize('complete,age,expected', [(True,601,'unknown_released'),(False,601,'unknown'),(True,599,'unknown')])
def test_request_miss_requires_old_create_and_complete_absent_list(run, monkeypatch, complete, age, expected):
    _,rid,_,calls,_=run
    def native(args, **kwargs):
        calls.append(args)
        if args[1]=='create': return {'ok':False,'unknown':True,'exit_code':None,'stdout':'','stderr':'timeout'}
        if args[1]=='describe': return {'ok':False,'exit_code':1,'stdout':json.dumps({'error':{'code':'RESOURCE_NOT_FOUND','http':404}}),'stderr':''}
        return {'ok':True,'exit_code':0,'stdout':json.dumps({'data':{'items':[],'total':0 if complete else 1}}),'stderr':''}
    monkeypatch.setattr(compute,'_native',native)
    sandboxes.create(rid,'unknown-create',{'timeout':60})
    old=(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat()
    db.execute('UPDATE compute_sandboxes SET created_at=? WHERE operation_id=?',(old,'unknown-create'))
    result=sandboxes.reconcile_create(rid,'unknown-create')
    assert result['status']==expected
    sandboxes.reconcile_create(rid,'unknown-create')
    assert sum(a[:2]==['sandbox','create'] for a in calls)==1
    row=db.query_one('SELECT * FROM compute_sandboxes WHERE operation_id=?',('unknown-create',))
    assert row['deleted_at'] is None
    assert row['sandbox_id'] is None
