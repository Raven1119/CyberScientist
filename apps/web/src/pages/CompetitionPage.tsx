import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../app-context'
import type { SolverEntry } from '../types'

type Choice = { provider?: string; note?: string; runtime: string; model_id: string; reasoning_effort: string }
type Template = { pi_notes?: string; data_status?: string; solver_id?: string | null; model_config: { brain: Choice; executor: Choice }; authorization: {
  unlimited_resources?: boolean; allow_model_calls: boolean; max_run_minutes: number; max_jobs: number; max_submissions: number;
  max_sandboxes: number; max_environment_saves: number; max_sandbox_minutes: number; allow_data_download: boolean }; solver_note: string }
type Item = { id: string; challenge_id: string; title: string; phase: string; priority: number;
  paused: number; run_id: string | null; local_best: number | null; platform_best: { score: number; score_confidence: string } | null;
  triage: { difficulty: string; estimated_minutes: number | null; estimated_cost_cny: number | null; recommended_model: string; reason: string } | null;
  leaderboard_best?: number | null; our_best?: number | null; score_gap?: number | null;
  triage_attempts?: { id: string; helper_effort: string; status: string }[];
  user_triage?: { platform_challenge_id: string; solver_entry: SolverEntry; pi_notes: string; data_status: string } | null;
  model_cost?: unknown; trace_diagnostic: unknown; usage: unknown[]; cost: unknown; next_action: string | null }
type Round = { id: string; label: string; status: string; items: Item[]; resources: { sessions: { provider: string; used: number }[]; rate_limits: unknown[]; provider_backoff?: unknown[]; native_throttle?: unknown[] } }
const choice = (model: string): Choice => ({ runtime: 'codex', model_id: model, reasoning_effort: 'xhigh' })
function ModelFields({ label, role, value, onChange }: { label: string; role: 'brain' | 'executor'; value: Choice; onChange: (value: Choice) => void }) {
  if (role === 'brain') return <div className="form-grid">
    <label>{label}提供方<select value="codex" disabled><option value="codex">Codex</option></select></label>
    <label>{label}模型<input value="gpt-6-astra" readOnly /></label>
    <label>{label}思考强度<select value="xhigh" disabled><option>xhigh</option></select></label>
  </div>
  return <div className="form-grid">
    <label>{label}提供方<select value={value.provider ?? value.runtime} onChange={e => onChange({ ...value, provider: e.target.value, runtime: e.target.value === 'deepseek' ? 'codex' : e.target.value, model_id: e.target.value === 'deepseek' ? 'deepseek-flash' : value.model_id, reasoning_effort: 'high' })}>
      <option value="codex">Codex</option><option value="deepseek">DeepSeek</option><option value="kimi">Kimi Code</option>{role === 'executor' && <option value="prime">Prime Agent</option>}
    </select></label>
    <label>{label}模型<input value={value.model_id} onChange={e => onChange({ ...value, model_id: e.target.value })} /></label>
    <label>{label}思考强度<select value={value.reasoning_effort} onChange={e => onChange({ ...value, reasoning_effort: e.target.value })}>
      {(value.provider === 'deepseek' ? ['low', 'high', 'max'] : ['low', 'medium', 'high', 'xhigh', 'max']).map(e => <option key={e}>{e}</option>)}
    </select></label>
  </div>
}

