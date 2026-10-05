import { useState } from 'react'
import { api } from './api'

type Entry = {
  id: string; type: string; topic_types: string[]; image: string; restore_command: string;
  contents: Record<string, string>; smoke_command: string; last_verified_at: string;
  restore_seconds: Record<string, number>; reproduction_md: string; known_issues: string[];
  receipts: { source: string; receipt_sha256: string; channel: string }[];
}

export default function EnvironmentCatalog() {
  const [entries, setEntries] = useState<Entry[]>([])
  const [message, setMessage] = useState('')
  return <article className="card card-body"><h2>环境目录</h2>
    <p>目录提供研究起点。PI 可选择条目或从零搭建；执行器先恢复并冒烟，随后可换镜像或安装依赖。</p>
    <button type="button" onClick={async () => {
      try {
        const result = await api.get<{ enabled: boolean; items: Entry[] }>('/api/v1/environment-catalog')
        setEntries(result.items)
        setMessage(!result.enabled ? '环境目录已关闭' : result.items.length ? '' : '尚无已验证的起点')
      } catch (error) { setMessage(error instanceof Error ? error.message : String(error)) }
    }}>查看环境目录</button>
    {message && <p role="status">{message}</p>}
    {entries.map(entry => <details key={entry.id}><summary>{entry.id} · {({ public_image: '公共镜像', private_image: '私有镜像', environment_bundle: '环境包' } as Record<string, string>)[entry.type] ?? entry.type}</summary>
      <p>适用题型：{entry.topic_types.join('、')} · 最近验证：{entry.last_verified_at}</p>
      <p>镜像或恢复命令：<code>{entry.image || entry.restore_command}</code></p>
      <p>锁定内容：{Object.entries(entry.contents).map(([name, version]) => `${name} ${version}`).join('、')}</p>
      <p>冒烟命令：<code>{entry.smoke_command}</code></p>
      <p>实测恢复：{Object.entries(entry.restore_seconds).map(([channel, seconds]) => `${channel} ${seconds}秒`).join('、')}</p>
      <pre>{entry.reproduction_md}</pre>
      {entry.known_issues.map(issue => <p key={issue}>{issue}</p>)}
      {entry.receipts.map(receipt => <p key={receipt.receipt_sha256}>{receipt.channel} 回执：{receipt.source} · SHA256 {receipt.receipt_sha256}</p>)}
    </details>)}
  </article>
}
