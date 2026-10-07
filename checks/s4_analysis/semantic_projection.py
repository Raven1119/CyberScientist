"""Versioned deterministic attribution without replacing frozen model outputs."""
import copy
import json
from collections import Counter

from .common import DEFAULT_DATA,atomic,sha,utcnow,write_json
from .semantics import KEYS,packet_steps,trace_steps,validate


def project(record,events):
    extraction=copy.deepcopy(record['extraction'])
    checked=validate(extraction,events)
    rows=[]
    for field in KEYS:
        for index,claim in enumerate(extraction[field]):
            if not isinstance(claim,dict):
                rows.append({'field':field,'claim_index':index,'evidence_validation':'failed','error':'not_object'})
                continue
            rows.append({'field':field,'claim_index':index,
              'claim_sha256':sha(json.dumps(record['extraction'][field][index],ensure_ascii=False,sort_keys=True).encode()),
              **{k:claim.get(k) for k in ['steps','evidence_source_types','scientific_truth_status',
                 'execution_observability','evidence_validation']}})
    return rows,checked


def main():
    root=DEFAULT_DATA;rows=[];errors=[];sources=Counter();statuses=Counter();records=0
    for path in sorted((root/'data/semantics').glob('*.json')):
        raw=path.read_bytes();record=json.loads(raw);aid=record['attempt_id']
        trace=root/'data/traces'/(aid+'.jsonl.zst')
        if not trace.exists():trace=root/'.raw/traces'/(aid+'.jsonl.zst')
        try:
            steps,digest=trace_steps(trace)
            if digest!=record.get('trace_sha256'):raise ValueError('trace_sha_mismatch')
            claims,checked=project(record,packet_steps(steps));records+=1
            for claim in claims:
                row={'attempt_id':aid,'challenge_id':record.get('challenge_id'),'ours':record.get('ours'),
                  'projection_schema':'s4_semantic_evidence_basis_v1','semantic_record_sha256':sha(raw),
                  'trace_sha256':digest,**claim}
                rows.append(row);sources.update(claim.get('evidence_source_types') or [])
                statuses[claim['evidence_validation']]+=1
        except (OSError,ValueError,KeyError) as exc:
            errors.append({'attempt_id':aid,'error_kind':type(exc).__name__,'error':str(exc)})
    atomic(root/'data/semantic_evidence_basis.jsonl',b''.join(
      (json.dumps(row,ensure_ascii=False)+'\n').encode() for row in rows))
    summary={'schema':'s4_semantic_evidence_basis_v1','generated_at':utcnow(),
      'records':records,'claims':len(rows),'source_types':dict(sources),'validation':dict(statuses),
      'errors':errors,'model_calls':0,'original_records_modified':False,
      'limitations':'Source classification and exact quote validation only; not semantic entailment or scientific correctness. Frozen manual audit accuracy does not transfer to later extraction revisions.'}
    write_json(root/'data/semantic_evidence_basis_summary.json',summary)
    print(json.dumps(summary))


if __name__=='__main__':main()
