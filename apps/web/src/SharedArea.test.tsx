import { it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import SharedArea from './SharedArea'
const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('./api', () => ({ api: { get } }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it('shows versions, provenance and formal validator without claiming a shared result is correct', async () => {
  get.mockResolvedValue({ enabled: true, validator: { status: 'observed', scorer_version: 'scorer-hash' },
    items: [{ id: 'file1', name: 'result.json', version: 2, sha256: 'hash', source_run_id: 'other', source_trial_id: 'trial', source_event_seq: 7, integrity: 'confirmed' }] })
  render(<SharedArea challengeId="topic" />); fireEvent.click(screen.getByRole('button'))
  expect((await screen.findByRole('table')).textContent).toContain('result.json · v2')
  expect(screen.getByRole('table').textContent).toContain('other / trial #7')
  expect(get).toHaveBeenCalledWith('/api/v1/challenges/topic/shared')
})
