import {useEffect,useState} from 'react'
import {api} from './api'
type Policy={revision:number;initial_method_approval?:boolean;clean_run_policy?:string}
export function CompetitionPolicySettings(){
 const [value,setValue]=useState<Policy>({revision:0}),[error,setError]=useState('')
 useEffect(()=>{void api.get<Policy>('/api/v1/settings').then(setValue).catch(e=>setError(String(e)))},[])
 const save=async(settings:Partial<Policy>)=>{try{setValue(await api.put<Policy>('/api/v1/settings',{base_revision:value.revision,settings}))}catch(e){setError(String(e))}}
 return <article className="card"><div className="card-head"><h2>比赛流程</h2></div><div className="card-body">
  <label><input type="checkbox" aria-label="启用初始方法审批" checked={value.initial_method_approval!==false} onChange={e=>void save({initial_method_approval:e.target.checked})}/>初始方法须批准后计算</label>
  <label>干净复跑策略<select aria-label="干净复跑策略" value={value.clean_run_policy??'when_not_accepted'} onChange={e=>void save({clean_run_policy:e.target.value})}><option value="when_not_accepted">最高科学分未 accept 时</option><option value="always_after_science">科学分完成后每题复跑</option></select></label>
  {error&&<p role="alert">{error}</p>}
 </div></article>
}
