"""Preparation has a long pre-effect budget, one reservation and bounded life."""
import json
from datetime import datetime, timedelta, timezone
import pytest
from cyberscientist import compute, compute_budget, db, power, run_clock, sandboxes, sandbox_warmup
from test_sandboxes import run
from test_sandbox_retry_cs12 import refusal


def virtual_clock(monkeypatch):
    clock = [0.0]; base = datetime.now(timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return base + timedelta(seconds=clock[0])
    monkeypatch.setattr(sandboxes, 'datetime', Clock)
    monkeypatch.setattr(sandboxes.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(sandboxes.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0]+seconds))
    monkeypatch.setattr(run_clock, 'remaining', lambda *a, **k: 3600-clock[0])
    return clock, base


def success(now, lifetime=600):
    return {'ok': True, 'exit_code': 0, 'stderr': '', 'stdout': json.dumps({'ok': True, 'data': {
        'sandboxID': 'fixture--warm-001', 'startedAt': now.isoformat(),
        'endAt': (now+timedelta(seconds=lifetime)).isoformat()}})}


def test_preparation_beyond_ttl_uses_one_frozen_lifetime_and_cost(run, monkeypatch):
    _,rid,_,_,_=run;clock,base=virtual_clock(monkeypatch);calls=[]
    db.execute('UPDATE authorizations SET max_compute_cost_cny=? WHERE run_id=?',('3',rid))
    monkeypatch.setattr(compute_budget,'rate',lambda *a,**k:{'hourly_rate_cny':'6','quote_ref':'synthetic-price'})
    def create(args, **kwargs):
        calls.append(list(args))
        if clock[0] < 1200:
            return refusal('IMAGE_PREPARATION_IN_PROGRESS: preparing', 'INVALID_REQUEST')
        return success(base+timedelta(seconds=clock[0]))
    monkeypatch.setattr(compute, '_native', create)
    result=sandboxes.create(rid, 'long-prepare', {'timeout':600,'image':'registry.example/lean:fixed'})
    assert result['status']=='active' and 1200<=clock[0]<1800
    assert len(calls)>7 and all(c==calls[0] for c in calls)
    rows=db.query('SELECT * FROM compute_sandboxes WHERE run_id=?',(rid,));assert len(rows)==1
    row=rows[0]
    assert row['lifetime_version']==2 and sandboxes.reserved_seconds(row)==600
    assert datetime.fromisoformat(row['created_at']) < datetime.fromisoformat(row['lifetime_started_at'])
    assert (datetime.fromisoformat(row['expires_at'])-datetime.fromisoformat(row['lifetime_started_at'])).total_seconds()==600
    assert len(db.query('SELECT * FROM compute_cost_reservations WHERE run_id=?',(rid,)))==1
    facts=json.loads(db.query_one("SELECT payload FROM events WHERE run_id=? AND type='sandbox.environment_observed'",(rid,))['payload'])
    assert max(w['seconds'] for w in facts['waits'])==300 and facts['preparation_budget_seconds']==2700
    assert facts['preparation_duration_seconds'] is None
    db.execute('UPDATE compute_cost_reservations SET hourly_rate_cny=? WHERE operation_id=?',('6','long-prepare'))
    db.execute("UPDATE compute_sandboxes SET status='deleted',deleted_at=? WHERE operation_id=?",
        ((base+timedelta(seconds=clock[0]+60)).isoformat(),'long-prepare'))
    assert sandboxes.reserved_seconds(db.query_one('SELECT * FROM compute_sandboxes WHERE operation_id=?',('long-prepare',)))==60
    assert compute_budget.summary(rid)['committed_estimate_cny']=='0.1'


def test_preparation_stops_at_45_minutes_and_keeps_unknown_reservation(run, monkeypatch):
    _,rid,_,_,_=run;clock,_=virtual_clock(monkeypatch);calls=[]
    monkeypatch.setattr(run_clock,'remaining',lambda *a,**k:10000-clock[0])
    monkeypatch.setattr(compute,'_native',lambda args,**kw:calls.append(list(args)) or refusal(
        'IMAGE_PREPARATION_IN_PROGRESS: preparing','INVALID_REQUEST'))
    result=sandboxes.create(rid,'still-preparing',{'timeout':600})
    assert result['status']=='unknown' and clock[0]==2700
    assert all(args==calls[0] for args in calls)
    assert len(db.query('SELECT * FROM compute_sandboxes WHERE run_id=?',(rid,)))==1
    assert sandboxes.reserved_seconds(db.query_one('SELECT * FROM compute_sandboxes WHERE operation_id=?',('still-preparing',)))==600


