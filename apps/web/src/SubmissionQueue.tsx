import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { useLatestRequest } from './useLatestRequest'

type Item = { submission_id: string; challenge_id: string; mailbox_id: string; is_harvest: number; not_before: string; reason: string }
export default function SubmissionQueue() {
  const [items, setItems] = useState<Item[]>([])
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const beginRead = useLatestRequest()
  const reload = useCallback(async () => {
    const current = beginRead()
    const [queue, switches] = await Promise.all([
      api.get<{ items: Item[]; paused: boolean }>('/api/v1/submission_queue'),
      api.get<{ features: Record<string, boolean> }>('/api/v1/features'),
    ])
    if (current()) {
      if (typeof queue.paused !== 'boolean' || typeof switches.features?.auto_submission !== 'boolean') throw new Error('自动提交状态未确认')
      setItems(queue.items ?? []); setEnabled(!queue.paused && switches.features.auto_submission)
    }
  }, [beginRead])
  useEffect(() => { let active = true; const refresh = () => { if (active) void reload().catch(() => {}) }; refresh(); const timer = window.setInterval(refresh, 5000); return () => { active = false; window.clearInterval(timer) } }, [reload])
  async function toggle() {
    setBusy(true); setError('')
    try { await api.put('/api/v1/features/auto_submission', { enabled: !enabled }); await reload() }
    catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  return <article className="card card-body"><h2>提交排队与保护</h2>
    <p>{enabled === null ? '自动提交状态未确认，正在读取' : enabled ? '自动提交已启用' : '自动提交已暂停；科研继续'}</p>
    <button className="btn" disabled={busy || enabled === null} onClick={() => void toggle()}>{enabled === null ? '等待提交状态' : enabled ? '暂停自动提交' : '恢复自动提交'}</button>
    {error && <p role="alert">{error}</p>}
    {items.length ? <table><thead><tr><th>题目</th><th>账号</th><th>类型</th><th>预计时间</th><th>原因</th></tr></thead><tbody>{items.map(item => <tr key={item.submission_id}><td>{item.challenge_id}</td><td>{item.mailbox_id}</td><td>{item.is_harvest ? '收割' : '实验'}</td><td>{item.not_before}</td><td>{item.reason}</td></tr>)}</tbody></table> : <p>没有排队中的提交</p>}
  </article>
}
