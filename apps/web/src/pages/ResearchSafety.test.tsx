import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ResearchPage from './ResearchPage'
import type { RunEvent } from '../types'

const { get, post, listSkills, toast, setCurrentChallengeId, stream, context } = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), listSkills: vi.fn(), toast: vi.fn(), setCurrentChallengeId: vi.fn(),
  stream: new Map<string, (event: RunEvent) => void>(),
  context: { currentChallengeId: null as string | null },
}))
vi.mock('../api', () => ({ api: { get, post }, listSkills, ApiError: class extends Error {} }))
vi.mock('../app-context', () => ({ useApp: () => ({ toast, setCurrentChallengeId, demoMode: true, ...context }) }))
vi.mock('../useRunEventStream', () => ({ useRunEventStream: (id: string, cb: (event: RunEvent) => void) => {
  if (id) stream.set(id, cb)
} }))
vi.mock('../design/Observation', () => ({ Observation: () => null }))
vi.mock('./RunOperations', () => ({ RunOperations: () => null }))

const summary = (id: string, phase = 'running') => ({ id: `run-${id}`, challenge_id: id, phase,
  mode: 'demo', created_at: '2026-09-28T00:00:00Z' })
const detail = (id: string, phase = 'running') => ({ ...summary(id, phase),
  intention: `${id} intention`, trials: [], budget: null, config_snapshot: {}, current_trial_id: `trial-${id}` })
const challenge = (id: string) => ({ id, title: `${id} details`, contract_status: 'unknown', is_demo: true })
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}
function data(path: string): unknown {
  if (path === '/api/v1/challenges') return { items: ['A', 'B'].map(challenge) }
  if (path === '/api/v1/runs') return { items: ['A', 'B'].map(id => summary(id)) }
  if (path === '/api/v1/runs/overview') return { items: [] }
  if (path === '/api/v1/settings') return { run_defaults: { max_model_turns: 0, max_run_minutes: 30, max_jobs: 0, max_submissions: 0 } }
  if (path.endsWith('/supervision')) return null
  if (path.endsWith('/checkpoints')) return { items: [] }
  if (/\/challenges\/[AB]$/.test(path)) return challenge(path.slice(-1))
  if (/\/runs\/run-[AB]$/.test(path)) return detail(path.slice(-1))
  throw new Error(path)
}
beforeEach(() => {
  context.currentChallengeId = null
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
  get.mockImplementation(async path => data(path))
  listSkills.mockResolvedValue({ skills: [], always_on: [], bound: [] })
  post.mockResolvedValue({})
})
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); stream.clear() })

