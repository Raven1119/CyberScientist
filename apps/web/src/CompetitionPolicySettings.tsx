import {useEffect,useState} from 'react'
import {api} from './api'
export function CompetitionPolicySettings(){
 const [enabled,setEnabled]=useState(true),[revision,setRevision]=useState(0),[error,setError]=useState('')
 useEffect(()=>{void api.get<{revision:number;initial_method_approval?:boolean}>('/api/v1/settings').then(s=>{setEnabled(s.initial_method_approval!==false);setRevision(s.revision)}).catch(e=>setError(String(e)))},[])
 const save=async(next:boolean)=>{try{const s=await api.put<{revision:number}>('/api/v1/settings',{base_revision:revision,settings:{initial_method_approval:next}});setEnabled(next);setRevision(s.revision)}catch(e){setError(String(e))}}
 return <article className="card"><div className="card-head"><h2>比赛流程</h2></div><div className="card-body"><label><input type="checkbox" aria-label="启用初始方法审批" checked={enabled} onChange={e=>void save(e.target.checked)}/>初始方法须批准后计算</label>{error&&<p role="alert">{error}</p>}</div></article>
}
