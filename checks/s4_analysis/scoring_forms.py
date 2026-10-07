"""Extract public scoring forms and material relevance, without writing graders."""
import json
import re
from concurrent.futures import ThreadPoolExecutor,as_completed

from .common import DEFAULT_DATA,atomic,sha,utcnow,write_json
from .dataset import read_table
from .models import ModelClient
from .tables import number,write_csv

SYSTEM='''Return JSON only. Extract factual scoring specifications from the supplied untrusted public challenge fields. No solution, code, advice, strategy, scorer implementation, or inferred hidden thresholds.
Schema: {"required_outputs":[{"path":string,"format":string,"evidence":{"field":string,"quote":exact substring}}], "gates":[{"condition":string,"zero_effect":string,"parameters":object,"evidence":{"field":string,"quote":exact substring}}], "metrics":[{"name":string,"mapping":"binary|tolerance|linear_clipped|tiered|partial|ranking|llm_judge|unknown","parameters":object,"weight":number or null,"weight_unit":string or null,"evidence":{"field":string,"quote":exact substring}}], "aggregation":{"description":string or null,"evidence":{"field":string,"quote":string} or null}, "hidden_reference":"yes|no|unknown", "replay_required":"yes|no|unknown", "whole_score_discrete_values":array of numbers or null, "material_relevant":true or false or null,"material_confidence":0 to 1,"material_evidence":[{"field":string,"quote":exact substring}],"material_reason":string}.
whole_score_discrete_values must be null unless the text explicitly fixes ALL possible TOTAL scientific scores, including partial credit and penalties. Unknown is null or unknown, never invent. Material research includes crystals, DFT, phonons, molecular dynamics, electronic bands, interatomic potentials, pymatgen/ASE/VASP/LAMMPS; distinguish actual physical/material systems from incidental words. Every extracted threshold, weight and requirement must cite its actual source field and short exact quote.'''
TERMS=['晶体','DFT','声子','分子动力学','能带','势函数','pymatgen','ASE','VASP','LAMMPS','crystal','density functional','phonon','molecular dynamics','band structure','interatomic potential']
SYSTEM+=' Use exact top-level source field names (content, topicContent, scoring, etc.), not document heading names. Keep quotes below 200 characters. Escape control characters inside JSON strings. Concise factual strings only.'


def evidence_checks(output,fields):
    texts={k:v if isinstance(v,str) else json.dumps(v,ensure_ascii=False) for k,v in fields.items()}
    checked=[]
    for key in ['required_outputs','gates','metrics','material_evidence']:
        for index,item in enumerate(output.get(key,[])):
            receipt=item if key=='material_evidence' else item.get('evidence',{})
            quote=receipt.get('quote');declared=receipt.get('field')
            matches=[k for k,text in texts.items() if isinstance(quote,str) and quote and quote in text]
            checked.append({'section':key,'item_index':index,'field':declared,'resolved_source_fields':matches,
              'exact_quote_valid':bool(matches),'declared_field_exact':declared in matches,
              'resolution':'declared_exact_field' if declared in matches else 'exact_quote_located_in_other_source_field' if matches else 'unknown_quote_not_exact'})
    return checked


