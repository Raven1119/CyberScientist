import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PostReviews from './PostReviews'
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('./api', () => ({ api: { get, post } }))
afterEach(() => { cleanup(); vi.resetAllMocks(); sessionStorage.clear() })

it('shows original failure and immutable successful versions with actual call bounds', async () => {
  get.mockResolvedValue({ status: 'failed', error: 'outside snapshot', versions: [{ id: 'v2', version: 2, status: 'done', calls_used: 2, native_call_limit: 3, report_md: 'full trace receipt' }] })
  render(<PostReviews runId="run-a" phase="finished" />)
  await userEvent.click(screen.getByRole('button', { name: '查看复盘及历史版本' }))
  expect(await screen.findByText(/原复盘：failed outside snapshot/)).toBeTruthy()
  expect(screen.getByText(/模型调用 2\/3/)).toBeTruthy()
  expect(screen.getByText('full trace receipt')).toBeTruthy()
})

it.each(['paused', 'waiting_score', 'recovering', 'running'])('does not grant a postreview during %s', phase => {
  render(<PostReviews runId="run-a" phase={phase} />)
  expect(screen.queryByRole('button', { name: '创建复盘版本' })).toBeNull()
  expect(post).not.toHaveBeenCalled()
})

it('reconciles a lost response after remount before explicitly creating a new version', async () => {
  post.mockRejectedValueOnce(new Error('timeout')).mockResolvedValue({ id: 'v2' })
  get.mockResolvedValue({ status: 'failed', versions: [] })
  const user = userEvent.setup(); let view = render(<PostReviews runId="run-a" phase="finished" />)
  expect(screen.getByRole('button', { name: '创建复盘版本' }).matches(':disabled')).toBe(true)
  async function grant() {
    await user.type(screen.getByLabelText('复盘原因'), 'Read the whole trace')
    await user.click(screen.getByLabelText('允许最多两次同会话格式纠正'))
    await user.click(screen.getByLabelText('授权本次复盘模型调用（最多 3 次）'))
    await user.click(screen.getByRole('button', { name: '创建复盘版本' }))
  }
  await grant(); await screen.findByRole('alert')
  const operation = post.mock.calls[0][1].operation_id
  get.mockResolvedValue({ status: 'failed', versions: [{ id: operation, version: 1, status: 'pending', calls_used: 0, native_call_limit: 3 }] })
  view.unmount(); view = render(<PostReviews runId="run-a" phase="finished" />)
  await screen.findByText(/版本 1 · pending/)
  await grant()
  expect(post.mock.calls[1][1]).toEqual({ operation_id: expect.any(String), reason: 'Read the whole trace', allow_model_calls: true, max_format_rewrites: 2 })
  expect(post.mock.calls[1][1].operation_id).not.toBe(operation)
})

it('keeps an unconfirmed operation and disables new grants until readonly reconciliation succeeds', async () => {
  sessionStorage.setItem('post-review-operation:run-a', 'uncertain')
  get.mockResolvedValue({ status: 'idle', versions: [] })
  render(<PostReviews runId="run-a" phase="finished" />)
  await screen.findByText(/原授权尚未确认/)
  expect(screen.getByLabelText('复盘原因').matches(':disabled')).toBe(true)
  expect(sessionStorage.getItem('post-review-operation:run-a')).toBe('uncertain')
  expect(post).not.toHaveBeenCalled()
})
