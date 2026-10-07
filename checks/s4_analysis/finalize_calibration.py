"""Fill v8 controls from subsequent public candidates, then freeze by topic."""
import json
from collections import Counter

from .collect_bundles import fetch_bundle
from .common import DEFAULT_DATA,PublicClient,sha,utcnow,write_json
from .dataset import read_table,truth
from .select import ranking
from .tables import number,write_csv


def main():
    root=DEFAULT_DATA
    if any((root/'scorer'/name).exists() for name in ['judge_config.json','judge_predictions.csv']):
        raise RuntimeError('Refusing to alter calibration after judge configuration was frozen')
    client=PublicClient();fields=['attempt_id','challenge_id','author_id','author_name','ours','round_seq','display_score',
        'science_score','trace_score','trace_decision','trace_engine','trace_count','created_at','raw.bundlePath','raw.bundleAvailable']
    rows=list(read_table('data/attempts.csv',fields));by_id={r['attempt_id']:r for r in rows}
    receipts={r['attempt_id']:r for r in read_table('data/bundles_index.csv')}
    history=json.loads((root/'data/bundle_fallback_history.json').read_text())
    def v8(row):return 'v8-process-evidence-sufficiency' in (row['trace_engine'] or '')
    def control(row):return v8(row) and row['trace_decision'] in ('review','block') and (number(row['science_score']) or 0)>=90
    existing=[r for r in rows if receipts.get(r['attempt_id'],{}).get('status')=='ok' and control(r)]
    used_topics={r['challenge_id'] for r in existing}
    candidates=[r for r in rows if control(r) and r['attempt_id'] not in {r['attempt_id'] for r in existing}
                and (r['raw.bundlePath'] or truth(r['raw.bundleAvailable']))]
    candidates.sort(key=lambda r:(r['challenge_id'] in used_topics,sha((r['challenge_id']+r['attempt_id']).encode())))
    for row in candidates:
        if len(existing)>=25:break
        result=fetch_bundle(client,{**row,'bundle_reason':'supplement_v8_high_science_control'})
        receipts[row['attempt_id']]=result;history.append(result)
        if result['status']=='ok':existing.append(row);used_topics.add(row['challenge_id'])
        write_csv(root/'data/bundles_index.csv',sorted(receipts.values(),key=lambda r:int(r['attempt_id'])))
        write_json(root/'data/bundle_fallback_history.json',history)
        print(json.dumps({'v8_controls':len(existing),'target':25,'unique_archives':sum(r['status']=='ok' for r in receipts.values()),'time':utcnow()}),flush=True)
    accepted=[r for r in rows if v8(r) and r['trace_decision']=='accept' and receipts.get(r['attempt_id'],{}).get('status')=='ok']
    accepted.sort(key=lambda r:(r['challenge_id'] in used_topics,sha((r['challenge_id']+r['attempt_id']).encode())))
    # Select diverse topics before taking second samples from a topic.
    def diverse(items,n):
        chosen=[];seen=set()
        for row in items:
            if row['challenge_id'] not in seen:chosen.append(row);seen.add(row['challenge_id'])
            if len(chosen)>=n:return chosen
        return (chosen+[r for r in items if r not in chosen])[:n]
    calibration=[{**r,'stratum':kind} for kind,items,n in [('accept',accepted,35),('review_block',existing,25)] for r in diverse(items,n)]
    refreshed=[]
    for row in calibration:
        body=client.get('/api/attempts/'+row['attempt_id'])
        results=body.get('resultsJson') or {}
        if not isinstance(results,dict):results={}
        row.update(trace_score=number(results.get('trace_score')),trace_decision=results.get('trace_decision'),
                   trace_engine=results.get('trace_score_engine'),receipt_sha256=sha(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()))
        write_json(root/'scorer/calibration_receipts'/(row['attempt_id']+'.json'),body)
        expected='accept' if row['stratum']=='accept' else ('review','block')
        if not v8(row) or row['trace_score'] is None or (row['trace_decision']!=expected if isinstance(expected,str) else row['trace_decision'] not in expected):
            row['calibration_status']='excluded_current_receipt_changed'
        else:row['calibration_status']='eligible';refreshed.append(row)
    topics=sorted({r['challenge_id'] for r in refreshed},key=lambda x:sha(('cs-s4-holdout-v1:'+x).encode()))
    train=set(topics[:round(.6*len(topics))]);additions={r['attempt_id']:r for r in read_table('data/selection_additions.csv')}
    for row in refreshed:
        row.update(split='train' if row['challenge_id'] in train else 'holdout',frozen_at=utcnow(),
                   bundle_sha256=receipts[row['attempt_id']].get('original_sha256'))
        additions[row['attempt_id']]={**row,'selection_reasons':'calibration_v8_verified','semantic_required':False}
    previous=root/'scorer/calibration_freeze.json'
    if previous.exists():write_json(root/'.raw/calibration_freeze_history/preliminary.json',json.loads(previous.read_text()))
    write_csv(root/'scorer/calibration.csv',refreshed)
    write_csv(root/'scorer/calibration_current_receipt_checks.csv',calibration)
    write_csv(root/'data/selection_additions.csv',list(additions.values()))
    write_json(previous,{'frozen_at':utcnow(),'rows':len(refreshed),'topics':len(topics),'train_topics':len(train),
        'holdout_topics':len(topics)-len(train),'strata':dict(Counter(r['stratum'] for r in refreshed)),
        'split_strata':dict(Counter(r['split']+':'+r['stratum'] for r in refreshed)),
        'status':'final_frozen_before_any_live_judge_call','engine':'v8-process-evidence-sufficiency_only',
        'split_rule':'SHA256(cs-s4-holdout-v1:topic); first round(0.6*Ntopics) train; topic never crosses split',
        'calibration_csv_sha256':sha((root/'scorer/calibration.csv').read_bytes()),
        'incomplete_reason':None if len(refreshed)==60 else 'public downloadable/unchanged v8 receipt candidates insufficient'})


if __name__=='__main__':main()
