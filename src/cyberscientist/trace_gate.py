"""v8 evidence checklist, with explicit limits on platform agreement."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).parent/'vendor/trace_gate_v8'
CALIBRATION = json.loads((ROOT/'calibration.json').read_text())
TAXONOMY = json.loads((ROOT/'taxonomy.json').read_text())


def reliability(code):
    grade = CALIBRATION['items'].get(code, {}).get('conditional_grade')
    return {'conditionally_reliable': 'reliable', 'indicative': 'indicative'}.get(grade, 'unavailable')


def cross_run_matches(outputs, run_id):
    """Compare code bytes only; common utilities can match without misconduct."""
    if not run_id:
        return {'status':'unknown', 'reason':'本包尚无Run归属'}
    from . import config, db
    wanted = {hashlib.sha256(raw).hexdigest():name for name,raw in outputs.items()
              if Path(name).suffix in ('.py','.cpp','.c','.rs','.jl','.lean','.sh')}
    matches=[];checked=0;unknown=0;seen=set()
    for row in db.query('SELECT run_id,package_path FROM submissions WHERE run_id<>? ORDER BY created_at DESC LIMIT 100', (run_id,)):
        if row['package_path'] in seen:continue
        seen.add(row['package_path'])
        try:
            path=(config.WORKSPACE_DIR/row['package_path']).resolve()
            if not path.is_relative_to(config.WORKSPACE_DIR.resolve()):raise ValueError()
            with zipfile.ZipFile(path) as archive:
                for item in archive.infolist():
                    if item.file_size>10_000_000 or Path(item.filename).suffix not in ('.py','.cpp','.c','.rs','.jl','.lean','.sh'):continue
                    digest=hashlib.sha256(archive.read(item)).hexdigest()
                    if digest in wanted:matches.append({'file':wanted[digest],'other_run_id':row['run_id'],'other_path':item.filename,'sha256':digest})
            checked+=1
        except (OSError,ValueError,zipfile.BadZipFile):unknown+=1
    return {'status':'observed', 'checked_packages':checked,'unreadable_packages':unknown,
            'scope':'most recent 100 submissions; code <=10MB; byte identity does not prove substantive reuse', 'matches':matches}


def report(rows, outputs, deterministic):
    calls = Counter(str(r.get('tool_call_id')) for r in rows if r.get('step_type')=='tool_call')
    results = Counter(str(r.get('tool_call_id')) for r in rows if r.get('step_type')=='tool_result')
    items = {i['code']: i for i in deterministic.get('check_items', [])}
    checks = []
    def add(code, state, evidence):
        checks.append({'code': code, 'status': state, 'evidence': evidence,
                       'reliability': reliability(code),
                       'affects_conclusion': reliability(code) in ('reliable', 'indicative')})
    for code in ('N11_OUTPUT_NOT_CAUSALLY_SUPPORTED', 'N06_FABRICATED_OR_UNSUPPORTED_EXECUTION',
                 'N09_NO_EXECUTION_EVIDENCE', 'N13_EXTREME_BREVITY'):
        state = items.get(code, {}).get('status')
        add(code, {'triggered':'risk', 'clear':'pass'}.get(state, 'unknown') if rows and (outputs or not code.startswith('N11')) else 'unknown',
            {'public_check_status':state or 'unobservable', 'output_files': len(outputs)})
    missing_results = list((calls-results).elements());missing_calls = list((results-calls).elements())
    add('N08_UNPAIRED_TOOL_CALLS', 'risk' if missing_results or missing_calls else 'pass' if rows else 'unknown',
        {'missing_results':missing_results[:50], 'missing_calls':missing_calls[:50],
         'missing_result_count':len(missing_results), 'missing_call_count':len(missing_calls)})
    duplicates = sum(v-1 for v in Counter(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows).values() if v>1)
    add('N12_TRACE_REPETITION_OR_INFLATION', 'risk' if duplicates else 'pass' if rows else 'unknown', {'exact_duplicate_rows':duplicates})
    stamps = [];invalid = 0
    for row in rows:
        if row.get('timestamp') is not None:
            try:
                stamp = datetime.fromisoformat(str(row['timestamp']).replace('Z','+00:00'))
                if stamp.tzinfo is None: raise ValueError()
                stamps.append(stamp.timestamp())
            except (ValueError, TypeError): invalid += 1
    inversions = sum(a>b for a,b in zip(stamps,stamps[1:]))
    add('N15_PROVENANCE_METADATA_ANOMALY', 'risk' if invalid or inversions else 'pass' if len(stamps)==len(rows) and stamps else 'unknown',
        {'timestamps':len(stamps),'rows':len(rows),'invalid':invalid,'nonmonotonic':inversions,
         'span_seconds':max(stamps)-min(stamps) if stamps else None,
         'duration_plausibility':'unknown_without_independent_receipts'})
    code_files = [name for name in outputs if Path(name).suffix.lower() in ('.py','.cpp','.c','.rs','.jl','.sh','.lean','.ipynb')]
    text = '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows)
    writes = {name: bool(re.search(r'(?:write_text|write_bytes|cat\s*>|apply_patch|file_change|fileChange|tee\s)',text) and name in text) for name in code_files}
    add('N17_PREEXISTING_SUBSTANTIVE_ARTIFACT', 'unknown',
        {'code_files':writes, 'notice':'路径与写入信号共现不证明代码由本轨迹创建；跨Run哈希需独立对账，不同科学题不能复用。'})
    explicit = [r for r in rows if r.get('science_status')=='completed' and r.get('exit_code')==0]
    add('N18_PROCESS_EVIDENCE_INSUFFICIENT', 'unknown',
        {'explicit_successful_science_receipts':len(explicit), 'successful_calculation_count':len(explicit) if explicit else None,
         'notice':'工具成功不等于科学计算；没有明确计算来源时不能零填或推断独立实验次数。'})
    visibility = deterministic.get('visibility', {'status':'unknown'})
    relevant = set()
    for c in checks:
        if c['status']=='pass':continue
        prefix=c['code'][:3]
        relevant.update({'N11':['C04','C10'],'N06':['C01','C06'],'N09':['C01','C14'],
                         'N08':['C09'],'N13':['C03'],'N12':['C09'],'N15':['C08','C16'],
                         'N17':['C02','C07','C11'],'N18':['C03','C06','C13']}.get(prefix,[]))
    missing = [c | {'question':'本包是否提供可核对的'+c['name']+'？缺失时保留unknown，并补做实际工作。'}
               for c in TAXONOMY['categories'] if c['id'] in relevant]
    from . import features
    return {'version':'v8-advisory-1','checks':checks,'visibility':visibility,
            'parser_pair_discrepancy': deterministic.get('parser_pair_discrepancy'),
            'calibration':{'source_sha256':CALIBRATION['sha256'],'observations':CALIBRATION['observations'],'scope':CALIBRATION['scope']},
            'missing_evidence':missing,'possible_cap':deterministic.get('advisory_cap'),
            'conclusion':'risk' if any(c['status']=='risk' and c['affects_conclusion'] for c in checks) else 'unknown',
            'score_prediction':None,
            'judge_replica_hint':{'enabled':features.enabled('judge_replica_hint'),
                'label':'仅供参考（留出集准确率 54–62%）','prediction':None,
                'status':'standalone_only' if features.enabled('judge_replica_hint') else 'disabled'}}
