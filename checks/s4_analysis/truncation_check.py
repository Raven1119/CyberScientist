"""Evidence existence annotations on full traces; exact quote/offset audit.

Scorer missing-evidence statements are claims, never ground-truth absences. The
model reads every source event (exhaustive chunks), and cited strings are checked
against original fields. Original trace absence and unassessable receipts remain
unknown. No scientific result is computed and no downloaded code is executed.
"""
import argparse
import json
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed

from .common import DEFAULT_DATA,sha,unzstd,utcnow,write_json
from .dataset import read_table
from .features import utf16_length
from .models import ModelClient
from .semantics import chunks,trace_steps
from .tables import write_csv

SYSTEM='''Return JSON only. Check each supplied scorer statement against ALL supplied trace events. The statement is not ground truth. Extract evidence only: no task solution, code, advice or strategy. Distinguish an observed command/result from an assistant claim. Do not infer original work absent from missing public data. Worker/private integrity receipts can be unassessable. Output {"checks":[{"id":string,"status":"present|partially_present|not_observed|not_assessable","confidence":0 to 1,"evidence":[{"step":1-based supplied index,"quote":exact substring <=160 characters}],"explanation":short factual string}]}. Return every statement ID once. present/partially_present require exact event quotes supporting the requested TYPE of evidence, not merely repeating the scorer statement. not_observed means only unseen in THIS supplied chunk, never proof of absence in the original run.'''


def strings(value,path=''):
    if isinstance(value,str):yield path,value
    elif isinstance(value,dict):
        for key,item in value.items():yield from strings(item,path+'.'+str(key))
    elif isinstance(value,list):
        for i,item in enumerate(value):yield from strings(item,path+'['+str(i)+']')


def locate(quote,step,events,packet):
    if not isinstance(step,int) or isinstance(step,bool) or not 1<=step<=len(events) or not isinstance(quote,str) or not quote or len(quote)>160:return None
    original=[]
    for field,text in strings(events[step-1]):
        start=text.find(quote)
        if start>=0:original.append({'field':field,'character_offset':start,'utf16_offset':utf16_length(text[:start])})
    if not original:return None
    folded=re.sub(r'[\s\ufeff]+',' ',quote).strip();matches=[]
    try:
        prompt=packet['judge_prompt'];view=json.loads(prompt[prompt.index('{'):]);excerpt={e['index'] for e in view['trace_events_excerpt']}
    except (KeyError,ValueError,TypeError):excerpt=None
    for event in packet.get('normalized_events',[]):
        text=event.get('one_line_text') or re.sub(r'[\s\ufeff]+',' ',event.get('text','')).strip()
        start=text.find(folded)
        if start<0:continue
        offset=utf16_length(text[:start]);length=utf16_length(text);cut=897 if length>900 else length
        matches.append({'v6_event_index':event['index'],'folded_utf16_offset':offset,'beyond_900':offset>=900,
            'beyond_actual_v6_cut':offset>=cut,'crosses_actual_v6_cut':offset<cut<offset+utf16_length(folded),
            'event_selected_in_judge_excerpt':event['index'] in excerpt if excerpt is not None else None,
            'v6_event_utf16_length':length,'actual_v6_content_limit':cut})
    return {'source_step':step,'quote':quote,'original_field_offsets':original,'v6_matches':matches,
      'v6_match_status':'exact_folded_quote_matches' if matches else 'not_located_in_v6_text_or_mapping_unknown'}


def effective_trace(root,aid):
    bundle=root/'.raw/bundle_selected_traces'/(aid+'.jsonl.zst')
    public=root/'data/traces'/(aid+'.jsonl.zst')
    if not public.exists():public=root/'.raw/traces'/(aid+'.jsonl.zst')
    if bundle.exists():return bundle,'local_only_archive_selected_trace'
    return public,'public_api_trace'


