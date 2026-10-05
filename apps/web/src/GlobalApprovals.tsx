import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Modal } from './components'
import type { ExperienceItem } from './types'
type Draft = ExperienceItem & { body_md: string }

export default function GlobalApprovals() {
  const [items, setItems] = useState<Draft[]>([])
  const [deferred, setDeferred] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const generation = useRef(0)
  const acting = useRef(false)
  const alive = useRef(true)
  async function refresh() {
    if (acting.current) return
    const request = ++generation.current
    try {
      const data = await api.get<{ items: Draft[] }>('/api/v1/experiences/pending-approvals')
      if (alive.current && request === generation.current) setItems((data.items ?? []).filter(v => v.scope === 'global' && v.status === 'candidate' && v.kind !== 'environment'))
    } catch (e) { if (alive.current && request === generation.current) setError(e instanceof Error ? e.message : '审批队列读取失败') }
  }
  useEffect(() => {
    alive.current = true; void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => { alive.current = false; ++generation.current; window.clearInterval(timer) }
  }, [])
  const current = items[0]
  async function decide(action: 'approve' | 'reject') {
    if (!current || acting.current) return
    acting.current = true; ++generation.current; setBusy(true); setError('')
    try {
      await api.post(`/api/v1/experiences/${encodeURIComponent(current.id)}/${action}`, {
        expected_revision: current.revision_id,
        ...(action === 'reject' ? { note: note.trim() || '用户在审批队列驳回此版本' } : {}),
      })
      if (alive.current) { setItems(v => v.filter(item => item.id !== current.id)); setNote('') }
    } catch (e) { if (alive.current) setError('审批未保存：' + (e instanceof Error ? e.message : String(e))) }
    finally { acting.current = false; if (alive.current) setBusy(false) }
  }
  if (!current) return error ? <p role="alert">{error}</p> : null
  if (deferred) return <button className="btn" onClick={() => setDeferred(false)}>待审批全局经验（{items.length}）</button>
  return <Modal open title={`待审批全局经验（${items.length}）`} onClose={() => setDeferred(true)}>
    <h3>{current.title}</h3><p>版本：{current.revision_id} · 证据：{current.evidence_status}</p>
    <p>适用范围：{current.applicability || '未说明'}</p>
    <p>证据引用：{current.evidence_refs?.join('，') || '无'}</p>
    <pre>{current.body_md}</pre>
    <label>驳回批注（可选）<input value={note} onChange={e => setNote(e.target.value)} /></label>
    {error && <p role="alert">{error}</p>}
    <button className="btn primary" disabled={busy} onClick={() => void decide('approve')}>批准此版本</button>
    <button className="btn" disabled={busy} onClick={() => void decide('reject')}>驳回此版本</button>
    <button className="btn" disabled={busy} onClick={() => { setError(''); void refresh() }}>重新读取</button>
    <button className="btn" disabled={busy} onClick={() => setDeferred(true)}>稍后处理</button>
  </Modal>
}