describe('research selection and lifecycle safety', () => {
  it('labels the selected Run frozen model separately from next research defaults', async () => {
    get.mockImplementation(async path => path === '/api/v1/runs/run-A'
      ? { ...detail('A'), config_snapshot: { settings: { brain: { model_id: 'frozen-pi', reasoning_effort: 'xhigh' },
          executor: { model_id: 'frozen-executor', reasoning_effort: 'high' } } } }
      : path === '/api/v1/challenges/A' ? { ...challenge('A'), model_config: {
          brain: { runtime: 'codex', model_id: 'next-pi' }, executor: { runtime: 'codex', model_id: 'next-executor' } } } : data(path))
    render(<ResearchPage />)
    await screen.findByText('A intention')
    expect(screen.getByLabelText('本轮冻结模型').textContent).toContain('frozen-executor / high')
    expect(screen.getByText(/下次研究模型/).textContent).toContain('next-executor')
  })
  it.each(['created', 'paused', 'recovering'])('does not offer steering a %s Run', async phase => {
    get.mockImplementation(async path => path === '/api/v1/runs' ? { items: [summary('A', phase)] }
      : path === '/api/v1/runs/run-A' ? detail('A', phase) : data(path))
    render(<ResearchPage />)
    await screen.findByText('A intention')
    fireEvent.change(screen.getByLabelText('指导内容'), { target: { value: 'unsent draft' } })
    expect(screen.getByRole('button', { name: '发送指导' }).matches(':disabled')).toBe(true)
    expect(post).not.toHaveBeenCalled()
  })
  it('refreshes stored scores without requiring a new SSE event or submitting anything', async () => {
    vi.useFakeTimers()
    let score = 64.79
    get.mockImplementation(async (path: string) => path === '/api/v1/challenges/A/submissions'
      ? { items: [] } : path === '/api/v1/challenges/A/local-scores'
        ? { scorer: null, calibrations: [], local_scores: [{ id: 'verified', run_id: 'run-A',
          science_score: score, score_source: 'executor_verified', package_sha256: 'abcdef1234569999' }] }
        : data(path))
    render(<ResearchPage />)
    await act(async () => { await Promise.resolve() })
    await act(async () => fireEvent.click(screen.getByRole('tab', { name: '提交与评分' })))
    expect(screen.getByText(/科学分 64.79/)).toBeTruthy()
    score = 100
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(screen.getByText(/科学分 100/)).toBeTruthy()
    expect(post).not.toHaveBeenCalled()
  })
  it('keeps each parallel question guidance draft and switches views without control requests', async () => {
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A intention')
    await user.type(screen.getByLabelText('指导内容'), 'A unsent draft')
    await user.selectOptions(screen.getByLabelText('切换题目'), 'B')
    await screen.findByText('B intention')
    await user.type(screen.getByLabelText('指导内容'), 'B unsent draft')
    await user.selectOptions(screen.getByLabelText('切换题目'), 'A')
    await screen.findByText('A intention')
    expect((screen.getByLabelText('指导内容') as HTMLTextAreaElement).value).toBe('A unsent draft')
    expect(post).not.toHaveBeenCalled()
  })
  it('lets the user inspect an older Run of the same question without controlling either Run', async () => {
    get.mockImplementation(async (path: string) => path === '/api/v1/runs'
      ? { items: [summary('A'), { ...summary('A', 'finished'), id: 'run-A-old', created_at: '2026-09-27T00:00:00Z' }] }
      : path === '/api/v1/runs/run-A-old' ? { ...detail('A', 'finished'), id: 'run-A-old', intention: 'older A intention' }
      : path === '/api/v1/runs/run-A-old/supervision' ? null
      : path.startsWith('/api/v1/runs/run-A-old/') ? { items: [] } : data(path))
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A intention')
    await user.selectOptions(screen.getByLabelText('查看 Run'), 'run-A-old')
    await screen.findByText('older A intention')
    expect(screen.queryByText('A intention')).toBeNull()
    await user.selectOptions(screen.getByLabelText('查看 Run'), 'run-A')
    await screen.findByText('A intention')
    expect(post).not.toHaveBeenCalled()
  })
  it('shows formally registered executor scores with their source and package', async () => {
    get.mockImplementation(async (path: string) => path === '/api/v1/challenges/A/submissions'
      ? { items: [] } : path === '/api/v1/challenges/A/local-scores'
        ? { scorer: null, calibrations: [], local_scores: [{ id: 'verified-score', run_id: 'run-A',
          science_score: 64.79, score_source: 'executor_verified', package_sha256: 'abcdef1234569999' }] }
        : data(path))
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A intention')
    await user.click(screen.getByRole('tab', { name: '提交与评分' }))
    expect((await screen.findByText(/科学分 64.79/)).textContent).toContain('执行器运行，经系统核对')
    expect(screen.getByText(/abcdef123456/)).toBeTruthy()
  })
  it('does not show a stale package preflight after the package path changes', async () => {
    const old = deferred<unknown>()
    get.mockImplementation(async (path: string) => path === '/api/v1/challenges/A/submissions'
      ? { items: [] } : path === '/api/v1/challenges/A/local-scores'
        ? { scorer: null, calibrations: [] } : data(path))
    post.mockImplementation((path: string) => path.endsWith('/submissions/preflight')
      ? old.promise : Promise.resolve({}))
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A intention')
    await user.click(screen.getByRole('tab', { name: '提交与评分' }))
    const input = await screen.findByLabelText(/工作区相对包路径/) as HTMLInputElement
    await user.type(input, 'first.zip')
    await user.click(screen.getByRole('button', { name: '检查封存包' }))
    await user.clear(input)
    await user.type(input, 'second.zip')
    await act(async () => { old.resolve({
      sealed_package_sha256: 'old-package', error_code: null,
      admission: { verdict: 'admitted', signals: {} },
      trace_diagnostics: { status: 'ready', checklist_cap: 49, advisories: [], details: [] },
    }) })
    expect(screen.queryByText(/old-package/)).toBeNull()
    expect(input.value).toBe('second.zip')
    post.mockImplementation((path: string) => path.endsWith('/submissions/preflight')
      ? Promise.resolve({ sealed_package_sha256: 'new-package', error_code: null,
        admission: { verdict: 'admitted', signals: {} },
        trace_diagnostics: { status: 'ready', checklist_cap: 49,
          advisories: [{ code: 'N09_NO_EXECUTION_EVIDENCE', grade: 'reliable',
            reason: '缺真实执行', action: '执行真实计算', implied_cap: 49 }],
          details: [{ code: 'N04_TRACE_SCHEMA_INVALID', grade: 'unavailable',
            reason: '结构异常', implied_cap: 20 }] },
      }) : Promise.resolve({}))
    await user.click(screen.getByRole('button', { name: '检查封存包' }))
    await screen.findByText(/new-package/)
    expect(screen.getByText(/N09_NO_EXECUTION_EVIDENCE/).textContent).toContain('执行真实计算')
    await user.click(screen.getByText(/查看全部触发项/))
    expect(screen.getByText(/N04_TRACE_SCHEMA_INVALID/).textContent).toContain('未知')
  })

  it('keeps the selected challenge when returning from another page', async () => {
    context.currentChallengeId = 'B'
    render(<ResearchPage />)
    await screen.findByText('B intention')
    expect((screen.getByLabelText('切换题目') as HTMLSelectElement).value).toBe('B')
    expect(setCurrentChallengeId).not.toHaveBeenCalledWith(null)
  })

  it('ignores delayed challenge and Run responses after switching to another question', async () => {
    const oldChallenge = deferred<unknown>(), oldRun = deferred<unknown>()
    get.mockImplementation((path: string) => path === '/api/v1/challenges/A' ? oldChallenge.promise
      : path === '/api/v1/runs/run-A' ? oldRun.promise : Promise.resolve(data(path)))
    const user = userEvent.setup()
    render(<ResearchPage />)
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/runs/run-A'))
    await user.selectOptions(screen.getByLabelText('切换题目'), 'B')
    await screen.findByText('B intention')
    await act(async () => { oldChallenge.resolve(challenge('A')); oldRun.resolve(detail('A', 'finished')) })
    expect(screen.queryByText('A intention')).toBeNull()
    expect(document.querySelector('.challenge-title')?.textContent).toBe('B details')
    expect(screen.getByRole('button', { name: '暂停研究' })).toBeTruthy()
  })

  it('clears old checkpoints immediately and ignores a late checkpoint response', async () => {
    const old = deferred<unknown>()
    get.mockImplementation((path: string) => path === '/api/v1/runs/run-A/checkpoints' ? old.promise
      : Promise.resolve(path === '/api/v1/runs/run-B/checkpoints'
        ? { items: [{ report: 'B checkpoint', evidence_refs: [] }] } : data(path)))
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A intention')
    await user.click(screen.getByRole('tab', { name: '检查点' }))
    await user.selectOptions(screen.getByLabelText('切换题目'), 'B')
    await screen.findByText('B checkpoint')
    await act(async () => { old.resolve({ items: [{ report: 'A checkpoint', evidence_refs: [] }] }) })
    expect(screen.queryByText('A checkpoint')).toBeNull()
    expect(screen.getByText('B checkpoint')).toBeTruthy()
  })

  it.each(['guidance.queued', 'guidance.sent', 'guidance.acknowledged'])('does not treat unrelated %s as consumption of user guidance', async (type) => {
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A intention')
    await user.type(screen.getByLabelText('指导内容'), 'check my evidence')
    await user.click(screen.getByRole('button', { name: '发送指导' }))
    await screen.findByText('已排队，等待大脑审阅后投递。')
    act(() => stream.get('run-A')!({ event_id: 'unrelated', seq: 1, occurred_at: new Date().toISOString(),
      source: 'brain', type, trial_id: null, payload: { kind: 'steer', guidance_id: 'other' } }))
    expect(screen.queryByText(/指导已被 Run 消费/)).toBeNull()
    expect(screen.getByText('已排队，等待大脑审阅后投递。')).toBeTruthy()
  })

  it('retries authorization for the already-created Run instead of creating another Run', async () => {
    get.mockImplementation(async path => path === '/api/v1/runs' ? { items: [] }
      : path === '/api/v1/runs/run-created' ? { phase: 'created' } : data(path))
    let failed = false
    post.mockImplementation(async path => {
      if (path === '/api/v1/runs') return { id: 'run-created' }
      if (path.endsWith('/authorize') && !failed) { failed = true; throw new Error('temporary failure') }
      return {}
    })
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A details', { selector: '.challenge-title' })
    await user.click(screen.getByRole('button', { name: '开始研究' }))
    await user.click(screen.getByRole('button', { name: '确认并开始' }))
    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.stringContaining('temporary failure')))
    await user.click(screen.getByRole('button', { name: /确认并开始|授权并启动现有 Run/ }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/runs/run-created/start'))
    expect(post.mock.calls.filter(([path]) => path === '/api/v1/runs')).toHaveLength(1)
  })

  it('offers authorization for an existing created Run after a page reload', async () => {
    get.mockImplementation(async path => path === '/api/v1/runs' ? { items: [summary('A', 'created')] }
      : path === '/api/v1/runs/run-A' ? detail('A', 'created') : data(path))
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A intention')
    await user.click(screen.getByRole('button', { name: '查看研究' }))
    await user.click(await screen.findByRole('button', { name: '授权并启动现有 Run' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/runs/run-A/start'))
    expect(post.mock.calls.some(([path]) => path === '/api/v1/runs')).toBe(false)
  })

  it('stops blind create retries after a lost creation response', async () => {
    get.mockImplementation(async path => path === '/api/v1/runs' ? { items: [] } : data(path))
    post.mockRejectedValue(new Error('connection lost'))
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A details', { selector: '.challenge-title' })
    await user.click(screen.getByRole('button', { name: '开始研究' }))
    await user.click(screen.getByRole('button', { name: '确认并开始' }))
    await screen.findByText(/创建结果未知/)
    expect((screen.getByRole('button', { name: '确认并开始' }) as HTMLButtonElement).disabled).toBe(true)
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('waits for authorization defaults before allowing budget edits or starting', async () => {
    const settings = deferred<unknown>()
    get.mockImplementation((path: string) => path === '/api/v1/settings' ? settings.promise
      : Promise.resolve(path === '/api/v1/runs' ? { items: [] } : data(path)))
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A details', { selector: '.challenge-title' })
    await user.click(screen.getByRole('button', { name: '开始研究' }))
    expect(screen.getByRole('button', { name: '确认并开始' }).matches(':disabled')).toBe(true)
    expect(screen.getByLabelText('算力上限（Bohrium Job 数）').matches(':disabled')).toBe(true)
    await act(async () => settings.resolve(data('/api/v1/settings')))
    await waitFor(() => expect(screen.getByRole('button', { name: '确认并开始' }).matches(':disabled')).toBe(false))
  })

  it('accepts only the matching review receipt even if it precedes the HTTP response', async () => {
    const response = deferred<unknown>()
    post.mockReturnValue(response.promise)
    const user = userEvent.setup()
    render(<ResearchPage />)
    await screen.findByText('A intention')
    await user.type(screen.getByLabelText('指导内容'), 'correlated message')
    await user.click(screen.getByRole('button', { name: '发送指导' }))
    const op = post.mock.calls[0][1].operation_id
    const event = { event_id: 'receipt', seq: 1, occurred_at: new Date().toISOString(), source: 'controller',
      type: 'user.steer.review_queued', trial_id: null, payload: { operation_id: 'unrelated' } }
    act(() => stream.get('run-A')!(event))
    expect(screen.queryByText(/已进入大脑审阅队列/)).toBeNull()
    act(() => stream.get('run-A')!({ ...event, event_id: 'matching-receipt', seq: 2, payload: { operation_id: op } }))
    await screen.findByText('已进入大脑审阅队列；尚未确认执行器接收。')
    await act(async () => { response.resolve({ status: 'queued' }) })
    expect(screen.getByText('已进入大脑审阅队列；尚未确认执行器接收。')).toBeTruthy()
  })
})
