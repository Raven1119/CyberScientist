"""After two 404s, move to ranked downloadable public candidates; keep failures."""
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed

from .collect_bundles import fetch_bundle
from .common import DEFAULT_DATA,PublicClient,sha,utcnow,write_json
from .dataset import read_table,truth
from .select import ranking
from .tables import number,write_csv


def main():
    root=DEFAULT_DATA;client=PublicClient()
    fields=['attempt_id','challenge_id','author_id','author_name','ours','round_seq','display_score',
            'science_score','trace_score','trace_decision','trace_count','created_at','raw.bundleAvailable','raw.bundlePath']
    rows=list(read_table('data/attempts.csv',fields));by_topic=defaultdict(list)
    for row in rows:by_topic[row['challenge_id']].append(row)
    requested=list(read_table('data/bundles_requested.csv'));initial={r['attempt_id']:r for r in requested}
    receipts={r['attempt_id']:r for r in read_table('data/bundles_index.csv')}
    history=list(receipts.values());chosen=[];additions={}
    def chain(topic,first,kind):
        candidates=[r for r in by_topic[topic] if r['raw.bundlePath'] or truth(r['raw.bundleAvailable'])]
        if kind=='control':candidates=[r for r in candidates if number(r['science_score']) is not None and number(r['science_score'])>=90 and r['trace_decision'] in ('review','block')]
        candidates.sort(key=ranking,reverse=True)
        ordered=[first]+[r for r in candidates if r['attempt_id']!=first['attempt_id']]
        attempted=[]
        for rank,row in enumerate(ordered,1):
            item={**row,'bundle_reason':kind+'_ranked_fallback'}
            # Completed over-limit probes stay skipped. A permanent 404 is retried
            # under the user's updated rule, then the next candidate is tried.
            previous=receipts.get(row['attempt_id'])
            result=previous if previous and previous['status']=='skipped' else fetch_bundle(client,item)
            attempted.append(result)
            if result['status']=='ok':
                return {'kind':kind,'topic':topic,'original_attempt_id':first['attempt_id'],
                        'attempt_id':row['attempt_id'],'fallback_ordinal':rank,'source':row},attempted
        return {'kind':kind,'topic':topic,'original_attempt_id':first['attempt_id'],'status':'no_downloadable_candidate'},attempted
    leaders=[r for r in requested if 'topic_first' in r['bundle_reason']]
    controls=[r for r in requested if 'calibration_review_block' in r['bundle_reason']]
    jobs=[(r['challenge_id'],r,'leader') for r in leaders]+[(r['challenge_id'],r,'control') for r in controls]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(chain,*job) for job in jobs]
        for future in as_completed(futures):
            choice,attempted=future.result();history.extend(attempted);chosen.append(choice)
            for item in attempted:receipts[item['attempt_id']]=item
            if choice.get('source'):
                source=choice['source'];aid=source['attempt_id']
                additions[aid]={**source,'selection_reasons':'bundle_ranked_fallback','semantic_required':False}
            write_csv(root/'data/bundles_index.csv',sorted(receipts.values(),key=lambda r:int(r['attempt_id'])))
            write_json(root/'data/bundle_fallback_history.json',history)
            write_json(root/'data/bundle_fallback_choices.json',chosen)
            print(json.dumps({'chains_complete':len(chosen),'expected':len(jobs),
                'successful_chains':sum('attempt_id' in c for c in chosen),
                'unique_archives':sum(r['status']=='ok' for r in receipts.values()),'time':utcnow()}),flush=True)
    # Freeze both strata only from actual successful archives, with topic groups.
    eligible={r['attempt_id']:r for r in rows if receipts.get(r['attempt_id'],{}).get('status')=='ok'}
    controls_ok=[r for r in eligible.values() if r['trace_decision'] in ('review','block') and number(r['science_score']) is not None and number(r['science_score'])>=90]
    accept_ok=[r for r in eligible.values() if r['trace_decision']=='accept']
    def diverse(items,limit):
        ordered=sorted(items,key=lambda r:sha((r['challenge_id']+':'+r['attempt_id']).encode()))
        used=set();out=[]
        for row in ordered:
            if row['challenge_id'] not in used:out.append(row);used.add(row['challenge_id'])
            if len(out)==limit:return out
        out.extend(r for r in ordered if r not in out)
        return out[:limit]
    calibration=[{**r,'stratum':kind} for kind,items,n in [('accept',accept_ok,35),('review_block',controls_ok,25)] for r in diverse(items,n)]
    topics=sorted({r['challenge_id'] for r in calibration},key=lambda x:sha(('cs-s4-holdout-v1:'+x).encode()))
    train=set(topics[:round(.6*len(topics))])
    for row in calibration:
        row['split']='train' if row['challenge_id'] in train else 'holdout'
        row['bundle_sha256']=receipts[row['attempt_id']].get('original_sha256')
        row['frozen_at']=utcnow()
        additions[row['attempt_id']]={**row,'selection_reasons':'calibration','semantic_required':False}
    write_csv(root/'scorer/calibration.csv',calibration)
    write_csv(root/'data/selection_additions.csv',list(additions.values()))
    write_json(root/'scorer/calibration_freeze.json',{'frozen_at':utcnow(),'attempt_ids':[r['attempt_id'] for r in calibration],
        'topics':len(topics),'train_topics':len(train),'holdout_topics':len(topics)-len(train),
        'rows':len(calibration),'requested_accept':35,'requested_review_block':25,
        'actual_accept':sum(r['stratum']=='accept' for r in calibration),
        'actual_review_block':sum(r['stratum']=='review_block' for r in calibration),
        'split_rule':'SHA256(cs-s4-holdout-v1:topic), first round(0.6*Ntopics) train; same topic never crosses split',
        'status':'frozen_before_model_judging','calibration_csv_sha256':sha((root/'scorer/calibration.csv').read_bytes())})


if __name__=='__main__':main()
