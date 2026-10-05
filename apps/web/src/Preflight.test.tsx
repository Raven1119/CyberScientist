import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from './api'
import Preflight from './Preflight'
vi.mock('./api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it('shows disabled harvest failure through actual preflight route with no Run action', async () => {
  vi.mocked(api.get).mockResolvedValue(null)
  vi.mocked(api.post).mockResolvedValue({ status: 'fail', observed_at: 'now', items: [{ name: 'harvest_mailbox', status: 'fail', detail: '收割邮箱未启用', facts: { platform: 'bohrium_playground' } }] })
  render(<Preflight />); fireEvent.click(screen.getByText('一键赛前自检'))
  expect(await screen.findByText('收割邮箱未启用')).toBeTruthy()
  expect(api.post).toHaveBeenCalledWith('/api/v1/preflight', {})
  fireEvent.click(screen.getByText('查看检查事实')); expect(screen.getByText(/bohrium_playground/)).toBeTruthy()
})
it('displays failed read separately from any successful cached report', async () => {
  vi.mocked(api.get).mockResolvedValue(null); vi.mocked(api.post).mockRejectedValue(new Error('unavailable'))
  render(<Preflight />); fireEvent.click(screen.getByText('一键赛前自检'))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '自检未完成：unavailable')
})
