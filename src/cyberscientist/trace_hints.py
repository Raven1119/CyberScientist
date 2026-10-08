"""Code-level advice on the official CLI trace. Never a submission gate."""
import hashlib
import io
import json
import zipfile
from . import db, trace_diagnostics

PREFIXES=('N08','N09','N11','N12','N14')


def inspect(content):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            manifest=json.loads(archive.read('arm_manifest.json'))
            trace=archive.read(manifest['trace'])
            rows=[json.loads(line) for line in trace.splitlines() if line.strip()]
            outputs={n:archive.read(n) for n in archive.namelist() if n.startswith('outputs/') and not n.endswith('/')}
        result=trace_diagnostics._evaluate(rows,'',outputs,convert=False)
        hints=[{'code':item['code'],'status':item['status'],'reason':item.get('reason','参考提示')}
               for item in result.get('details',[]) if item.get('code','').startswith(PREFIXES)]
        return {'status':'ready','advisory_only':True,'input':'official_cli_generated_trace',
                'trace_sha256':hashlib.sha256(trace).hexdigest(),'hints':hints,
                'notice':'提示不估分、不拦截；以平台扣分码为校准依据'}
    except Exception as exc:
        return {'status':'unknown','advisory_only':True,'hints':[],
                'reason':type(exc).__name__,'notice':'参考检查失败不阻止提交'}


def compare(local, receipt):
    ours=sorted({item['code'] for item in local.get('hints',[])})
    actual=sorted({item['code'] for item in receipt.get('deductions',[]) if isinstance(item,dict) and isinstance(item.get('code'),str)})
    return {'local_codes':ours,'worker_codes':actual,'matched':sorted(set(ours)&set(actual)),
            'local_only':sorted(set(ours)-set(actual)),'worker_only':sorted(set(actual)-set(ours)),
            'local_status':local.get('status','unknown'),'scores_compared':False}


def record_tx(conn,row,receipt):
    hint=conn.execute("SELECT payload FROM events WHERE run_id=? AND type='submission.platform_feedback' AND json_extract(payload,'$.submission_id')=? AND json_extract(payload,'$.kind')='trace_hint' ORDER BY seq DESC LIMIT 1",(row['run_id'],row['id'])).fetchone()
    if not hint or 'deductions' not in receipt:return
    local=json.loads(hint[0])['response']
    comparison=compare(local,receipt)
    digest=hashlib.sha256(json.dumps(comparison,sort_keys=True).encode()).hexdigest()
    changed=conn.execute('INSERT OR IGNORE INTO trace_hint_calibrations VALUES(?,?,?,?)',
        (row['id'],digest,json.dumps(comparison,ensure_ascii=False),db.utcnow())).rowcount
    if changed:db.append_event_tx(conn,row['run_id'],'controller','submission.trace_hint_compared',
        {'submission_id':row['id'],**comparison},trial_id=row['trial_id'])
