"""Negotiate the native catalog's Fast tier per session, never global config."""
from __future__ import annotations
import json
import re
from . import db


async def prepare(rpc,params,model,provider,requested):
    facts={'requested':requested,'model':model,'provider':provider or 'codex','tier':None,'status':'not_requested'}
    if provider not in (None,'codex'): return facts | {'status':'provider_not_supported'}
    if requested is None: return facts
    params.setdefault('config',{})['features.fast_mode']=bool(requested)
    params['serviceTier']='default'
    if not requested: return facts | {'status':'disabled'}
    try:
        cursor=None;entry=None
        for _ in range(10):
            catalog=await rpc.request('model/list',{'limit':100,'includeHidden':True,**({'cursor':cursor} if cursor else {})},timeout=30)
            entry=next((m for m in catalog.get('data',[]) if m.get('model')==model or m.get('id')==model),None)
            if entry: break
            cursor=catalog.get('nextCursor')
            if not cursor: break
        tiers=entry.get('serviceTiers',[]) if entry else []
        selected=next((t['id'] for t in tiers if t.get('id')=='priority' or t.get('name','').lower()=='fast'),None)
        if not selected:
            params.pop('serviceTier',None);params['config']['features.fast_mode']=False
            return facts | {'status':'unsupported' if entry else 'model_not_in_catalog'}
        params['serviceTier']=selected
        return facts | {'status':'requested','tier':selected,'catalog_source':'native_model_list'}
    except Exception as exc:
        from .jsonrpc_stdio import ProtocolError
        try: refusal=json.loads(str(exc))
        except (ValueError,TypeError): refusal={}
        if not isinstance(exc,ProtocolError) or not isinstance(refusal,dict) or refusal.get('code')!=-32601: raise
        params.pop('serviceTier',None);params['config']['features.fast_mode']=False
        return facts | {'status':'catalog_method_unsupported'}


async def open_negotiated(rpc,params,facts,resume_id=None):
    from .codex_protocol import open_thread
    from .jsonrpc_stdio import ProtocolError
    try: return await open_thread(rpc,params,resume_id),facts
    except ProtocolError as exc:
        message=str(exc)
        from .model_limits import classify
        try: refusal=json.loads(message)
        except (ValueError,TypeError): refusal={}
        unsupported=bool(re.search(r'(?:unsupported|not supported|does not support|doesn.t support)',message,re.I)
                         and re.search(r'(?:service.?tier|fast|priority)',message,re.I))
        if classify(message) or not isinstance(refusal,dict) or refusal.get('code')!=-32602 or not facts.get('tier') or not unsupported: raise
        # An explicit parameter refusal precedes every model turn. Unknown
        # transport, quotas and provider errors never use this downgrade path.
        params['serviceTier']='default';params['config']['features.fast_mode']=False
        facts=facts | {'tier':None,'rejected_tier':facts['tier'],'status':'unsupported_native'}
        return await open_thread(rpc,params,resume_id),facts


def confirmed(facts,response):
    actual=response.get('serviceTier')
    return facts | {'observed_tier':actual,'enabled':bool(facts.get('tier') and actual==facts['tier']),
                    'status':'enabled' if facts.get('tier') and actual==facts['tier'] else 'tier_unconfirmed' if facts.get('tier') else facts['status']}


def record(facts):
    if facts['requested'] is None: return
    db.execute('INSERT OR REPLACE INTO runtime_observations VALUES(?,?,?)',
               ('codex_fast:'+str(facts.get('model')),json.dumps(facts),db.utcnow()))


def rate_facts(body):
    # Exclude account IDs, reset-credit objects, balances and authentication.
    items=body.get('rateLimitsByLimitId') or {'codex':body.get('rateLimits',{})}
    result={}
    for name,value in items.items():
        if not isinstance(value,dict): continue
        result[name]={window:{key:data.get(key) for key in ('usedPercent','windowDurationMins','resetsAt')}
                      for window in ('primary','secondary') if isinstance(data:=value.get(window),dict)}
    return result


async def observe_rates(rpc):
    try:
        facts=rate_facts(await rpc.request('account/rateLimits/read',{},timeout=15))
        db.execute('INSERT OR REPLACE INTO runtime_observations VALUES(?,?,?)',('codex_rate_limits',json.dumps(facts),db.utcnow()))
        return facts
    except Exception: return None
