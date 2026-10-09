import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { Mailbox } from './types'

export function AccountRoles() {
  const [items, setItems] = useState<Mailbox[]>([])
  const [enabled, setEnabled] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [cliNotice, setCliNotice] = useState('')
  const [agentToken, setAgentToken] = useState('')
  const [bindingNotice, setBindingNotice] = useState('')
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
  const bindAgent = async () => {
    setBusy(true); setError(''); setBindingNotice('')
    try {
      const result = await api.post<Mailbox>('/api/v1/mailboxes/agent-token', {token: agentToken})
      setBindingNotice(`${result.email} 身份已核验并绑定`)
      await refresh()
    } catch (e) { setError(String(e)) }
    finally { setAgentToken(''); setBusy(false) }
  }
  return <article className="card" aria-label="账号角色和认领状态">
    <div className="card-head"><h2>比赛账号</h2></div>
    <div className="card-body">
      <label htmlFor="agent-token">已认领Agent的令牌</label>
      <input id="agent-token" type="password" autoComplete="off" value={agentToken}
        onChange={e => setAgentToken(e.target.value)} />
      <button type="button" className="btn" disabled={busy || !agentToken.trim()}
        onClick={() => void bindAgent()}>核验并绑定Agent</button>
      {bindingNotice && <p role="status">{bindingNotice}</p>}
      <button type="button" className="btn" aria-label="切换收割开关" disabled={busy} onClick={() => void toggle()}>
        收割{enabled ? '已开启' : '已关闭'}
      </button>
      <button type="button" className="btn" aria-label="检查官方CLI更新" onClick={() => {
        void api.get<{version: string; latest?: string; update_available?: boolean}>('/api/v1/ops/official-cli')
          .then(r => setCliNotice(r.update_available ? `官方CLI有新版本 ${r.latest}，当前 ${r.version}；需人工升级` : `当前官方CLI ${r.version}；${r.latest ? '无更新' : '最新版本未知'}`))
          .catch(e => setError(String(e)))
      }}>检查官方CLI更新</button>
      {cliNotice && <p role="status">{cliNotice}</p>}
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
