export type GateReport = {
  version: string
  conclusion: string
  possible_cap: number | null
  checks: { code: string; status: string; reliability: string; evidence: unknown }[]
  visibility: { over_900?: number; event_count?: number; over_900_ratio?: number | null }
  missing_evidence: { id: string; question: string }[]
  judge_replica_hint: { enabled: boolean; label: string; status: string }
}

export default function TraceGate({ report }: { report: GateReport }) {
  const labels: Record<string, string> = { pass: '通过', risk: '风险', unknown: '无法判定' }
  return <section aria-label="轨迹门报告">
    <p>轨迹门 {report.version} · {labels[report.conclusion] || report.conclusion} · 可能封顶 {report.possible_cap ?? '无法判定'}（不预测评分）</p>
    <ul>{report.checks.map(item => <li key={item.code}>
      <details><summary>{item.code}：{labels[item.status] || item.status} · 平台一致性 {item.reliability}</summary>
        <pre>{JSON.stringify(item.evidence, null, 2)}</pre></details>
    </li>)}</ul>
    <p>超过900字符：{report.visibility.over_900 ?? '未知'}/{report.visibility.event_count ?? '未知'}；关键证据是否可见仍需核对原文与实际裁判输入。</p>
    {report.missing_evidence.length > 0 && <details><summary>缺失证据自查</summary><ul>
      {report.missing_evidence.map(item => <li key={item.id}>{item.id}：{item.question}</li>)}
    </ul></details>}
    {report.judge_replica_hint.enabled && <p>{report.judge_replica_hint.label} · {report.judge_replica_hint.status}；独立复刻工具尚无本包预测。</p>}
  </section>
}
