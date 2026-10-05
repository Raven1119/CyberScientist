import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import EnvironmentCatalog from './EnvironmentCatalog'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('./api', () => ({ api: { get } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

it('shows verified starting points, locked contents, recovery timing and limitations', async () => {
  get.mockResolvedValue({ enabled: true, items: [{
    id: 'python-public', type: 'public_image', topic_types: ['基础工具'],
    image: 'registry.example/python:fixed', restore_command: '', contents: { python: '3.10.6' },
    smoke_command: 'python3 --version', last_verified_at: '2026-10-05', restore_seconds: { sandbox: 32.1 },
    reproduction_md: 'FROM registry.example/python:fixed', known_issues: ['未包含重型科学依赖'],
    receipts: [{ channel: 'sandbox', source: 'fixture://receipt', receipt_sha256: 'a'.repeat(64) }],
  }] })
  render(<EnvironmentCatalog />)
  await userEvent.click(screen.getByRole('button', { name: '查看环境目录' }))
  expect(get).toHaveBeenCalledWith('/api/v1/environment-catalog')
  expect(await screen.findByText(/python-public · 公共镜像/)).toBeTruthy()
  expect(screen.getByText(/python 3.10.6/)).toBeTruthy()
  expect(screen.getByText(/sandbox 32.1秒/)).toBeTruthy()
  expect(screen.getByText('未包含重型科学依赖')).toBeTruthy()
})

it('keeps a disabled catalog visible and reports missing or failed queries accurately', async () => {
  get.mockResolvedValue({ enabled: false, items: [] })
  render(<EnvironmentCatalog />)
  await userEvent.click(screen.getByRole('button', { name: '查看环境目录' }))
  expect(await screen.findByRole('status')).toHaveProperty('textContent', '环境目录已关闭')
  get.mockRejectedValue(new Error('fixture unavailable'))
  await userEvent.click(screen.getByRole('button', { name: '查看环境目录' }))
  expect(await screen.findByText('fixture unavailable')).toBeTruthy()
})
