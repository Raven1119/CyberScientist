import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import MailboxPage from './MailboxPage'

const { get, post, toast } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), toast: vi.fn() }))
vi.mock('../api', () => ({ api: { get, post, delete: vi.fn() }, ApiError: class extends Error {} }))
vi.mock('../app-context', () => ({ useApp: () => ({ toast, demoMode: false }) }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})

const candidate = (id: string, score: number, warnings: string[]) => ({
  id, run_id: 'run-a', trial_id: 'trial-a', mailbox_id: 'exp-a', mailbox_email: 'exp@example.com',
  package_path: `submissions/${id}/package.zip`, package_sha256: 'a'.repeat(64),
  score, displayScore: score, score_status: 'scored', status: 'submitted',
  score_confidence: warnings.length ? 'provisional' : 'confirmed',
  score_anomaly: null, scorecard_consistent: 1, harbor_score: 100, trace_score: 72,
  is_highest: score === 90, warnings, created_at: '2026-09-27T00:00:00Z',
  submitted_at: '2026-09-27T00:00:00Z', is_harvest: 0,
})

function mockData() {
  get.mockImplementation(async (path: string) => {
    if (path === '/api/v1/mailboxes') return { items: [
      { id: 'exp-a', role: 'experiment', email: 'exp@example.com', status: 'active',
        submission_limit: 10, secret_configured: true, is_demo: 0 },
      { id: 'harvest-a', role: 'harvest', email: 'harvest@example.com', status: 'active',
        submission_limit: 10, secret_configured: true, is_demo: 0 }], platform_is_demo: false }
    if (path === '/api/v1/mailboxes/usage') return { items: [
      { mailbox_id: 'exp-a', email: 'exp@example.com', role: 'experiment',
        platform_challenge_id: 'challenge-a', challenge_title: '题 A', used: 2, limit: 10 },
      { mailbox_id: 'harvest-a', email: 'harvest@example.com', role: 'harvest',
        platform_challenge_id: 'challenge-a', challenge_title: '题 A', used: 1, limit: 10 }] }
    if (path === '/api/v1/runs') return { items: [{ id: 'run-a', challenge_id: 'challenge-a', phase: 'finished' }] }
    if (path === '/api/v1/runs/run-a') return { current_trial_id: 'trial-a' }
    if (path.endsWith('/submissions')) return { items: [] }
    if (path.startsWith('/api/v1/harvest/candidates')) return { items: [
      candidate('high', 90, []), candidate('low', 80, ['不是当前最高分', '分数仍为暂定，尚未确认'])] }
    if (path === '/api/v1/polling') return { tasks: [] }
    throw new Error(path)
  })
  post.mockResolvedValue({ status: 'submitted' })
}

it('shows challenge by mailbox usage for both roles', async () => {
  mockData()
  render(<MailboxPage />)
  const table = await screen.findByRole('table', { name: '题目邮箱用量' })
  expect(table.textContent).toContain('2 / 10')
  expect(table.textContent).toContain('1 / 10')
  expect(table.textContent).toContain('收割')
  expect(table.textContent).toContain('实验')
})

it('lets the user select a lower candidate and requires warning acknowledgment', async () => {
  mockData()
  render(<MailboxPage />)
  fireEvent.click(await screen.findByRole('radio', { name: /展示分 80/ }))
  fireEvent.click(screen.getByRole('button', { name: '收割选中候选' }))
  expect(screen.getByText('不是当前最高分')).toBeTruthy()
  const submit = screen.getByRole('button', { name: '确认提交' }) as HTMLButtonElement
  expect(submit.disabled).toBe(true)
  fireEvent.click(screen.getByRole('checkbox', { name: '已知悉上述警示' }))
  expect(submit.disabled).toBe(false)
  fireEvent.click(submit)
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/harvest/submit',
    expect.objectContaining({ submission_id: 'low', acknowledge_warnings: true })))
})
