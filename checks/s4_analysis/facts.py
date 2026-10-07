"""P0 scoring and within-round timing facts; no semantic or causal guesses."""
import json
import re
import statistics
from collections import Counter,defaultdict
from pathlib import Path

from .common import DEFAULT_DATA,sha,utcnow,write_json
from .dataset import read_table,truth
from .select import ranking
from .tables import number,timestamp,write_csv

FIELDS=['attempt_id','challenge_id','round_seq','topic_type','author_id','ours','display_score',
 'science_score','trace_score','trace_decision','trace_engine','trace_quality_class','created_at',
 'updated_at','score_is_final','minutes_since_round_start','is_within_round',
 'raw.scoringDetails.source','raw.scoringDetails.trace_factor','raw.scoringState.zeroReason',
 'raw.scoringState.overrideInEffect','raw.resultsJson.scored_by','raw.scorecard.harbor_reward',
 'raw.scorecard.executability','raw.scorecard.packaging','raw.scorecard.output_coverage',
 'raw.scorecard.result_fidelity','raw.scorecard.harbor_replay_executed','raw.status',
 'raw.scoringDetails.reasoning_bonus.points','raw.scoringDetails.reasoning_bonus.applied',
 'raw.scoringDetails.zero_reason','raw.scoringDetails.counts_toward_season']


def median(values):return statistics.median(values) if values else None


