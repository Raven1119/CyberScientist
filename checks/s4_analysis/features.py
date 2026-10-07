"""Deterministic trace features and indexed candidate events, never proof claims."""
import argparse
import json
import re
import time
from bisect import bisect_left
from collections import Counter,defaultdict

from .common import DEFAULT_DATA,sha,unzstd,utcnow,write_json
from .dataset import read_table
from .tables import number,timestamp,write_csv

INSTALL=re.compile(r'\b(?:pip(?:3)?\s+install|uv\s+(?:pip\s+install|add)|conda\s+install|apt(?:-get)?\s+install)\s+([^\n;&]{1,1000})')
IMPORT=re.compile(r'^[\t ]*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))',re.M)
PATH=re.compile(r'(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_./-]{1,240})\.(?:csv|jsonl?|npz|npy|png|pdf|txt|lean|pt|pth|ya?ml|dat|xyz|cif)\b')
NUMBER=re.compile(r'(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?')
ERROR=re.compile(r'Traceback \(most recent call last\)|\b(?:ERROR|Exception|Error):|exit (?:code|status)\s*[:=]?\s*([1-9]\d*)',re.I)
VERIFY=re.compile(r'\b(?:assert|pytest|unittest|verify|verifier|recompute|cross.?check|independent|sanity.?check|validation)\b|独立|复算|验证',re.I)
WRITE=re.compile(r'\b(?:write_text|write_bytes|to_csv|to_json|np\.save|numpy\.save|json\.dump|savefig|torch\.save|open\s*\([^\n]{0,180}["\x27][wa][b+]?["\x27])|(?:^|[\s;])(?:cat|echo|printf)[^\n]{0,200}>',re.M)


def utf16_length(value):return len(value.encode('utf-16-le'))//2


def offsets(pattern,text):
    astral=[i for i,char in enumerate(text) if ord(char)>0xFFFF]
    return [[m.start()+bisect_left(astral,m.start()),m.end()+bisect_left(astral,m.end())] for m in pattern.finditer(text)]


def declared_outputs(root,aid):
    inventory=root/'data/bundle_inventories'/(aid+'.json')
    if not inventory.exists():return None
    paths={f['path'] for f in json.loads(inventory.read_text())['files']
           if any(part in ('outputs','results','artifacts') for part in f['path'].split('/')[:-1])}
    docs=root/'data/bundle_docs'/(aid+'.json')
    if docs.exists():
        for doc in json.loads(docs.read_text())['documents']:
            if doc['kind']!='manifest':continue
            try:manifest=json.loads(doc['text'])
            except ValueError:continue
            def visit(value):
                if isinstance(value,str):
                    if PATH.fullmatch(value):paths.add(value)
                elif isinstance(value,dict):
                    for k,v in value.items():
                        if k in ('path','file','output_path'):visit(v)
                        elif isinstance(v,(list,dict)):visit(v)
                elif isinstance(value,list):
                    for v in value:visit(v)
            for key in ['artifacts','expected_outputs','outputs']:visit(manifest.get(key))
            if isinstance(manifest.get('execution'),dict):visit(manifest['execution'].get('artifacts'))
    return sorted(paths)


