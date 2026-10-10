import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from './api'
import GateReviews from './GateReviews'
vi.mock('./api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
test('individual false positive needs a reason and submits the same item', async () => {
  const gate = { id: 'g1', rule: 'bearer_token', source: 'native.jsonl', line: 5, context: '[redacted]', risk: 'high', exact_stored: 0 }
  vi.mocked(api.get).mockResolvedValue({ items: [gate] }); vi.mocked(api.post).mockResolvedValue({})
  render(<GateReviews />)
  expect(await screen.findByText('无 Run · native.jsonl:5')).toBeTruthy()
  const button = screen.getByText('放行并续接') as HTMLButtonElement
  expect(button.disabled).toBe(true)
  fireEvent.click(screen.getByLabelText('此项是误报'))
  fireEvent.change(screen.getByLabelText('复核理由 g1'), { target: { value: '公开的合成示例' } })
  fireEvent.click(button)
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/ops/gates/g1/resolve', { false_positive: true, reason: '公开的合成示例' }))
})
test('stored credential exposes no release operation', async () => {
  vi.mocked(api.get).mockResolvedValue({ items: [{ id: 'g2', rule: 'stored_credential', source: 'native', context: '[redacted]', risk: 'critical', exact_stored: 1 }] })
  render(<GateReviews />)
  expect(await screen.findByText('已存凭据原文命中，禁止放行')).toBeTruthy()
  expect(screen.queryByText('放行并续接')).toBeNull()
})
