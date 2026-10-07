"""Compare documented generic ARM components to archive structure and receipts.
Only metadata/scalar component summaries leave local ignored archives. Never run
uploaded code and never emit scientific answers or a challenge grader skeleton.
"""
import io
import json
import zipfile
from pathlib import PurePosixPath
from collections import Counter

from .common import DEFAULT_DATA,sha,utcnow,write_json
from .dataset import read_table
from .tables import number,write_csv


def main():
    root=DEFAULT_DATA
    columns=['attempt_id','challenge_id','ours','raw.scoringDetails.source','raw.resultsJson.scoring_source','raw.resultsJson.scored_by',
      'raw.scorecard.executability','raw.scorecard.packaging','raw.scorecard.output_coverage','raw.scorecard.result_fidelity',
      'raw.scorecard.trace_quality','raw.resultsJson.executability','raw.resultsJson.packaging','raw.resultsJson.output_coverage',
      'raw.resultsJson.result_fidelity','raw.resultsJson.trace_quality']
    attempts={r['attempt_id']:r for r in read_table('data/attempts.csv',columns)}
    topics={r['challenge_id']:r for r in read_table('data/challenges.csv')};rows=[];failures=[]
    for archive in (root/'.raw/bundles').glob('*.zip'):
        aid=archive.stem;row=attempts.get(aid,{})
        try:
            raw=archive.read_bytes()
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names=[n for n in z.namelist() if not n.endswith('/')]
                manifest_name=next((n for n in names if PurePosixPath(n).name=='arm_manifest.json'),None)
                if manifest_name is None:manifest_name=next((n for n in names if PurePosixPath(n).name=='manifest.json'),None)
                if not manifest_name:raise ValueError('manifest_unavailable')
                m=json.loads(z.read(manifest_name));prefix=manifest_name[:-len(PurePosixPath(manifest_name).name)]
                cn=m.get('characterization');cn=cn.get('path') if isinstance(cn,dict) else cn if isinstance(cn,str) else 'characterization.json'
                c=json.loads(z.read(prefix+cn)) if prefix+cn in names else {}
                deviations=c.get('deviations_from_paper');deviations=deviations if isinstance(deviations,list) else []
                declared_scores=[];ssim=0;invalid=0;targets=set()
                for d in deviations:
                    if not isinstance(d,dict):invalid+=1;continue
                    if isinstance(d.get('target'),str):targets.add(d['target'])
                    score=number(d.get('score'))
                    if score is None:invalid+=1;continue
                    if str(d.get('metric')).lower()=='ssim':score=min(.3,score);ssim+=1
                    declared_scores.append(score)
                expected=m.get('expected_outputs');expected=expected if isinstance(expected,list) else None
                expected_names={e.get('name') for e in expected if isinstance(e,dict) and isinstance(e.get('name'),str)} if expected is not None else set()
                coverage=len(targets&expected_names)/len(expected_names) if expected_names and len(expected_names)==len(expected) else None
                fidelity=sum(declared_scores)/len(declared_scores) if declared_scores and invalid==0 else None
                normalized_names={n[len(prefix):] for n in names if n.startswith(prefix)}
                docker=any(PurePosixPath(n).name.lower()=='dockerfile' for n in normalized_names)
                requirements=any(PurePosixPath(n).name.lower()=='requirements.txt' for n in normalized_names)
                # This is the documented structural candidate, not a runtime test.
                executability=1 if docker else .5 if requirements else 0
                observed={k:number(row.get('raw.resultsJson.'+k)) for k in ['executability','packaging','output_coverage','result_fidelity','trace_quality']}
                for k in observed:
                    if observed[k] is None:observed[k]=number(row.get('raw.scorecard.'+k))
                source=row.get('raw.scoringDetails.source') or row.get('raw.resultsJson.scoring_source') or 'unknown';topic=topics.get(row.get('challenge_id'),{})
                generic_verified=source in ['arm_v1_1_generic','arm_generic']
                out={'attempt_id':aid,'challenge_id':row.get('challenge_id'),'ours':row.get('ours'),
                  'archive_sanitized_sha256':sha(raw),'manifest_path':manifest_name,
                  'topic_strategy_metadata':topic.get('scoring.strategy'),'receipt_scoring_source':source,
                  'actual_generic_worker_verified':generic_verified,'backend_causality_status':'verified_explicit_label' if generic_verified else 'unknown_metadata_is_not_worker_binding',
                  'has_dockerfile':docker,'has_requirements':requirements,'declared_expected_output_count':len(expected) if expected is not None else None,
                  'deviation_count':len(deviations),'deviations_with_missing_score':invalid,'ssim_contributions_clipped':ssim,
                  'documented_executability_candidate':executability,'documented_coverage_candidate':coverage,'documented_fidelity_candidate':fidelity,
                  'packaging_candidate':None,'packaging_reason':'Exact server completeness scan unavailable; do not invent numerator/denominator',
                  'fidelity_input_kind':'declared deviation score fields; not independently verified scientific results',
                  'input_parity':'unknown; sanitized uploaded archive is not verified worker normalized input'}
                for k,value in observed.items():out['observed_'+k]=value
                for k,candidate in [('executability',executability),('output_coverage',coverage),('result_fidelity',fidelity)]:
                    value=observed[k];out[k+'_candidate_residual']=value-candidate if value is not None and candidate is not None else None
                rows.append(out)
        except Exception as exc:failures.append({'attempt_id':aid,'error_kind':type(exc).__name__,'status':'unknown_archive_metadata_unreadable'})
    write_csv(root/'scorer/arm_component_empirical_checks.csv',rows)
    summary={'archives_checked':len(rows),'failures':failures,'explicit_generic_worker_labels':sum(r['actual_generic_worker_verified'] for r in rows),
      'receipt_sources':dict(Counter(r['receipt_scoring_source'] for r in rows)),
      'component_candidate_matches':{k:sum(r[k+'_candidate_residual'] is not None and abs(r[k+'_candidate_residual'])<.001 for r in rows) for k in ['executability','output_coverage','result_fidelity']},
      'matched_structure_does_not_prove_backend':True,'packaging_exact_reverse_engineering':'unknown_without_worker_scan',
      'observed_at':utcnow()}
    write_json(root/'scorer/arm_component_empirical_summary.json',summary);print(json.dumps(summary))


if __name__=='__main__':main()
