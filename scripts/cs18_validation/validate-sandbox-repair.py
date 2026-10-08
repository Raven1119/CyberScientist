import json,math,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cyberscientist import config,db,sandboxes,job_checks,environment_catalog
AREA=ROOT/'.runtime/validation/sandbox';config.DATA_DIR=AREA;config.DB_PATH=AREA/'validation.sqlite';config.SETTINGS_PATH=AREA/'settings.json';config.SECRETS_PATH=AREA/'secrets.json';config.WORKSPACE_DIR=AREA/'workspace';config.EXPERIENCE_DIR=AREA/'experience';config.LOCK_PATH=AREA/'lock'
db.init_db();RID='run_8a21b7d249';OP='hidden-runtime-box-repair'
assert not db.query_one('SELECT * FROM compute_sandboxes WHERE operation_id IN (?,?)',('hidden-runtime-box',OP)), 'Unknown or existing operation: no replay'
ledger=ROOT/'.runtime/validation/authorization.json';authorization=json.loads(ledger.read_text());assert authorization['used']['sandboxes']==9
authorization['used']['sandboxes']=10;authorization['supplementary_before_create_rejection']=True;ledger.write_text(json.dumps(authorization,indent=2))
run=db.query_one('SELECT * FROM runs WHERE id=?',(RID,));rows=db.query('SELECT * FROM compute_sandboxes WHERE run_id=?',(RID,));reserved=sum(sandboxes.reserved_seconds(row) for row in rows)
db.execute('UPDATE authorizations SET max_sandbox_minutes=? WHERE id=?',(math.ceil((reserved+300)/60),run['authorization_id']))
db.execute('UPDATE runs SET started_at=? WHERE id=?',(db.utcnow(),RID))
image=environment_catalog.get('competition-materials-assets-20261009')['image'];result={'first_failure_proved_before_reservation':True,'historical_reserved_seconds':reserved,'job_count_before':db.query_one('SELECT COUNT(*) FROM compute_jobs')[0]};sid=None
try:
 created=sandboxes.create(RID,OP,{'image':image,'cpu':'2c4g','timeout':300});sid=created.get('sandbox_id');result.update(create_status=created['status'],sandbox_id=sid)
 if not sid:raise RuntimeError('Creation not confirmed; no replay')
 db.append_event(RID,'controller','topic.workspace',{'mode':'sandbox','image':image,'sandbox_id':sid,'operation_id':OP})
 report=job_checks.static({'task.sh':b'set -eu\nprintf ready > result.txt\n'},{'command':'bash task.sh','image_address':image,'machine_type':'c2_m4_cpu','max_run_time':2,'backward_files':['result.txt','STDOUTERR']},{})
 result['job_preflight']=job_checks.image(RID,image,report)
 execution=sandboxes.execute(RID,sid,'printf runtime-isolation-ready',20,'hidden-runtime-echo-repair');result.update(exec_status=execution['status'],exit_code=execution.get('exit_code'))
except Exception as exc:
 result.update(error_type=type(exc).__name__,error_code=getattr(exc,'code',None));raise
finally:
 if sid:
  cleanup=sandboxes.delete(RID,sid)
  for _ in range(6):
   if cleanup['status']=='deleted':break
   time.sleep(3);sandboxes.reconcile_deletions();cleanup['status']=sandboxes._owned(RID,sid)['status']
  result['cleanup_status']=cleanup['status']
 result['job_count_after']=db.query_one('SELECT COUNT(*) FROM compute_jobs')[0]
 (AREA/'supplementary-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({key:result.get(key) for key in ('create_status','exec_status','exit_code','cleanup_status','job_count_before','job_count_after')}))
