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
            wall_seconds: 42, bohrium_amount: 'unknown', final_status: 'finished' } },
      ] })
    post.mockResolvedValue({ id: 'eval_two', suite: 'hard', status: 'running', results: [] })
    render(<EvaluationPage />)
    expect(await screen.findByText(/完成 1\/1/)).toBeTruthy()
    expect(screen.getByText('[30, 100]')).toBeTruthy()
    expect(screen.getByText(/只做本地科学评分/)).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: '运行困难层' }))
    expect(post).toHaveBeenCalledWith('/api/v1/evals', { suite: 'hard', repeats: 2, label: '' })
  })
})
