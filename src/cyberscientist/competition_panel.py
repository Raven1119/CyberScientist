"""Competition view and audited per-Run controls; historical snapshots stay intact."""
import json
import uuid
from datetime import datetime, timezone
from . import config,db,method_approval,observation


def state(run_id, key, fallback=None):
    row=db.query_one('SELECT value FROM system_state WHERE key=?',(key+':'+run_id,))
    return json.loads(row[0]) if row else fallback


def view():
    from . import alerts,features,platform_scores,clean_runs
    from . import mailboxes
    usage=mailboxes.mailbox_usage()['items']
    rows=[]
    for run in db.query("SELECT r.*,c.title FROM runs r JOIN challenges c ON c.id=r.challenge_id WHERE r.id=(SELECT r2.id FROM runs r2 WHERE r2.challenge_id=r.challenge_id ORDER BY r2.created_at DESC,r2.rowid DESC LIMIT 1) ORDER BY r.created_at DESC"):
        snapshot=json.loads(run['config_snapshot']);method=method_approval.state(run['id'])
        receipt=db.query_one('SELECT s.*,m.email FROM submissions s JOIN mailboxes m ON m.id=s.mailbox_id WHERE s.run_id=? ORDER BY s.created_at DESC,s.rowid DESC LIMIT 1',(run['id'],))
        clean=db.query_one("SELECT 1 FROM events WHERE run_id=? AND trial_id=? AND type='trial.clean_run'",(run['id'],run['current_trial_id']))
        phase='等待批准' if run['gate']=='awaiting_method_approval' else '暂停' if run['phase'] in ('paused','pausing') else '完成' if run['phase'] in ('finished','failed','cancelled') else '干净复跑' if clean else '探索'
        brief=db.query_one("SELECT payload FROM events WHERE run_id=? AND type='research.brief_written' ORDER BY seq DESC LIMIT 1",(run['id'],))
        proposal=method.get('proposal') or {}
        current=json.loads(brief['payload']).get('brief',{}) if brief else {}
        summary=(current.get('method_proposal') or {}).get('method_md') or current.get('method_md') or current.get('science_md') or current.get('ranked_methods') or proposal.get('method_md','尚未提案')
        if not isinstance(summary,str):summary=json.dumps(summary,ensure_ascii=False)
        next_step='等待初始方法批准' if phase=='等待批准' else state(run['id'],'panel_next','由 PI 根据科学检查与真实回执决定')
        elapsed=None
        if receipt and receipt['submitted_at']:
            from .mailboxes import _instant
            start=_instant(receipt['submitted_at']);end=_instant(receipt['scored_at']) if receipt['score_is_final'] else datetime.now(timezone.utc)
            elapsed=max(0,(end-start).total_seconds()) if start and end else None
        rows.append({'run_id':run['id'],'challenge_id':run['challenge_id'],'title':run['title'],'track':snapshot.get('competition',{}).get('round_id','单题'),'phase':phase,'run_phase':run['phase'],'current_trial_id':run['current_trial_id'],
                     'account_usage':[item for item in usage if json.dumps([
                         item['target_platform'],item['target_origin'],item['platform_challenge_id']],
                         separators=(',',':'))==mailboxes._challenge_key(db.get_db(),run['id'])],
                     'method_summary':summary[:300],'clean_run':clean_runs.offer(run['id']),'method':method,'receipt':{k:receipt[k] for k in ('id','harbor_score','trace_score','trace_decision','receipt_details_json','score_is_final','email')} if receipt else None,'scoring_seconds':elapsed,'next_step':next_step,'submission_held':state(run['id'],'submission_hold',False),'mailbox_id':state(run['id'],'preferred_mailbox'),
                     'executor':state(run['id'],'executor_override',snapshot['settings'].get('executor',{}))})
    # Public aggregation cache only; never expose author identities or ranking rows.
    with platform_scores._lock:
        cache=list(platform_scores._cache.items())
    distribution=[{'topic':key.rsplit('|',1)[-1],'scores':{k:v for k,v in value[1].items() if k in ('status','top_10_scores','leaderboard_best_score','display_score_bins','harbor_score_quantiles','trace_score_quantiles')}} for key,value in cache]
    repairs=[dict(r) for r in db.query('SELECT * FROM monitor_repairs ORDER BY created_at DESC LIMIT 30')]
    return {'items':rows,'distributions':distribution,'repairs':repairs,'alerts':alerts.pending(),'auto_submission':features.enabled('auto_submission')}


@config.serialized_mutation
def change(run_id,body):
    action=body.get('action');operation=body.get('operation_id')
    if not isinstance(operation,str) or not operation or action not in ('submission_hold','mailbox','executor'):raise ValueError('控制参数无效')
    with db.transaction() as conn:
        run=conn.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
        if not run:raise ValueError('Run不存在')
        value=body.get('value')
        if action=='submission_hold':
            if type(value) is not bool:raise ValueError('暂缓提交须为布尔值')
            key='submission_hold'
        elif action=='mailbox':
            if value is not None:
                mailbox=conn.execute("SELECT * FROM mailboxes WHERE id=? AND role='experiment' AND status='active'",(value,)).fetchone()
                if not mailbox or not config.resolve_secret(mailbox['secret_ref'] or ''):raise ValueError('需要可用实验账号')
            key='preferred_mailbox'
        else:
            from . import challenge_models
            value=challenge_models.choose('executor',value,config.load_settings())
            # Executables remain backend configuration, never user-supplied API fields.
            key='executor_override'
        fingerprint=json.dumps({'action':action,'value':value},sort_keys=True)
        prior=conn.execute('SELECT request_summary,run_id FROM operations WHERE operation_id=?',(operation,)).fetchone()
        if prior:
            if prior[0]!=fingerprint or prior['run_id']!=run_id:raise ValueError('幂等键冲突')
            return {'deduplicated':True}
        conn.execute('INSERT OR REPLACE INTO system_state VALUES(?,?)',(key+':'+run_id,json.dumps(value)))
        conn.execute("INSERT INTO operations(operation_id,run_id,kind,status,request_summary,created_at) VALUES(?,?,?,'confirmed',?,?)",(operation,run_id,'panel.'+action,fingerprint,db.utcnow()))
        db.append_event_tx(conn,run_id,'user','panel.'+action,{'value':value,'operation_id':operation,'effective':'next_native_session' if action=='executor' else 'next_new_package' if action=='mailbox' else 'now'})
    return {'action':action,'value':value}


def record_repair(body):
    text=body.get('text','');ident=body.get('operation_id')
    if not isinstance(text,str) or not text.strip() or len(text)>4000 or not isinstance(ident,str) or not ident or observation.strip_secrets(text)!=text:raise ValueError('修复记录无效或含凭据')
    with db.transaction() as conn:
        old=conn.execute('SELECT * FROM monitor_repairs WHERE operation_id=?',(ident,)).fetchone()
        if old:
            if old['text_md']!=text or old['run_id']!=body.get('run_id'):raise ValueError('幂等键冲突')
            return dict(old)
        conn.execute('INSERT INTO monitor_repairs VALUES(?,?,?,?)',(ident,body.get('run_id'),text,db.utcnow()))
    return {'operation_id':ident}
