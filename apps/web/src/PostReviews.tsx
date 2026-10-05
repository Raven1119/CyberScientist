import { useEffect, useState } from 'react'
import { api } from './api'

interface Version { id: string; version: number; status: string; calls_used: number; native_call_limit: number; error?: string; report_md?: string }
interface Reviews { status: string; error?: string; report_md?: string; versions: Version[] }

export default function PostReviews({ runId, phase }: { runId: string; phase: string }) {
  const key = `post-review-operation:${runId}`
  const [pending, setPending] = useState(() => sessionStorage.getItem(key))
  const [reviews, setReviews] = useState<Reviews | null>(null)
  const [reason, setReason] = useState('')
  const [authorized, setAuthorized] = useState(false)
  const [rewrites, setRewrites] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const terminal = ['finished', 'failed', 'cancelled'].includes(phase)
  async function load() {
    try {
      const data = await api.get<Reviews>(`/api/v1/runs/${runId}/post-review`)
      setReviews(data)
      const operation = sessionStorage.getItem(key)
      if (operation && data.versions.some(version => version.id === operation)) {
        sessionStorage.removeItem(key); setPending(null); setAuthorized(false); setError('')
      } else { setError(operation ? '原授权尚未确认；保留操作标识，请继续核对，不发起另一复盘。' : '') }
    }
    catch (problem) { setError(String(problem)) }
  }
  useEffect(() => { if (sessionStorage.getItem(key)) void load() }, [key])
  async function repeat() {
    if (pending || busy) return
    setBusy(true); setError('')
    let operation = sessionStorage.getItem(key)
    if (!operation) { operation = crypto.randomUUID(); sessionStorage.setItem(key, operation) }
    setPending(operation)
    try {
      await api.post(`/api/v1/runs/${runId}/post-review`, { operation_id: operation, reason: reason.trim(),
        allow_model_calls: true, max_format_rewrites: rewrites ? 2 : 0 })
      sessionStorage.removeItem(key); setPending(null); setAuthorized(false); await load()
    } catch (problem) { setError(`请求未确认，保留操作标识供核对或同请求重试：${String(problem)}`) }
    finally { setBusy(false) }
  }
  return <article className="card card-body"><h2>完整复盘</h2>
    <button type="button" disabled={busy} onClick={() => void load()}>查看复盘及历史版本</button>
    {reviews && <><p>原复盘：{reviews.status} {reviews.error}</p>
      {reviews.report_md && <details><summary>原复盘报告</summary><pre>{reviews.report_md}</pre></details>}
      {reviews.versions.map(version => <details key={version.id}><summary>版本 {version.version} · {version.status} · 模型调用 {version.calls_used}/{version.native_call_limit}</summary>
        {version.error && <p>{version.error}</p>}<pre>{version.report_md ?? '尚无报告'}</pre>
      </details>)}</>}
    {pending && <p role="status">未确认授权 {pending}；请点击查看复盘及历史版本核对。</p>}
    {terminal ? <fieldset disabled={busy || !!pending}><legend>重新做完整复盘</legend>
      <p>新增版本保留原报告和原 Run 授权。只分析已结束的研究记录。</p>
      <label>复盘原因<input maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <label><input type="checkbox" checked={rewrites} onChange={event => setRewrites(event.target.checked)} />允许最多两次同会话格式纠正</label>
      <label><input type="checkbox" checked={authorized} onChange={event => setAuthorized(event.target.checked)} />授权本次复盘模型调用（最多 {rewrites ? 3 : 1} 次）</label>
      <button type="button" disabled={!authorized || !reason.trim()} onClick={() => void repeat()}>创建复盘版本</button>
    </fieldset> : <p>暂停、恢复和等待评分不触发复盘；研究真正结束后才可重新复盘。</p>}
    {error && <p role="alert">{error}</p>}
  </article>
}
