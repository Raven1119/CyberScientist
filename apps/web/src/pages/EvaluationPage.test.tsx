import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import EvaluationPage from './EvaluationPage'

const { get, post, toast } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), toast: vi.fn() }))
vi.mock('../api', () => ({ api: { get, post } }))
vi.mock('../app-context', () => ({ useApp: () => ({ toast, demoMode: false }) }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

describe('evaluation page', () => {
  it('shows persisted progress and bounded launch controls', async () => {
    get.mockImplementation(async (path: string) => path === '/api/v1/evals' ?
      { items: [{ id: 'eval_one', suite: 'fast', status: 'running', label: '', created_at: '' }] } :
      { id: 'eval_one', suite: 'fast', status: 'running', results: [
        { id: 'er_1', challenge_id: 'figqa', repeat_index: 1, run_id: 'run_one', status: 'complete',
          error: null, result: { science_score: 100, trace_checklist_score: 80,
            trace_qualified_cap: null, display_interval: { lower: 30, upper: 100 },
            wall_seconds: 42, job_count: 2, job_unknown_count: 1,
            sandbox_minutes: 3.5, sandbox_minutes_status: 'confirmed',
            bohrium_amount: 'unknown', final_status: 'finished',
            bohrium_cost_details: { job_native_amount_total: '0.12', currency: null, total_amount: null,
              sandbox_observed: { amounts: { CNY: '0.08', photons: '2.5' }, unmatched_count: 1 },
              sandbox_estimate: { amount: '0.0400', currency: 'CNY', status: 'estimated_partial', unpriced_count: 1 } } } },
      ] })
    post.mockResolvedValue({ id: 'eval_two', suite: 'hard', status: 'running', results: [] })
    render(<EvaluationPage />)
    expect(await screen.findByText(/完成 1\/1/)).toBeTruthy()
    expect(screen.getByText('[30, 100]')).toBeTruthy()
    expect(screen.getByText('2 (+1 unknown)')).toBeTruthy()
    expect(screen.getByText('3.5')).toBeTruthy()
    expect(screen.getByText(/Job 原始金额 0.12（币种未确认，非总费用）/)).toBeTruthy()
    expect(screen.getByText(/沙箱估算 0.0400 CNY（未定价 1 项，非账单）/)).toBeTruthy()
    expect(screen.getByText(/沙箱查询费用 0.08 CNY（未确认最终结算；缺 1 项）/)).toBeTruthy()
    expect(screen.getByText(/沙箱查询费用 2.5 photons/)).toBeTruthy()
    expect(screen.getByText(/只做本地科学评分/)).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: '运行困难层' }))
    expect(post).toHaveBeenCalledWith('/api/v1/evals', { suite: 'hard', repeats: 2, label: '' })
  })
})