def scorer_facts(rows,root):
    scores=Counter();grid=[];boundaries=defaultdict(list);engines=defaultdict(list)
    formula=[];exceptions=[];science=[]
    for row in rows:
        trace=number(row['trace_score']);decision=row['trace_decision']
        if trace is not None:
            scores[trace]+=1;boundaries[decision or 'unknown'].append(trace)
            if abs(trace/.025-round(trace/.025))>1e-6:grid.append(row)
        engines[row['trace_engine'] or 'unknown'].append(row)
        display=number(row['display_score']);harbor=number(row['science_score'])
        factor=1 if decision=='accept' else trace/100 if decision=='review' and trace is not None else 0 if decision=='block' else None
        if display is not None and harbor is not None and factor is not None:
            expected=harbor*factor;residual=display-expected
            receipt_factor=number(row['raw.scoringDetails.trace_factor'])
            bonus=number(row['raw.scoringDetails.reasoning_bonus.points'])
            with_bonus=expected+(bonus or 0)
            receipt_expected=harbor*receipt_factor+(bonus or 0) if receipt_factor is not None else None
            kind='matches_simple_formula' if abs(residual)<=.001 else 'negative_display_sentinel' if display<0 else 'explicit_override' if truth(row['raw.scoringState.overrideInEffect']) else 'explicit_zero_reason' if display==0 and (row['raw.scoringState.zeroReason'] or row['raw.scoringDetails.zero_reason']) else 'reasoning_bonus_explains' if abs(display-with_bonus)<=.001 else 'receipt_factor_explains' if receipt_expected is not None and abs(display-receipt_expected)<=.001 else 'unexplained'
            item={'attempt_id':row['attempt_id'],'challenge_id':row['challenge_id'],'ours':row['ours'],
                  'display_score':display,'harbor_score':harbor,'trace_score':trace,'trace_decision':decision,
                  'predicted_display_score':expected,'residual':residual,'within_tolerance':abs(residual)<=.001,
                  'score_is_final':row['score_is_final'],'override_in_effect':row['raw.scoringState.overrideInEffect'],
                  'zero_reason':row['raw.scoringState.zeroReason'] or row['raw.scoringDetails.zero_reason'],'engine':row['trace_engine'],
                  'receipt_trace_factor':receipt_factor,'reasoning_bonus_points':bonus,'predicted_with_receipt_factor_bonus':receipt_expected,
                  'exception_class':kind,'raw_status':row['raw.status']}
            formula.append(item)
            if abs(residual)>.001:exceptions.append(item)
        reward=number(row['raw.scorecard.harbor_reward'])
        if reward is not None and harbor is not None:
            science.append({'attempt_id':row['attempt_id'],'challenge_id':row['challenge_id'],'ours':row['ours'],
                'harbor_reward':reward,'harbor_score':harbor,'reward_times_100_residual':harbor-reward*100,
                **{key.removeprefix('raw.scorecard.'):row[key] for key in FIELDS if key.startswith('raw.scorecard.')},
                'scoring_source':row['raw.scoringDetails.source'],'scored_by':row['raw.resultsJson.scored_by']})
    write_csv(root/'scorer/display_formula_checks.csv',formula)
    write_csv(root/'scorer/display_formula_exceptions.csv',exceptions,fields=list(formula[0]) if formula else None)
    write_csv(root/'scorer/science_layer.csv',science)
    write_csv(root/'scorer/grid_exceptions.csv',grid,fields=FIELDS)
    write_csv(root/'scorer/trace_score_histogram.csv',[{'trace_score':s,'count':n} for s,n in sorted(scores.items())])
    codes=defaultdict(list)
    for item in read_table('data/deductions.csv'):codes[item.get('raw.code') or 'unknown'].append(item)
    source=(Path(__file__).resolve().parents[2]/'src/cyberscientist/vendor/trace_score_cli_v6/index.ts').read_text()
    code_rows=[]
    for code,items in sorted(codes.items()):
        counts=Counter(item.get('raw.score_effect') for item in items)
        code_rows.append({'code':code,'occurrences':len(items),'attempts':len({r['attempt_id'] for r in items}),
            'effects_json':json.dumps(dict(counts),ensure_ascii=False),
            'titles_json':json.dumps(sorted({r.get('raw.title') or '' for r in items}),ensure_ascii=False),
            'sample_attempt_ids':';'.join(sorted({r['attempt_id'] for r in items},key=int)[:10]),
            'present_in_pinned_v6_source':code!='unknown' and '"'+code+'"' in source,
            'explanations_json':json.dumps(sorted({r.get('raw.description') or r.get('raw.explanation') or '' for r in items}),ensure_ascii=False)})
    write_csv(root/'scorer/code_table.csv',code_rows)
    timelines=[]
    for clock in ['created_at','updated_at']:
        groups=defaultdict(list)
        for row in rows:groups[(row['trace_engine'] or 'unknown',(row[clock] or '')[:10],row['is_within_round'])].append(row)
        for (engine,day,within),items in sorted(groups.items(),key=str):
            timelines.append({'engine':engine,'timestamp_basis':clock,'date':day,'created_within_round':within,
                'count':len(items),'attempt_id_min':min(int(r['attempt_id']) for r in items),
                'attempt_id_max':max(int(r['attempt_id']) for r in items),'actual_scored_at_observable':False})
    write_csv(root/'scorer/engine_timeline.csv',timelines)
    v8=[r for r in rows if 'v8-process-evidence-sufficiency' in (r['trace_engine'] or '')]
    v8_hist=Counter(number(r['trace_score']) for r in v8 if number(r['trace_score']) is not None)
    v8_ranges={}
    for decision in sorted({r['trace_decision'] or 'unknown' for r in v8}):
        values=[number(r['trace_score']) for r in v8 if (r['trace_decision'] or 'unknown')==decision and number(r['trace_score']) is not None]
        v8_ranges[decision]={'count':len(values),'min':min(values,default=None),'max':max(values,default=None)}
    by_id={r['attempt_id']:r for r in rows};cooccurrence=[]
    for code,items in codes.items():
        subset=[by_id[item['attempt_id']] for item in items if item['attempt_id'] in by_id and 'v8-process-evidence-sufficiency' in (by_id[item['attempt_id']]['trace_engine'] or '')]
        values=[number(r['trace_score']) for r in subset if number(r['trace_score']) is not None]
        cooccurrence.append({'code':code,'v8_attempts':len(subset),'min_trace_score':min(values,default=None),'max_trace_score':max(values,default=None),
           'decision_counts_json':json.dumps(dict(Counter(r['trace_decision'] for r in subset))),
           'spike_counts_json':json.dumps({str(cap):sum(value==cap for value in values) for cap in [20,29,49,59,69]}),
           'interpretation':'co-occurrence only; does not identify hidden trigger or causality'})
    write_csv(root/'scorer/cap_cooccurrence.csv',cooccurrence)
    rules={'generated_at':utcnow(),'source_snapshot_phase':json.loads((root/'data/coverage.json').read_text())['phase'],
       'attempts':len(rows),'trace_score_observations':sum(scores.values()),'grid_step_tested':.025,
       'grid_exception_count':len(grid),'trace_decisions':dict(Counter(r['trace_decision'] or 'unknown' for r in rows)),
       'decision_score_ranges':{key:{'count':len(v),'min':min(v),'max':max(v)} for key,v in boundaries.items()},
       'score_spikes':[{'score':s,'count':n} for s,n in scores.most_common(20)],
       'display_formula':{'accept':'harbor_score','review':'harbor_score * trace_score/100','block':'0',
                          'tolerance':.001,'tested':len(formula),'exceptions':len(exceptions),
                          'final_tested':sum(truth(r['score_is_final']) for r in formula),
                          'final_exceptions':sum(truth(r['score_is_final']) for r in exceptions),
                          'exception_classes':dict(Counter(r['exception_class'] for r in exceptions))},
       'v8_only':{'attempts':len(v8),'trace_score_observations':sum(v8_hist.values()),'decision_score_ranges':v8_ranges,
          'grid_exceptions':sum(abs(value/.025-round(value/.025))>1e-6 for value in v8_hist.elements()),
          'score_spikes':[{'score':value,'count':n} for value,n in v8_hist.most_common(20)]},
       'grading_time_evidence':{'actual_timestamp_observable':False,'public_status_counts':dict(Counter(r['raw.status'] or 'unknown' for r in rows)),
          'late_scored_status_attempts':sum(r['raw.status']=='late_scored' for r in rows),
          'created_within_round_is_not_scored_within_round':True},
       'engine_counts':{key:len(value) for key,value in engines.items()},
       'unobservable':['actual_scored_at','private judge P/H','server-normalized final trace','worker integrity receipts'],
       'inference_boundary':'spikes and absence of cap violations do not identify hidden cap triggers or v8 fusion weights',
       'pinned_v6_source_sha256':sha(source.encode()),'code_count':len(code_rows)}
    write_json(root/'scorer/v8_rules.json',rules)
    return rules,code_rows


