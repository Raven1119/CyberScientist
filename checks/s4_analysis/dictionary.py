"""Generate per-column provenance for every published tabular dataset."""
import csv
import json

from .common import DEFAULT_DATA,atomic,sha,unzstd,utcnow,write_json
from .dataset import duckdb_module

DESCRIPTIONS={
 'attempt_id':'Public platform attempt ID; join to attempts and step tables.',
 'challenge_id':'Public challenge slug; join to challenges and full topic snapshots.',
 'ours':'Boolean label from local configured-mailbox/operator-confirmed ownership; no mailbox identity published.',
 'display_score':'scoringState.displayScore, else attempt.score. Negative sentinels retained verbatim.',
 'science_score':'resultsJson.harbor_score, else scorecard.harbor_score; source named separately.',
 'trace_score':'resultsJson.trace_score, else scorecard.trace_score; zero differs from unknown.',
 'trace_engine':'resultsJson.trace_score_engine; absence remains unknown.',
 'trace_decision':'Unmodified resultsJson.trace_decision; unknown does not imply accept.',
 'created_at':'Public createdAt, ISO-8601 with timezone.',
 'updated_at':'Public updatedAt; NOT a verified scoring-completion timestamp.',
 'minutes_since_round_start':'(createdAt - public topic roundStartAt)/60; can be negative or after round end.',
 'is_within_round':'roundStartAt <= createdAt < roundEndAt, with timezone-aware endpoints.',
 'actual_scoring_delay_minutes':'Unknown: the public schema exposes no scoredAt timestamp.',
 'updated_at_delay_proxy_median_minutes':'Median updatedAt-createdAt for final rows; may include edits and rescoring, not actual score latency.',
 'steady_then_higher_proxy':'First within-round display score is >0 and <=70, later best improves >=20; >=2 submissions. Missing/negative sentinel first or best score is unknown, excluded from the assessable denominator. Numeric proxy only.',
 'semantic_required':'Head ranks 1-5, all selected high-science controls, jumps and ours; empty public traces yield unknown.',
 'selection_reasons':'Semicolon-separated deterministic inclusion reasons; multiple reasons preserved.',
 'sanitized_sha256':'SHA-256 after secret redaction; not interchangeable with original_sha256.',
 'original_sha256':'SHA-256 of public response/archive before redaction, computed in memory only.',
 'snapshot_path':'Sharded compressed JSONL containing the full sanitized public attempt record.',
 'score_is_final':'Public scoringState.scoreIsFinal; HTTP success alone is not final scoring.',
}


def describe(column):
    if column in DESCRIPTIONS:return DESCRIPTIONS[column]
    if column.startswith('raw.'):
        return 'Original public attempt detail field $.'+column[4:]+'; nullable, flattened without value inference; arrays are JSON strings.'
    if column.endswith('_json'):return 'JSON-encoded structured values; preserve nested source fields and nulls.'
    if column.endswith('_at'):return 'Recorded ISO-8601 timestamp; the column name distinguishes source and observation time.'
    if column.endswith('_path'):return 'Repository-relative evidence path; .raw/ paths are local-only and ignored by Git.'
    if column.endswith('_bytes'):return 'Byte count at the named stage; original and sanitized counts may differ.'
    if column.endswith('_minutes'):return 'Elapsed minutes under the dataset definition; unknown is empty/NULL.'
    if column.startswith('raw.'):return 'Unmodified public source field.'
    return 'Named factual field from the generating script; no imputation. See source and dataset definition above.'


def main():
    root=DEFAULT_DATA;lines=['# Data dictionary','',
      'Generated '+utcnow()+'. CSV empty cells and Parquet NULL mean unknown/missing; 0 is an observed zero.',
      'Parquet physical columns are nullable strings to preserve heterogeneous public API values. Cast numeric and Boolean columns explicitly.',
      'Public author names and attempt IDs remain identifiable. Only local mailbox identities are replaced by `ours`.',
      'Full topic JSON stores original scoring descriptions and resource declarations. Attempt JSONL shards preserve fields omitted from wide tables.',
      'Round windows come from actual API fields; round 5 lasts 24.5 hours. Season status and round phase can disagree and are preserved.',
      'Scoring completion time is not exposed: updatedAt is only a labelled edit/rescore proxy.',
      'The scorer grid/cap statistics are observations, not proof of hidden model weights or trigger conditions.',
      'Jump = a >=20 point trace or display increase between consecutive submissions by the same author on the same topic.',
      'Within-round timing uses start inclusive/end exclusive. The steady-then-higher pattern is a numeric proxy, not a claim about scientific intent.',
      '','Scripts: CyberScientist `checks/s4_analysis/`. Collection and analysis phases are recorded in coverage and PROGRESS.','']
    schema=[]
    for folder in ['data','scorer']:
        for path in sorted((root/folder).rglob('*')):
            if path.suffix not in ('.csv','.parquet'):continue
            relative=str(path.relative_to(root))
            if path.suffix=='.csv':
                with path.open(newline='') as handle:columns=next(csv.reader(handle),[])
            else:
                with duckdb_module().connect() as connection:
                    result=connection.execute('SELECT * FROM read_parquet(?) LIMIT 0',[str(path)])
                    columns=[row[0] for row in result.description]
            lines.extend(['## '+relative,'','| Column | Meaning / provenance |','|---|---|'])
            for column in columns:
                description=describe(column);lines.append('| `'+column.replace('|','\\|')+'` | '+description.replace('|','\\|')+' |')
                schema.append({'dataset':relative,'column':column,'description':description})
            lines.append('')
    # JSONL has named top-level columns too. Nested objects/arrays remain typed
    # source containers rather than an invented flattened schema.
    groups={}
    for folder,pattern in [('data/traces','*.jsonl.zst'),('data/attempt_details','*.jsonl.zst'),
                           ('data/topics','*.json'),('data/semantics','*.json'),('scorer/forms','*.json')]:
        paths=sorted((root/folder).glob(pattern))
        if paths:groups[folder+'/<id>.'+('jsonl.zst' if 'jsonl' in pattern else 'json')]=paths
    for folder in ['data','scorer']:
        for path in sorted((root/folder).glob('*.jsonl*')):
            groups[str(path.relative_to(root))]=[path]
    for dataset,paths in groups.items():
        columns=set()
        for path in paths:
            raw=path.read_bytes();raw=unzstd(raw) if path.suffix=='.zst' else raw
            values=[json.loads(line) for line in raw.splitlines() if line.strip()] if '.jsonl' in path.name else [json.loads(raw)]
            for value in values:
                if isinstance(value,dict):columns.update(value)
        lines.extend(['## '+dataset,'',
          'JSON object top-level columns. Nested objects/arrays retain their source keys and are queried as structured JSON; per-step source identity and SHA are retained in the corresponding index. Empty trace files contain no observed columns.','',
          '| Column | Meaning / provenance |','|---|---|'])
        for column in sorted(columns):
            description=describe(column)
            lines.append('| `'+column.replace('|','\\|')+'` | '+description.replace('|','\\|')+' |')
            schema.append({'dataset':dataset,'column':column,'description':description})
        lines.append('')
    taxonomy=root/'data/missing_evidence_taxonomy.json'
    if taxonomy.exists():lines.extend(['## Frozen missing-evidence taxonomy','', '```json',taxonomy.read_text().strip(),'```',''])
    atomic(root/'DATA_DICTIONARY.md',('\n'.join(lines).rstrip()+'\n').encode())
    write_json(root/'data/table_schema.json',schema)
    print(json.dumps({'datasets':len({r['dataset'] for r in schema}),'columns':len(schema)}))


if __name__=='__main__':main()
