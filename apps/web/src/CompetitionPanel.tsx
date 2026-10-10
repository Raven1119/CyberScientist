import {useCallback,useEffect,useState} from 'react'
import {api} from './api'
import {MethodApproval} from './MethodApproval'
import {CleanRunButton} from './CleanRunButton'
import {AccountRoles} from './AccountRoles'
import {useLatestRequest} from './useLatestRequest'
import {useApp} from './app-context'
type Row={account_usage?:{mailbox_id:string;email:string;submitted:number;used:number;limit:number;exhausted:boolean}[];clean_run?:{policy:string;recommended:boolean};run_id:string;challenge_id:string;title:string;track:string;phase:string;run_phase:string;current_trial_id:string|null;method_summary:string;scoring_seconds:number|null;next_step:string;submission_held:boolean;mailbox_id:string|null;executor:{model_id:string};receipt:null|{platform_status?:string|null;harbor_score:number|null;trace_score:number|null;trace_decision:string|null;receipt_details_json:string;email:string}}
type Panel={items:Row[];auto_submission:boolean;distributions:unknown[];repairs:{operation_id:string;text_md:string;created_at:string}[];alerts:{id:string;title:string}[]}
export function CompetitionPanel(){
 const {setPage,setCurrentChallengeId,setFocusedRunId}=useApp()
 const [value,setValue]=useState<Panel|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[guidance,setGuidance]=useState<Record<string,string>>({}),[accounts,setAccounts]=useState<{id:string;email:string;role:string;status:string}[]>([])
 const beginRead=useLatestRequest()
 const refresh=useCallback(async()=>{const current=beginRead();const [p,a]=await Promise.all([api.get<Panel>('/api/v1/competition-panel'),api.get<{items:typeof accounts}>('/api/v1/mailboxes')]);if(!current())return;if(!Array.isArray(p.items)||!Array.isArray(p.repairs)||!Array.isArray(p.alerts)||!Array.isArray(p.distributions)||p.items.some(r=>!r.run_id||!r.executor))throw new Error('比赛面板接口返回无效');setValue(p);setAccounts(a.items??[]);setError('')},[beginRead])
 useEffect(()=>{void refresh().catch(e=>setError(String(e)));const timer=setInterval(()=>void refresh().catch(e=>setError(String(e))),5000);return()=>clearInterval(timer)},[refresh])
 const act=async(path:string,body:unknown,method:'post'|'put'='post')=>{setBusy(true);setError('');try{await api[method](path,body);await refresh()}catch(e){setError(String(e))}finally{setBusy(false)}}
 const control=(r:Row,action:string,text?:string)=>act(`/api/v1/runs/${r.run_id}/control`,{action,text,operation_id:crypto.randomUUID()})
 const change=(r:Row,action:string,value:unknown)=>act(`/api/v1/runs/${r.run_id}/panel`,{action,value,operation_id:crypto.randomUUID()})
 return <article className="card" aria-label="比赛实时面板"><div className="card-head"><h2>比赛实时面板</h2><button className="btn" aria-label="切换全局提交" disabled={busy||!value} onClick={()=>void act('/api/v1/features/auto_submission',{enabled:!value?.auto_submission},'put')}>{value?.auto_submission?'全局暂停提交':'全局恢复提交'}</button></div>
 <div className="card-body">{error&&<p role="alert">{error}</p>}
 {value&&<table><thead><tr><th>题目 / 赛道 / 阶段</th><th>方法</th><th>真实回执 / 评分时长 / 账号</th><th>下一步 / 操作</th></tr></thead><tbody>{value?.items.map(r=><tr key={r.run_id}>
 <td>{r.title}<br/>{r.track} · {r.phase}<br/><button type="button" aria-label={`${r.title}查看研究`} onClick={()=>{setCurrentChallengeId(r.challenge_id);setFocusedRunId(r.run_id);setPage('research')}}>查看研究</button></td><td>{r.method_summary}<MethodApproval runId={r.run_id} onChanged={()=>void refresh()}/></td>
 <td>{['pending_review','needs_review'].includes(r.receipt?.platform_status??'')&&<strong>人工复核中<br/></strong>}科学 {r.receipt?.harbor_score??'unknown'} · 轨迹 {r.receipt?.trace_score??'unknown'}<br/>{r.receipt?.trace_decision??'unknown'}<pre>{r.receipt?.receipt_details_json?JSON.stringify(JSON.parse(r.receipt.receipt_details_json).deductions??[]):'[]'}</pre>{r.scoring_seconds===null?'unknown':`${Math.round(r.scoring_seconds/60)} 分钟`}<br/>{r.receipt?.email??'尚未提交'}
 <details><summary>本题各账号提交次数</summary>{r.account_usage?.map(a=><p key={a.mailbox_id}>{a.email}：已确认提交 {a.submitted} 次 · 额度占用 {a.used}/{a.limit}{a.exhausted?' · 本题提交上限已用尽':''}</p>)}</details></td>
 <td>{r.next_step}{r.clean_run&&<p>干净复跑：{r.clean_run.policy} · {r.clean_run.recommended?'建议 PI 评估':'暂未触发'}</p>}<div className="button-row">
 <button aria-label={`${r.title}启动`} disabled={busy||r.run_phase!=='created'} onClick={()=>void act(`/api/v1/runs/${r.run_id}/start`,{})}>启动</button>
 <button aria-label={`${r.title}暂停`} disabled={busy||r.run_phase!=='running'} onClick={()=>void control(r,'pause')}>暂停</button>
 <button aria-label={`${r.title}恢复`} disabled={busy||!['paused','recovering'].includes(r.run_phase)} onClick={()=>void control(r,'resume')}>恢复</button>
 <button aria-label={`${r.title}停止`} disabled={busy||['finished','cancelled','failed'].includes(r.run_phase)} onClick={()=>void control(r,'terminate')}>停止</button>
 <CleanRunButton runId={r.run_id}/>
 <button aria-label={`${r.title}立即提交`} disabled={busy||!r.current_trial_id} onClick={()=>void act(`/api/v1/runs/${r.run_id}/submissions`,{trial_id:r.current_trial_id,operation_id:crypto.randomUUID()})}>立即提交</button>
 <button aria-label={`${r.title}切换暂缓提交`} disabled={busy} onClick={()=>void change(r,'submission_hold',!r.submission_held)}>{r.submission_held?'恢复本题提交':'暂缓提交'}</button>
 </div><label>实验账号<select aria-label={`${r.title}账号分配`} value={r.mailbox_id??''} onChange={e=>void change(r,'mailbox',e.target.value||null)}><option value="">自动轮换</option>{accounts.filter(a=>a.role==='experiment'&&a.status==='active').map(a=><option key={a.id} value={a.id}>{a.email}</option>)}</select></label>
 <label>下次会话执行者<select aria-label={`${r.title}执行者档位`} value={r.executor.model_id} onChange={e=>void change(r,'executor',{runtime:'codex',provider:e.target.value.startsWith('deepseek')?'deepseek':'codex',model_id:e.target.value,reasoning_effort:e.target.value.startsWith('deepseek')?'high':'xhigh',fast_mode:!e.target.value.startsWith('deepseek')})}><option value="gpt-5.6-terra">Terra fast</option><option value="gpt-6-astra">Astra fast</option><option value="gpt-6.1-sol">Sol fast</option><option value="deepseek-flash">DeepSeek（手动）</option></select></label>
 <label>给 PI 的指导<textarea aria-label={`${r.title}给PI指导`} value={guidance[r.run_id]??''} onChange={e=>setGuidance({...guidance,[r.run_id]:e.target.value})}/></label><button aria-label={`${r.title}发送PI指导`} disabled={busy||!guidance[r.run_id]?.trim()} onClick={()=>void control(r,'steer',guidance[r.run_id])}>发送给 PI</button>
 </td></tr>)}</tbody></table>}
 <details><summary>榜单分布与最高分</summary><pre>{JSON.stringify(value?.distributions??[],null,2)}</pre></details>
 <details><summary>监控修复记录</summary>{value?.repairs.map(r=><p key={r.operation_id}>{r.created_at} · {r.text_md}</p>)}</details>
 <aside aria-label="比赛告警">{value?.alerts.map(a=><p key={a.id} role="alert">{a.title}</p>)}</aside><AccountRoles/>
 </div></article>
}
