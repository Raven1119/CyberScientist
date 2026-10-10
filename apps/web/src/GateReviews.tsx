import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { useLatestRequest } from './useLatestRequest'

type Gate = { id: string; run_id: string | null; rule: string; source: string; line: number | null; context: string; risk: string; exact_stored: number }
export default function GateReviews() {
  const [items, setItems] = useState<Gate[]>([])
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const beginRead = useLatestRequest()
  const reload = useCallback(async () => { const current = beginRead(); const result = await api.get<{ items: Gate[] }>('/api/v1/ops/gates'); if (current()) setItems(result.items ?? []) }, [beginRead])
  useEffect(() => { const refresh = () => void reload().catch(() => {}); refresh(); const timer = window.setInterval(refresh, 5000); return () => window.clearInterval(timer) }, [reload])
  async function resolve(item: Gate) {
    setBusy(item.id); setError('')
    try { await api.post(`/api/v1/ops/gates/${item.id}/resolve`, { false_positive: checked[item.id] === true, reason: reasons[item.id] }); await reload() }
    catch (err) { setError(String(err)) } finally { setBusy('') }
  }
  return <article className="card card-body"><h2>拦截复核</h2>
    <p>放行仅对该项及原内容有效；原记录保留，原提交流程自动续接并通知 PI。</p>
    {error && <p role="alert">{error}</p>}
    {!items.length && <p>没有待复核项</p>}
    {items.map(item => <section key={item.id} aria-label={item.id}>
      <h3>{item.rule} · {item.risk}</h3><p>{item.run_id ?? '无 Run'} · {item.source}{item.line != null ? `:${item.line}` : ''}</p><pre>{item.context}</pre>
      {item.exact_stored ? <p>已存凭据原文命中，禁止放行</p> : <>
        <label><input type="checkbox" checked={checked[item.id] ?? false} onChange={e => setChecked(prev => ({ ...prev, [item.id]: e.target.checked }))} />此项是误报</label>
        <label>复核理由<textarea aria-label={`复核理由 ${item.id}`} value={reasons[item.id] ?? ''} onChange={e => setReasons(prev => ({ ...prev, [item.id]: e.target.value }))} /></label>
        <button className="btn" disabled={Boolean(busy) || !checked[item.id] || !reasons[item.id]?.trim()} onClick={() => void resolve(item)}>放行并续接</button>
      </>}
    </section>)}
  </article>
}
