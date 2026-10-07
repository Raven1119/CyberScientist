"""Deterministic receipt comparisons, reuse proxies and image-lock inventory.

No scientific computation, downloaded code execution, grader reconstruction or
inference that missing public fields prove missing original research.
"""
import io
import json
import re
import sys
import zipfile
from collections import Counter,defaultdict
from pathlib import Path

from .common import DEFAULT_DATA,sha,utcnow,write_json,atomic
from .dataset import read_table,truth
from .features import extract
from .tables import number,write_csv


def jaccard(left,right):
    a=set(left);b=set(right)
    return len(a&b)/len(a|b) if a and b else None


def reliability(tp,fp,fn,positive):
    precision=tp/(tp+fp) if tp+fp else None
    recall=tp/(tp+fn) if tp+fn else None
    grade='unknown_or_unusable'
    if precision is not None and recall is not None:
        if positive>=5 and min(precision,recall)>=.9:grade='conditionally_reliable'
        elif positive>=3 and min(precision,recall)>=.7:grade='indicative'
    return precision,recall,grade


def agreement(root):
    attempts={r['attempt_id']:r for r in read_table('data/attempts.csv',
      ['attempt_id','challenge_id','ours','trace_engine','trace_score'])}
    returned=defaultdict(set)
    for r in read_table('data/deductions.csv'):returned[r['attempt_id']].add(r['raw.code'])
    pairs=[];groups=defaultdict(list);caps=[];coverage=[]
    selected=list(read_table('data/selected.csv'))
    if (root/'data/selection_additions.csv').exists():selected+=list(read_table('data/selection_additions.csv'))
    for aid,item in {r['attempt_id']:r for r in selected}.items():
        path=root/'.raw/v6_reports'/(aid+'.json')
        report=json.loads(path.read_text()) if path.exists() else {}
        row=attempts.get(aid,{})
        is_v8='v8-process-evidence-sufficiency' in (row.get('trace_engine') or '')
        coverage.append({'attempt_id':aid,'challenge_id':item['challenge_id'],'ours':item['ours'],
          'v6_status':report.get('status','unknown_uncollected_or_unprepared'),
          'is_v8':is_v8,'included_in_code_comparison':is_v8 and report.get('status')=='ok'})
    for path in (root/'.raw/v6_reports').glob('*.json'):
        report=json.loads(path.read_text());aid=path.stem;row=attempts.get(aid,{})
        if report.get('status')!='ok' or 'v8-process-evidence-sufficiency' not in (row.get('trace_engine') or ''):continue
        local={i['code']:i for i in report.get('items',[]) if i.get('polarity')=='negative'}
        for code in sorted(set(local)|returned[aid]):
            item=local.get(code);status=item.get('status') if item else 'unknown_v8_only'
            pair={'attempt_id':aid,'challenge_id':row['challenge_id'],'ours':row['ours'],'code':code,
              'v6_status':status,'v8_listed':code in returned[aid],
              'v6_input_source':'archive_selected' if report.get('input_provenance') else 'public_api',
              'platform_input_parity':'unknown','v6_trace_sha256':report.get('trace_sha256')}
            pairs.append(pair);groups[code].append(pair)
        score=number(row.get('trace_score'));cap=number(report.get('cap'))
        caps.append({'attempt_id':aid,'challenge_id':row['challenge_id'],'ours':row['ours'],
          'v8_trace_score':score,'v6_cap':cap,'v8_above_local_cap':score>cap+.001 if score is not None and cap is not None else None,
          'input_parity':'unknown'})
    aggregates=[]
    for code,items in sorted(groups.items()):
        observed=[i for i in items if i['v6_status'] in ['triggered','clear']]
        tp=sum(i['v6_status']=='triggered' and i['v8_listed'] for i in observed)
        fp=sum(i['v6_status']=='triggered' and not i['v8_listed'] for i in observed)
        fn=sum(i['v6_status']=='clear' and i['v8_listed'] for i in observed)
        tn=sum(i['v6_status']=='clear' and not i['v8_listed'] for i in observed)
        p,r,grade=reliability(tp,fp,fn,tp+fn)
        aggregates.append({'code':code,'samples':len(items),'ours_samples':sum(truth(i['ours']) for i in items),
          'v8_listed_positives':sum(i['v8_listed'] for i in items),'not_observable_or_v8_only':len(items)-len(observed),
          'TP':tp,'FP':fp,'FN':fn,'TN':tn,'conditional_precision':p,'conditional_recall':r,'conditional_grade':grade,
          'open_precision_lower':p,'open_precision_upper':1 if tp+fp else None,
          'open_recall_lower':tp/(tp+fn+tn) if tp+fn+tn else None,
          'open_recall_upper':(tp+fp)/(tp+fp+fn) if tp+fp+fn else None,
          'unlisted_v8_interpretation':'closed-world metrics conditional; open-world unknown',
          'mechanically_reproducible':'unknown_no_pinned_v6_rule' if all(i['v6_status']=='unknown_v8_only' for i in items) else 'pinned_v6_only_not_verified_v8'})
    write_csv(root/'scorer/v6_v8_pairs.csv',pairs);write_csv(root/'scorer/v6_v8_agreement.csv',aggregates)
    write_csv(root/'scorer/v6_v8_cap_checks.csv',caps)
    write_csv(root/'scorer/v6_v8_coverage.csv',coverage)
    summary={'samples':len(caps),'pairs':len(pairs),'codes':len(aggregates),'v8_above_local_cap':sum(i['v8_above_local_cap'] is True for i in caps),
      'not_observable_pairs':sum(r['not_observable_or_v8_only'] for r in aggregates),'observed_at':utcnow(),
      'selected_attempts':len(coverage),'coverage_v6_statuses':dict(Counter(r['v6_status'] for r in coverage)),
      'not_included_attempts':sum(not r['included_in_code_comparison'] for r in coverage),
      'source_quality':'Public API often omits tool bodies; archive and platform worker inputs not equated'}
    write_json(root/'scorer/v6_v8_summary.json',summary)
    docs=Path(__file__).resolve().parents[2]/'docs';path=docs/'TRACE_CHECKLIST_V6_V8_AGREEMENT.md'
    marker='\n## CS-UP-11 expanded public snapshot\n'
    text=path.read_text().split(marker)[0]+marker+'\nGenerated '+utcnow()+f". Current available v8 comparison: {len(caps)} of {len(coverage)} selected attempts / {len(pairs)} code pairs; {summary['not_observable_pairs']} unavailable pairs within that comparison. All selected IDs, including empty, uncollected, failed and non-v8 inputs, remain in private `scorer/v6_v8_coverage.csv`. This section is regenerated as trace collection advances. Original 63-sample evidence above remains unchanged.\n\n"
    text+='| Full code | Observable positives | TP | FP | FN | TN | Precision | Recall | Conditional grade |\n|---|---:|---:|---:|---:|---:|---:|---:|---|\n'
    fmt=lambda v:'unknown' if v is None else f'{v:.3f}'
    for r in aggregates:text+=f"| {r['code']} | {r['TP']+r['FN']} | {r['TP']} | {r['FP']} | {r['FN']} | {r['TN']} | {fmt(r['conditional_precision'])} | {fmt(r['conditional_recall'])} | {r['conditional_grade']} |\n"
    text+=f"\n{summary['v8_above_local_cap']} observed scores exceed the locally reconstructed v6 cap. This does not identify the cause: version, public-field omissions, redaction and worker input differences remain confounded. N17 and N18 have no pinned v6 rule and remain unknown for mechanical reproduction. Open-world precision/recall bounds and every attempt ID are retained in private scorer tables. Public missing tool fields cannot establish that original execution evidence was absent.\n"
    atomic(path,text.encode())
    return summary


