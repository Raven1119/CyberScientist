import { useEffect, useRef, useState } from 'react'
import { api } from './api'

interface Result { status: string; observed_at?: string; reason?: string; changes?: unknown[] }
const labels: Record<string, string> = { unchanged: '未发现变化', changed: '发现变化，请核对兼容性', unknown: '尚未确认', disabled: '已关闭' }
export default function ProtocolDrift() {
  const [result, setResult] = useState<Result>({ status: 'unknown' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  useEffect(() => { let active = true
    const request = generation.current
    api.get<Result>('/api/v1/protocol-drift').then(value => { if (active && request === generation.current) setResult(value) }).catch(() => {})
    return () => { active = false }
  }, [])
  const check = async () => {
    setBusy(true); setError('')
    const request = ++generation.current
    try { const value = await api.post<Result>('/api/v1/protocol-drift/check', {}); if (request === generation.current) setResult(value) }
    catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setBusy(false) }
  }
  return <article className="card card-body"><h2>平台协议检查</h2>
    <p>{labels[result.status] ?? '尚未确认'}{result.observed_at ? ' · ' + result.observed_at : ''}</p>
    <p>导入轮次和赛前自检会刷新公开协议、接口文档与评分格式；变化会弹窗并提供给 PI。</p>
    {result.reason && <p>{result.reason}</p>}
    {Boolean(result.changes?.length) && <pre>{JSON.stringify(result.changes, null, 2)}</pre>}
    {error && <p role="alert">检查未完成：{error}</p>}
    <button type="button" className="btn" disabled={busy} onClick={() => void check()}>{busy ? '检查中…' : '检查公开协议变化'}</button>
  </article>
}
