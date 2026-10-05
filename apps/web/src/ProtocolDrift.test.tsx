import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import ProtocolDrift from './ProtocolDrift'
import { api } from './api'
vi.mock('./api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it('reads cached status then requests the actual check and displays changed fields', async () => {
  vi.mocked(api.get).mockResolvedValue({ status: 'unknown' })
  vi.mocked(api.post).mockResolvedValue({ status: 'changed', changes: [{ document: 'protocol', changed_paths: ['version'] }] })
  render(<ProtocolDrift />)
  fireEvent.click(screen.getByText('检查公开协议变化'))
  await screen.findByText('发现变化，请核对兼容性')
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/protocol-drift/check', {}))
  expect(screen.getByText(/"version"/)).toBeTruthy()
})
it('preserves an unknown failure instead of displaying unchanged', async () => {
  vi.mocked(api.get).mockResolvedValue({ status: 'unknown' }); vi.mocked(api.post).mockRejectedValue(new Error('timeout'))
  render(<ProtocolDrift />); fireEvent.click(screen.getByText('检查公开协议变化'))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '检查未完成：timeout')
  expect(screen.queryByText('未发现变化')).toBeNull()
})

it('ignores an old initial GET that returns after a fresh POST check', async () => {
  let resolve!: (value: unknown) => void
  vi.mocked(api.get).mockImplementation(() => new Promise(r => { resolve = r }))
  vi.mocked(api.post).mockResolvedValue({ status: 'changed', changes: [{ changed_paths: ['version'] }] })
  render(<ProtocolDrift />); fireEvent.click(screen.getByText('检查公开协议变化'))
  await screen.findByText('发现变化，请核对兼容性')
  await act(async () => { resolve({ status: 'unchanged' }) })
  expect(screen.getByText('发现变化，请核对兼容性')).toBeTruthy()
  expect(screen.queryByText('未发现变化')).toBeNull()
})
