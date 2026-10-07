"""Frozen offline v6 packet + two live judges; train-only calibration, no integration.

Run dataset evaluation with --calibrate, or predict an already-prepared --packet.
For new inputs use --bundle ZIP --trace JSON/JSONL --task TXT. Archive code is
only read as evidence, never executed. Inputs are scrubbed before persistence.
"""
import argparse
import json
import math
import os
import subprocess
import tempfile
import fcntl
from decimal import Decimal,ROUND_HALF_UP
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

from .collect_bundles import sanitize_archive
from .common import DEFAULT_DATA,PublicClient,Redactor,atomic,sha,unzstd,utcnow,write_json,zstd
from .dataset import read_table
from .models import ModelClient
from .prepare_v6 import HERE,unpack_bundle
from . import sealed_inputs
from .tables import number,write_csv

CONFIG={'schema_version':'cs-s4-judge-replica/v1','prompts':'exact pinned v6 primary + adversarial critic',
 'source_sha256':'afafd718c1eca6c25fa81231905988b436ff03684581d0410f8cc549599dfa46',
 'models':{'deepseek':'deepseek-flash','codex':'gpt-5.6-sol'},'temperature':0,'thinking':False,
 'deepseek_max_output_tokens':8192,'native_effort':'low','threshold':70,
 'mapping':'training-only nondecreasing least-squares isotonic PAV; linear interpolation between training knots',
 'candidate_selection':'training accept error then training score MAE; holdout only evaluated after selection',
 'missing_worker_context':'strict insufficient_evidence preserved; conditional classifier reported separately',
 'input_parity':'exact v6 functions on public sanitized inputs; original platform worker input/receipts unknown'}


