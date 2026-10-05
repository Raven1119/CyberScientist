import { useState } from 'react'
import { api } from '../api'

export function RunContinuation({ runId, phase, refresh, toast }: {
  runId: string; phase: string; refresh: () => void; toast: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)
  async function resume() {
    setBusy(true)
    try {
      await api.post(`/api/v1/runs/${runId}/control`, { action: 'reopen', text: '用户从前端续跑原Run', operation_id: crypto.randomUUID() })
      await api.post(`/api/v1/runs/${runId}/control`, { action: 'resume', operation_id: crypto.randomUUID() })
      toast('已在原工作区和事件流续跑，保留原授权。'); refresh()
    } catch (err) { toast('续跑失败：' + String(err)); refresh() } finally { setBusy(false) }
  }
  return phase === 'finished'
    ? <button type="button" className="btn" disabled={busy} onClick={() => void resume()}>续跑原 Run</button>
    : phase === 'waiting_score' ? <span>等待评分 · 原生会话收尾后不消耗 token，活动时钟暂停</span> : null
}
