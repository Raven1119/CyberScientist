import {useState} from 'react'
import {api} from './api'
export const CLEAN_REQUEST='请转干净复跑。先整理方法、输入参数和坑，不能含探索代码或探索数值；start_trial 使用 fresh_executor_session=true 与 clean_handoff。方法来自本方此前的探索。'
export function CleanRunButton({runId}:{runId:string}){
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('')
 return <><button className="btn" aria-label="转干净复跑" disabled={busy} onClick={async()=>{setBusy(true);try{await api.post(`/api/v1/runs/${runId}/control`,{action:'steer',text:CLEAN_REQUEST,operation_id:crypto.randomUUID()});setMessage('已发给 PI，等待执行者空闲后新开会话')}catch(e){setMessage(String(e))}finally{setBusy(false)}}}>转干净复跑</button>{message&&<span role="status">{message}</span>}</>
}