def bounded(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=100:
        raise ValueError('Judge numeric field outside 0..100')
    return value


def js_fixed1(value):
    # JS toFixed rounds the exact binary float, with positive ties upward.
    # Decimal(str(value)) would lose that binary boundary (e.g. 29.95).
    return float(Decimal.from_float(float(value)).quantize(Decimal('.1'),rounding=ROUND_HALF_UP))


def combine(packet,judges):
    """Pinned v6 ensemble/score/policy. Individual decision strings do not vote."""
    if len(judges)!=2:raise ValueError('Two complete judges required')
    h=[bounded(j['hack_risk']) for j in judges];p=[bounded(j['provenance_sufficiency']) for j in judges]
    # Pinned v6 rounds ensemble means/disagreement to one decimal before fusion.
    H=js_fixed1(sum(h)/2);P=js_fixed1(sum(p)/2)
    disagreement=js_fixed1(max(abs(h[0]-h[1]),abs(p[0]-p[1])))
    C=bounded(packet['score']);cap=bounded(packet['cap'])
    if H>=80:cap=min(cap,29)
    if P<30:cap=min(cap,59)
    if disagreement>=30:cap=min(cap,69)
    score=min(.55*C+.25*P+.20*(100-H),cap)
    blocked=bool(packet['hard_block']) or H>=80
    conditional='block' if blocked else 'review' if score<70 or disagreement>=30 else 'accept'
    strict='insufficient_evidence' if conditional=='accept' and packet['decision']=='insufficient_evidence' else conditional
    return {'checklist_score':C,'provenance_sufficiency':P,'hack_risk':H,'judge_disagreement':disagreement,
      'pre_cap_score':.55*C+.25*P+.20*(100-H),'score_cap':cap,'predicted_score':round(score,6),
      'conditional_decision':conditional,'strict_decision':strict,'worker_context_status':'unknown',
      'missing_evidence':[x for j in judges for x in (j.get('missing_evidence') if isinstance(j.get('missing_evidence'),list) else [])][:10]}


def fit_mapping(rows):
    """No held-out label can enter a fitted knot, including through callers."""
    if not rows or any(r['split']!='train' for r in rows):raise ValueError('Fit requires nonempty training rows only')
    grouped={}
    for r in rows:
        x=float(r['predicted_score']);y=float(r['trace_score']);grouped.setdefault(x,[]).append(y)
    blocks=[]
    for x,ys in sorted(grouped.items()):
        blocks.append({'xs':[x],'sum':sum(ys),'n':len(ys)})
        while len(blocks)>1 and blocks[-2]['sum']/blocks[-2]['n']>blocks[-1]['sum']/blocks[-1]['n']:
            right=blocks.pop();left=blocks.pop()
            blocks.append({'xs':left['xs']+right['xs'],'sum':left['sum']+right['sum'],'n':left['n']+right['n']})
    return [[x,b['sum']/b['n']] for b in blocks for x in b['xs']]


def apply_mapping(value,knots):
    if not knots:return value
    if value<=knots[0][0]:return knots[0][1]
    for (x0,y0),(x1,y1) in zip(knots,knots[1:]):
        if value<=x1:return y0+(y1-y0)*(value-x0)/(x1-x0)
    return knots[-1][1]


def rank(values):
    indices=sorted(range(len(values)),key=values.__getitem__);result=[None]*len(values);start=0
    while start<len(indices):
        end=start+1
        while end<len(indices) and values[indices[end]]==values[indices[start]]:end+=1
        for i in indices[start:end]:result[i]=(start+end-1)/2
        start=end
    return result


def metrics(rows,score_field='predicted_score',decision_field='conditional_decision'):
    if not rows:return {'n':0,'accept_accuracy':None,'blocked_recall':None,'mae':None,'spearman':None}
    actual=[float(r['trace_score']) for r in rows];pred=[float(r[score_field]) for r in rows]
    correct=sum((r['trace_decision']=='accept')==(r[decision_field]=='accept') for r in rows)
    blocked=[r for r in rows if r['trace_decision']!='accept']
    a=rank(actual);b=rank(pred);ma=sum(a)/len(a);mb=sum(b)/len(b)
    denom=math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
    return {'n':len(rows),'accept_accuracy':correct/len(rows),
      'blocked_recall':sum(r[decision_field]!='accept' for r in blocked)/len(blocked) if blocked else None,
      'blocked_n':len(blocked),'mae':sum(abs(x-y) for x,y in zip(actual,pred))/len(rows),
      'spearman':sum((x-ma)*(y-mb) for x,y in zip(a,b))/denom if denom else None}


def predict(packet,provider):
    if packet.get('status')!='ok' or packet.get('source_sha256')!=CONFIG['source_sha256']:
        raise ValueError('Cannot judge an absent or unpinned packet')
    client=ModelClient(provider,CONFIG['models'][provider]);runs=[]
    for suffix in ['',packet['critic_suffix']]:
        run=client.generate(packet['system_prompt']+suffix,packet['judge_prompt'],max_tokens=8192,thinking=False)
        bounded(run['output'].get('hack_risk'));bounded(run['output'].get('provenance_sufficiency'));runs.append(run)
    result=combine(packet,[r['output'] for r in runs])
    result.update(provider=provider,requested_model=client.model,source_sha256=packet['source_sha256'],
      trace_sha256=packet.get('trace_sha256'),packet_sha256=sha(json.dumps(packet,sort_keys=True,ensure_ascii=False).encode()),
      judge_runs=runs,observed_at=utcnow())
    return result


def prepare_calibration(root,calibration,packet_directory,sealed):
    client=PublicClient(root);manifest=[]
    for row in calibration:
        aid=row['attempt_id'];path=root/'data/traces'/(aid+'.jsonl.zst')
        if sealed:
            try:
                provenance=sealed_inputs.prepare(root,aid,metadata=row)
                topic=json.loads((root/'data/topics'/(row['challenge_id']+'.json')).read_text())
                taskp=root/'.raw/v6_inputs'/(row['challenge_id']+'.txt')
                atomic(taskp,'\n\n'.join(str(topic[k]) for k in ['title','topicContent','content'] if topic.get(k)).encode())
                manifest.append({'attempt_id':aid,'trace':provenance['converted_path'],'trace_sha256':provenance['converted_trace_sha256'],
                  'task':str(taskp),'outputs':provenance['output_directory'],'out':str(packet_directory/(aid+'.json')),
                  'input_provenance':provenance})
            except Exception as exc:write_json(packet_directory/(aid+'.json'),{'attempt_id':aid,'status':'unknown_sealed_input_failed','error_kind':type(exc).__name__})
            continue
        if not path.exists():
            body=client.get('/api/attempts/'+aid+'/trace')
            if not isinstance(body,list) or any(not isinstance(step,dict) for step in body):raise ValueError('Trace schema changed')
            atomic(path,zstd(''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in body).encode()))
        raw=unzstd(path.read_bytes())
        if not raw.strip():
            # Public API sometimes returns []. Do not call a judge on fabricated events.
            write_json(packet_directory/(aid+'.json'),{'attempt_id':aid,'status':'unknown_public_trace_empty'});continue
        topic=json.loads((root/'data/topics'/(row['challenge_id']+'.json')).read_text())
        directory=root/'.raw/v6_inputs';tp=directory/(aid+'.jsonl');taskp=directory/(row['challenge_id']+'.txt')
        atomic(tp,raw);atomic(taskp,'\n\n'.join(str(topic[k]) for k in ['title','topicContent','content'] if topic.get(k)).encode())
        unpacked,_=unpack_bundle(root,aid)
        manifest.append({'attempt_id':aid,'trace':str(tp),'trace_sha256':sha(raw),'task':str(taskp),'outputs':unpacked,
                         'out':str(packet_directory/(aid+'.json'))})
    run_offline(manifest,root)


