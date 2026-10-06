import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { useApp } from './app-context'
import { Modal } from './components'
import GlobalApprovals from './GlobalApprovals'

interface Alert { id: string; run_id: string | null; challenge_id: string | null; kind: string; title: string; payload: Record<string, unknown> }

export default function PersistentAlerts() {
  const { setPage, setCurrentChallengeId, setFocusedRunId } = useApp()
  const [items, setItems] = useState<Alert[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    const poll = async () => {
      try { const data = await api.get<{ items: Alert[] }>('/api/v1/alerts'); if (active) setItems(data.items) }
      catch { /* Connection health is shown by the application; unacknowledged alerts stay visible. */ }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])
  const current = items[0]
  const acknowledge = useCallback(async (navigate = false) => {
    if (!current || busy) return
    setBusy(true); setError('')
    try {
      await api.post(`/api/v1/alerts/${current.id}/acknowledge`, {})
      setItems(previous => previous.filter(item => item.id !== current.id))
      if (navigate && current.run_id) { setCurrentChallengeId(current.challenge_id); setFocusedRunId(current.run_id); setPage('research') }
      else if (navigate) setPage(current.kind === 'harvest.summary' ? 'competition' : 'settings')
    } catch (err) { setError('确认未保存：' + (err instanceof Error ? err.message : String(err))) }
    finally { setBusy(false) }
  }, [current, busy, setPage, setCurrentChallengeId, setFocusedRunId])
  if (!current) return <GlobalApprovals />
  return <Modal open title={current.title} onClose={() => void acknowledge()}>
    {current.run_id && <p>Run：{current.run_id}</p>}
    {current.kind === 'harvest.summary' && <>
      <p>赛道：{String(current.payload.track ?? current.payload.round_id)}</p>
      <table><thead><tr><th>题目</th><th>主邮箱成绩</th><th>最好实验成绩</th><th>等待出分</th><th>成绩状态</th></tr></thead><tbody>
        {(current.payload.topics as { challenge_id: string; main_best: number | null; experiment_best: number | null; pending_submission_ids: string[]; no_confirmed_score: boolean }[] ?? []).map(topic =>
          <tr key={topic.challenge_id}><td>{topic.challenge_id}</td><td>{topic.main_best ?? 'unknown'}</td><td>{topic.experiment_best ?? 'unknown'}</td><td>{topic.pending_submission_ids.join(', ') || '无'}</td><td>{topic.no_confirmed_score ? '无任何确认成绩' : '已有确认成绩'}</td></tr>)}
      </tbody></table>
    </>}
    {current.kind === 'platform.protocol_changed' && <>
      <p>协议变化已提供给所有 PI；需核对适配器兼容性。</p>
      <pre>{JSON.stringify(current.payload.changes, null, 2)}</pre>
    </>}
    {Boolean(current.payload.error || current.payload.reason) && <p>{String(current.payload.error || current.payload.reason)}</p>}
    {current.payload.confirmed_score != null && <p>已确认平台成绩：{String(current.payload.confirmed_score)}</p>}
    {current.payload.science_score != null && <p>本地正式科学分：{String(current.payload.science_score)}</p>}
    {current.payload.remaining_seconds != null && <p>剩余授权时间：{Math.max(0, Math.ceil(Number(current.payload.remaining_seconds) / 60))} 分钟</p>}
    {current.payload.retry_at != null && <p>下次重试时间：{String(current.payload.retry_at)}</p>}
    {error && <p role="alert">{error}</p>}
    <button type="button" className="btn" disabled={busy} onClick={() => void acknowledge()}>已知悉</button>
    <button type="button" className="btn primary" disabled={busy} onClick={() => void acknowledge(true)}>{current.run_id ? '查看研究' : current.kind === 'harvest.summary' ? '查看比赛' : '查看设置'}</button>
    <p>未确认的提醒在刷新和后端重启后继续保留。</p>
  </Modal>
}
