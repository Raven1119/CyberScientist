import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PackageReviews from './PackageReviews'
const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('./api', () => ({ api: { get } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

it('shows scorer coverage, method/network findings and suggested controls without running them', async () => {
  get.mockResolvedValue({ items: [{ operation_id: 'review-a', status: 'done', source_sha256: 'a', sealed_sha256: 'b', error: null,
    result: { verdict: 'issues', issues: ['missing residual'], summary_md: 'too lenient', scorer_audit: {
      coverage_findings: ['dimensions missing'], threshold_format_md: 'missing 0.01', leniency_md: 'always 100',
      method_completeness_md: 'equations missing', replay_network_md: 'network unknown',
      negative_controls: [{ case_md: 'wrong dimension', expected_failure_md: 'score zero', covers_md: 'dimensions' }],
    } } }] })
  render(<PackageReviews runId="run-fixture" />)
  await userEvent.click(screen.getByRole('button', { name: '查看审查报告' }))
  expect(get).toHaveBeenCalledWith('/api/v1/runs/run-fixture/package-reviews')
  expect(await screen.findByText(/建议负向对照：wrong dimension/)).toBeTruthy()
  expect(screen.getByText(/重放联网依赖：network unknown/)).toBeTruthy()
  expect(screen.getByText(/方法完整性：equations missing/)).toBeTruthy()
})