export default function CompetitionPage() {
  const { toast, demoMode } = useApp()
  const [roster, setRoster] = useState<SolverEntry[]>([])
  const [rounds, setRounds] = useState<{ id: string; label: string; status: string }[]>([])
  const [id, setId] = useState('')
  const [round, setRound] = useState<Round | null>(null)
  const [ids, setIds] = useState('')
  const [triageInput, setTriageInput] = useState('')
  const [season, setSeason] = useState('')
  const [seq, setSeq] = useState(1)
  const [busy, setBusy] = useState(false)
  const [shutdown, setShutdown] = useState<{ can_shutdown: boolean; message: string; remote_jobs: unknown[]; remote_sandboxes: unknown[] } | null>(null)
  const [overrides, setOverrides] = useState<Record<string, Template>>({})
  const [template, setTemplate] = useState<Template>({ model_config: { brain: choice('gpt-6-astra'), executor: choice('gpt-6.1-sol') },
    authorization: { unlimited_resources: true, allow_model_calls: true, max_run_minutes: 60, max_jobs: 2, max_submissions: 0,
      max_sandboxes: 2, max_environment_saves: 0, max_sandbox_minutes: 60, allow_data_download: true }, solver_note: '' })
  useEffect(() => {
    let active = true
    void api.get<{ brain: Choice; executor: Choice; solver_roster?: SolverEntry[] }>('/api/v1/settings').then(settings => {
      if (active) setRoster(settings.solver_roster ?? [])
      if (active && settings.brain && settings.executor) setTemplate(t => ({ ...t, model_config: { brain: choice('gpt-6-astra'), executor: settings.executor } }))
    }).catch(() => {})
    return () => { active = false }
  }, [])
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
  useEffect(() => { setOverrides({}) }, [id])
  async function action(path: string, body: unknown, method: 'post' | 'put' = 'post') {
    setBusy(true)
    try { const value = await api[method]<Round>(path, body); setRound(value); setId(value.id); if (path.endsWith('/triage-import')) setOverrides(previous => { const next = { ...previous }; const imported = new Set(((body as { items: { platform_challenge_id: string }[] }).items).map(item => item.platform_challenge_id)); for (const item of value.items) if (item.user_triage && imported.has(item.user_triage.platform_challenge_id)) delete next[item.challenge_id]; return next }) }
    catch (e) { toast(e instanceof Error ? e.message : '操作失败') }
    finally { setBusy(false) }
  }
  const solverSelect = (label: string, current: Template, change: (value: Template) => void) => <label>{label}求解者条目<select value={current.solver_id ?? ''} onChange={e => {
    const entry = roster.find(v => v.id === e.target.value)
    change({ ...current, solver_id: e.target.value || null, solver_note: entry?.note ?? current.solver_note,
      model_config: { ...current.model_config, executor: entry ?? current.model_config.executor } })
  }}><option value="">手动模型配置</option>{roster.map(v => <option key={v.id} value={v.id}>{v.name} · {v.model_id}</option>)}</select></label>
  const itemTemplate = (item: Item): Template => overrides[item.challenge_id] ?? (item.user_triage ? {
    ...template, solver_id: item.user_triage.solver_entry.id, solver_note: item.user_triage.solver_entry.note ?? template.solver_note,
    model_config: { ...template.model_config, executor: item.user_triage.solver_entry },
    pi_notes: item.user_triage.pi_notes, data_status: item.user_triage.data_status,
  } : template)
  const url = `/api/v1/rounds/${encodeURIComponent(id)}`
  const rankedItems = [...(round?.items ?? [])].sort((a, b) => {
    if (a.score_gap == null) return b.score_gap == null ? b.priority - a.priority : 1
    if (b.score_gap == null) return -1
    return b.score_gap - a.score_gap || b.priority - a.priority
  })
  return <section><div className="page-head"><h1>比赛轮次</h1></div>
    <button className="btn" disabled={busy} onClick={async () => {
      setBusy(true)
      try { setShutdown(await api.post('/api/v1/system/safe-shutdown', {})) }
      catch (e) { toast(e instanceof Error ? e.message : '安全暂停失败') }
      finally { setBusy(false) }
    }}>安全关机</button>
    {shutdown && <div role="status"><strong>{shutdown.message}</strong><p>远程任务继续运行和计费。</p>
      <pre>{JSON.stringify({ jobs: shutdown.remote_jobs, sandboxes: shutdown.remote_sandboxes }, null, 2)}</pre></div>}
    <p>导入整轮，查看分诊，确认模型与有界授权后自动排队。资源不限的比赛不设 Run 与会话并发数上限，提供方限速仍排队；普通有界 Run 使用连接设置的上限。未确认的分数显示 unknown。</p>
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
      <label><input type="checkbox" checked={template.authorization.unlimited_resources === true} onChange={e => setTemplate(t => ({ ...t, authorization: { ...t.authorization, unlimited_resources: e.target.checked } }))} />比赛资源不限</label>
      {template.authorization.unlimited_resources && <p>Job 数、并发、规格、金额、模型判断、Trial 与维护调用不限；用量照常记录。研究时长、提交次数和速率限制继续生效。</p>}
      {solverSelect("整轮", template, setTemplate)}
      {(['brain', 'executor'] as const).map(role => <ModelFields key={role} role={role} label={role === 'brain' ? 'PI ' : '求解者 '}
        value={template.model_config[role]} onChange={value => setTemplate(t => ({ ...t, solver_id: role === 'executor' ? null : t.solver_id, model_config: { ...t.model_config, [role]: value } }))} />)}
      <p>Prime 模型须与连接设置中的 Profile 一致；各提供方的原生认证在连接设置中配置。</p>
      {([['max_run_minutes', '每 Run 分钟'], ['max_jobs', '每 Run Job 数'], ['max_submissions', '每 Run 总 Attempt 数（含收割）'],
        ['max_sandboxes', '每 Run 沙箱并发'], ['max_environment_saves', '每 Run 环境保存数'], ['max_sandbox_minutes', '每 Run 沙箱累计分钟']] as const).map(([key, title]) =>
        <label key={key}>{title}{template.authorization.unlimited_resources && !['max_run_minutes', 'max_submissions', 'max_environment_saves'].includes(key) ? <output>不限</output> : <input type="number" min="0" value={template.authorization[key]} onChange={e => setTemplate(t => ({ ...t,
          authorization: { ...t.authorization, [key]: Number(e.target.value) } }))} />}</label>)}
      <label>给 PI 的求解者备注<input value={template.solver_note} onChange={e => setTemplate(t => ({ ...t, solver_note: e.target.value }))} /></label>
    </fieldset>
    {round && <><p>轮次 {round.id} · {round.status}</p>
      <details><summary>提供方速率状态</summary><pre>{JSON.stringify({ provider_backoff: round.resources.provider_backoff ?? [], request_models: round.resources.native_throttle ?? [] }, null, 2)}</pre></details>
      <p>提供方会话 {round.resources.sessions.map(s => `${s.provider}: ${s.used}`).join('，') || '0'} · 限流等待 {round.resources.rate_limits.length}</p>
      <label>事务性分诊 JSON<textarea value={triageInput} onChange={e => setTriageInput(e.target.value)} placeholder='[{"platform_challenge_id":"题目ID","priority":10,"solver_entry":"已配置条目ID","data_status":"用户报告的数据状态","pi_notes":"数据风险和环境建议"}]' /></label>
      <p>导入只配置队列和用户事务提示，不授权研究；会替换所列题目本页尚未确认的逐题配置。系统分诊可选，最多三题并行，每题最多两次尝试，超时后仅助手降一档；原生格式重写每次最多两次。</p>
      <button className="btn" disabled={busy || round.status !== 'draft' || !triageInput.trim()} onClick={async () => {
        try { const items = JSON.parse(triageInput); await action(`${url}/triage-import`, { items }) }
        catch (e) { toast(e instanceof Error ? e.message : '分诊JSON无效') }
      }}>导入用户分诊</button>
      <button className="btn" disabled={busy || round.status !== 'draft'} onClick={() => void action(`${url}/triage`, { allow_model_calls: true })}>授权一次题目分诊</button>
      <button className="btn primary" disabled={busy || round.status !== 'draft'} onClick={() => void action(`${url}/confirm`, {
        template, overrides })}>确认模板与授权，开始排队</button>
      <div className="evaluation-table-wrap"><table><thead><tr><th>题目与分诊</th><th>Run</th><th>本地最好分</th><th>榜单最高确认分</th><th>我方确认最好分</th><th>可提升分差</th><th>轨迹诊断</th><th>token / 金额</th><th>状态与下一步</th><th>操作</th></tr></thead>
        <tbody>{rankedItems.map(item => <tr key={item.id}>
          <td>{item.title}{item.triage && <p>{item.triage.difficulty} · {item.triage.recommended_model}<br />预计 {item.triage.estimated_minutes ?? 'unknown'} 分钟 / {item.triage.estimated_cost_cny ?? 'unknown'} 元<br />{item.triage.reason}</p>}
            {Boolean(item.triage_attempts?.length) && <details><summary>分诊助手尝试历史</summary><pre>{JSON.stringify(item.triage_attempts, null, 2)}</pre></details>}
            {round.status === 'draft' && <details><summary>此题模型与备注</summary>
              {solverSelect(item.title, itemTemplate(item), value => setOverrides(v => ({ ...v, [item.challenge_id]: value })))}
              {(['brain', 'executor'] as const).map(role => <ModelFields key={role} role={role} label={`${item.title}${role === 'brain' ? ' PI ' : '求解者 '}`}
                value={(itemTemplate(item)).model_config[role]} onChange={value => setOverrides(v => {
                  const current = v[item.challenge_id] ?? itemTemplate(item)
                  return { ...v, [item.challenge_id]: { ...current, solver_id: role === 'executor' ? null : current.solver_id, model_config: { ...current.model_config, [role]: value } } }
                })} />)}
              <label>{item.title}给 PI 的备注<input value={(itemTemplate(item)).solver_note} onChange={e => setOverrides(v => ({
                ...v, [item.challenge_id]: { ...itemTemplate(item), solver_note: e.target.value }
              }))} /></label>
            </details>}
            {round.status === 'draft' && <details><summary>此题授权</summary>
              <label><input type="checkbox" aria-label={`${item.title}资源不限`} checked={(itemTemplate(item)).authorization.unlimited_resources === true}
                onChange={e => setOverrides(v => { const current = v[item.challenge_id] ?? itemTemplate(item); return { ...v, [item.challenge_id]: { ...current, authorization: { ...current.authorization, unlimited_resources: e.target.checked } } } })} />此题资源不限</label>
              {([['max_run_minutes', '分钟'], ['max_jobs', 'Job 数'], ['max_submissions', '总 Attempt 数（含收割）'],
                ['max_sandboxes', '沙箱并发'], ['max_environment_saves', '环境保存数'], ['max_sandbox_minutes', '沙箱累计分钟']] as const).map(([key, title]) =>
                <label key={key}>{title}{(itemTemplate(item)).authorization.unlimited_resources && !['max_run_minutes', 'max_submissions', 'max_environment_saves'].includes(key) ? <output>不限</output> : <input aria-label={`${item.title}${title}`} type="number" min="0" value={(itemTemplate(item)).authorization[key]}
                  onChange={e => setOverrides(v => { const current = v[item.challenge_id] ?? itemTemplate(item); return { ...v,
                    [item.challenge_id]: { ...current, authorization: { ...current.authorization, [key]: Number(e.target.value) } } } })} />}</label>)}
              <label>{item.title}用户数据状态<input value={itemTemplate(item).data_status ?? ''} onChange={e => setOverrides(v => ({ ...v, [item.challenge_id]: { ...itemTemplate(item), data_status: e.target.value } }))} /></label>
              <label>{item.title}PI 事务提示<textarea maxLength={8000} value={itemTemplate(item).pi_notes ?? ''} onChange={e => setOverrides(v => ({ ...v, [item.challenge_id]: { ...itemTemplate(item), pi_notes: e.target.value } }))} /></label>
            </details>}</td>
          <td>{item.run_id || '排队中'}</td><td>{item.local_best ?? 'unknown'}</td>
          <td>{item.leaderboard_best ?? 'unknown'}</td><td>{item.our_best ?? 'unknown'}</td><td>{item.score_gap ?? 'unknown'}</td>
          <td>{item.trace_diagnostic ? <details><summary>查看诊断</summary><pre>{JSON.stringify(item.trace_diagnostic, null, 2)}</pre></details> : 'unknown'}</td>
          <td><details><summary>用量与费用</summary><pre>{JSON.stringify({ tokens: item.usage, model_cost: item.model_cost, cost: item.cost }, null, 2)}</pre></details></td>
          <td>{item.phase}<p>{item.next_action}</p></td>
          <td><label>优先级<input aria-label={`${item.title}优先级`} type="number" value={item.priority}
            onChange={e => void action(`${url}/items/${item.id}`, { priority: Number(e.target.value) }, 'put')} /></label>
            <button className="btn small" disabled={busy} onClick={() => void action(`${url}/items/${item.id}`, { paused: !item.paused }, 'put')}>{item.paused ? '继续排队' : '暂停此项'}</button>
            <button className="btn small" disabled={busy || round.status === 'draft'} onClick={() => void action(`${url}/runs`, { challenge_id: item.challenge_id, template: itemTemplate(item) })}>按当前模板追加 Run</button></td>
        </tr>)}</tbody></table></div>
    </>}
  </section>
}
