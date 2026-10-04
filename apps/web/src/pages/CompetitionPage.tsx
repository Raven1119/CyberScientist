import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../app-context'

type Choice = { runtime: string; model_id: string; reasoning_effort: string }
type Template = { model_config: { brain: Choice; executor: Choice }; authorization: {
  allow_model_calls: boolean; max_run_minutes: number; max_jobs: number; max_submissions: number;
  max_sandboxes: number; max_sandbox_minutes: number; allow_data_download: boolean }; solver_note: string }
type Item = { id: string; challenge_id: string; title: string; phase: string; priority: number;
  paused: number; run_id: string | null; local_best: number | null; platform_best: { score: number; score_confidence: string } | null;
  triage: { difficulty: string; estimated_minutes: number | null; estimated_cost_cny: number | null; recommended_model: string; reason: string } | null;
  trace_diagnostic: unknown; usage: unknown[]; cost: unknown; next_action: string | null }
type Round = { id: string; label: string; status: string; items: Item[]; resources: { sessions: { provider: string; used: number }[]; rate_limits: unknown[] } }
const choice = (model: string): Choice => ({ runtime: 'codex', model_id: model, reasoning_effort: 'xhigh' })

export default function CompetitionPage() {
  const { toast, demoMode } = useApp()
  const [rounds, setRounds] = useState<{ id: string; label: string; status: string }[]>([])
  const [id, setId] = useState('')
  const [round, setRound] = useState<Round | null>(null)
  const [ids, setIds] = useState('')
  const [season, setSeason] = useState('')
  const [seq, setSeq] = useState(1)
  const [busy, setBusy] = useState(false)
  const [shutdown, setShutdown] = useState<{ can_shutdown: boolean; message: string; remote_jobs: unknown[]; remote_sandboxes: unknown[] } | null>(null)
  const [overrides, setOverrides] = useState<Record<string, Template>>({})
  const [template, setTemplate] = useState<Template>({ model_config: { brain: choice('gpt-6.1-sol'), executor: choice('gpt-6.1-sol') },
    authorization: { allow_model_calls: true, max_run_minutes: 60, max_jobs: 2, max_submissions: 0,
      max_sandboxes: 2, max_sandbox_minutes: 60, allow_data_download: true }, solver_note: '' })
  useEffect(() => {
    let active = true
    const refresh = async () => {
      try {
        const list = await api.get<{ items: typeof rounds }>('/api/v1/rounds')
        if (!active) return
        setRounds(list.items)
        const selected = id || list.items[0]?.id
        if (selected) {
          const value = await api.get<Round>(`/api/v1/rounds/${encodeURIComponent(selected)}`)
          if (active) { setId(selected); setRound(value) }
        }
      } catch (e) { if (active) toast(e instanceof Error ? e.message : '轮次读取失败') }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 10000)
    return () => { active = false; window.clearInterval(timer) }
  }, [id, toast])
  async function action(path: string, body: unknown, method: 'post' | 'put' = 'post') {
    setBusy(true)
    try { const value = await api[method]<Round>(path, body); setRound(value); setId(value.id) }
    catch (e) { toast(e instanceof Error ? e.message : '操作失败') }
    finally { setBusy(false) }
  }
  const url = `/api/v1/rounds/${encodeURIComponent(id)}`
  return <section><div className="page-head"><h1>比赛轮次</h1></div>
    <button className="btn" disabled={busy} onClick={async () => {
      setBusy(true)
      try { setShutdown(await api.post('/api/v1/system/safe-shutdown', {})) }
      catch (e) { toast(e instanceof Error ? e.message : '安全暂停失败') }
      finally { setBusy(false) }
    }}>安全关机</button>
    {shutdown && <div role="status"><strong>{shutdown.message}</strong><p>远程任务继续运行和计费。</p>
      <pre>{JSON.stringify({ jobs: shutdown.remote_jobs, sandboxes: shutdown.remote_sandboxes }, null, 2)}</pre></div>}
    <p>导入整轮，查看分诊，确认模型与有界授权后自动排队。默认同时最多 6 个 Run、每个提供方 10 个会话；连接设置可调整。未确认的分数显示 unknown。</p>
    <div className="form-grid">
      <label>赛季 slug<input value={season} onChange={e => setSeason(e.target.value)} /></label>
      <label>轮次<input type="number" min="1" value={seq} onChange={e => setSeq(Number(e.target.value))} /></label>
      <label>或题目 ID 列表<textarea value={ids} onChange={e => setIds(e.target.value)} placeholder="每行一个题目 ID" /></label>
    </div>
    <button className="btn" disabled={busy || (!ids.trim() && !season.trim())} onClick={() => void action('/api/v1/rounds/import', {
      challenge_ids: ids.trim() ? ids.trim().split(/[\s,]+/) : null, season, round_seq: season ? seq : null, mode: demoMode ? 'demo' : 'connected' })}>导入整轮</button>
    <label>选择轮次<select value={id} onChange={e => setId(e.target.value)}><option value="">暂无轮次</option>
      {rounds.map(r => <option key={r.id} value={r.id}>{r.label || r.id} · {r.status}</option>)}</select></label>
    <fieldset><legend>整轮模板与授权</legend>
      {(['brain', 'executor'] as const).map(role => <label key={role}>{role === 'brain' ? 'PI 模型' : '求解者模型'}
        <input value={template.model_config[role].model_id} onChange={e => setTemplate(t => ({ ...t, model_config: { ...t.model_config,
          [role]: { ...t.model_config[role], model_id: e.target.value } } }))} /></label>)}
      {([['max_run_minutes', '每 Run 分钟'], ['max_jobs', '每 Run Job 数'], ['max_submissions', '每 Run 实验提交数'],
        ['max_sandboxes', '每 Run 沙箱并发'], ['max_sandbox_minutes', '每 Run 沙箱累计分钟']] as const).map(([key, title]) =>
        <label key={key}>{title}<input type="number" min="0" value={template.authorization[key]} onChange={e => setTemplate(t => ({ ...t,
          authorization: { ...t.authorization, [key]: Number(e.target.value) } }))} /></label>)}
      <label>给 PI 的求解者备注<input value={template.solver_note} onChange={e => setTemplate(t => ({ ...t, solver_note: e.target.value }))} /></label>
    </fieldset>
    {round && <><p>轮次 {round.id} · {round.status}</p>
      <p>提供方会话 {round.resources.sessions.map(s => `${s.provider}: ${s.used}`).join('，') || '0'} · 限流等待 {round.resources.rate_limits.length}</p>
      <button className="btn" disabled={busy || round.status !== 'draft'} onClick={() => void action(`${url}/triage`, { allow_model_calls: true })}>授权一次题目分诊</button>
      <button className="btn primary" disabled={busy || round.status !== 'draft'} onClick={() => void action(`${url}/confirm`, {
        template, overrides })}>确认模板与授权，开始排队</button>
      <div className="evaluation-table-wrap"><table><thead><tr><th>题目与分诊</th><th>Run</th><th>本地最好分</th><th>平台最好分</th><th>轨迹诊断</th><th>token / 金额</th><th>状态与下一步</th><th>操作</th></tr></thead>
        <tbody>{round.items.map(item => <tr key={item.id}>
          <td>{item.title}{item.triage && <p>{item.triage.difficulty} · {item.triage.recommended_model}<br />预计 {item.triage.estimated_minutes ?? 'unknown'} 分钟 / {item.triage.estimated_cost_cny ?? 'unknown'} 元<br />{item.triage.reason}</p>}
            {round.status === 'draft' && <label>此题求解者模型<input aria-label={`${item.title}求解者模型`}
              value={overrides[item.challenge_id]?.model_config.executor.model_id ?? template.model_config.executor.model_id}
              onChange={e => setOverrides(v => { const current = v[item.challenge_id] ?? template; return { ...v,
                [item.challenge_id]: { ...current, model_config: { ...current.model_config,
                  executor: { ...current.model_config.executor, model_id: e.target.value } } } } })} /></label>}
            {round.status === 'draft' && <details><summary>此题授权</summary>
              {([['max_run_minutes', '分钟'], ['max_jobs', 'Job 数'], ['max_submissions', '实验提交数'],
                ['max_sandboxes', '沙箱并发'], ['max_sandbox_minutes', '沙箱累计分钟']] as const).map(([key, title]) =>
                <label key={key}>{title}<input type="number" min="0" value={(overrides[item.challenge_id] ?? template).authorization[key]}
                  onChange={e => setOverrides(v => { const current = v[item.challenge_id] ?? template; return { ...v,
                    [item.challenge_id]: { ...current, authorization: { ...current.authorization, [key]: Number(e.target.value) } } } })} /></label>)}
            </details>}</td>
          <td>{item.run_id || '排队中'}</td><td>{item.local_best ?? 'unknown'}</td>
          <td>{item.platform_best ? `${item.platform_best.score} (${item.platform_best.score_confidence})` : 'unknown'}</td>
          <td>{item.trace_diagnostic ? <details><summary>查看诊断</summary><pre>{JSON.stringify(item.trace_diagnostic, null, 2)}</pre></details> : 'unknown'}</td>
          <td><details><summary>用量与费用</summary><pre>{JSON.stringify({ tokens: item.usage, cost: item.cost }, null, 2)}</pre></details></td>
          <td>{item.phase}<p>{item.next_action}</p></td>
          <td><label>优先级<input aria-label={`${item.title}优先级`} type="number" value={item.priority}
            onChange={e => void action(`${url}/items/${item.id}`, { priority: Number(e.target.value) }, 'put')} /></label>
            <button className="btn small" disabled={busy} onClick={() => void action(`${url}/items/${item.id}`, { paused: !item.paused }, 'put')}>{item.paused ? '继续排队' : '暂停此项'}</button>
            <button className="btn small" disabled={busy || round.status === 'draft'} onClick={() => void action(`${url}/runs`, { challenge_id: item.challenge_id, template })}>按当前模板追加 Run</button></td>
        </tr>)}</tbody></table></div>
    </>}
  </section>
}
