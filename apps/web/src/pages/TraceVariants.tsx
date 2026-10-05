import { useState } from 'react'
import { api } from '../api'
import type { Submission } from '../types'

export function TraceVariants({ runId, items, refresh }: { runId: string; items: Submission[]; refresh: () => Promise<void> }) {
  const storageKey = `cs-trace-variant:${runId}`
  const saved = (() => { try { return JSON.parse(sessionStorage.getItem(storageKey) ?? 'null') as { source: string; id: string } | null } catch { return null } })()
  const [source, setSource] = useState(saved?.source ?? '')
  const [prediction, setPrediction] = useState('')
  const [narrative, setNarrative] = useState('')
  const [writtenAt, setWrittenAt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [operation, setOperation] = useState<string | null>(saved?.id ?? null)
  const eligible = items.filter(s => !s.is_harvest && s.score_confidence === 'confirmed' && s.score_status === 'scored')
  async function submit() {
    setBusy(true); setError('')
    const id = operation ?? crypto.randomUUID(); setOperation(id)
    sessionStorage.setItem(storageKey, JSON.stringify({ source, id }))
    try {
      const result = await api.post<{ status: string }>(`/api/v1/submissions/${source}/trace-variants`, {
        operation_id: id, prediction_md: prediction.trim(),
        narrative_jsonl: narrative.trim() || undefined, narrative_written_at: writtenAt.trim() || undefined, projection_only: !narrative.trim(),
      })
      if (result.status !== 'submitted') {
        setError(`提交状态 ${result.status}，尚未确认`); await refresh(); return
      }
      await refresh(); setOperation(null); sessionStorage.removeItem(storageKey); setPrediction(''); setNarrative('')
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  return <section aria-label="轨迹变体">
    <h3>轨迹变体</h3>
    <p>科学产物保持冻结，消耗本 Run 的提交额度。预测必填；留空叙述使用原事件的系统投影。</p>
    {error && <p role="alert">{error}。保留操作标识；未知结果先核对，修改意图请准备新操作。</p>}
    <label>原提交<select value={source} disabled={busy} onChange={e => { setSource(e.target.value); setOperation(null); sessionStorage.removeItem(storageKey) }}>
      <option value="">选择已确认评分的提交</option>
      {eligible.map(s => <option key={s.id} value={s.id}>{s.id} · {s.score ?? '未知'}</option>)}
    </select></label>
    <label>变体预测<textarea value={prediction} maxLength={4000} disabled={busy} onChange={e => setPrediction(e.target.value)} /></label>
    <label>新叙述 JSONL<textarea value={narrative} disabled={busy} onChange={e => setNarrative(e.target.value)} /></label>
    <label>叙述写作时间<input value={writtenAt} disabled={busy} placeholder="有事后注释时填写实际 ISO 时间" onChange={e => setWrittenAt(e.target.value)} /></label>
    <button className="btn" disabled={busy || !source || !prediction.trim()} onClick={() => void submit()}>提交轨迹变体</button>
    {operation && <button className="btn" disabled={busy} onClick={() => { setOperation(null); sessionStorage.removeItem(storageKey) }}>准备新操作</button>}
    <table aria-label="原提交与变体对比"><thead><tr><th>原提交 / 分数 / 预测</th><th>变体 / 分数 / 预测</th><th>科学产物</th></tr></thead>
      <tbody>{items.filter(s => s.variant_of).map(s => {
        const base = items.find(b => b.id === s.variant_of)
        const score = (row?: Submission) => row?.score_status === 'scored'
          ? `${row.score ?? '未知'} · ${row.score_confidence === 'confirmed' ? '已确认' : '暂定'}${row.score_anomaly ? ` · 异常 ${row.score_anomaly}` : ''}${row.scorecard_consistent === 0 ? ' · 分项不一致' : ''}` : '等待评分'
        return <tr key={s.id}><td>{s.variant_of} · {score(base)}<br />{base?.prediction_md}</td>
          <td>{s.id} · {score(s)}<br />{s.prediction_md}</td>
          <td>{s.science_artifact_match === 1 ? '哈希一致' : '尚未确认'}</td></tr>
      })}</tbody></table>
  </section>
}