def reuse(root):
    columns=['attempt_id','challenge_id','author_id','ours','created_at','science_score','trace_score','trace_decision']
    attempts=list(read_table('data/attempts.csv',columns));features={r['attempt_id']:r for r in read_table('data/trace_features.csv')}
    claims=defaultdict(list)
    for r in read_table('data/missing_evidence.csv'):
        if re.search(r'cop(?:y|ied)|reus|pre.?exist|independent.*execut|own.*execut',r.get('text') or '',re.I):claims[r['attempt_id']].append(r['evidence_index'])
    groups=defaultdict(list)
    for r in attempts:
        if r['author_id']:groups[(r['challenge_id'],r['author_id'])].append(r)
    output=[];noise=[]
    for (topic,author),rows in groups.items():
        rows.sort(key=lambda r:(r['created_at'] or '',int(r['attempt_id'])))
        for before,after in zip(rows,rows[1:]):
            a=features.get(before['attempt_id'],{});b=features.get(after['attempt_id'],{})
            ca=a.get('code_sequence_sha256');cb=b.get('code_sequence_sha256')
            ha=json.loads(a.get('command_hashes_json') or '[]');hb=json.loads(b.get('command_hashes_json') or '[]')
            nonempty=number(a.get('step_count')) is not None and number(a['step_count'])>0 and number(b.get('step_count')) is not None and number(b['step_count'])>0
            similarity=jaccard(ha,hb) if nonempty else None
            ta=a.get('canonical_trace_sha256') if nonempty else None;tb=b.get('canonical_trace_sha256') if nonempty else None
            row={'challenge_id':topic,'author_id':author,'before_attempt_id':before['attempt_id'],'attempt_id':after['attempt_id'],'ours':after['ours'],
              'before_created_at':before['created_at'],'created_at':after['created_at'],
              'code_hash_equal':ca==cb if ca and cb else None,'command_hash_jaccard':similarity,
              'same_available_trace_sha':ta==tb if ta and tb else None,'source_content_status':'available_nonempty_both' if nonempty else 'unknown_empty_or_uncollected_trace',
              'later_copy_related_missing_evidence_indices_json':json.dumps(claims[after['attempt_id']]),
              'later_copy_related_statement_present':bool(claims[after['attempt_id']]),
              'before_trace_score':number(before['trace_score']),'trace_score':number(after['trace_score']),
              'science_score_equal':number(before['science_score'])==number(after['science_score']) if number(before['science_score']) is not None and number(after['science_score']) is not None else None}
            output.append(row)
            if row['science_score_equal'] and (row['same_available_trace_sha'] or similarity is not None and similarity>=.95):
                noise.append({**row,'match_kind':'same_author_science_and_available_trace_or_command_proxy',
                  'trace_score_delta':row['trace_score']-row['before_trace_score'] if row['trace_score'] is not None and row['before_trace_score'] is not None else None,
                  'causal_noise_claim':'unknown_input_worker_or_version_may_differ'})
    originals=defaultdict(list)
    for path in (root/'data/bundle_inventories').glob('*.json'):
        d=json.loads(path.read_text());index=d.get('index',d);digest=index.get('original_sha256')
        if digest:originals[digest].append(index.get('attempt_id',path.stem))
    byid={r['attempt_id']:r for r in attempts}
    for digest,ids in originals.items():
        for previous,later in zip(sorted(ids,key=int),sorted(ids,key=int)[1:]):
            a=byid.get(previous,{});b=byid.get(later,{})
            x=number(a.get('trace_score'));y=number(b.get('trace_score'))
            noise.append({'before_attempt_id':previous,'attempt_id':later,'challenge_id':b.get('challenge_id'),'ours':b.get('ours'),
              'match_kind':'identical_original_archive_sha256','original_archive_sha256':digest,'before_trace_score':x,'trace_score':y,
              'trace_score_delta':y-x if x is not None and y is not None else None,'causal_noise_claim':'unknown_worker_inputs_may_differ'})
    write_csv(root/'data/reuse_check.csv',output);write_csv(root/'scorer/scoring_noise.csv',noise,
      fields=None if noise else ['attempt_id','before_attempt_id','challenge_id','ours','match_kind','trace_score_delta','causal_noise_claim'])
    summary={'consecutive_pairs':len(output),'both_code_hash_available':sum(r['code_hash_equal'] is not None for r in output),
      'both_command_hash_available':sum(r['command_hash_jaccard'] is not None for r in output),
      'noise_candidates':len(noise),'identical_original_archive_pairs':sum(r['match_kind']=='identical_original_archive_sha256' for r in noise),'observed_at':utcnow()}
    write_json(root/'scorer/reuse_noise_summary.json',summary);return summary


