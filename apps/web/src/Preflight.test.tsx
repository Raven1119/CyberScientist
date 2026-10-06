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
it('shows observed image creation time while cache lifetime remains unknown', async () => {
  vi.mocked(api.get).mockResolvedValue({ status: 'pass', observed_at: 'now', items: [{ name: 'sandbox_image_warmup', status: 'pass', detail: '平台缓存有效期unknown', facts: { images: [{ entry_id: 'lean', created_success_at: '2026-10-07T03:00:00Z', cache_validity_seconds: null }] } }] })
  render(<Preflight />)
  expect(await screen.findByText('各镜像沙箱创建时间')).toBeTruthy()
  fireEvent.click(screen.getByText('查看检查事实'))
  expect(screen.getByText(/2026-10-07T03:00:00Z/)).toBeTruthy()
  expect(screen.getByText('平台缓存有效期unknown')).toBeTruthy()
  expect(api.post).not.toHaveBeenCalled()
})
