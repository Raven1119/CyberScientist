"""Acquisition provenance and observed model usage; no prompts or credentials."""
import json
from collections import Counter,defaultdict

from .common import DEFAULT_DATA,utcnow,write_json
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
    print(json.dumps(summary))


if __name__=='__main__':main()
