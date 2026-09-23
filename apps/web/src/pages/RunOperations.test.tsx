import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import { RunOperations } from './RunOperations'
vi.mock('../api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

it('keeps unknown work occupied and prevents stopping without a remote ID', async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith('/jobs') ? {
    items: [{ operation_id: 'uncertain', platform_job_id: null, status: 'unknown' }], reserved_jobs: 1, active_or_unknown: 1,
  } : { state: 'idle' })
  render(<RunOperations runId="run-a" phase="running" />)
  await screen.findByText('远端 ID 未知')
  expect((screen.getByText('停止此任务') as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByText('整理本轮经验') as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText(/已占用 1 个 Job/)).toBeTruthy()
})

it('curates the selected paused Run and reuses the operation ID after an uncertain receipt', async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith('/jobs') ? {
    items: [], reserved_jobs: 0, active_or_unknown: 0,
  } : { state: 'idle' })
  vi.mocked(api.post).mockRejectedValue(new Error('connection lost'))
  render(<RunOperations runId="run-paused" phase="paused" />)
  fireEvent.click(screen.getByText('整理本轮经验'))
  await screen.findByText('connection lost')
  fireEvent.click(screen.getByText('整理本轮经验'))
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
  const [first, second] = vi.mocked(api.post).mock.calls
  expect(first[0]).toBe('/api/v1/runs/run-paused/curation')
  expect(first[1]).toEqual(second[1])
})
