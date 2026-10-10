import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import { RunOperations } from './RunOperations'
vi.mock('../api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

it('does not replace a reconciled Job with an older in-flight poll response', async () => {
  let resolveOld!: (value: unknown) => void
  const old = new Promise(resolve => { resolveOld = resolve })
  let jobReads = 0
  vi.mocked(api.get).mockImplementation(path => path.endsWith('/jobs')
    ? (++jobReads === 1 ? old : Promise.resolve({ items: [{ operation_id: 'job-a', platform_job_id: 123,
      status: 'Finished', retrieval_status: 'retrieved' }], reserved_jobs: 1, active_or_unknown: 0 }))
    : Promise.resolve({ state: 'idle', items: [], active_or_unknown: 0, cumulative_minutes: 0 }))
  vi.mocked(api.post).mockResolvedValue({})
  render(<RunOperations runId="run-a" phase="running" />)
  fireEvent.click(screen.getByText('核对远端状态'))
  await screen.findByText('Finished')
  resolveOld({ items: [{ operation_id: 'job-a', platform_job_id: 123, status: 'unknown' }],
    reserved_jobs: 1, active_or_unknown: 1 })
  await waitFor(() => expect(jobReads).toBe(2))
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(screen.getByText('Finished')).toBeTruthy()
  expect(screen.queryByText('unknown')).toBeNull()
})

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

it('shows a finished job whose result retrieval failed', async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith('/jobs') ? {
    items: [{ operation_id: 'job-a', platform_job_id: 123, status: 'Finished', retrieval_status: 'failed' }],
    reserved_jobs: 1, active_or_unknown: 0,
  } : { state: 'idle' })
  render(<RunOperations runId="run-a" phase="running" />)
  expect(await screen.findByText('完成 · 结果未取回')).toBeTruthy()
  expect(screen.getByText('结果取回：失败')).toBeTruthy()
})

it('shows a sandbox and deletes only a known active one', async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith('/jobs') ? {
    items: [], reserved_jobs: 0, active_or_unknown: 0,
  } : path.endsWith('/sandboxes') ? {
    items: [{ operation_id: 'box-a', sandbox_id: 'fixture--box-001', status: 'active',
      expires_at: '2026-09-27T12:00:00Z', alive_minutes: 2.5,
      request: { image: 'fixture/image:v1' } }], active_or_unknown: 1, cumulative_minutes: 2.5,
  } : { state: 'idle' })
  vi.mocked(api.post).mockResolvedValue({})
  render(<RunOperations runId="run-a" phase="running" />)
  expect(await screen.findByText('fixture/image:v1')).toBeTruthy()
  expect(screen.getByText(/累计存活 2.5 分钟/)).toBeTruthy()
  fireEvent.click(screen.getByText('删除沙箱'))
  await waitFor(() => expect(api.post).toHaveBeenCalledWith(
    '/api/v1/runs/run-a/sandboxes/fixture--box-001/delete', undefined))
})