def input_view(root,aid,items):
    path,source=effective_trace(root,aid);steps,digest=trace_steps(path)
    # Native message/content/item/parts and ARM tool fields are all evidence.
    events=[{**step,'index':i+1} for i,step in enumerate(steps)]
    packetp=root/'.raw/v6_reports'/(aid+'.json');packet=json.loads(packetp.read_text()) if packetp.exists() else {}
    topic=json.loads((root/'data/topics'/(items[0]['challenge_id']+'.json')).read_text())
    task={k:topic.get(k) for k in ['title','content','topicContent','scoring']}
    identity={'schema_version':2,'trace_sha256':digest,'trace_source':source,
      'missing_claims_sha256':sha(json.dumps([{'id':i['evidence_index'],'text':i['text']} for i in items],sort_keys=True).encode()),
      'task_sha256':sha(json.dumps(task,sort_keys=True,ensure_ascii=False).encode()),
      'packet_sha256':sha(json.dumps({k:packet.get(k) for k in ['normalized_events','judge_prompt','source_sha256']},sort_keys=True,ensure_ascii=False).encode())}
    identity['input_fingerprint']=sha(json.dumps(identity,sort_keys=True).encode())
    return events,packet,task,identity


def persist(root,target,result):
    if target.exists():
        previous=target.read_bytes()
        from .common import atomic
        atomic(root/'.raw/truncation_history'/target.stem/(sha(previous)+'.json'),previous)
    write_json(target,result)


