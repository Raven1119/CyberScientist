"""Freeze reproducible selection rules before trace inspection or calibration."""
import argparse
from collections import defaultdict,Counter

from .common import DEFAULT_DATA, sha, utcnow, write_json
from .dataset import read_table, truth
from .tables import number, write_csv

FIELDS=['attempt_id','challenge_id','author_id','author_name','ours','round_seq',
        'display_score','science_score','trace_score','trace_decision','trace_count',
        'created_at','raw.bundleAvailable']


def ranking(row):
    # Missing is below a real zero; tie order is fixed and independent of traces.
    return (number(row.get('display_score')) if number(row.get('display_score')) is not None else -1,
            number(row.get('trace_score')) if number(row.get('trace_score')) is not None else -1,
            -int(row['attempt_id']))


def select(rows, jump=20):
    topics=defaultdict(list);selected={};bundles={};tops={};controls={}
    def add(row,reason,semantic=False,**extra):
        aid=row['attempt_id']
        item=selected.setdefault(aid,{key:row.get(key) for key in FIELDS})
        item.setdefault('_reasons',set()).add(reason)
        item['semantic_required']=bool(item.get('semantic_required') or semantic)
        item.update(extra)
    for row in rows:topics[row['challenge_id']].append(row)
    for topic,items in sorted(topics.items()):
        by_author=defaultdict(list)
        for row in items:by_author[row['author_id'] or 'unknown:'+row['attempt_id']].append(row)
        leaders=sorted([max(group,key=ranking) for group in by_author.values()],key=ranking,reverse=True)[:10]
        tops[topic]=leaders[0]
        for rank,row in enumerate(leaders,1):add(row,'head_top10',rank<=5,head_rank=rank)
        bundle=leaders[0];bundles[bundle['attempt_id']]={**bundle,'bundle_reason':'topic_first'}
        candidates=[r for r in items if number(r.get('science_score')) is not None and number(r['science_score'])>=90
                    and r.get('trace_decision') in ('review','block')]
        candidates.sort(key=lambda r:(number(r['science_score']),-(number(r.get('trace_score')) or 0),-int(r['attempt_id'])),reverse=True)
        # One control per author before taking five, preserving diverse provenance.
        kept=[];authors=set()
        for row in candidates:
            if row['author_id'] in authors:continue
            authors.add(row['author_id']);kept.append(row)
            if len(kept)==5:break
        controls[topic]=kept
        for row in kept:add(row,'high_science_review_block',True)
        for group in by_author.values():
            group.sort(key=lambda r:(r.get('created_at') or '',int(r['attempt_id'])))
            for before,after in zip(group,group[1:]):
                deltas=[number(after.get(key))-number(before.get(key)) for key in ('display_score','trace_score')
                        if number(after.get(key)) is not None and number(before.get(key)) is not None]
                if any(delta>=jump for delta in deltas):
                    add(before,'jump_before',True);add(after,'jump_after',True)
        for row in items:
            if truth(row.get('ours')):add(row,'ours',True)
        for extreme,predicate in [('over_200',lambda n:n>200),('under_5',lambda n:n<5)]:
            candidates=[r for r in items if number(r.get('trace_count')) is not None and predicate(number(r['trace_count']))]
            for row in sorted(candidates,key=ranking,reverse=True)[:3]:add(row,'extreme_'+extreme)
    # Controls are spread round-robin across the six rounds and distinct topics.
    queues=defaultdict(list)
    for topic,items in sorted(controls.items(),key=lambda x:sha(x[0].encode())):
        if items:queues[str(items[0].get('round_seq'))].append(items[0])
    chosen_controls=[]
    while len(chosen_controls)<25 and any(queues.values()):
        for key in sorted(queues):
            if queues[key] and len(chosen_controls)<25:chosen_controls.append(queues[key].pop(0))
    control_topics={r['challenge_id'] for r in chosen_controls}
    accepts=[]
    for topic in sorted(tops,key=lambda x:(x in control_topics,sha(x.encode()))):
        if tops[topic].get('trace_decision')=='accept':accepts.append(tops[topic])
        if len(accepts)==35:break
    calibration=[]
    for kind,items in [('accept',accepts),('review_block',chosen_controls)]:
        for row in items:
            add(row,'calibration_candidate',False)
            bundles[row['attempt_id']]={**row,'bundle_reason':bundles.get(row['attempt_id'],{}).get('bundle_reason','')+';calibration_'+kind}
            calibration.append({**row,'stratum':kind,'split':'pending_download_verification'})
    for item in selected.values():item['selection_reasons']=';'.join(sorted(item.pop('_reasons')))
    return list(selected.values()),list(bundles.values()),calibration


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--audit',action='store_true');args=parser.parse_args()
    if args.audit:quality_audit();return
    rows=list(read_table('data/attempts.csv',FIELDS));selected,bundles,calibration=select(rows)
    root=DEFAULT_DATA
    write_csv(root/'data/selected.csv',selected)
    write_csv(root/'data/bundles_requested.csv',bundles)
    write_csv(root/'scorer/calibration_candidates.csv',calibration)
    facts={'selected_at':utcnow(),'source_rows':len(rows),'selected':len(selected),
           'semantic_required':sum(r['semantic_required'] for r in selected),
           'bundle_requests':len(bundles),'calibration_candidates':len(calibration),
           'jump_definition':'consecutive same-author/same-topic; trace or display increase >=20 points',
           'ranking':'display descending, trace descending, earliest numeric ID on ties',
            'calibration_freeze':'topic-grouped assignment occurs only after bundle download and before any judge call; both strata may share a topic'}
    write_json(root/'data/selection_rules.json',facts);print(facts)


