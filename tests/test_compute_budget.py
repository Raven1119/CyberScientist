"""Shared estimate caps are quota gates, with unknown resource reservations kept."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from cyberscientist import compute, compute_budget, db, sandboxes
from test_compute_gateway import run, spec, receipt


def _prices(rid):
    for kind, sku in [('job', 'c8_m8_cpu'), ('sandbox', '4c8g')]:
        db.append_event(rid, 'controller', kind+'.price_quote', {
            'rates': {sku: {'hourly_rate': '6', 'currency': 'CNY', 'sku_id': 1}},
            'source': 'synthetic CPU price', 'observed_at': db.utcnow(), 'source_receipt_sha256': 'a'*64})


def test_job_and_sandbox_share_one_atomic_cap(run, monkeypatch):
    rid, source = run
    db.execute('UPDATE authorizations SET max_compute_cost_cny=?,max_sandboxes=4,max_sandbox_minutes=600 WHERE run_id=?', ('1.5',rid))
    _prices(rid)
    calls=[]
    monkeypatch.setattr(compute, '_native', lambda *a, **k: calls.append(a) or receipt('JobId: 123'))
    assert compute.submit(rid,'priced-job',spec(),str(source))['platform_job_id'] == 123
    assert compute_budget.summary(rid)['committed_estimate_cny'] == '1'
    with pytest.raises(compute.ComputeError, match='估算上限'):
        sandboxes.create(rid,'over-cap',{'cpu':'4c8g','timeout':600})
    assert len(calls) == 1
    assert not db.query("SELECT 1 FROM compute_sandboxes WHERE operation_id='over-cap'")
    assert not db.query("SELECT 1 FROM compute_cost_reservations WHERE operation_id='over-cap'")


def test_unknown_job_keeps_money_reserved_and_deduplicates(run, monkeypatch):
    rid, source = run
    db.execute('UPDATE authorizations SET max_compute_cost_cny=? WHERE run_id=?', ('1', rid))
    _prices(rid)
    calls=[]
    monkeypatch.setattr(compute,'_native',lambda *a,**k: calls.append(a) or {'ok':False,'unknown':True,'stderr':'timeout','stdout':''})
    assert compute.submit(rid,'uncertain-job',spec(),str(source))['status'] == 'unknown'
    assert compute.submit(rid,'uncertain-job',spec(),str(source))['deduplicated']
    assert len(calls) == 1
    assert compute_budget.summary(rid)['remaining_cny'] == '0'
    with pytest.raises(compute.ComputeError,match='估算上限'):
        compute.submit(rid,'another-job',spec(),str(source))
    assert len(calls) == 1


def test_known_terminal_resource_settles_estimate_and_preserves_original_bound(run, monkeypatch):
    rid, source = run
    db.execute('UPDATE authorizations SET max_compute_cost_cny=? WHERE run_id=?', ('2',rid))
    _prices(rid)
    monkeypatch.setattr(compute,'_native',lambda *a,**k: receipt('JobId: 123'))
    compute.submit(rid,'closed-job',spec(),str(source))
    row=db.query_one('SELECT created_at FROM compute_jobs WHERE operation_id=?',('closed-job',))
    ended=(datetime.fromisoformat(row['created_at'])+timedelta(minutes=5)).isoformat()
    db.execute("UPDATE compute_jobs SET status='Finished',updated_at=? WHERE operation_id='closed-job'",(ended,))
    assert compute_budget.summary(rid)['committed_estimate_cny'] == '0.5'
    assert db.query_one('SELECT amount_cny FROM compute_cost_reservations WHERE operation_id=?',('closed-job',))['amount_cny'] == '1'


def test_concurrent_cost_reservations_cannot_exceed_cap(run):
    rid,_=run
    db.execute('UPDATE authorizations SET max_compute_cost_cny=? WHERE run_id=?', ('1',rid))
    def reserve(op):
        try:
            with db.transaction() as conn:
                compute_budget.reserve_tx(conn,rid,'job',op,600,{'hourly_rate_cny':'6','quote_ref':'public-quote'})
            return True
        except compute.ComputeError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(reserve,['left','right']))
    assert sum(result)==1 and compute_budget.summary(rid)['committed_estimate_cny']=='1'


@pytest.mark.parametrize('cap',[True,-1,0,float('inf'),'NaN'])
def test_invalid_money_cap_cannot_grant_spending(cap):
    with pytest.raises(compute.ComputeError):compute_budget.validate_cap(cap)


def test_migrations_only_add_metadata_and_preserve_old_rows():
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    conn.execute('CREATE TABLE authorizations(id TEXT PRIMARY KEY)')
    conn.execute("INSERT INTO authorizations VALUES('existing')")
    conn.execute('CREATE TABLE compute_sandbox_operations(operation_id TEXT PRIMARY KEY)')
    for _ in range(2):
        db._ensure_columns(conn,'authorizations',db.AUTHORIZATION_V2_COLUMNS)
        db._ensure_columns(conn,'compute_sandbox_operations',db.SANDBOX_OPERATION_V3_COLUMNS)
        conn.executescript(db.SCHEMA_COMPUTE_COST)
    assert conn.execute('SELECT * FROM authorizations').fetchone()['max_compute_cost_cny'] is None
    assert conn.execute('SELECT id FROM authorizations').fetchone()['id']=='existing'