def process(root,aid,items):
    events,packet,task,identity=input_view(root,aid,items)
    target=root/'data/truncation_claims'/(aid+'.json')
    if target.exists():
        previous=json.loads(target.read_text())
        if previous.get('input_fingerprint')==identity['input_fingerprint']:return previous
        if all(previous.get(k)==v for k,v in identity.items() if k not in ['packet_sha256','input_fingerprint']):
            for check in previous['checks']:
                check['evidence']=[locate(e['quote'],e['source_step'],events,packet) for e in check.get('evidence',[])]
                check['evidence']=[e for e in check['evidence'] if e]
            previous.update(identity,observed_at=utcnow(),offsets_recomputed_without_model_call=True)
            persist(root,target,previous);return previous
    result={'attempt_id':aid,'challenge_id':items[0]['challenge_id'],'ours':items[0]['ours'],**identity,
      'observed_at':utcnow(),'checks':[],'model_receipts':[]}
    if not events:
        result['checks']=[{'evidence_index':i['evidence_index'],'status':'unknown_public_trace_empty','confidence':None,'evidence':[]} for i in items]
        persist(root,target,result);return result
    votes=defaultdict(list);failed_chunks=0
    statements=[{'id':i['evidence_index'],'statement':i['text']} for i in items];allowed={i['id'] for i in statements}
    parts=chunks(events)
    for chunk_id,chunk in enumerate(parts):
        try:
            response=ModelClient().generate(SYSTEM,json.dumps({'task':task,'statements':statements,'events':chunk},ensure_ascii=False),max_tokens=8192)
            result['model_receipts'].append({k:v for k,v in response.items() if k!='output'})
            output=response['output'].get('checks',[])
            entries=output if isinstance(output,list) else []
            counts=defaultdict(int)
            for check in entries:
                if isinstance(check,dict):counts[str(check.get('id'))]+=1
            for check in entries:
                if not isinstance(check,dict) or str(check.get('id')) not in allowed:continue
                identity=str(check['id']);status=check.get('status');confidence=check.get('confidence')
                if counts[identity]!=1:continue
                if status not in ['present','partially_present','not_observed','not_assessable'] or isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not 0<=confidence<=1:continue
                evidence=[]
                for citation in check.get('evidence',[]) if isinstance(check.get('evidence'),list) else []:
                    if not isinstance(citation,dict):continue
                    located=locate(citation.get('quote'),citation.get('step'),events,packet)
                    if located:evidence.append(located)
                if status in ('present','partially_present') and not evidence:status='unknown_invalid_evidence_quote'
                votes[identity].append({'status':status,'confidence':confidence,'evidence':evidence,'explanation':check.get('explanation'),'chunk_id':chunk_id})
        except Exception:failed_chunks+=1
    total=len(parts)
    for item in items:
        options=votes[item['evidence_index']];supported=[v for v in options if v['status'] in ('present','partially_present')]
        if supported:chosen=max(supported,key=lambda v:(v['status']=='present',v['confidence']))
        elif failed_chunks or {v['chunk_id'] for v in options}!=set(range(total)):chosen={'status':'unknown_incomplete_chunks','confidence':None,'evidence':[]}
        elif all(v['status']=='not_observed' for v in options):chosen={'status':'not_observed_in_complete_fetched_trace','confidence':min(v['confidence'] for v in options),'evidence':[]}
        else:chosen={'status':'not_assessable_from_public_trace','confidence':None,'evidence':[]}
        result['checks'].append({'evidence_index':item['evidence_index'],**chosen,'failed_chunks':failed_chunks,'total_chunks':total,
                                'annotation_kind':'model assessment with exact source-quote validation; not an integrity verdict'})
    persist(root,target,result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--watch',action='store_true');p.add_argument('--workers',type=int,default=16);args=p.parse_args()
    root=DEFAULT_DATA;attempted=set();done=0
    while True:
        groups=defaultdict(list);rows=list(read_table('data/missing_evidence.csv'))
        for row in rows:groups[row['attempt_id']].append(row)
        selected={r['attempt_id'] for r in read_table('data/selected.csv')}
        if (root/'data/selection_additions.csv').exists():selected.update(r['attempt_id'] for r in read_table('data/selection_additions.csv'))
        pending=[];fingerprints={}
        for aid in groups:
            if aid not in selected or not effective_trace(root,aid)[0].exists():continue
            fingerprint=input_view(root,aid,groups[aid])[3]['input_fingerprint'];fingerprints[aid]=fingerprint
            target=root/'data/truncation_claims'/(aid+'.json')
            if (aid,fingerprint) in attempted:continue
            if not target.exists() or json.loads(target.read_text()).get('input_fingerprint')!=fingerprint:pending.append(aid)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(process,root,aid,groups[aid]):aid for aid in pending}
            for future in as_completed(futures):
                aid=futures[future];attempted.add((aid,fingerprints[aid]));done+=1
                try:future.result()
                except Exception as exc:write_json(root/'.local/truncation_failures'/(aid+'.json'),{'attempt_id':aid,'error_kind':type(exc).__name__,'observed_at':utcnow()})
                if done%20==0:print(json.dumps({'processed_this_run':done,'available_reports':len(list((root/'data/truncation_claims').glob('*.json'))),'time':utcnow()}),flush=True)
        annotations={}
        for path in (root/'data/truncation_claims').glob('*.json'):
            report=json.loads(path.read_text())
            for check in report['checks']:annotations[(report['attempt_id'],check['evidence_index'])]=(report,check)
        output=[]
        for row in rows:
            pair=annotations.get((row['attempt_id'],row['evidence_index']))
            if pair:
                report,check=pair
                output.append({**row,'assessment_status':check['status'],'model_confidence':check.get('confidence'),
                   'trace_source':report['trace_source'],'trace_sha256':report['trace_sha256'],
                   'packet_sha256':report.get('packet_sha256'),'input_fingerprint':report.get('input_fingerprint'),
                   'evidence_steps_offsets_json':json.dumps(check.get('evidence',[]),ensure_ascii=False),'explanation':check.get('explanation')})
            else:output.append({**row,'assessment_status':'unknown_outside_selected_trace_scope' if row['attempt_id'] not in selected else 'unknown_trace_not_collected_or_analysis_pending','model_confidence':None,'evidence_steps_offsets_json':'[]'})
        write_csv(root/'data/truncation_check.csv',output)
        if not args.watch:break
        time.sleep(30)


if __name__=='__main__':main()
