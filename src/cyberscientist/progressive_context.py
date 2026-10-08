"""Progressive model inputs with versioned, capability-scoped source documents."""
from copy import deepcopy
import hashlib
import json
import tempfile
import os
from . import config,db,observation


def enabled(run_id):
    row=db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(run_id,))
    return bool(row and json.loads(row[0]).get('progressive_context_version') == 1)


def encode(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def measure(value):
    return {'total_bytes':len(encode(value).encode()),'sections':{key:len(encode(item).encode()) for key,item in value.items()}}


def experience_index(items,limit=8):
    result=[]
    for item in items[:limit]:
        entry={k:item[k] for k in ('id','title','revision_id','revision_hash','scope','kind') if k in item}
        entry['summary']=' '.join(str(item.get('applicability') or item.get('body_md') or '').split())[:160]
        result.append(entry)
    return result


def catalog_index(items):
    return [{'id':item.get('id') or item.get('name'),
             'use':' '.join(str(item.get('description') or item.get('name') or item.get('title') or item.get('purpose') or item.get('identity') or '环境起点，详情按需查询').split())[:130],
             'location':item.get('image') or item.get('image_address') or item.get('source_path') or 'research_environment list',
             'status':item.get('status','unknown')} for item in items]


def _store(run_id,packet):
    safe=observation.strip_secrets(encode(packet));digest=hashlib.sha256(safe.encode()).hexdigest()
    root=config.WORKSPACE_DIR/'runs'/run_id/'facts';root.mkdir(parents=True,exist_ok=True)
    if root.is_symlink() or not root.resolve().is_relative_to(config.WORKSPACE_DIR.resolve()):
        raise ValueError('事实目录越界或为符号链接')
    path=root/(digest+'.json')
    if path.is_symlink():raise ValueError('事实目录含符号链接')
    if not path.exists():
        with tempfile.NamedTemporaryFile(mode='w',dir=root,delete=False) as handle:
            handle.write(safe);temporary=handle.name
        os.replace(temporary,path)
    return {'tool':'research_files','scope':'facts','path':path.name,'sha256':digest,'bytes':len(safe.encode())}


def compact(run_id,packet):
    """Retain unique scientific text. Repeated authority and large facts stay readable."""
    full=deepcopy(packet);out=deepcopy(packet);reference=_store(run_id,full)
    # Keep complete frozen statement once, including all task-specific contracts.
    challenge=out.get('challenge') or {}
    frozen=out.pop('round_challenge_snapshot',None)
    if frozen and not challenge.get('content'):
        challenge.update({k:frozen[k] for k in ('title','content','resources') if k in frozen});out['challenge']=challenge
    content=challenge.get('content') or ''
    if content and isinstance(out.get('run_objective'),str):
        out['run_objective']=out['run_objective'].replace(content,'[题面见challenge.content]')
    feedback=out.get('feedback')
    if isinstance(feedback,dict):
        for key in list(feedback):
            if key in out and key not in ('feedback','quality'):
                feedback.pop(key)
        feedback.pop('round_challenge_snapshot',None)
        # goal_md is the same title/statement projected by observation.build_frame.
        if content:feedback.pop('goal_md',None)
        if 'experiences' in feedback:feedback['experiences']=experience_index(feedback['experiences'])
        if 'experience_index' in feedback:feedback.pop('experience_index')
    entries=out.get('experience_manifest') or out.get('experiences') or []
    if entries:out['experience_manifest']=experience_index(entries)
    out.pop('experiences',None);out.pop('experience_index',None)
    startup=out.get('research_startup')
    if isinstance(startup,dict):
        if startup.get('problem_md')==content:startup.pop('problem_md')
        startup.pop('resources',None)
        startup['strategy_cards']=experience_index(startup.get('strategy_cards') or [])
        if 'environment_catalog' in startup:startup.pop('environment_catalog')
        startup['brief_fields']=list(dict.fromkeys([*startup.get('brief_fields',[]),'selected_capabilities']))
    for key in ('environment_catalog','runtime_environments'):
        if key in out:out[key]=catalog_index(out[key] or [])
    facts=out.get('operating_facts') or {}
    if facts:
        out['operating_facts']={k:facts[k] for k in ('now_utc','elapsed_seconds','remaining','time','budget','submission_limits') if k in facts}
        out['operating_facts']['details']=reference
    if 'data_status' in out:
        out['data_status']=[{k:item[k] for k in ('id','status','path','local_path','bytes','size','error') if k in item} for item in out['data_status']]
    from . import capabilities
    out['capability_index']=capabilities.index(run_id)
    out['progressive_disclosure']={'source':reference,'instruction':'选择方法和环境前先查能力索引。经验正文用research_experience按ID读取；完整运行事实用research_files scope=facts分页读取或research_operating_facts。','selected_capabilities_required':True}
    metrics={'before':measure(full),'after':measure(out)}
    db.append_event(run_id,'controller','context.compacted',metrics)
    return out


def executor_prompt(run_id,trial_id,challenge,goal,success,authority,enabled_skills,experience):
    from . import skills
    data={'challenge':challenge,'goal':goal,'success_check':success,'authority':authority,'experience':experience}
    reference=_store(run_id,data)
    return ('选择方法和环境前先查能力索引。\n'
            + f'Run ID：{run_id}；Trial ID：{trial_id}。\n目标：{goal}\n成功判据：{success}\n'
            + '题面与契约：'+encode(challenge)+'\n'
            + '能力索引：'+authority.get('capability_summary','')+'\n'
            + '环境索引：'+encode(catalog_index(authority.get('environment_catalog') or authority.get('runtime_environments') or []))+'\n'
            + '经验索引：'+encode(experience_index((experience or {}).get('items',[])))+'\n'
            + '完整事实：'+encode(reference)+'，PI可通过research_files读取；执行者可用research_operating_facts/research_environment/research_experience按需读取。\n'
            + skills.prompt_segment(enabled_skills)+'\n'
            + f'交付目录：{config.WORKSPACE_DIR / "runs" / run_id / "trials" / trial_id}。结果包result_package.zip，真实原生轨迹由系统绑定，禁止编造工具调用、结果或费用。')
