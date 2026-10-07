"""Acquisition provenance and observed model usage; no prompts or credentials."""
import json
from collections import Counter,defaultdict
from pathlib import Path

from .common import DEFAULT_DATA,utcnow,write_json
from .dataset import read_table,truth
from .tables import write_csv


def usage_rows(root):
    rows=[]
    for path in sorted((root/'.local/model_cache').glob('*.json')):
        record=json.loads(path.read_text());usage=record.get('usage') or {}
        rows.append({'request_sha256':record.get('request_sha256'),
          'provider':record.get('provider'),'requested_model':record.get('requested_model'),
          'provider_model':record.get('provider_model'),'observed_at':record.get('observed_at'),
          'request_attempts':record.get('request_attempts'),'elapsed_s':record.get('elapsed_s'),
          'input_tokens':usage.get('prompt_tokens',usage.get('input_tokens')),
          'output_tokens':usage.get('completion_tokens',usage.get('output_tokens')),
          'cached_input_tokens':usage.get('prompt_cache_hit_tokens',usage.get('cached_input_tokens')),
          'finish_reason':record.get('finish_reason')})
    return rows


def analysis_coverage(root):
    selected={r['attempt_id']:r for r in read_table('data/selected.csv',root=root)}
    semantic={aid for aid,r in selected.items() if truth(r.get('semantic_required'))}
    if (root/'data/selection_additions.csv').exists():
        for row in read_table('data/selection_additions.csv',root=root):
            selected.setdefault(row['attempt_id'],row);semantic.add(row['attempt_id'])
    features={r['attempt_id']:r for r in read_table('data/trace_features.csv',root=root)}
    claims=Counter(r['attempt_id'] for r in read_table('data/missing_evidence.csv',root=root))
    output=[]
    for aid,item in sorted(selected.items(),key=lambda pair:int(pair[0])):
        trace=root/'data/traces'/(aid+'.jsonl.zst')
        local=root/'.raw/traces'/(aid+'.jsonl.zst')
        semantics=root/'data/semantics'/(aid+'.json');v6=root/'.raw/v6_reports'/(aid+'.json')
        truncation=root/'data/truncation_claims'/(aid+'.json')
        sem=json.loads(semantics.read_text()) if semantics.exists() else {}
        report=json.loads(v6.read_text()) if v6.exists() else {}
        checks=json.loads(truncation.read_text()).get('checks',[]) if truncation.exists() else []
        archive_provenance=root/'scorer/sealed_input_provenance'/(aid+'.json');archive_steps=None
        if archive_provenance.exists():
            source=json.loads(archive_provenance.read_text());converted=Path(source['converted_path'])
            if converted.exists():archive_steps=sum(bool(line.strip()) for line in converted.read_bytes().splitlines())
        output.append({'attempt_id':aid,'challenge_id':item['challenge_id'],'ours':item['ours'],
          'trace_retrieved':trace.exists() or local.exists(),'trace_storage':'private' if trace.exists() else 'local_only' if local.exists() else 'unknown_not_retrieved',
          'public_trace_status':features.get(aid,{}).get('public_trace_status','unknown_no_features_yet'),
          'feature_present':aid in features,'semantic_required':aid in semantic,
          'semantic_status':sem.get('status','unknown_no_extraction') if aid in semantic else 'not_required',
          'semantic_input_surface':'public_api_trace','downloaded_archive_selected_trace_steps':archive_steps,
          'v6_status':report.get('status','unknown_not_prepared'),
          'missing_evidence_statements':claims[aid],'truncation_checks':len(checks),
          'truncation_assessed_checks':sum(c.get('status') in ['present','partially_present','not_observed_in_complete_fetched_trace','not_assessable_from_public_trace'] for c in checks),
          'truncation_status_counts_json':json.dumps(dict(Counter(c.get('status','unknown') for c in checks)),sort_keys=True)})
    write_csv(root/'data/analysis_coverage.csv',output)
    summary={'generated_at':utcnow(),'selected_attempts':len(output),'selected_ours':sum(truth(r['ours']) for r in output),
      'trace_retrieved':sum(r['trace_retrieved'] for r in output),'features':sum(r['feature_present'] for r in output),
      'semantic_required':len(semantic),'semantic_statuses':dict(Counter(r['semantic_status'] for r in output if r['semantic_required'])),
      'public_semantic_empty_with_nonempty_archive':sum(r['semantic_status']=='unknown_public_trace_empty' and (r['downloaded_archive_selected_trace_steps'] or 0)>0 for r in output),
      'public_trace_statuses':dict(Counter(r['public_trace_status'] for r in output)),
      'v6_statuses':dict(Counter(r['v6_status'] for r in output)),
      'interpretation':'Acquisition and annotation coverage only; empty public traces or unavailable fields do not prove absence of original research.'}
    write_json(root/'data/analysis_coverage_summary.json',summary)
    return summary


def main():
    root=DEFAULT_DATA;sources=[];redactions=Counter()
    for path in sorted((root/'.raw/http').glob('*.meta.json')):
        row=json.loads(path.read_text());redactions.update(row.get('redactions') or {})
        sources.append({'cache_id':path.name.removesuffix('.meta.json'),
          **{k:row.get(k) for k in ['url','http_status','fetched_at','original_sha256',
            'sanitized_sha256','original_bytes','redaction_revision','rescrubbed_at']},
          'redaction_counts_json':json.dumps(row.get('redactions') or {},sort_keys=True)})
    write_csv(root/'data/snapshot_sources.csv',sources)
    rows=usage_rows(root);write_csv(root/'data/model_usage.csv',rows)
    grouped=defaultdict(lambda:Counter())
    for row in rows:
        group=grouped[(row['provider'],row['requested_model'])];group['successful_cached_requests']+=1
        for key in ['request_attempts','input_tokens','output_tokens','cached_input_tokens']:
            if isinstance(row[key],(int,float)):group[key]+=row[key]
            else:group['missing_'+key]+=1
    failures=[json.loads(path.read_text()) for path in (root/'.local/model_failures').glob('*.json')]
    successful={row['request_sha256'] for row in rows}
    failure_counts=Counter(record.get('provider','unknown') for record in failures)
    summary={'generated_at':utcnow(),'public_response_snapshots':len(sources),
      'public_snapshot_redaction_operation_counts':dict(redactions),
      'usage_groups':[{'provider':p,'requested_model':m,**dict(counts)} for (p,m),counts in sorted(grouped.items())],
      'failed_request_records':len(failures),'failed_records_by_provider':dict(failure_counts),
      'failed_then_successful_request_hashes':sum(record.get('request_sha256') in successful for record in failures),
      'usage_scope':'Unique successful request hashes in the analysis model cache; includes superseded calibration/extraction requests. Repeated cache reads do not create new requests.',
      'unknown_usage':'Cancelled, truncated, failed/retried responses and uncached exploratory probes may have consumed billed tokens not exposed here; totals are observed successful response usage, not a billing total.',
      'redaction_scope':'Operation counts in per-response metadata, not distinct secrets or a proof of historical absence. Earlier private Git history incident remains recorded separately.'}
    probe=root/'.local/model-probe.json'
    if probe.exists():
        record=json.loads(probe.read_text());summary['uncached_deepseek_probe_usage']=(record.get('response') or {}).get('usage')
    write_json(root/'data/model_usage_summary.json',summary)
    summary['analysis_coverage']=analysis_coverage(root)
    print(json.dumps(summary))


if __name__=='__main__':main()