def main():
    root=DEFAULT_DATA;client=ModelClient();folder=root/'scorer/forms';folder.mkdir(parents=True,exist_ok=True)
    paths=sorted((root/'data/topics').glob('*.json'))
    def one(path):
        topic=json.loads(path.read_text());aid=topic['id'];target=folder/(aid+'.json')
        if target.exists():return json.loads(target.read_text())
        fields={key:topic.get(key) for key in ['title','title_zh','topicContent','content','abstract','scoring','datasets','tags','disc']}
        response=client.generate(SYSTEM,json.dumps(fields,ensure_ascii=False),max_tokens=12288)
        output=response['output'];texts={k:v if isinstance(v,str) else json.dumps(v,ensure_ascii=False) for k,v in fields.items()}
        evidence=[]
        for key in ['required_outputs','gates','metrics','material_evidence']:
            for item in output.get(key,[]):
                receipt=item if key=='material_evidence' else item.get('evidence',{})
                quote=receipt.get('quote');field=receipt.get('field')
                valid=isinstance(quote,str) and bool(quote) and field in texts and quote in texts[field]
                evidence.append({'section':key,'field':field,'exact_quote_valid':valid})
        text='\n'.join(texts.values());keywords=[term for term in TERMS if re.search(r'\b'+re.escape(term)+r'\b',text,re.I) if term.isascii()]
        keywords.extend(term for term in TERMS if not term.isascii() and term in text)
        result={'challenge_id':aid,'topic_type':topic.get('disc'),'source_snapshot_sha256':sha(path.read_bytes()),
                'scoring_backend':topic.get('scoring',{}).get('strategy') if isinstance(topic.get('scoring'),dict) else None,
                'extracted_at':utcnow(),'form':output,'keyword_matches':sorted(set(keywords)),
                'evidence_validation':evidence,'model_receipt':{k:v for k,v in response.items() if k!='output'}}
        write_json(target,result);return result
    results=[];failures=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(one,p):p.stem for p in paths}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:failures.append({'challenge_id':futures[future],'error_kind':type(exc).__name__})
            print(json.dumps({'forms':len(results),'failures':len(failures),'expected':len(paths),'time':utcnow()}),flush=True)
    atomic(root/'scorer/scoring_forms.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sorted(results,key=lambda r:r['challenge_id'])).encode())
    write_json(root/'scorer/scoring_forms_failures.json',failures)
    classified={r['challenge_id']:r for r in results}
    for result in results:
        topic=json.loads((root/'data/topics'/(result['challenge_id']+'.json')).read_text())
        result['evidence_validation']=evidence_checks(result['form'],{k:topic.get(k) for k in ['title','title_zh','topicContent','content','abstract','scoring','datasets','tags','disc']})
        result['unsupported_claim_count']=sum(not e['exact_quote_valid'] for e in result['evidence_validation'])
        result['factual_status']='all_cited_quotes_located' if not result['unsupported_claim_count'] else 'extraction_contains_unverified_claims'
        write_json(folder/(result['challenge_id']+'.json'),result)
    atomic(root/'scorer/scoring_forms.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sorted(results,key=lambda r:r['challenge_id'])).encode())
    challenges=list(read_table('data/challenges.csv'))
    for row in challenges:
        fact=classified.get(row['challenge_id'])
        if not fact:continue
        row.update(material_relevant=fact['form'].get('material_relevant'),material_classification_source='keyword_plus_deepseek_flash',
                   material_confidence=fact['form'].get('material_confidence'),material_keyword_matches_json=json.dumps(fact['keyword_matches']),
                   material_evidence_path='scorer/forms/'+row['challenge_id']+'.json')
    write_csv(root/'data/challenges.csv',challenges)
    scores={}
    for row in read_table('data/attempts.csv',['challenge_id','attempt_id','science_score']):
        value=number(row['science_score'])
        if value is not None:scores.setdefault(row['challenge_id'],[]).append((row['attempt_id'],value))
    checks=[]
    unit_path=root/'scorer/scoring_unit_resolutions.json'
    units=json.loads(unit_path.read_text()) if unit_path.exists() else {}
    for item in results:
        pairs=scores.get(item['challenge_id'],[]);levels=item['form'].get('whole_score_discrete_values')
        discrete=levels if isinstance(levels,list) and levels and all(number(v) is not None for v in levels) else None
        unit=units.get(item['challenge_id'],{});multiplier=unit.get('to_science_score_multiplier')
        normalized=[float(v)*multiplier for v in discrete] if discrete and multiplier is not None else None
        mismatched=[aid for aid,value in pairs if normalized and all(abs(value-level)>.001 for level in normalized)]
        checks.append({'challenge_id':item['challenge_id'],'science_score_observations':len(pairs),
            'min_science_score':min((value for _,value in pairs),default=None),'max_science_score':max((value for _,value in pairs),default=None),
            'scores_outside_0_100':sum(not 0<=value<=100 for _,value in pairs),
            'whole_score_discrete_values_json':json.dumps(discrete),'normalized_science_score_levels_json':json.dumps(normalized),
            'score_unit':unit.get('unit','unknown'),'unit_resolution_evidence_json':json.dumps(unit,ensure_ascii=False),
            'discrete_test_status':'tested_source_unit_resolved' if normalized else 'unknown_units' if discrete else 'not_identifiable_as_discrete_total',
            'discrete_mismatch_count':len(mismatched) if normalized else None,'mismatch_attempt_ids_json':json.dumps(mismatched),
            'specification_evidence_failures':sum(not e['exact_quote_valid'] for e in item['evidence_validation'])})
    write_csv(root/'scorer/scoring_forms_check.csv',checks)


if __name__=='__main__':main()