def rhythm_facts(rows,root):
    topics={p.stem:json.loads(p.read_text()) for p in (root/'data/topics').glob('*.json')}
    groups=defaultdict(list)
    for row in rows:
        if truth(row['is_within_round']):groups[row['challenge_id']].append(row)
    rhythms=[];curves=[]
    for topic_id,topic in sorted(topics.items()):
        items=groups[topic_id];authors=defaultdict(list)
        for row in items:authors[row['author_id']].append(row)
        leaders=sorted([max(group,key=ranking) for group in authors.values()],key=ranking,reverse=True)[:10]
        pattern_count=0
        for leader in leaders:
            history=sorted(authors[leader['author_id']],key=lambda r:(r['created_at'] or '',int(r['attempt_id'])))
            first=number(history[0]['display_score']);best=number(leader['display_score'])
            pattern=first is not None and best is not None and 0<first<=70 and best-first>=20 and len(history)>1
            pattern_count+=pattern
            curves.append({'challenge_id':topic_id,'topic_type':topic.get('disc'),'author_id':leader['author_id'],
                'ours':leader['ours'],'within_round_attempt_count':len(history),'best_attempt_id':leader['attempt_id'],
                'first_display_score':first,'best_display_score':best,'steady_then_higher_proxy':pattern,
                'curve_json':json.dumps([{'index':i+1,'attempt_id':r['attempt_id'],'minutes':number(r['minutes_since_round_start']),
                                         'display_score':number(r['display_score'])} for i,r in enumerate(history)])})
        timed=[r for r in items if number(r['minutes_since_round_start']) is not None]
        scored=[r for r in timed if number(r['display_score']) is not None]
        best=max(scored,key=ranking) if scored else None
        end=timestamp(topic.get('roundEndAt'))
        last=max((timestamp(r['created_at']) for r in timed),default=None)
        proxy_delays=[]
        for row in items:
            a,b=timestamp(row['created_at']),timestamp(row['updated_at'])
            if a and b and truth(row['score_is_final']) and b>=a:proxy_delays.append((b-a).total_seconds()/60)
        rhythms.append({'challenge_id':topic_id,'round_seq':topic.get('roundSeq'),'topic_type':topic.get('disc'),
           'round_start_at':topic.get('roundStartAt'),'round_end_at':topic.get('roundEndAt'),
           'within_round_submissions':len(items),'within_round_authors':len(authors),
           'first_submission_minutes':min((number(r['minutes_since_round_start']) for r in timed),default=None),
           'best_score_first_minutes':number(best['minutes_since_round_start']) if best else None,
           'best_attempt_id':best['attempt_id'] if best else None,'best_display_score':number(best['display_score']) if best else None,
           'last_submission_minutes_before_end':(end-last).total_seconds()/60 if end and last else None,
           'head_authors':len(leaders),'steady_then_higher_proxy_count':pattern_count,
           'steady_then_higher_proxy_fraction':pattern_count/len(leaders) if leaders else None,
           'actual_scoring_delay_minutes':None,'score_time_status':'not_exposed_by_public_schema',
           'updated_at_delay_proxy_median_minutes':median(proxy_delays),
           'updated_at_delay_proxy_count':len(proxy_delays)})
    write_csv(root/'data/rhythm.csv',rhythms);write_csv(root/'data/rhythm_author_curves.csv',curves)
    by_type=defaultdict(list)
    for row in rhythms:by_type[row['topic_type'] or 'unknown'].append(row)
    write_csv(root/'data/rhythm_by_type.csv',[{'topic_type':kind,'topics':len(items),
       'within_round_submissions':sum(r['within_round_submissions'] for r in items),
       'median_first_submission_minutes':median([r['first_submission_minutes'] for r in items if r['first_submission_minutes'] is not None]),
       'median_best_score_first_minutes':median([r['best_score_first_minutes'] for r in items if r['best_score_first_minutes'] is not None]),
       'head_authors':sum(r['head_authors'] for r in items),
       'steady_then_higher_proxy_count':sum(r['steady_then_higher_proxy_count'] for r in items)} for kind,items in sorted(by_type.items())])
    return {'within_round_submissions':sum(r['within_round_submissions'] for r in rhythms),'topics':len(rhythms),'head_author_curves':len(curves)}


def main():
    root=DEFAULT_DATA;rows=list(read_table('data/attempts.csv',FIELDS))
    rules,codes=scorer_facts(rows,root);rhythm=rhythm_facts(rows,root)
    print(json.dumps({'rows':len(rows),'scorer':rules,'rhythm':rhythm},ensure_ascii=False))


if __name__=='__main__':main()