def test_authorization_can_stop_preparation_before_45_minutes(run,monkeypatch):
    _,rid,_,_,_=run;clock,_=virtual_clock(monkeypatch);calls=[]
    monkeypatch.setattr(run_clock,'remaining',lambda *a,**k:1000-clock[0])
    monkeypatch.setattr(compute,'_native',lambda args,**kw:calls.append(args) or refusal(
        'IMAGE_PREPARATION_IN_PROGRESS: preparing','INVALID_REQUEST'))
    assert sandboxes.create(rid,'grant-short',{'timeout':600})['status']=='unknown'
    assert clock[0]<1000 and all(args==calls[0] for args in calls)


def test_long_interval_shutdown_stops_before_next_create(run,monkeypatch):
    _,rid,_,_,_=run;clock,_=virtual_clock(monkeypatch);calls=[]
    monkeypatch.setattr(power,'shutdown_requested',lambda:clock[0]>=245)
    monkeypatch.setattr(compute,'_native',lambda args,**kw:calls.append((clock[0],args)) or refusal(
        'IMAGE_PREPARATION_IN_PROGRESS: preparing','INVALID_REQUEST'))
    result=sandboxes.create(rid,'shutdown-long',{'timeout':600})
    assert result['status']=='unknown' and 245<=clock[0]<250
    assert all(when<245 for when,_ in calls)


def test_create_late_success_after_pause_cleans_only_its_known_sandbox(run,monkeypatch):
    _,rid,_,calls,_=run;native=compute._native
    def paused(args,**kwargs):
        value=native(args,**kwargs)
        if args[:2]==['sandbox','create']:
            db.execute("UPDATE runs SET phase='paused',gate='closed' WHERE id=?",(rid,))
        return value
    monkeypatch.setattr(compute,'_native',paused)
    assert sandboxes.create(rid,'late-pause',{'timeout':600})['status']=='deleted'
    assert [a[2] for a in calls if a[:2]==['sandbox','delete']]==['fixture--box-001']


def test_old_lifetime_rows_keep_the_original_budget_basis(run):
    _,rid,_,_,_=run;start=datetime.now(timezone.utc);end=start+timedelta(seconds=1200)
    db.execute("INSERT INTO compute_sandboxes(operation_id,run_id,trial_id,request_json,status,created_at,expires_at,updated_at) VALUES(?,?,?,'{}','unknown',?,?,?)",
        ('legacy',rid,'legacy-trial',start.isoformat(),end.isoformat(),start.isoformat()))
    row=db.query_one('SELECT * FROM compute_sandboxes WHERE operation_id=?',('legacy',))
    assert row['lifetime_version']==1 and row['lifetime_started_at'] is None
    assert sandboxes.reserved_seconds(row)==1200


def test_unknown_start_time_keeps_full_lifetime_reserved_even_after_delete(run):
    _,rid,_,_,_=run
    sid=sandboxes.create(rid,'time-unknown',{'timeout':600})['sandbox_id']
    assert not sandboxes.list_run(rid)['items'][0]['lifetime_observed']
    assert sandboxes.delete(rid,sid)['status']=='deleted'
    row=db.query_one('SELECT * FROM compute_sandboxes WHERE operation_id=?',('time-unknown',))
    assert row['lifetime_started_at'] is None and sandboxes.reserved_seconds(row)==600


@pytest.mark.parametrize('stop',['paused','shutdown'])
def test_unknown_create_reconciliation_after_stop_cleans_its_resource(run,monkeypatch,stop):
    _,rid,_,calls,_=run;native=compute._native
    def lost(args,**kw):
        value=native(args,**kw)
        if args[:2]==['sandbox','create']:
            return {'ok':False,'unknown':True,'stdout':'','stderr':'lost'}
        return value
    monkeypatch.setattr(compute,'_native',lost)
    assert sandboxes.create(rid,'lost-after-stop',{'timeout':600})['status']=='unknown'
    if stop=='paused':db.execute("UPDATE runs SET phase='paused',gate='closed' WHERE id=?",(rid,))
    else:monkeypatch.setattr(power,'shutdown_requested',lambda:True)
    assert sandboxes.reconcile_create(rid,'lost-after-stop')['status']=='deleted'
    assert [args[2] for args in calls if args[:2]==['sandbox','delete']]==['fixture--box-001']


@pytest.mark.parametrize('stop',['paused','shutdown'])
def test_unknown_delete_is_never_reactivated_by_create_reconciliation(run,monkeypatch,stop):
    _,rid,_,calls,_=run;sid=sandboxes.create(rid,'unknown-delete',{'timeout':600})['sandbox_id'];native=compute._native
    def lost_delete(args,**kw):
        if args[:2]==['sandbox','delete']:
            calls.append(args);return {'ok':False,'unknown':True,'stdout':'','stderr':'lost reply'}
        return native(args,**kw)
    monkeypatch.setattr(compute,'_native',lost_delete)
    assert sandboxes.delete(rid,sid)['status']=='unknown'
    if stop=='paused':db.execute("UPDATE runs SET phase='paused',gate='closed' WHERE id=?",(rid,))
    else:monkeypatch.setattr(power,'shutdown_requested',lambda:True)
    assert sandboxes.reconcile_create(rid,'unknown-delete')['status']=='unknown'
    assert len([args for args in calls if args[:2]==['sandbox','delete']])==1