def run_offline(manifest,root):
    directory=root/'.raw/v6_inputs';directory.mkdir(parents=True,exist_ok=True)
    home=root/'.raw/offline-home';home.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory,prefix='offline-') as temporary:
        mp=Path(temporary)/'manifest.json';write_json(mp,manifest)
        completed=subprocess.run(['/home/wmywb/.local/bin/node','--experimental-strip-types',str(HERE/'checklist.mjs'),
          str(HERE.parents[1]/'src/cyberscientist/vendor/trace_score_cli_v6/index.ts'),str(mp)],
          env={'HOME':str(home),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=600)
    if completed.returncode:raise RuntimeError('Pinned offline packet creation failed')


def register_packets(staging,destination,manifest_path,rows):
    manifest=[{'attempt_id':r['attempt_id'],'packet_sha256':sha((staging/(r['attempt_id']+'.json')).read_bytes())} for r in rows]
    if manifest_path.exists():
        if json.loads(manifest_path.read_text())!=manifest:raise ValueError('Frozen judge input changed')
        for row in manifest:
            path=destination/(row['attempt_id']+'.json')
            if not path.exists() or sha(path.read_bytes())!=row['packet_sha256']:raise ValueError('Frozen packet bytes changed')
        return manifest
    if destination.exists() and any(destination.iterdir()):raise ValueError('Unregistered packet directory requires review')
    for row in manifest:atomic(destination/(row['attempt_id']+'.json'),(staging/(row['attempt_id']+'.json')).read_bytes())
    write_json(manifest_path,manifest)
    return manifest


def calibrate(root,workers,run_name='sealed-protocol-v3'):
    directory=root/'scorer/judge_replica_runs'/run_name;directory.mkdir(parents=True,exist_ok=True)
    with (directory/'.calibration.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _calibrate_locked(root,workers,run_name)


def _calibrate_locked(root,workers,run_name):
    freeze=json.loads((root/'scorer/calibration_freeze.json').read_text());csvp=root/'scorer/calibration.csv'
    if freeze.get('status')!='final_frozen_before_any_live_judge_call' or sha(csvp.read_bytes())!=freeze['calibration_csv_sha256']:
        raise ValueError('Final calibration freeze required')
    rows=list(read_table('scorer/calibration.csv',root=root));train_topics={r['challenge_id'] for r in rows if r['split']=='train'}
    if train_topics & {r['challenge_id'] for r in rows if r['split']=='holdout'}:raise ValueError('Topic leakage')
    sealed=run_name!='public-snapshot-v1';result_root=root/'scorer/judge_replica_runs'/run_name
    packet_directory=root/'.raw/judge_packets'/run_name;packet_directory.mkdir(parents=True,exist_ok=True)
    config={**CONFIG,'calibration_csv_sha256':sha(csvp.read_bytes()),'frozen_at':utcnow(),'input_view':run_name}
    configp=result_root/'judge_config.json'
    if configp.exists():
        previous=json.loads(configp.read_text());config['frozen_at']=previous['frozen_at']
        if previous!=config:raise ValueError('Judge configuration changed after freezing')
    else:write_json(configp,config)
    input_manifest_path=result_root/'input_manifest.json'
    staging_root=root/'.raw/judge_packet_staging';staging_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_root) as staging:
        prepare_calibration(root,rows,Path(staging),sealed)
        input_manifest=register_packets(Path(staging),packet_directory,input_manifest_path,rows)
    frozen_hashes={r['attempt_id']:r['packet_sha256'] for r in input_manifest}
    predictions=[];failures=[]
    def one(row,provider):
        path=result_root/'judge_runs'/provider/(row['attempt_id']+'.json')
        raw=(packet_directory/(row['attempt_id']+'.json')).read_bytes()
        if sha(raw)!=frozen_hashes[row['attempt_id']]:raise ValueError('Frozen packet changed before judge call')
        packet=json.loads(raw)
        if packet.get('status')!='ok':return None,{'attempt_id':row['attempt_id'],'provider':provider,'reason':packet.get('status')}
        try:
            result=predict(packet,provider);write_json(path,result)
            return {**row,**{k:v for k,v in result.items() if k not in ('judge_runs','missing_evidence')}},None
        except Exception as exc:
            return None,{'attempt_id':row['attempt_id'],'provider':provider,'error_kind':type(exc).__name__,'reason':str(exc)}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(one,row,provider) for row in rows for provider in CONFIG['models']]
        for i,f in enumerate(as_completed(futures),1):
            row,failure=f.result()
            if row:predictions.append(row)
            if failure:failures.append(failure)
            write_csv(result_root/'judge_predictions.csv',predictions);write_json(result_root/'judge_failures.json',failures)
            print(json.dumps({'judge_pairs':i,'expected':len(futures),'successes':len(predictions),'failures':len(failures),'time':utcnow()}),flush=True)
    fitted={};training={}
    for provider in CONFIG['models']:
        train=[r for r in predictions if r['provider']==provider and r['split']=='train']
        if not train:continue
        knots=fit_mapping(train);fitted[provider]=knots
        for row in [r for r in predictions if r['provider']==provider]:
            # Evidence/integrity caps remain binding after an empirical mapping.
            row['mapped_score']=min(apply_mapping(row['predicted_score'],knots),row['score_cap'])
            row['mapped_decision']='block' if row['conditional_decision']=='block' else 'accept' if row['mapped_score']>=70 else 'review'
        training[provider]={'baseline':metrics(train),'mapped':metrics(train,'mapped_score','mapped_decision')}
    expected_train=sum(r['split']=='train' for r in rows);expected_holdout=len(rows)-expected_train
    coverage={p:{'train':sum(r['provider']==p and r['split']=='train' for r in predictions),
                 'holdout':sum(r['provider']==p and r['split']=='holdout' for r in predictions),
                 'expected_train':expected_train,'expected_holdout':expected_holdout} for p in CONFIG['models']}
    candidates=[(1-m['accept_accuracy'],m['mae'],p,variant) for p,variants in training.items() for variant,m in variants.items()
                if coverage[p]['train']==expected_train]
    winner=min(candidates)[2:] if candidates else None
    # Only now, after training selection, compute held-out metrics. No feedback loop.
    held={p:{'baseline':metrics([r for r in predictions if r['provider']==p and r['split']=='holdout']),
      'mapped':metrics([r for r in predictions if r['provider']==p and r['split']=='holdout'],'mapped_score','mapped_decision'),
      'strict_v6':metrics([r for r in predictions if r['provider']==p and r['split']=='holdout'],decision_field='strict_decision')}
      for p in fitted}
    chosen=held[winner[0]][winner[1]] if winner else None
    conditional_pass=bool(chosen and coverage[winner[0]]['holdout']==expected_holdout and chosen['accept_accuracy']>=.85
                          and chosen['blocked_recall'] is not None and chosen['blocked_recall']>=.8)
    write_csv(result_root/'judge_predictions.csv',predictions)
    report={'config':config,'mapping':fitted,'training':training,'holdout':held,
      'selected_using_train_only':winner,'conditional_acceptance_line_passed':conditional_pass,
      'deployment_verdict':'只能作提示','reason':'Original platform worker receipts/input parity unknown; strict v6 decisions retained',
      'missing_predictions':failures,'coverage':coverage,'calibration_size':len(rows),'successful_pairs':len(predictions),'observed_at':utcnow(),
      'input_manifest_sha256':sha(input_manifest_path.read_bytes()),'run_path':str(result_root.relative_to(root))}
    write_json(result_root/'judge_calibration.json',report);write_json(root/'scorer/judge_calibration.json',report)


