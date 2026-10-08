import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cyberscientist import config,db,preflight
settings=config.load_settings();result={'accounts':[],'versions':{}}
for row in db.query('SELECT id,secret_ref FROM mailboxes ORDER BY id'):
 ok,code,profile=preflight._identity(settings['playground']['base_url'],row['secret_ref'])
 result['accounts'].append({'mailbox_id':row['id'],'credential_present':bool(config.resolve_secret(row['secret_ref'])),'identity_valid':ok,'http_status':code})
ok,code,profile=preflight._identity(settings['playground']['base_url'],settings['playground']['token_secret_ref'])
result['operator']={'identity_valid':ok,'http_status':code}
commands={'codex':[str(ROOT/'.runtime/bin/codex-0.161.0'),'--version'],'bohr':[str(ROOT/'.runtime/bin/bohr-2.7.8'),'--version'],'bohr_legacy':[str(ROOT/'.runtime/bin/bohr-legacy'),'--version'],'official_cli':['node',str(ROOT/'tools/playground-cli/0.1.40/dist/main.js'),'--version'],'clients':[str(ROOT/'.cyberscientist/toolchain-venv/bin/python'),'-c','import dflow,bohrium,importlib.metadata as m;print(m.version("pydflow"),m.version("bohrium-sdk"))']}
for name,args in commands.items():
 try:
  process=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
  result['versions'][name]={'exit_code':process.returncode,'stdout':process.stdout.strip(),'stderr':process.stderr.strip()}
 except Exception as exc:result['versions'][name]={'error_type':type(exc).__name__}
(ROOT/'.runtime/validation/hidden/identities.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'authenticated_accounts':sum(x['identity_valid'] for x in result['accounts']),'configured_accounts':len(result['accounts']),'operator':ok,'version_exit_codes':{k:v.get('exit_code') for k,v in result['versions'].items()}}))
