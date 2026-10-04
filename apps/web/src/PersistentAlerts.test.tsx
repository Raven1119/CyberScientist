import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { ReactNode } from 'react'
import PersistentAlerts from './PersistentAlerts'
import { api } from './api'
const navigation = vi.hoisted(() => ({ setPage: vi.fn(), setCurrentChallengeId: vi.fn(), setFocusedRunId: vi.fn() }))
vi.mock('./app-context', () => ({ useApp: () => navigation }))
vi.mock('./api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
vi.mock('./components', () => ({ Modal: ({ title, children }: { title: string; children: ReactNode }) => <div role="dialog" aria-label={title}>{children}</div> }))
afterEach(cleanup)
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.get).mockResolvedValue({ items: [{ id: 'a', run_id: 'r', challenge_id: 'c', title: '自动收割状态不明', payload: { status: 'unknown' } }] }) })
test('unacknowledged alert returns on refresh and navigation saves acknowledgement', async () => {
  const first = render(<PersistentAlerts />)
  expect(await screen.findByRole('dialog', { name: '自动收割状态不明' })).toBeTruthy()
  first.unmount(); render(<PersistentAlerts />)
  expect(await screen.findByRole('dialog')).toBeTruthy()
  vi.mocked(api.post).mockResolvedValue({ acknowledged_at: 'saved' })
  fireEvent.click(screen.getByText('查看研究'))
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/alerts/a/acknowledge', {}))
  expect(navigation.setFocusedRunId).toHaveBeenCalledWith('r')
  expect(navigation.setCurrentChallengeId).toHaveBeenCalledWith('c')
  expect(navigation.setPage).toHaveBeenCalledWith('research')
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
})
test('failed acknowledgement keeps the durable alert visible', async () => {
  vi.mocked(api.post).mockRejectedValue(new Error('offline'))
  render(<PersistentAlerts />); await screen.findByRole('dialog')
  fireEvent.click(screen.getByText('已知悉'))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '确认未保存：offline')
  expect(screen.getByRole('dialog')).toBeTruthy()
  expect(navigation.setPage).not.toHaveBeenCalled()
})
