import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../app-context'

type Item = { id: string; suite: string; label: string; status: string; created_at: string }
type Result = { id: string; challenge_id: string; repeat_index: number; run_id: string | null;
  status: string; error: string | null; result: null | { science_score: number | null;
    trace_checklist_score: number | null; trace_qualified_cap: number | null;
    display_interval: { lower: number | null; upper: number | null }; wall_seconds: number | null;
    job_count?: number; job_unknown_count?: number; sandbox_minutes?: number;
    sandbox_minutes_status?: string; bohrium_amount: string; final_status: string;
    bohrium_cost_details?: { job_native_amount_total: string | null; currency: string | null;
      total_amount: string | null } } }
type Detail = { id: string; suite: string; status: string; results: Result[] }

export default function EvaluationPage() {
  const { toast, demoMode } = useApp()
  const [items, setItems] = useState<Item[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    async function refresh() {
      try {
        const listed = await api.get<{ items: Item[] }>('/api/v1/evals')
        if (!active) return
        setItems(listed.items)
        const id = selected || listed.items[0]?.id
        if (id) {
          const current = await api.get<Detail>(`/api/v1/evals/${encodeURIComponent(id)}`)
          if (active) { setSelected(id); setDetail(current) }
        }
      } catch (error) {
        if (active) toast(error instanceof Error ? error.message : '评测状态读取失败')
      }
    }
    void refresh()
    const timer = window.setInterval(() => { void refresh() }, 10000)
    return () => { active = false; window.clearInterval(timer) }
  }, [selected, toast])

  async function start(suite: 'fast' | 'hard') {
    setBusy(true)
    try {
      const created = await api.post<Detail>('/api/v1/evals', { suite, repeats: 2, label: '' })
      setSelected(created.id)
      setDetail(created)
      toast(`评测 ${created.id} 已启动`)
    } catch (error) {
      toast(error instanceof Error ? error.message : '评测启动失败')
    } finally { setBusy(false) }
  }

  return <section className="evaluation-page">
    <div className="page-head"><div><p className="eyebrow">LOCAL EVALUATION</p><h1>评测</h1></div></div>
    <p>每题运行 2 次真实研究 Run。只做本地科学评分与公开 v6 轨迹检查表诊断，不提交比赛 Attempt。v6 与历史 v8 只在可见代码上做过条件比较；金额无法读取时显示 unknown。</p>
    <p>快速层每个 Run 最多 60 分钟、2 个 Job、60 沙箱分钟；困难层最多 180 分钟、5 个 Job、180 沙箱分钟。仅 CPU。</p>
    <div className="actions">
      <button type="button" className="btn" disabled={busy || demoMode} onClick={() => void start('fast')}>运行快速层</button>
      <button type="button" className="btn" disabled={busy || demoMode} onClick={() => void start('hard')}>运行困难层</button>
    </div>
    <label>选择评测 <select aria-label="选择评测" value={selected || ''} onChange={(e) => setSelected(e.target.value)}>
      <option value="">暂无评测</option>
      {items.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.suite} · {item.status}</option>)}
    </select></label>
    {detail && <>
      <p>评测 {detail.id} · {detail.status} · 完成 {detail.results.filter((item) => item.status === 'complete').length}/{detail.results.length}</p>
      <div className="evaluation-table-wrap"><table><thead><tr><th>题目</th><th>重复</th><th>Run</th><th>科学分</th><th>轨迹 C</th><th>达标上限</th><th>展示分区间</th><th>耗时</th><th>Job</th><th>沙箱分钟</th><th>金额</th><th>状态</th></tr></thead>
        <tbody>{detail.results.map((item) => <tr key={item.id}>
          <td>{item.challenge_id}</td><td>{item.repeat_index}</td><td>{item.run_id || '—'}</td>
          <td>{item.result?.science_score ?? 'unknown'}</td><td>{item.result?.trace_checklist_score ?? 'unknown'}</td>
          <td>{item.result?.trace_qualified_cap ?? '—'}</td>
          <td>{item.result ? `[${item.result.display_interval.lower ?? '?'}, ${item.result.display_interval.upper ?? '?'}]` : '—'}</td>
          <td>{item.result?.wall_seconds ?? '—'}</td>
          <td>{item.result?.job_count ?? '—'}{item.result?.job_unknown_count ? ` (+${item.result.job_unknown_count} unknown)` : ''}</td>
          <td title={item.result?.sandbox_minutes_status || undefined}>{item.result?.sandbox_minutes ?? '—'}</td>
          <td>{item.result?.bohrium_amount ?? 'unknown'}
            {item.result?.bohrium_cost_details?.job_native_amount_total != null &&
              <small> Job 原始金额 {item.result.bohrium_cost_details.job_native_amount_total}（币种未确认，非总费用）</small>}
          </td>
          <td title={item.error || undefined}>{item.status}</td>
        </tr>)}</tbody></table></div>
      <a href={`/api/v1/evals/${encodeURIComponent(detail.id)}/report`} target="_blank" rel="noreferrer">查看 JSON 报告 ↗</a>
    </>}
  </section>
}
