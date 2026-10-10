import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import SubmissionQueue from './SubmissionQueue'
import { api } from './api'
vi.mock('./api', () => ({ api: { get: vi.fn(), put: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
test('does not claim automatic submission is enabled before reading the backend', () => {
  vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
  render(<SubmissionQueue />)
  expect(screen.getByText('自动提交状态未确认，正在读取')).toBeTruthy()
  expect(screen.getByRole('button').matches(':disabled')).toBe(true)
  expect(api.put).not.toHaveBeenCalled()
})
test('queued item is visible and resume calls the persistent switch', async () => {
  let enabled = false
  vi.mocked(api.get).mockImplementation(async path => path.endsWith('features') ? { features: { auto_submission: enabled } } : { paused: !enabled, items: [{ submission_id: 's', challenge_id: 'topic', mailbox_id: 'account', is_harvest: 1, not_before: '2026-10-08T05:00Z', reason: '同账号同题提交间隔' }] })
  vi.mocked(api.put).mockImplementation(async () => { enabled = true; return {} })
  render(<SubmissionQueue />)
  expect(await screen.findByText('同账号同题提交间隔')).toBeTruthy()
  expect(screen.getByText('收割')).toBeTruthy()
  fireEvent.click(screen.getByText('恢复自动提交'))
  await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/v1/features/auto_submission', { enabled: true }))
  expect(await screen.findByText('自动提交已启用')).toBeTruthy()
})
