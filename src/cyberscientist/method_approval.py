"""One durable initial-method decision per Run; compute still requires an open gate."""
import hashlib
import json
from . import config, db, observation

FIELDS = ('method_md', 'parameters_md', 'basis_md', 'outputs_md')


def required(run):
    snapshot=json.loads(run['config_snapshot'])
    return snapshot.get('method_approval_version') == 1 and snapshot['settings'].get('initial_method_approval',True)


def state(run_id):
    row=db.query_one('SELECT * FROM method_approvals WHERE run_id=?',(run_id,))
    if not row:return {'status':'not_proposed','version':0,'proposal':None}
    return {k:v for k,v in dict(row).items() if k not in ('proposal_json','pending_json')} | {'proposal':json.loads(row['proposal_json'])}


def hold(run_id, decision, packet):
    run=db.query_one('SELECT * FROM runs WHERE id=?',(run_id,))
    old=db.query_one('SELECT * FROM method_approvals WHERE run_id=?',(run_id,))
    if not required(run) or old and old['status']=='approved':return False
    start=next((a for a in decision['actions'] if a['op']=='start_trial'),None)
    if not start and not decision.get('research_brief'):return False
    brief=decision.get('research_brief') or {}
    proposal=brief.get('method_proposal') or {}
    valid=isinstance(proposal,dict) and all(isinstance(proposal.get(k),str) and proposal[k].strip() for k in FIELDS)
    valid=valid and isinstance(proposal.get('capabilities'),list) and bool(proposal['capabilities']) and all(isinstance(v,str) and v.strip() for v in proposal['capabilities'])
    safe=json.loads(observation.strip_secrets(json.dumps(proposal,ensure_ascii=False)))
    pending={'decision':decision,'packet':packet} if start else None
    with db.transaction() as conn:
        version=(old['version'] if old else 0)+1
        conn.execute("INSERT INTO method_approvals(run_id,status,version,proposal_json,pending_json,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,version=excluded.version,proposal_json=excluded.proposal_json,pending_json=excluded.pending_json,updated_at=excluded.updated_at",(run_id,'pending' if valid else 'awaiting_revision',version,json.dumps(safe,ensure_ascii=False),json.dumps(pending,ensure_ascii=False) if pending else None,db.utcnow()))
        conn.execute("UPDATE runs SET gate='awaiting_method_approval' WHERE id=?",(run_id,))
        db.append_event_tx(conn,run_id,'brain','method.proposed' if valid else 'method.incomplete',{'version':version,'proposal':safe,'required_fields':[*FIELDS,'capabilities']})
    return True


@config.serialized_mutation
def decide(run_id, body):
    actor,action=body.get('actor'),body.get('action')
    text=body.get('text') or ''
    if actor not in ('user','monitor') or action not in ('approve','modify','reject') or not isinstance(text,str) or len(text)>20000 or not body.get('operation_id'):
        raise ValueError('方法审批参数无效')
    if action!='approve' and not text.strip():raise ValueError('修改或驳回需要说明')
    if observation.strip_secrets(text)!=text:raise ValueError('审批说明不得含凭据')
    fingerprint=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
    with db.transaction() as conn:
        prior=conn.execute('SELECT * FROM method_approval_actions WHERE operation_id=?',(body['operation_id'],)).fetchone()
        if prior:
            if prior['run_id']!=run_id or prior['request_hash']!=fingerprint:raise ValueError('审批幂等键冲突')
            return {'deduplicated':True,'action':prior['action']}
        run=conn.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
        row=conn.execute('SELECT * FROM method_approvals WHERE run_id=?',(run_id,)).fetchone()
        if not run or run['phase']!='running' or run['gate']!='awaiting_method_approval' or not row or row['version']!=body.get('version') or row['status'] not in ('pending','awaiting_revision'):
            raise ValueError('提案状态或版本已变化，请刷新')
        if action!='reject' and row['status']!='pending':raise ValueError('提案未完整，不能批准')
        when=db.utcnow()
        conn.execute('INSERT INTO method_approval_actions VALUES(?,?,?,?,?,?,?,?)',(body['operation_id'],run_id,row['version'],actor,action,text,fingerprint,when))
        conn.execute('UPDATE method_approvals SET status=?,approved_by=?,approved_at=?,updated_at=? WHERE run_id=?',('awaiting_revision' if action=='reject' else 'approved',actor if action!='reject' else None,when if action!='reject' else None,when,run_id))
        conn.execute('UPDATE runs SET gate=?,state_version=state_version+1 WHERE id=?',('awaiting_method_approval' if action=='reject' else 'open',run_id))
        # Persist the PI wake with approval: a process exit cannot lose it.
        from . import collab
        request_id = collab._enqueue_request_tx(
            conn, run_id, source='lifecycle', blocking=False,
            trigger='method_revision_requested' if action == 'reject' else 'method_approved')
        guidance = text
        if action == 'approve':
            guidance = '初始方法已批准，按批准的方法继续。' + row['proposal_json']
        conn.execute('UPDATE review_requests SET frame_json=? WHERE id=?',
                     (json.dumps({'user_guidance': guidance}, ensure_ascii=False), request_id))
        db.append_event_tx(conn,run_id,'user','method.'+action,{'actor':actor,'version':row['version'],'at':when,'text':text,'operation_id':body['operation_id']})
        return {'action':action,'text':text,'pending':json.loads(row['pending_json']) if row['pending_json'] else None,'deduplicated':False}
