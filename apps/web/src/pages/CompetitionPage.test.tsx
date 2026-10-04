import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CompetitionPage from './CompetitionPage'
const { get, post, put, toast } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), toast: vi.fn() }))
vi.mock('../api', () => ({ api: { get, post, put } }))
vi.mock('../app-context', () => ({ useApp: () => ({ toast, demoMode: false }) }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
const detail = { id: 'round_one', label: '', status: 'draft', resources: { sessions: [{ provider: 'codex', used: 2 }], rate_limits: [] }, items: [
  { id: 'ri_one', challenge_id: 'same_challenge', title: '测试题', run_id: null, phase: 'queued', priority: 0, paused: 0,
    local_best: null, platform_best: null, trace_diagnostic: null, usage: [], cost: null, next_action: '等待资源名额',
    triage: { difficulty: 'easy', recommended_model: 'deepseek-flash', reason: '公开输入较小', estimated_minutes: 10, estimated_cost_cny: null } },
] }
it('shows confirmed versus unknown facts and requires a bounded template before queueing', async () => {
  get.mockImplementation(async (path: string) => path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : detail)
  post.mockResolvedValue({ ...detail, status: 'running' })
  render(<CompetitionPage />)
  expect(await screen.findByText(/easy · deepseek-flash/)).toBeTruthy()
  expect(screen.getByText('等待资源名额')).toBeTruthy()
  expect(screen.getAllByText('unknown').length).toBeGreaterThan(1)
  await userEvent.setup().click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  expect(post.mock.calls[0][0]).toBe('/api/v1/rounds/round_one/confirm')
  expect(post.mock.calls[0][1].template.authorization.max_submissions).toBe(0)
  await userEvent.setup().click(await screen.findByRole('button', { name: '按当前模板追加 Run' }))
  expect(post.mock.calls[1][1].challenge_id).toBe('same_challenge')
})
