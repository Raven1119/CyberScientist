"""Optional diagnostic work is separate from durable receipts and source integrity."""
import json
from . import config,db


def mode(run_id=None,settings=None):
    if settings is None and run_id:
        row=db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(run_id,))
        if row:settings=json.loads(row[0]).get('settings',{})
    return (settings or config.load_settings()).get('evidence_mode','development')


def automatic_trace_hint(content,run_id=None):
    if mode(run_id)=='competition':
        return {'status':'not_run','advisory_only':True,'hints':[],'reason':'比赛模式省去自动轨迹诊断；可显式按需检查'}
    from . import trace_hints
    return trace_hints.inspect(content)


def memory_manifest(context,settings):
    if mode(settings=settings)!='competition':return context
    return {key:context[key] for key in ('id','run_id','trial_id','boundary','sha256','index_sha256')} | {'source':'experience_contexts','items':[{'id':item['id'],'revision_id':item['revision_id']} for item in context['items']]}