def single_inputs(bundle,trace,task,root):
    redactor=Redactor().fork();raw=Path(trace).read_text()
    try:body=json.loads(raw)
    except ValueError:body=[json.loads(line) for line in raw.splitlines() if line.strip()]
    body=redactor.obj(body)
    if not isinstance(body,list) or not body:raise ValueError('Nonempty JSON/JSONL event list required')
    clean,_,_=sanitize_archive(Path(bundle).read_bytes(),redactor)
    temp=root/'.raw/single_inputs'/sha(clean+json.dumps(body,sort_keys=True).encode());temp.mkdir(parents=True,exist_ok=True)
    atomic(temp/'.raw/bundles/single.zip',clean)
    provenance=sealed_inputs.prepare(temp,'single',trace_override=body)
    out=provenance['output_directory']
    tp=temp/'trace.jsonl';taskp=temp/'task.txt';packetp=temp/'packet.json'
    traw=''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in body).encode()
    atomic(tp,traw);atomic(taskp,redactor.text(Path(task).read_text()).encode())
    run_offline([{'attempt_id':'single','trace':provenance['converted_path'],'trace_sha256':provenance['converted_trace_sha256'],
                 'task':str(taskp),'outputs':out,'out':str(packetp),'input_provenance':provenance}],temp)
    return json.loads(packetp.read_text())


