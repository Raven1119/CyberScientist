import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { GuidanceItem, RunOverviewPanel } from './ResearchPage'
import type { RunOverview } from '../types'

afterEach(cleanup)

it('shows controller repair facts with truthful queued delivery status', () => {
  render(<GuidanceItem item={{id: 'repair', source: 'controller', kind: 'steer', intent: 'continue',
    status: 'queued', text_md: 'final_package_score: INVALID_COMMAND', target_trial_id: 'trial-a',
    ack_disposition: null, created_at: '2026-10-02T00:00:00Z'}} />)
  expect(screen.getByText('系统修复反馈')).toBeTruthy()
  expect(screen.getByText('排队中')).toBeTruthy()
  expect(screen.getByText('final_package_score: INVALID_COMMAND')).toBeTruthy()
})

it('shows all active Runs, score confidence and attention, and selects by Run ID', () => {
  const items: RunOverview[] = [
    { id: 'run_first', challenge_id: 'a', challenge_title: '题 A', phase: 'running',
      gate: 'open', current_trial_id: 'trial-a', latest_score: 85,
      score_confidence: 'provisional', job_count: 2, sandbox_count: 0,
      needs_attention: false, attention_reason: null },
    { id: 'run_second', challenge_id: 'b', challenge_title: '题 B', phase: 'recovering',
      gate: 'awaiting_budget', current_trial_id: null, latest_score: null,
      score_confidence: null, job_count: 0, sandbox_count: 1,
      needs_attention: true, attention_reason: '等待用户调整额度' },
    { id: 'run_third', challenge_id: 'c', challenge_title: '题 C', phase: 'paused',
      gate: 'open', current_trial_id: null, latest_score: null,
      score_confidence: null, job_count: 0, sandbox_count: 0,
      needs_attention: true, attention_reason: '连续两次检测到研究无进展' },
  ]
  const select = vi.fn()
  render(<RunOverviewPanel items={items} onSelect={select} />)
  const panel = screen.getByRole('article', { name: '本轮总览' })
  expect(panel.textContent).toContain('活跃 Run 3')
  expect(panel.textContent).toContain('最近得分 85（暂定）')
  expect(panel.textContent).toContain('Job 0 · 沙箱 1')
  expect(panel.textContent).toContain('需关注：等待用户调整额度')
  expect(panel.textContent).toContain('需关注：连续两次检测到研究无进展')
  fireEvent.click(screen.getByRole('button', { name: /题 B · run_seco/ }))
  expect(select).toHaveBeenCalledWith(items[1])
})
