import hashlib,json,shutil,sqlite3,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cyberscientist import config,db,sandboxes,job_checks,environment_catalog
AREA=ROOT/'.runtime/validation/sandbox';AREA.mkdir(parents=True,exist_ok=True)
if (AREA/'validation.sqlite').exists():raise RuntimeError('验证沙箱账本已存在；只读对账，禁止重放创建')
with sqlite3.connect(ROOT/'.cyberscientist/cyberscientist.db') as source:
 with sqlite3.connect(AREA/'validation.sqlite') as target:source.backup(target)
for name in ('settings.json','secrets.json'):shutil.copy2(ROOT/'.cyberscientist'/name,AREA/name)
config.DATA_DIR=AREA;config.DB_PATH=AREA/'validation.sqlite';config.SETTINGS_PATH=AREA/'settings.json';config.SECRETS_PATH=AREA/'secrets.json';config.WORKSPACE_DIR=AREA/'workspace';config.EXPERIENCE_DIR=AREA/'experience';config.LOCK_PATH=AREA/'lock'
db.init_db();RID='run_8a21b7d249';r=db.query_one('SELECT * FROM runs WHERE id=?',(RID,));snap=json.loads(r['config_snapshot']);snap['settings']=config.load_settings();snap['settings']['initial_method_approval']=False;snap.get('competition',{}).pop('budget_policy',None)
used=db.query_one('SELECT COUNT(*) FROM compute_sandboxes WHERE run_id=?',(RID,))[0]
db.execute('UPDATE authorizations SET unlimited_resources=0,max_run_minutes=15,max_sandboxes=?,max_sandbox_minutes=120,max_jobs=0,max_submissions=0 WHERE id=?',(used+1,r['authorization_id']))
db.execute("UPDATE runs SET phase='running',gate='open',clock_version=0,started_at=?,ended_at=NULL,config_snapshot=? WHERE id=?",(db.utcnow(),json.dumps(snap),RID))
entry=environment_catalog.get('competition-materials-assets-20261009');image=entry['image_address'] if 'image_address' in entry else entry['image']
files={'task.sh':b'set -eu\nprintf ready > result.txt\n'};spec={'command':'bash task.sh','image_address':image,'machine_type':'c2_m4_cpu','max_run_time':2,'backward_files':['result.txt','STDOUTERR']}
result={'job_count_before':db.query_one('SELECT COUNT(*) FROM compute_jobs')[0]}
result['job_preflight']=job_checks.static(files,spec,{})
sid=None
try:
 created=sandboxes.create(RID,'hidden-runtime-box',{'image':image,'cpu':'2c4g','timeout':300});sid=created.get('sandbox_id');result['create_status']=created['status'];result['sandbox_id']=sid
 if not sid:raise RuntimeError('真实创建未确认，无重放')
 db.append_event(RID,'controller','topic.workspace',{'mode':'sandbox','image':image,'sandbox_id':sid,'operation_id':'hidden-runtime-box','reason':'bounded migration verification'})
 result['job_preflight']=job_checks.image(RID,image,result['job_preflight'])
 execution=sandboxes.execute(RID,sid,'printf runtime-isolation-ready',20,'hidden-runtime-echo');result['exec_status']=execution['status'];result['exit_code']=execution.get('exit_code')
except Exception as exc:
 result['error_type']=type(exc).__name__;result['error_code']=getattr(exc,'code',None)
 raise
finally:
 if sid:
  cleanup=sandboxes.delete(RID,sid)
  for _ in range(6):
   if cleanup['status']=='deleted':break
   time.sleep(3);sandboxes.reconcile_deletions();cleanup['status']=sandboxes._owned(RID,sid)['status']
  result['cleanup_status']=cleanup['status']
 result['job_count_after']=db.query_one('SELECT COUNT(*) FROM compute_jobs')[0]
 (AREA/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'create':result.get('create_status'),'exec':result.get('exec_status'),'exit_code':result.get('exit_code'),'cleanup':result.get('cleanup_status'),'jobs_created':result['job_count_after']-result['job_count_before']}))