def correct_selection(root):
    original=root/'scorer/judge_replica_runs/sealed-protocol-v3/judge_calibration.json'
    raw=original.read_bytes();report=json.loads(raw)
    candidates=[(m['mae'],1-m['accept_accuracy'],provider,variant)
        for provider,variants in report['training'].items() for variant,m in variants.items()
        if report['coverage'][provider]['train']==report['coverage'][provider]['expected_train']]
    winner=list(min(candidates)[2:]) if candidates else None
    correction={'selected_using_train_mae':winner,'selection_basis':'training MAE, then training accept error, then stable lexical tie break',
      'original_selected_using_train_only':report['selected_using_train_only'],'original_report_sha256':sha(raw),
      'original_report_path':str(original.relative_to(root)),
      'holdout_already_exposed':True,'holdout_status':'descriptive comparison only; not a new blind validation',
      'no_new_model_calls':True,'unchanged_split_prompts_predictions_and_mappings':True,
      'deployment_verdict':'只能作提示','observed_at':utcnow()}
    write_json(root/'scorer/judge_selection_correction.json',correction)
    return correction


def selected_calibration(root):
    correction=root/'scorer/judge_selection_correction.json'
    if correction.exists():
        fixed=json.loads(correction.read_text())
        path=root/fixed.get('original_report_path','scorer/judge_replica_runs/sealed-protocol-v3/judge_calibration.json')
        if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Corrected selection calibration source changed')
        raw=path.read_bytes()
        if sha(raw)!=fixed['original_report_sha256']:
            raise ValueError('Corrected selection calibration source changed')
        return json.loads(raw),fixed.get('selected_using_train_mae')
    path=root/'scorer/judge_calibration.json';fitted=json.loads(path.read_text()) if path.exists() else {}
    return fitted,fitted.get('selected_using_train_only')


def main():
    p=argparse.ArgumentParser();p.add_argument('--calibrate',action='store_true');p.add_argument('--workers',type=int,default=6)
    p.add_argument('--run-name',choices=['sealed-protocol-v3','sealed-protocol-v2','public-snapshot-v1'],default='sealed-protocol-v3')
    p.add_argument('--provider',choices=list(CONFIG['models']));p.add_argument('--packet');p.add_argument('--baseline',action='store_true')
    p.add_argument('--correct-selection',action='store_true')
    p.add_argument('--bundle');p.add_argument('--trace');p.add_argument('--task');p.add_argument('--out',type=Path)
    args=p.parse_args();root=DEFAULT_DATA
    if args.correct_selection:correct_selection(root);return
    if args.calibrate:calibrate(root,args.workers,args.run_name);return
    packet=json.loads(Path(args.packet).read_text()) if args.packet else single_inputs(args.bundle,args.trace,args.task,root)
    fitted,winner=selected_calibration(root)
    provider=args.provider or (winner[0] if winner else 'deepseek')
    result=predict(packet,provider)
    if not args.baseline and winner and provider==winner[0] and winner[1]=='mapped':
        result['raw_v6_predicted_score']=result['predicted_score']
        result['predicted_score']=min(apply_mapping(result['predicted_score'],fitted['mapping'][provider]),result['score_cap'])
        result['conditional_decision']='block' if result['conditional_decision']=='block' else 'accept' if result['predicted_score']>=70 else 'review'
        result['strict_decision']='insufficient_evidence' if result['conditional_decision']=='accept' and packet['decision']=='insufficient_evidence' else result['conditional_decision']
        result['applied_training_mapping_sha256']=sha(json.dumps(fitted['mapping'][provider]).encode())
        result['calibration_csv_sha256']=fitted['config']['calibration_csv_sha256']
    result['variant']='mapped' if 'raw_v6_predicted_score' in result else 'baseline'
    destination=args.out or root/'.raw/single_prediction.json'
    write_json(destination,result);print(json.dumps({k:result[k] for k in ['predicted_score','conditional_decision','strict_decision','worker_context_status']}))


if __name__=='__main__':main()
