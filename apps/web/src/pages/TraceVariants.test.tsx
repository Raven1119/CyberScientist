import { expect, it, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { TraceVariants } from './TraceVariants'
import type { Submission } from '../types'
const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('../api', () => ({ api: { post } }))
afterEach(() => { cleanup(); sessionStorage.clear(); vi.resetAllMocks() })

it('compares confirmed scores and predictions and requires prediction before submitting', async () => {
  const items = [{ id: 'base', score: 20, score_status: 'scored', score_confidence: 'confirmed', prediction_md: 'base prediction' },
    { id: 'variant', variant_of: 'base', score: 25, score_status: 'scored', science_artifact_match: 1, prediction_md: 'variant prediction' }] as Submission[]
  post.mockResolvedValue({ status: 'submitted' }); const refresh = vi.fn().mockResolvedValue(undefined)
  render(<TraceVariants runId="run-fixture" items={items} refresh={refresh} />)
  expect(screen.getByRole('table').textContent).toContain('base · 20')
  expect(screen.getByRole('table').textContent).toContain('variant · 25')
  expect(screen.getByRole('table').textContent).toContain('哈希一致')
  fireEvent.change(screen.getByLabelText('原提交'), { target: { value: 'base' } })
  expect(screen.getByRole('button', { name: '提交轨迹变体' }).matches(':disabled')).toBe(true)
  fireEvent.change(screen.getByLabelText('变体预测'), { target: { value: 'better documented' } })
  fireEvent.click(screen.getByRole('button', { name: '提交轨迹变体' }))
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/submissions/base/trace-variants',
    expect.objectContaining({ prediction_md: 'better documented', projection_only: true })))
  expect(refresh).toHaveBeenCalled()
})

it('keeps the same operation and prediction after an unknown receipt and labels provisional scores', async () => {
  const items = [{ id: 'base', score: 20, score_status: 'scored', score_confidence: 'confirmed' },
    { id: 'variant', variant_of: 'base', score: 25, score_status: 'scored', score_confidence: 'provisional', score_anomaly: 'pending', science_artifact_match: 1 }] as Submission[]
  post.mockResolvedValue({ status: 'unknown' }); const refresh = vi.fn().mockResolvedValue(undefined)
  render(<TraceVariants runId="run-fixture" items={items} refresh={refresh} />)
  expect(screen.getByRole('table').textContent).toContain('25 · 暂定 · 异常 pending')
  fireEvent.change(screen.getByLabelText('原提交'), { target: { value: 'base' } })
  fireEvent.change(screen.getByLabelText('变体预测'), { target: { value: 'prediction kept' } })
  fireEvent.click(screen.getByRole('button', { name: '提交轨迹变体' }))
  await screen.findByRole('alert')
  const first = post.mock.calls[0][1].operation_id
  expect((screen.getByLabelText('变体预测') as HTMLTextAreaElement).value).toBe('prediction kept')
  fireEvent.click(screen.getByRole('button', { name: '提交轨迹变体' }))
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2))
  expect(post.mock.calls[1][1].operation_id).toBe(first)
})

it('retains only the Run-scoped operation metadata across refresh failure and remount', async () => {
  const items = [{ id: 'base', score: 20, score_status: 'scored', score_confidence: 'confirmed' }] as Submission[]
  post.mockResolvedValue({ status: 'unknown' })
  const refresh = vi.fn().mockRejectedValue(new Error('refresh unavailable'))
  const view = render(<TraceVariants runId="run-fixture" items={items} refresh={refresh} />)
  fireEvent.change(screen.getByLabelText('原提交'), { target: { value: 'base' } })
  fireEvent.change(screen.getByLabelText('变体预测'), { target: { value: 'same intent' } })
  fireEvent.click(screen.getByRole('button', { name: '提交轨迹变体' }))
  await waitFor(() => expect(refresh).toHaveBeenCalled())
  const first = post.mock.calls[0][1].operation_id
  view.unmount()
  render(<TraceVariants runId="run-fixture" items={items} refresh={vi.fn().mockResolvedValue(undefined)} />)
  fireEvent.change(screen.getByLabelText('变体预测'), { target: { value: 'same intent' } })
  fireEvent.click(screen.getByRole('button', { name: '提交轨迹变体' }))
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2))
  expect(post.mock.calls[1][1].operation_id).toBe(first)
  expect(sessionStorage.getItem('cs-trace-variant:run-fixture')).not.toContain('same intent')
})
