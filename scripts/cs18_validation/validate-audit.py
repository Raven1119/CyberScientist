import hashlib,json,re,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cyberscientist import config,db,runtime_release,runtime_layout,skills
AREA=ROOT/'.runtime/validation/hidden';DEV=ROOT.parent/'CyberScientist'
development=[DEV,*ROOT.parent.glob('CyberScientist-night-*')]
result={'development_hidden_during_audit':not DEV.exists(),'counts':{},'active_path_hits':[]}
for table in ('runs','submissions','compute_jobs','mailboxes'):
 result['counts'][table]=db.query_one('SELECT COUNT(*) FROM '+table)[0]
for name in ('.cyberscientist/settings.json','.runtime/codex/config.toml','.env'):
 text=(ROOT/name).read_text()
 for root in development:
  if re.search(re.escape(str(root))+r'(?![A-Za-z0-9_.-])',text):result['active_path_hits'].append({'file':name})
for table,key,column in [('runtime_observations','kind','payload_json'),('environment_catalog_entries','id','descriptor_json'),('compute_jobs','operation_id','input_directory'),('data_materializations','id','store_path')]:
 for row in db.query('SELECT '+key+','+column+' FROM '+table):
  for root in development:
   if isinstance(row[column],str) and re.search(re.escape(str(root))+r'(?![A-Za-z0-9_.-])',row[column]):result['active_path_hits'].append({'table':table,'key':row[key]})
cap=db.query_one("SELECT payload_json FROM runtime_observations WHERE kind='competition_toolchain'")
result['content_violations']=runtime_release.scan_content(ROOT,development,experience_root=ROOT/'experience',capability_content=cap[0] if cap else '')
result['forbidden_paths']=[str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.name in ('AGENTS.md','STATUS.md','.package-checks','.git')]
result['fast_facts']={r['kind']:json.loads(r['payload_json']) for r in db.query("SELECT * FROM runtime_observations WHERE kind LIKE 'codex_fast:%'")}
outside=json.loads((ROOT/'.runtime/validation/outside-skill-baseline.json').read_text())['outside_names']
session_data=json.loads((ROOT/'.runtime/validation/native-sessions.json').read_text())
result['native_roles']={}
for role,record in session_data['roles'].items():
 path=Path(record['native_path']);text=path.read_text();rows=[json.loads(x) for x in text.splitlines()]
 names={name:len(re.findall(r'(?<![\w:-])'+re.escape(name)+r'(?![\w:-])',text)) for name in outside}
 names={name:n for name,n in names.items() if n}
 first_frames='\n'.join(text.splitlines()[:8])
 result['native_roles'][role]={'session_id':record['session_id'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'cwd':record['cwd'],'model':record['model'],'effort':record['effort'],'fast':record.get('fast'),'development_path_hits':len(re.findall(re.escape(str(DEV))+r'(?![A-Za-z0-9_.-])',text)),'construction_text_hits':text.count('CyberScientist — 施工约定'),'global_agents_path_hits':text.count('/home/wmywb/.codex/AGENTS.md'),'first_frames_development_path_hits':len(re.findall(re.escape(str(DEV))+r'(?![A-Za-z0-9_.-])',first_frames)),'outside_name_hits':names,'outside_name_locations':{name:sorted({x.get('type','')+':'+('base_instructions' if name in str(x.get('payload',{}).get('base_instructions','')) else 'other') for x in rows if re.search(r'(?<![\w:-])'+re.escape(name)+r'(?![\w:-])',json.dumps(x))}) for name in names}}
catalog=skills.scan_catalog();settings=config.load_settings()
result['app_skill_ids']=sorted(x['id'] for x in catalog)
result['effective_skills']=sorted(settings['skills']['always_on'])
result['skill_copy_mismatches']=[]
for name in result['effective_skills']:
 for p in (ROOT/'skills'/name).rglob('*'):
  if p.is_file():
   q=ROOT/'.runtime/codex/skills'/name/p.relative_to(ROOT/'skills'/name)
   if not q.is_file() or hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(q.read_bytes()).digest():result['skill_copy_mismatches'].append(str(p.relative_to(ROOT)))
result['all_resume_on_startup_disabled']=db.query_one('SELECT COUNT(*) FROM runs WHERE resume_on_startup!=0')[0]==0
with urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health',timeout=10) as response:result['health']=json.load(response)
with urllib.request.urlopen('http://127.0.0.1:8765/api/v1/ops/digest',timeout=10) as response:result['digest']=json.load(response)
with urllib.request.urlopen('http://127.0.0.1:8765/api/v1/runs/run_8a21b7d249',timeout=10) as response:
 historical=json.load(response);result['historical_run_view']={'http_status':response.status,'id':historical.get('run',historical).get('id'),'keys':list(historical)}
with urllib.request.urlopen('http://127.0.0.1:8765/api/v1/runs/run_8a21b7d249/artifacts/trials/trial_04dc15406d/result_package.zip',timeout=30) as response:
 result['historical_artifact_view']={'http_status':response.status,'content_length':response.headers.get('Content-Length'),'zip_header':response.read(4).hex()}
result['version']=runtime_layout.version()
result['experience_files']={p.relative_to(ROOT/'experience').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'experience').rglob('*') if p.is_file()}
result['secrets_sha256']=hashlib.sha256((ROOT/'.cyberscientist/secrets.json').read_bytes()).hexdigest()
baseline=json.loads((AREA/'baseline.json').read_text())
result['preserved']={key:result[key]==baseline[key] for key in ('experience_files','secrets_sha256','counts')}
(AREA/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'counts':result['counts'],'active_path_hits':len(result['active_path_hits']),'content_violations':len(result['content_violations']),'forbidden_paths':result['forbidden_paths'],'native_outside_name_hits':{k:v['outside_name_hits'] for k,v in result['native_roles'].items()},'skill_copy_mismatches':len(result['skill_copy_mismatches'])}))