def extract(aid,item,steps,report,root):
    events=[];types=Counter();calls=set();results=set();times=[];installs=[];imports=[];locations=set();gpu=[]
    lengths=[];codes=[];errors=[];retry=[];sources=set();versions=set();output_paths=declared_outputs(root,aid)
    generated=defaultdict(list);normalized={e['index']:e for e in report.get('normalized_events',[])}
    for i,step in enumerate(steps,1):
        kind=step.get('step_type') or step.get('type') or 'unknown';types[kind]+=1
        call_id=step.get('tool_call_id')
        if isinstance(call_id,str) and call_id or isinstance(call_id,int) and not isinstance(call_id,bool):
            if kind=='tool_call':calls.add(str(call_id))
            if kind=='tool_result':results.add(str(call_id))
        stamp=timestamp(step.get('timestamp')) or timestamp(step.get('time'))
        if stamp:times.append(stamp)
        original='\n'.join(str(step.get(k) or '') for k in ['title','body','code','tool_name','tool_args','tool_output'])
        event=normalized.get(i)
        folded=event.get('one_line_text',re.sub(r'\s+',' ',event['text']).strip()) if event else re.sub(r'\s+',' ',original).strip()
        length=utf16_length(folded);lengths.append(length)
        base={'attempt_id':aid,'challenge_id':item['challenge_id'],'ours':item['ours'],'step_index':i,
              'source_step_order':step.get('step_order'),'source_step_id':step.get('step_id'),'step_type':kind,
              'event_utf16_chars':length,'over_900_chars':length>900,'v6_normalized_text_available':event is not None}
        def emit(event_kind,**extra):events.append({**base,'event_kind':event_kind,**extra})
        emit('event_length',number_offsets_utf16_json=json.dumps(offsets(NUMBER,folded)),
             path_offsets_utf16_json=json.dumps(offsets(PATH,folded)),
             command_field_present=bool(step.get('code') or step.get('tool_args')),
             code_field_omitted_by_v6_arm_normalizer=bool(step.get('code')) and report.get('format','').startswith('arm_steps'))
        for match in INSTALL.finditer(original):
            installs.append(match.group(0));emit('software_install_candidate',declaration=match.group(0))
        for match in IMPORT.finditer(original):
            name=match.group(1) or match.group(2);imports.append(name);emit('import_candidate',module=name)
        if re.search(r'\bbohr\s+job|\bjob\s+submit|bohrium_job|/api/.*jobs',original,re.I):locations.add('bohrium_job');emit('compute_location_candidate',location='bohrium_job')
        if re.search(r'bohr\s+sandbox|\bsdbx\b|bohrium_sandbox|sandbox_id',original,re.I):locations.add('bohrium_sandbox');emit('compute_location_candidate',location='bohrium_sandbox')
        if re.search(r'\blocalhost\b|/home/[^/]+/|\bWSL\b|local execution',original,re.I):locations.add('local_path_or_claim');emit('compute_location_candidate',location='local_path_or_claim')
        if re.search(r'nvidia-smi|\bcuda\b|\bGPU\b|torch\.device\(["\x27]cuda',original,re.I):gpu.append(i);emit('gpu_reference_candidate')
        if ERROR.search(original):errors.append(i);emit('error_candidate')
        if re.search(r'\bretry\b|try again|重试',original,re.I):retry.append(i);emit('retry_candidate')
        if VERIFY.search(original):emit('verification_candidate')
        if re.search(r'https?://|\b(?:search|LKM|literature)\b|文献|检索',original,re.I):emit('network_literature_lkm_candidate',url_count=len(re.findall('https?://',original)))
        if step.get('cost_usd') is not None or step.get('cost') is not None or re.search(r'\bcost\b|费用|成本',original,re.I):emit('cost_declaration_candidate',cost_usd=number(step.get('cost_usd')))
        meta=json.dumps(step.get('source_event'),ensure_ascii=False)
        for source in ['codex','kimi','claude','opencode','openclaw','bohrclaw']:
            if re.search(r'\b'+source+r'\b',meta+' '+str(step.get('tool_name') or ''),re.I):sources.add(source)
        for version in re.findall(r'(?:converter|playground(?:-cli)?|codex(?:-cli)?)\s*[/:=v -]+(\d+\.\d+(?:\.\d+)?(?:[-\w.]*)?)',original+' '+meta,re.I):versions.add(version)
        if step.get('code'):codes.append(str(step['code']))
        if WRITE.search(original) and output_paths:
            for output in output_paths:
                short=output.split('/')[-1]
                if output in original or len(short)>=5 and short in original:
                    generated[output].append(i)
                    location=folded.find(output);matched=output
                    if location<0:location=folded.find(short);matched=short
                    emit('output_generation_candidate',output_path=output,
                         matched_by='exact_path' if output in original else 'basename_candidate',
                         normalized_utf16_offset=utf16_length(folded[:location]) if location>=0 else None,
                         evidence_surface='v6_normalized_text' if location>=0 else 'public_code_or_other_field_omitted_by_v6')
    ordered=sorted(set(times));gaps=[(b-a).total_seconds() for a,b in zip(ordered,ordered[1:])]
    feature={'attempt_id':aid,'challenge_id':item['challenge_id'],'ours':item['ours'],'step_count':len(steps),
        'public_trace_status':'nonempty' if steps else 'empty_unknown_original',
        'step_types_json':json.dumps(dict(types)),'tool_call_ids':len(calls),'tool_result_ids':len(results),
        'paired_tool_call_ids':len(calls&results),'unpaired_tool_call_ids':len(calls-results),'orphan_result_ids':len(results-calls),
        'software_install_declarations_json':json.dumps(sorted(set(installs)),ensure_ascii=False),
        'imports_json':json.dumps(sorted(set(imports))),'compute_location_candidates_json':json.dumps(sorted(locations)),
        'gpu_reference_steps_json':json.dumps(gpu),'source_markers_json':json.dumps(sorted(sources)),
        'converter_or_cli_version_markers_json':json.dumps(sorted(versions)),
        'first_timestamp':ordered[0].isoformat() if ordered else None,'last_timestamp':ordered[-1].isoformat() if ordered else None,
        'duration_s':(ordered[-1]-ordered[0]).total_seconds() if ordered else None,'longest_gap_s':max(gaps) if gaps else None,
        'error_candidate_steps_json':json.dumps(errors),'retry_candidate_steps_json':json.dumps(retry),
        'events_over_900':sum(n>900 for n in lengths),'events_over_900_fraction':sum(n>900 for n in lengths)/len(lengths) if lengths else None,
        'submitted_output_inventory_status':'available' if output_paths is not None else 'unknown_bundle_unavailable',
        'submitted_output_paths_json':json.dumps(output_paths),'output_generation_candidate_steps_json':json.dumps(dict(generated)),
        'code_sequence_sha256':sha('\n'.join(codes).encode()) if codes else None,
        'v6_input_status':report.get('status'),'v6_checklist_score':report.get('score') if report.get('status')=='ok' else None,
        'v6_cap':report.get('cap') if report.get('status')=='ok' else None,'extracted_at':utcnow()}
    return feature,events


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true');args=parser.parse_args()
    root=DEFAULT_DATA;cache=root/'.raw/features';cache.mkdir(parents=True,exist_ok=True);processed={}
    while True:
        selected=list(read_table('data/selected.csv'))
        if (root/'data/selection_additions.csv').exists():selected+=list(read_table('data/selection_additions.csv'))
        rows={r['attempt_id']:r for r in selected};changed=0
        for aid,item in rows.items():
            report_path=root/'.raw/v6_reports'/(aid+'.json')
            if not report_path.exists():continue
            encoded=report_path.read_bytes();digest=sha(encoded)
            if processed.get(aid)==digest:continue
            trace=root/'data/traces'/(aid+'.jsonl.zst')
            if not trace.exists():trace=root/'.raw/traces'/(aid+'.jsonl.zst')
            if not trace.exists():continue
            steps=[json.loads(line) for line in unzstd(trace.read_bytes()).splitlines() if line.strip()]
            feature,events=extract(aid,item,steps,json.loads(encoded),root)
            write_json(cache/(aid+'.json'),{'feature':feature,'events':events});processed[aid]=digest;changed+=1
        if changed:
            all_features=[];all_events=[]
            for p in cache.glob('*.json'):
                value=json.loads(p.read_text());all_features.append(value['feature']);all_events.extend(value['events'])
            write_csv(root/'data/trace_features.csv',all_features);write_csv(root/'data/trace_events.csv',all_events)
            print(json.dumps({'features':len(all_features),'events':len(all_events),'changed':changed,'time':utcnow()}),flush=True)
        if not args.watch:break
        time.sleep(30)


if __name__=='__main__':main()
