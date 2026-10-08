import asyncio,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cyberscientist import config,db,collab,codex_protocol
from cyberscientist.controller import RunController
from cyberscientist.brains.codex import CodexBrain
from cyberscientist.prime.codex_exec import CodexExecutor
AREA=ROOT/'.runtime/validation';AREA.mkdir(exist_ok=True)
RID='run_8a21b7d249'
async def main():
 settings=config.load_settings();ctrl=RunController();base=ROOT/'workspace/validation/native';base.mkdir(parents=True,exist_ok=True)
 work=base/'pi';work.mkdir(exist_ok=True);spec=ctrl._brain_spec(RID,settings,work);spec.pop('run_id',None)
 brain=CodexBrain(settings['brain']['executable'],'gpt-6-astra','xhigh','codex',fast_mode=True);brain.allow_format_rewrites=False
 result={'new_research_runs':0,'compute_jobs_created':0,'submissions_created':0,'roles':{}}
 session=None
 try:
  start=time.monotonic();session=await brain.open(spec)
  packet={'run_id':RID,'state_version':0,'trigger':'acceptance','user_prompt':'已结束旧题上的最小只读会话。请确认已就绪，actions仅输出wait。不计算、不提交、不读取历史研究结果。'}
  decision=None
  async def consume():
   nonlocal decision
   async for event in brain.review(session,packet):
    if event.type=='decision':decision=event.payload['decision']
  await asyncio.wait_for(consume(),600)
  if not decision:raise RuntimeError('PI没有返回合法决定')
  result['roles']['pi']={'session_id':session.session_id,'cwd':str(work),'model':session.raw['model'],'effort':session.raw['reasoning_effort'],'fast':session.raw['fast_mode'],'native_path':session.raw['thread'].get('path'),'elapsed_seconds':time.monotonic()-start,'decision_valid':True}
 finally:
  if session:await brain.close(session)
 executor=CodexExecutor(settings['executor']['executable'],'gpt-5.6-terra','xhigh',provider='codex',fast_mode=True)
 work=base/'executor';work.mkdir(exist_ok=True)
 with db.transaction() as c:token=collab.issue_token(c,RID,'executor','acceptance-only',9999,ttl_hours=1)
 variables={'CS_TOOL_TOKEN':token,'CS_TOOL_ROLE':'executor','CS_API_URL':'http://127.0.0.1:8765'}
 spec={'working_directory':str(work),'fast_mode':True,'env':codex_protocol.native_brain_environment()|variables,'instructions':'已结束旧题的只读准备会话。当前未授权科学计算或提交。','mcp_servers':[{'name':'cyberscientist','command':sys.executable,'args':['-m','cyberscientist.mcp_bridge'],'env':[{'name':k,'value':v} for k,v in variables.items()]}]}
 sid=None
 try:
  start=time.monotonic();sid=await executor.start(spec);native=executor._sessions[sid]
  thread=await native.rpc.request('thread/read',{'threadId':sid},timeout=30)
  receipt=await executor.prompt(sid,'请回复“准备就绪”，随后结束本回合。')
  if receipt.status!='accepted':raise RuntimeError('执行者turn未接受')
  async def consume_executor():
   async for event in executor.events(sid):
    if event['type']=='executor.turn_completed':return
    if event['type']=='run.aborted':raise RuntimeError('执行者原生回合失败')
  await asyncio.wait_for(consume_executor(),600)
  fact=db.query_one("SELECT payload_json FROM runtime_observations WHERE kind='codex_fast:gpt-5.6-terra'")
  result['roles']['executor']={'session_id':sid,'cwd':str(work),'model':'gpt-5.6-terra','effort':'xhigh','fast':json.loads(fact[0]) if fact else None,'native_path':thread['thread'].get('path'),'elapsed_seconds':time.monotonic()-start,'completed':True}
 finally:
  if sid:await executor.close(sid)
 for role,record in result['roles'].items():
  path=Path(record['native_path']);raw=path.read_bytes();text=raw.decode()
  record.update(native_bytes=len(raw),native_sha256=hashlib.sha256(raw).hexdigest(),development_path_hits=text.count('/home/wmywb/CyberScientist/'),construction_text_hits=text.count('CyberScientist — 施工约定'),global_agents_path_hits=text.count('/home/wmywb/.codex/AGENTS.md'),unrelated_builtin_hits={name:text.count(name) for name in ('imagegen','openai-docs','review-agent','skill-creator','skill-installer')})
 (AREA/'native-sessions.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps({'roles':list(result['roles']),'native_sessions':[v['session_id'] for v in result['roles'].values()]}))
asyncio.run(main())
