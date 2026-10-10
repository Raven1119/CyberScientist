import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { useLatestRequest } from './useLatestRequest'

type Review = { operation_id: string; status: string; source_sha256: string; sealed_sha256: string; error: string | null;
  scorer_source?: { status: string; scorer_version?: string };
  result: null | { verdict: string; issues: string[]; summary_md: string; scorer_audit?: {
    coverage_findings: string[]; threshold_format_md: string; leniency_md: string;
    method_completeness_md: string; replay_network_md: string;
    negative_controls: { case_md: string; expected_failure_md: string; covers_md: string }[];
  } } }

export default function PackageReviews({ runId }: { runId: string }) {
  const [reviews, setReviews] = useState<Review[]>([])
  const [error, setError] = useState('')
  const [viewing, setViewing] = useState(false)
  const beginRead = useLatestRequest(runId)
  const load = useCallback(async () => {
    const current = beginRead()
    try { const data = await api.get<{ items: Review[] }>(`/api/v1/runs/${runId}/package-reviews`); if (current()) { setReviews(data.items); setError(data.items.length ? '' : '尚无审查报告') } }
    catch (problem) { if (current()) setError(problem instanceof Error ? problem.message : String(problem)) }
  }, [runId, beginRead])
  useEffect(() => {
    if (!viewing) return
    void load()
    const timer = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(timer)
  }, [viewing, load])
  return <article className="card card-body"><h2>包审查与评分器审计</h2>
    <p>审查意见供 PI 判断；负向对照由 PI 决定是否交给执行器运行。</p>
    <button type="button" onClick={() => { if (viewing) void load(); else setViewing(true) }}>查看审查报告</button>
    {error && <p role="status">{error}</p>}
    {reviews.map(review => <details key={review.operation_id}><summary>{review.operation_id} · {review.status}</summary>
      <p>{review.error || review.result?.summary_md}</p>
      <p>评分器源码：{review.scorer_source?.status ?? 'unknown'} · 版本 {review.scorer_source?.scorer_version ?? 'unknown'}</p>
      {review.result?.issues.map(issue => <p key={issue}>{issue}</p>)}
      {review.result?.scorer_audit && <>
        <p>覆盖检查：{review.result.scorer_audit.coverage_findings.join('；')}</p>
        <p>阈值与格式：{review.result.scorer_audit.threshold_format_md}</p>
        <p>放水检查：{review.result.scorer_audit.leniency_md}</p>
        <p>方法完整性：{review.result.scorer_audit.method_completeness_md}</p>
        <p>重放联网依赖：{review.result.scorer_audit.replay_network_md}</p>
        {review.result.scorer_audit.negative_controls.map(control => <p key={control.case_md}>建议负向对照：{control.case_md} · 预期：{control.expected_failure_md} · 覆盖：{control.covers_md}</p>)}
      </>}
      <p>原包 SHA256 {review.source_sha256} · 封存 SHA256 {review.sealed_sha256}</p>
    </details>)}
  </article>
}