def quality_audit(root=DEFAULT_DATA):
    rows=list(read_table('data/attempts.csv',FIELDS,root=root));legacy,_,_=select(rows)
    guarded=[{**r,'display_score':None if number(r.get('display_score')) is not None and number(r['display_score'])<0 else r.get('display_score')} for r in rows]
    qualified,_,_=select(guarded);legacy_ids={r['attempt_id'] for r in legacy};valid_ids={r['attempt_id'] for r in qualified}
    frozen=list(read_table('data/selected.csv',root=root));output=[]
    for row in frozen:
        aid=row['attempt_id'];replayed=aid in legacy_ids
        output.append({'attempt_id':aid,'challenge_id':row['challenge_id'],'ours':row['ours'],
          'frozen_selection_reasons':row['selection_reasons'],'present_in_current_raw_rule_replay':replayed,
          'qualified_with_negative_display_treated_unknown':aid in valid_ids if replayed else None,
          'status':'not_in_current_rule_replay_snapshot_may_differ' if not replayed else 'overinclusive_negative_sentinel_jump_candidate' if aid not in valid_ids else 'qualifies_under_guarded_rule'})
    write_csv(root/'data/selection_quality.csv',output)
    source=root/'data/attempts.csv'
    if not source.exists():source=source.with_suffix('.parquet')
    new_ids=legacy_ids-{r['attempt_id'] for r in frozen}
    additions=root/'data/selection_additions.csv'
    additional_ids={r['attempt_id'] for r in read_table('data/selection_additions.csv',root=root)} if additions.exists() else set()
    summary={'observed_at':utcnow(),'frozen_base_rows':len(frozen),'current_raw_rule_ids':len(legacy_ids),
      'guarded_rule_ids':len(valid_ids),'statuses':dict(Counter(r['status'] for r in output)),
      'new_current_rule_ids_outside_frozen_base':sorted(legacy_ids-{r['attempt_id'] for r in frozen},key=int),
      'new_current_rule_ids_covered_by_additions':sorted(new_ids&additional_ids,key=int),
      'uncovered_current_rule_ids':sorted(new_ids-additional_ids,key=int),
      'attempt_table_sha256':sha(source.read_bytes()),'frozen_selection_sha256':sha((root/'data/selected.csv').read_bytes()),
      'action':'Original selection, calibration, model outputs and extra archived samples retained. This is an eligibility-quality annotation, not a retrospective re-fit or sample deletion.','model_calls':0}
    write_json(root/'data/selection_quality_summary.json',summary);print(summary)


if __name__=='__main__':main()
