import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

type Proposal = {method_md:string; parameters_md:string; basis_md:string; outputs_md:string; capabilities:string[]}
type State = {status:string; version:number; proposal:Proposal|null; approved_by?:string; approved_at?:string}
export function MethodApproval({runId,onChanged}:{runId:string;onChanged?:()=>void}) {
  const [value,setValue]=useState<State|null>(null)
  const [text,setText]=useState(''),[actor,setActor]=useState('user'),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const refresh=useCallback(async()=>{try {setValue(await api.get<State>(`/api/v1/runs/${runId}/method`))}catch(e){setError(String(e))}},[runId])
  useEffect(()=>{setValue(null);void refresh();const id=setInterval(()=>void refresh(),5000);return()=>clearInterval(id)},[refresh])
  const act=async(action:string)=>{
    setBusy(true);setError('')
    try {await api.post(`/api/v1/runs/${runId}/method`,{action,actor,text,version:value?.version,operation_id:crypto.randomUUID()});setText('');await refresh();onChanged?.()}
    catch(e){setError(String(e))}finally{setBusy(false)}
  }
  if(!value||value.status==='not_proposed')return error?<p role="alert">{error}</p>:null
  if(value.status==='approved')return <p>初始方法已批准 · {value.approved_by} · {value.approved_at}</p>
  const complete=value.status==='pending'
  return <article className="card" aria-label="初始方法审批">
    <div className="card-head"><h2>等待初始方法批准</h2><span>正常等待，批准前不计算</span></div>
    <div className="card-body">
      {Object.entries(value.proposal??{}).map(([key,body])=><div key={key}><strong>{{method_md:'方法',parameters_md:'参数',basis_md:'依据',outputs_md:'预期产物',capabilities:'所需能力'}[key]??key}</strong><pre className="pre-wrap">{Array.isArray(body)?body.join('\n'):String(body)}</pre></div>)}
      {!complete&&<p role="status">提案未完整，需要 PI 重新提案。</p>}
      <button className="btn" aria-label="复制方法提案" onClick={()=>void navigator.clipboard.writeText(JSON.stringify(value.proposal,null,2))}>复制提案全文</button>
      <label>批准人<select aria-label="方法批准人" value={actor} onChange={e=>setActor(e.target.value)}><option value="user">用户</option><option value="monitor">监控</option></select></label>
      <label>修改内容或驳回理由<textarea aria-label="方法修改或驳回理由" value={text} onChange={e=>setText(e.target.value)} /></label>
      <button className="btn btn-dark" aria-label="批准初始方法" disabled={busy||!complete} onClick={()=>void act('approve')}>批准</button>
      <button className="btn" aria-label="修改后批准初始方法" disabled={busy||!complete||!text.trim()} onClick={()=>void act('modify')}>修改后批准</button>
      <button className="btn" aria-label="驳回初始方法" disabled={busy||!text.trim()} onClick={()=>void act('reject')}>驳回</button>
      {error&&<p role="alert">{error}</p>}
    </div>
  </article>
}
