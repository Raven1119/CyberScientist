import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { Mailbox } from './types'

export function AccountRoles() {
  const [items, setItems] = useState<Mailbox[]>([])
  const [enabled, setEnabled] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const refresh = useCallback(async () => {
    try {
      const [accounts, settings] = await Promise.all([
        api.get<{items: Mailbox[]}>('/api/v1/mailboxes'),
        api.get<{features?: Record<string, boolean>}>('/api/v1/settings'),
      ])
      setItems(accounts.items ?? [])
      setEnabled(settings.features?.auto_harvest === true)
    } catch (e) { setError(String(e)) }
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  const change = async (id: string, role: string) => {
    setBusy(true); setError('')
    try { await api.put(`/api/v1/mailboxes/${id}/role`, {role}); await refresh() }
    catch (e) { setError(String(e)) }
    finally { setBusy(false) }
  }
  const toggle = async () => {
    setBusy(true); setError('')
    try { await api.put('/api/v1/features/auto_harvest', {enabled: !enabled}); await refresh() }
    catch (e) { setError(String(e)) }
    finally { setBusy(false) }
  }
  return <article className="card" aria-label="账号角色和认领状态">
    <div className="card-head"><h2>比赛账号</h2></div>
    <div className="card-body">
      <button type="button" className="btn" aria-label="切换收割开关" disabled={busy} onClick={() => void toggle()}>
        收割{enabled ? '已开启' : '已关闭'}
      </button>
      {error && <p role="alert" className="form-error">{error}</p>}
      {items.filter(m => m.status === 'active').map(m => <div className="meta-row" key={m.id}>
        <span>{m.email} · {!m.secret_configured && <span className="form-error">凭据未配置 · </span>}<span className={m.claim_status === 'pending' ? 'form-error' : ''}>
          {m.claim_status === 'pending' ? '等待主人认领' : m.claim_status === 'confirmed' ? '已认领' : '认领状态未知'}
        </span></span>
        <select aria-label={`${m.email}账号角色`} value={m.role} disabled={busy}
          onChange={e => void change(m.id, e.target.value)}>
          <option value="experiment">实验账号</option><option value="harvest">收割账号</option>
        </select>
      </div>)}
    </div>
  </article>
}
