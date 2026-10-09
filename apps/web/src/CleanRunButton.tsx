import {useState} from 'react'
import {api} from './api'
export const CLEAN_REQUEST='请转干净复跑。clean_handoff 按 method_md（流程）、parameters_md（参数）、validation_md（验证）、pitfalls_md（故障）四段整理；不得含探索代码或探索结果数值，允许方法与计算参数及其选择依据；start_trial 使用 fresh_executor_session=true。方法来自本方此前的探索。'
export function CleanRunButton({runId}:{runId:string}){
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('')
 return <><button className="btn" aria-label="转干净复跑" disabled={busy} onClick={async()=>{setBusy(true);try{await api.post(`/api/v1/runs/${runId}/control`,{action:'steer',text:CLEAN_REQUEST,operation_id:crypto.randomUUID()});setMessage('已发给 PI，等待执行者空闲后新开会话')}catch(e){setMessage(String(e))}finally{setBusy(false)}}}>转干净复跑</button>{message&&<span role="status">{message}</span>}</>
}