MODULE_PACKAGES={'PIL':'pillow','sklearn':'scikit-learn','cv2':'opencv-python','yaml':'pyyaml','skimage':'scikit-image','Bio':'biopython','OpenSSL':'pyopenssl'}


def package_name(module):
    name=module.split('.')[0]
    if name in sys.stdlib_module_names or name.startswith('_'):return None
    return MODULE_PACKAGES.get(name,name).lower().replace('_','-')


def environment_inventory(root):
    workspace=Path(__file__).resolve().parents[2];directory=workspace/'environments/cs-up-12'
    selected=list(read_table('data/selected.csv'));head=[r for r in selected if number(r.get('head_rank')) is not None and number(r['head_rank'])<=10]
    features={r['attempt_id']:r for r in read_table('data/trace_features.csv')};topics={r['challenge_id']:r for r in read_table('data/challenges.csv')}
    output=[];packages=defaultdict(set)
    for row in head:
        aid=row['attempt_id'];f=features.get(aid,{});source='public_api'
        provenance=root/'scorer/sealed_input_provenance'/(aid+'.json')
        if provenance.exists():
            p=json.loads(provenance.read_text());trace=Path(p['converted_path'])
            if trace.exists():
                steps=[json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
                enriched,_=extract(aid,row,steps,{'_canonical_input_sha256':sha(trace.read_bytes())},root)
                # Keep source labels; this does not replace the canonical API feature table.
                f=enriched;source='archive_selected_officially_converted'
        topic=topics.get(row['challenge_id'],{});imports=json.loads(f.get('imports_json') or '[]')
        mapped=sorted({package_name(m) for m in imports if package_name(m)})
        for package in mapped:packages[package].add(aid)
        output.append({'attempt_id':aid,'challenge_id':row['challenge_id'],'ours':row['ours'],'head_rank':row['head_rank'],
          'topic_type':topic.get('topic_type') or topic.get('disc'),'trace_source':source,'imports_json':json.dumps(imports),
          'candidate_packages_json':json.dumps(mapped),'install_declarations_json':f.get('software_install_declarations_json'),
          'compute_location_candidates_json':f.get('compute_location_candidates_json'),'gpu_reference_steps_json':f.get('gpu_reference_steps_json'),
          'gpu_use_confirmed':None,'stack_versions_status':'visible declarations only; no remote validation',
          'source_markers_json':f.get('source_markers_json'),'converter_or_cli_version_markers_json':f.get('converter_or_cli_version_markers_json'),
          'visible_command_steps':f.get('visible_command_steps'),'tool_results_with_visible_content':f.get('tool_results_with_visible_content'),
          'software_visibility':'unknown_missing_public_content' if not mapped else 'candidate_references_not_verified_installation'})
    write_csv(root/'data/environments.csv',output)
    gap=[];locks={}
    for path in directory.glob('*.requirements.lock'):
        versions={}
        for line in path.read_text().splitlines():
            match=re.match(r'^([A-Za-z0-9_.-]+)==([^\s;]+)',line)
            if match:versions[match[1].lower().replace('_','-')]=match[2]
        locks[path.name.split('.')[0]]=(versions,sha(path.read_bytes()),str(path.relative_to(workspace)))
    locks['lean-mathlib']=({},sha((directory/'lean-mathlib.pins.json').read_bytes()),str((directory/'lean-mathlib.pins.json').relative_to(workspace)))
    for image,(versions,digest,path) in locks.items():
        for package,ids in sorted(packages.items()):
            gap.append({'image':image,'package_candidate':package,'head_attempt_count':len(ids),'attempt_ids_json':json.dumps(sorted(ids,key=int)),
              'ours_attempt_count':sum(truth(r['ours']) for r in head if r['attempt_id'] in ids),
              'lock_status':'not_applicable_python_stack_unknown' if image=='lean-mathlib' else 'present_in_verified_lock_snapshot' if package in versions else 'absent_from_verified_lock_snapshot',
              'locked_version':versions.get(package),'lock_source':path,'lock_sha256':digest,'snapshot_date':'2026-10-06',
              'current_remote_verification':'not_performed','import_to_distribution_mapping':'heuristic; local project module may have same name'})
    write_csv(root/'data/env_gap.csv',gap,fields=None if gap else ['image','package_candidate','head_attempt_count','ours_attempt_count','lock_status','locked_version','lock_source','lock_sha256','current_remote_verification'])
    bytype=defaultdict(list)
    for row in output:bytype[row.get('topic_type') or 'unknown'].append(row)
    write_csv(root/'data/environments_by_type.csv',[{'topic_type':kind,'head_attempts':len(rows),'ours_attempts':sum(truth(r['ours']) for r in rows),
      'software_visible_attempts':sum(r['software_visibility'].startswith('candidate') for r in rows),
      'imports_json':json.dumps(sorted({m for r in rows for m in json.loads(r['imports_json'])})),
      'actual_gpu_usage':'unknown; references do not confirm execution'} for kind,rows in sorted(bytype.items())])
    summary={'head_attempts':len(output),'attempts_with_package_candidates':sum(bool(json.loads(r['candidate_packages_json'])) for r in output),
      'distinct_package_candidates':len(packages),'image_locks':len(locks),'no_new_compute_jobs':True,'observed_at':utcnow()}
    write_json(root/'data/environment_summary.json',summary);return summary


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--section',choices=['all','agreement','reuse','environment'],default='all');args=p.parse_args()
    for name,fn in [('agreement',agreement),('reuse',reuse),('environment',environment_inventory)]:
        if args.section in ['all',name]:print(json.dumps({name:fn(DEFAULT_DATA)}),flush=True)


if __name__=='__main__':main()
