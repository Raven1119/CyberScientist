import { it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react'
import SharedArea from './SharedArea'
const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('./api', () => ({ api: { get } }))
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers() })
it('shows versions, provenance and formal validator without claiming a shared result is correct', async () => {
  get.mockResolvedValue({ enabled: true, validator: { status: 'observed', scorer_version: 'scorer-hash' },
    items: [{ id: 'file1', name: 'result.json', version: 2, sha256: 'hash', source_run_id: 'other', source_trial_id: 'trial', source_event_seq: 7, integrity: 'confirmed' }] })
  render(<SharedArea challengeId="topic" />); fireEvent.click(screen.getByRole('button'))
  expect((await screen.findByRole('table')).textContent).toContain('result.json · v2')
  expect(screen.getByRole('table').textContent).toContain('other / trial #7')
  expect(get).toHaveBeenCalledWith('/api/v1/challenges/topic/shared')
})

it('refreshes a viewed shared result after the backend changes without writing', async () => {
  vi.useFakeTimers()
  const value = { enabled: true, validator: { status: 'unknown' }, items: [] as object[] }
  get.mockImplementation(async () => ({ ...value, items: [...value.items] }))
  render(<SharedArea challengeId="topic" />)
  await act(async () => fireEvent.click(screen.getByRole('button')))
  value.items = [{ id: 'new', name: 'new-backend-file.json', version: 1, sha256: 'hash',
    source_run_id: 'other', source_trial_id: 'trial', source_event_seq: 8, integrity: 'confirmed' }]
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  expect(screen.getByRole('table').textContent).toContain('new-backend-file.json')
  expect(get).toHaveBeenCalledTimes(2)
})

it('shows slow backend replies without allowing an older completed reply to overwrite a newer one', async () => {
  vi.useFakeTimers()
  const pending: ((value: unknown) => void)[] = []
  get.mockImplementation(() => new Promise(resolve => pending.push(resolve)))
  render(<SharedArea challengeId="topic" />)
  await act(async () => fireEvent.click(screen.getByRole('button')))
  await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
  const value = (name: string) => ({ enabled: true, validator: { status: 'unknown' },
    items: [{ id: name, name, version: 1, sha256: 'hash', source_run_id: 'other',
      source_trial_id: 'trial', source_event_seq: 8, integrity: 'confirmed' }] })
  await act(async () => pending[0](value('slow-first.json')))
  expect(screen.getByRole('table').textContent).toContain('slow-first.json')
  await act(async () => pending[2](value('newest.json')))
  await act(async () => pending[1](value('older.json')))
  expect(screen.getByRole('table').textContent).toContain('newest.json')
  expect(screen.getByRole('table').textContent).not.toContain('older.json')
})
