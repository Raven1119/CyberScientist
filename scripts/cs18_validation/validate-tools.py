import asyncio,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cyberscientist import db,collab,codex_protocol
from cyberscientist.jsonrpc_stdio import JsonRpcStdio
AREA=ROOT/'.runtime/validation';AREA.mkdir(exist_ok=True);RID='run_8a21b7d249'
PACKAGE='submissions/sub_8e446f6e58/package.zip';TRIAL='trial_04dc15406d'
CALLS={
'research_files':{'action':'list','scope':'skills'},'research_shared':{'action':'list'},
'research_trace_variant':{'source_submission_id':'absent-validation-submission','operation_id':'connectivity-only','prediction_md':'只检查拒绝路径，无提交授权'},
'research_review_package':{'trial_id':'absent-validation-trial','operation_id':'connectivity-only'},
'research_trace':{'action':'list','limit':1},'platform_scores':{},
'research_operating_facts':{},'research_experience':{'action':'list'},
'research_web_search':{'query':'ABACUS official documentation'},
'research_web_read':{'url':'https://play.bohrium.com/api/protocol'},
'research_lkm':{'query':'ABACUS electronic structure code'},
'research_checkpoint':{'checkpoint_key':'runtime-connectivity','review':'none','stage':'progress','report_md':'只读通路核查；没有科研结果或提交。','evidence_refs':[]},
'ack_guidance':{'guidance_id':'absent-validation-guidance','disposition':'challenged','reason_md':'此项只检查无指导时的拒绝路径。'},
'research_job':{'action':'list'},'research_sandbox':{'action':'list'},
'research_package_check':{'trial_id':TRIAL,'package_path':PACKAGE},
'research_trace_narrative_check':{'trial_id':TRIAL,'package_path':PACKAGE},
'research_local_score':{'action':'prepare','trial_id':'absent-validation-trial','operation_id':'connectivity-only'},
'research_data':{'action':'list'},'research_environment':{'action':'list'}}
async def main():
 result=[];called=set()
 for role in ('brain','executor'):
  with db.transaction() as c:token=collab.issue_token(c,RID,role,'connectivity-only',9998,ttl_hours=1)
  env=codex_protocol.native_brain_environment()|{'CS_TOOL_TOKEN':token,'CS_TOOL_ROLE':role,'CS_API_URL':'http://127.0.0.1:8765'}
  rpc=JsonRpcStdio([sys.executable,'-m','cyberscientist.mcp_bridge'],cwd=str(ROOT),env=env,name='runtime-tool-probe')
  try:
   await rpc.start();await rpc.request('initialize',{'protocolVersion':'2024-11-05','clientInfo':{'name':'bounded-runtime-probe','version':'1'},'capabilities':{}},timeout=30)
   tools=(await rpc.request('tools/list',{},timeout=30))['tools']
   for tool in tools:
    name=tool['name']
    if name in called:continue
    called.add(name)
    try:
     receipt=await rpc.request('tools/call',{'name':name,'arguments':CALLS[name]},timeout=180)
     text=json.dumps(receipt,sort_keys=True);content=json.loads(receipt['content'][0]['text'])
     error=content.get('error') or content.get('detail') or (content.get('code') if receipt.get('isError') else None)
     result.append({'name':name,'role':role,'transport':'returned','response_sha256':hashlib.sha256(text.encode()).hexdigest(),'is_error':bool(receipt.get('isError') or error),'error_code':content.get('code') or (error.get('code') if isinstance(error,dict) else None),'keys':list(content) if isinstance(content,dict) else []})
    except Exception as exc:result.append({'name':name,'role':role,'transport':'failed','error_type':type(exc).__name__})
    (AREA/'tool-calls.json').write_text(json.dumps({'expected_tools':sorted(CALLS),'called':result},ensure_ascii=False,indent=2))
  finally:await rpc.stop()
 print(json.dumps({'called':len(called),'expected':len(CALLS),'successful':sum(x.get('transport')=='returned' and not x.get('is_error') for x in result),'rejected_or_failed':sum(x.get('transport')!='returned' or x.get('is_error',False) for x in result)}))
asyncio.run(main())
