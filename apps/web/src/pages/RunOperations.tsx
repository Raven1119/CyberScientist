import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

type Job = { operation_id: string; platform_job_id: number | null; status: string; retrieval_status: string; observed_at: string | null }
type Jobs = { items: Job[]; reserved_jobs: number; active_or_unknown: number }
type Curation = { state: string; summary?: string; error?: string; proposals_applied?: number }
const terminal = new Set(['Finished', 'Failed', 'Stopped', 'not_started'])

export function RunOperations({ runId, phase }: { runId: string; phase: string }) {
  const [jobs, setJobs] = useState<Jobs | null>(null)
  const [curation, setCuration] = useState<Curation>({ state: 'idle' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [curationOperation, setCurationOperation] = useState<string | null>(null)
  const refresh = useCallback(async () => {
    const [j, c] = await Promise.all([
      api.get<Jobs>(`/api/v1/runs/${runId}/jobs`),
      api.get<Curation>(`/api/v1/runs/${runId}/curation`),
    ])
    setJobs(j); setCuration(c)
  }, [runId])
  useEffect(() => {
    let mounted = true
    const load = () => { if (mounted) void refresh().catch(e => { if (mounted) setError(String(e)) }) }
    load()
    const timer = window.setInterval(load, 5000)
    return () => { mounted = false; window.clearInterval(timer) }
  }, [refresh])
  async function act(path: string, body?: object) {
    setBusy(true); setError('')
    try { await api.post(path, body); await refresh() }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  const canCurate = ['paused', 'recovering', 'finished', 'failed', 'cancelled'].includes(phase)
  return <article className="card">
    <div className="card-head"><h2>远程任务与本轮经验</h2>
      <button className="btn" disabled={busy} onClick={() => void act(`/api/v1/runs/${runId}/jobs/reconcile`)}>核对远端状态</button>
    </div>
    <div className="card-body">
      {error && <p role="alert">{error}</p>}
      <p>已占用 {jobs?.reserved_jobs ?? '—'} 个 Job；运行中或结果未知 {jobs?.active_or_unknown ?? '—'} 个。未知结果继续占用额度。</p>
      {jobs?.items.length === 0 && <p className="sub">本 Run 暂无受控 Job 记录。升级前的任务请查看历史审计记录。</p>}
      {jobs && jobs.items.length > 0 && <table><thead><tr><th>任务</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>{jobs.items.map(job => <tr key={job.operation_id}>
          <td>{job.platform_job_id ?? '远端 ID 未知'}<br /><small>{job.operation_id}</small></td>
          <td>{job.status === 'Finished' && job.retrieval_status === 'failed'
            ? <strong role="alert">完成 · 结果未取回</strong>
            : <>{job.status}{['stopping', 'stop_unknown'].includes(job.status) && '（尚未确认停止）'}</>}
            <br /><small>结果取回：{job.retrieval_status === 'retrieved' ? '已取回' : job.retrieval_status === 'failed' ? '失败' : job.retrieval_status === 'unknown' ? '未知' : '尚未尝试'}</small></td>
          <td><button className="btn danger" disabled={busy || !job.platform_job_id || terminal.has(job.status) || ['stopping', 'stop_unknown'].includes(job.status)}
            onClick={() => void act(`/api/v1/runs/${runId}/jobs/${encodeURIComponent(job.operation_id)}/stop`)}>停止此任务</button></td>
        </tr>)}</tbody></table>}
      <p className="sub">整理会调用已配置的大脑，读取本轮事件与检查点。全局经验仍需审批；推导出的经验保留 hypothesis 等级。</p>
      <button className="btn" disabled={busy || !canCurate || curation.state === 'running'} onClick={() => {
        const id = curationOperation ?? crypto.randomUUID()
        setCurationOperation(id)
        void act(`/api/v1/runs/${runId}/curation`, { operation_id: id })
      }}>{curation.state === 'running' ? '正在整理本轮经验…' : '整理本轮经验'}</button>
      {!canCurate && <span className="small-text"> 暂停后可整理</span>}
      {curation.state === 'done' && <p role="status">整理完成：保存 {curation.proposals_applied ?? 0} 条。{curation.summary}</p>}
      {curation.state === 'failed' && <p role="alert">整理失败：{curation.error}</p>}
      {['done', 'failed'].includes(curation.state) && curationOperation && <button className="btn" onClick={() => setCurationOperation(null)}>准备新一次整理</button>}
    </div>
  </article>
}
