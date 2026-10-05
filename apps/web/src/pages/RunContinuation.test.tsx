import { it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, screen, waitFor, cleanup } from '@testing-library/react'
import { RunContinuation } from './RunContinuation'
const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('../api', () => ({ api: { post } }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it('reopens then resumes the same Run without creating or replacing it', async () => {
  post.mockResolvedValue({ status: 'confirmed' }); const refresh = vi.fn()
  render(<RunContinuation runId="original" phase="finished" refresh={refresh} toast={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: '续跑原 Run' }))
  await waitFor(() => expect(refresh).toHaveBeenCalled())
  expect(post.mock.calls.map(([url, body]) => [url, body.action])).toEqual([
    ['/api/v1/runs/original/control', 'reopen'], ['/api/v1/runs/original/control', 'resume']])
})
it('shows waiting without offering an unauthorized model wake', () => {
  render(<RunContinuation runId="original" phase="waiting_score" refresh={vi.fn()} toast={vi.fn()} />)
  expect(screen.getByText(/活动时钟暂停/)).toBeTruthy(); expect(screen.queryByRole('button')).toBeNull()
})