def test_late_create_get_cannot_overwrite_concurrent_delete_unknown(run,monkeypatch):
    _,rid,_,calls,_=run;native=compute._native
    def interleaved(args,**kw):
        if args[:2]==['sandbox','delete']:
            calls.append(args);return {'ok':False,'unknown':True,'stdout':'','stderr':'lost reply'}
        value=native(args,**kw)
        if args[:2]==['sandbox','create']:
            return {'ok':False,'unknown':True,'stdout':'','stderr':'lost reply'}
        if args[:2]==['sandbox','describe']:
            db.execute("UPDATE compute_sandboxes SET status='active',sandbox_id=? WHERE operation_id=?",('fixture--box-001','interleaved'))
            assert sandboxes.delete(rid,'fixture--box-001')['status']=='unknown'
        return value
    monkeypatch.setattr(compute,'_native',interleaved)
    assert sandboxes.create(rid,'interleaved',{'timeout':600})['status']=='unknown'
    db.execute("UPDATE runs SET phase='paused',gate='closed' WHERE id=?",(rid,))
    assert sandboxes.reconcile_create(rid,'interleaved')['status']=='unknown'
    assert len([args for args in calls if args[:2]==['sandbox','delete']])==1


def test_late_create_post_cannot_overwrite_reconciled_delete_unknown(run,monkeypatch):
    _,rid,_,calls,_=run;native=compute._native
    def interleaved(args,**kw):
        if args[:2]==['sandbox','delete']:
            calls.append(args);return {'ok':False,'unknown':True,'stdout':'','stderr':'lost reply'}
        value=native(args,**kw)
        if args[:2]==['sandbox','create']:
            db.execute("UPDATE runs SET phase='paused',gate='closed' WHERE id=?",(rid,))
            assert sandboxes.reconcile_create(rid,'late-post')['status']=='unknown'
        return value
    monkeypatch.setattr(compute,'_native',interleaved)
    assert sandboxes.create(rid,'late-post',{'timeout':600})['status']=='unknown'
    assert len([args for args in calls if args[:2]==['sandbox','delete']])==1
    assert db.query_one("SELECT 1 FROM events WHERE run_id=? AND type='sandbox.create_late_receipt'",(rid,))


def test_short_resource_ttl_does_not_shorten_create_rpc_timeout(run,monkeypatch):
    _,rid,_,_,_=run;native=compute._native;timeouts=[]
    def probe(args,**kw):
        timeouts.append(kw.get('timeout'));return native(args,**kw)
    monkeypatch.setattr(compute,'_native',probe)
    assert sandboxes.create(rid,'short-life',{'timeout':60})['status']=='active'
    assert timeouts==[240]


def test_creation_times_are_per_image_and_not_registration_times(run,monkeypatch):
    from cyberscientist import environment_catalog
    monkeypatch.setattr(environment_catalog,'items',lambda:[{'id':'one','image':'first','last_verified_at':'2026-10-01T00:00:00Z'},
                                                          {'id':'two','image':'second','last_verified_at':'2026-10-02T00:00:00Z'}])
    assert all(item['created_success_at'] is None for item in sandbox_warmup.latest())
    for operation,when in [('old','2026-10-06T00:00:00Z'),('new','2026-10-07T00:00:00Z')]:
        sandbox_warmup.record_success('first',operation,'fixture--warm-001',success(datetime.now(timezone.utc)),observed_at=when)
    values=sandbox_warmup.latest()
    assert values[0]['created_success_at']=='2026-10-07T00:00:00Z' and values[1]['created_success_at'] is None


def test_warmup_does_not_infer_success_from_build_or_catalog(run):
    _,rid,_,_,_=run
    with pytest.raises(ValueError):
        sandbox_warmup.record_success('image','op','fixture--warm-001',{'ok':True,'stdout':'{"data":{"status":2}}'})
    assert not db.query("SELECT * FROM runtime_observations WHERE kind LIKE 'sandbox-create:%'")
    value=sandbox_warmup.record_success('image','op','fixture--warm-001',success(datetime.now(timezone.utc)))
    assert value['cache_validity_seconds'] is None and value['rewarm_interval_seconds'] is None
    sandbox_warmup.record_success('image','op','fixture--warm-001',success(datetime.now(timezone.utc)))
    assert len(db.query("SELECT * FROM runtime_observations WHERE kind LIKE 'sandbox-create:%'"))==1
