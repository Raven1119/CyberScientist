import { useState } from 'react'
import { api } from './api'

type Shared = { enabled: boolean; items: { id: string; name: string; version: number; sha256: string;
  source_run_id: string; source_trial_id: string; source_event_seq: number; integrity: string }[];
  validator: { status: string; scorer_version?: string; detail?: string } }
export default function SharedArea({ challengeId }: { challengeId: string }) {
  const [data, setData] = useState<Shared | null>(null)
  const [error, setError] = useState('')
  return <article className="card card-body"><h2>题目共享区</h2>
    <p>版本只追加。导入会复制到本 Trial 并记录来源；共享文件的科学正确性需要另行验证。</p>
    <button type="button" onClick={async () => {
      try { setData(await api.get(`/api/v1/challenges/${challengeId}/shared`)); setError('') }
      catch (err) { setError(String(err)) }
    }}>查看共享区</button>
    {error && <p role="alert">{error}</p>}
    {data && <>
      <p>{data.enabled ? '共享区已启用' : '共享区已关闭，保留历史版本'}</p>
      <p>正式验证器：{data.validator.status === 'observed' ? data.validator.scorer_version : data.validator.detail ?? data.validator.status}</p>
      <table aria-label="共享版本"><thead><tr><th>文件 / 版本</th><th>来源事件</th><th>哈希与完整性</th></tr></thead>
        <tbody>{data.items.map(item => <tr key={item.id}><td>{item.name} · v{item.version}</td>
          <td>{item.source_run_id} / {item.source_trial_id} #{item.source_event_seq}</td>
          <td>{item.sha256}<br />{item.integrity === 'confirmed' ? '哈希确认' : '文件未确认'}</td></tr>)}</tbody></table>
    </>}
  </article>
}
