import { useEffect, useRef, useState } from 'react'
import { api } from './api'
interface Report { observed_at: string; status: string; items: { name: string; status: string; detail: string; facts: unknown }[] }
const names: Record<string, string> = { harvest_mailbox: '收割邮箱', experiment_mailbox: '实验邮箱', playground: 'Playground 凭据', bohrium: 'Bohrium 凭据', codex: 'Codex 原生模型', deepseek: 'DeepSeek', web_search: '联网搜索', web_read: '网页读取', lkm: 'LKM', protocol_drift: '协议漂移', disk: '磁盘', backend: '后端健康', code: '代码版本与标签' }
const labels: Record<string, string> = { pass: '通过', warn: '警告', fail: '失败' }
export default function Preflight() {
  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  useEffect(() => { let active = true; const request = generation.current
    api.get<Report | null>('/api/v1/preflight').then(value => { if (active && request === generation.current && (!value || Array.isArray(value.items))) setReport(value) }).catch(() => {})
    return () => { active = false }
  }, [])
  const check = async () => {
    setBusy(true); setError(''); ++generation.current
    try { const value = await api.post<Report>('/api/v1/preflight', {}); if (!Array.isArray(value.items)) throw new Error('自检响应格式未知'); setReport(value) }
    catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setBusy(false) }
  }
  return <article className="card card-body"><h2>赛前自检</h2>
    <p>只读检查邮箱、凭据、原生模型目录、公开工具、协议、磁盘及后端版本。不会登录、启动 Run 或模型 turn。</p>
    <button type="button" className="btn" disabled={busy} onClick={() => void check()}>{busy ? '自检中…' : '一键赛前自检'}</button>
    {error && <p role="alert">自检未完成：{error}</p>}
    {report && <><p>{labels[report.status]} · {report.observed_at}</p><table><thead><tr><th>检查项</th><th>结果</th><th>事实</th></tr></thead>
      <tbody>{report.items.map(item => <tr key={item.name}><td>{names[item.name] ?? item.name}</td><td>{labels[item.status]}</td><td>{item.detail}<details><summary>查看检查事实</summary><pre>{JSON.stringify(item.facts, null, 2)}</pre></details></td></tr>)}</tbody></table></>}
  </article>
}
