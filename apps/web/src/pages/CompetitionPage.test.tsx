import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CompetitionPage from './CompetitionPage'
const { get, post, put, toast } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), toast: vi.fn() }))
vi.mock('../api', () => ({ api: { get, post, put } }))
vi.mock('../app-context', () => ({ useApp: () => ({ toast, demoMode: false }) }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

it('shows unlimited resources and preserves explicit authorization through confirmation', async () => {
  get.mockImplementation(async (path: string) => path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : detail)
  post.mockResolvedValue({ ...detail, status: 'running' })
  render(<CompetitionPage />)
  await screen.findByText(/easy · deepseek-flash/)
  expect((screen.getByLabelText('比赛资源不限') as HTMLInputElement).checked).toBe(true)
  expect(screen.getAllByText('不限').length).toBeGreaterThanOrEqual(3)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  expect(post.mock.calls[0][1].template.authorization).toMatchObject({ unlimited_resources: true, max_submissions: 0 })
})

it('keeps bounded template values when unlimited authorization is switched off', async () => {
  get.mockImplementation(async (path: string) => path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : detail)
  post.mockResolvedValue({ ...detail, status: 'running' })
  render(<CompetitionPage />)
  await screen.findByText(/easy · deepseek-flash/)
  const user = userEvent.setup()
  await user.click(screen.getByLabelText('比赛资源不限'))
  expect((screen.getByLabelText('每 Run Job 数') as HTMLInputElement).value).toBe('2')
  await user.click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  expect(post.mock.calls[0][1].template.authorization).toMatchObject({ unlimited_resources: false, max_jobs: 2, max_submissions: 0 })
})
const detail = { id: 'round_one', label: '', status: 'draft', resources: { sessions: [{ provider: 'codex', used: 2 }], rate_limits: [] }, items: [
  { id: 'ri_one', challenge_id: 'same_challenge', title: '测试题', run_id: null, phase: 'queued', priority: 0, paused: 0,
    local_best: null, platform_best: null, trace_diagnostic: null, usage: [], cost: null, next_action: '等待资源名额',
    triage: { difficulty: 'easy', recommended_model: 'deepseek-flash', reason: '公开输入较小', estimated_minutes: 10, estimated_cost_cny: null } },
] }
it('keeps an explicit topic resource grant visible and independent from the round template', async () => {
  get.mockImplementation(async (path: string) => path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : detail)
  post.mockResolvedValue({ ...detail, status: 'running' })
  render(<CompetitionPage />)
  await screen.findByText(/easy · deepseek-flash/)
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('测试题给 PI 的备注'), '显式题目授权')
  await user.click(screen.getByLabelText('比赛资源不限'))
  expect((screen.getByLabelText('测试题资源不限') as HTMLInputElement).checked).toBe(true)
  expect(screen.queryByLabelText('测试题Job 数')).toBeNull()
  await user.click(screen.getByLabelText('测试题资源不限'))
  expect(screen.getByLabelText('测试题Job 数')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  expect(post.mock.calls[0][1].overrides.same_challenge.authorization.unlimited_resources).toBe(false)
})
it('shows confirmed versus unknown facts and requires a bounded template before queueing', async () => {
  get.mockImplementation(async (path: string) => path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : detail)
  post.mockResolvedValue({ ...detail, status: 'running' })
  render(<CompetitionPage />)
  expect(await screen.findByText(/easy · deepseek-flash/)).toBeTruthy()
  expect(screen.getByText('等待资源名额')).toBeTruthy()
  expect(screen.getAllByText('unknown').length).toBeGreaterThan(1)
  await userEvent.setup().click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  expect(post.mock.calls[0][0]).toBe('/api/v1/rounds/round_one/confirm')
  expect(post.mock.calls[0][1].template.authorization.max_submissions).toBe(0)
  expect(post.mock.calls[0][1].template.authorization.max_environment_saves).toBe(0)
  await userEvent.setup().click(await screen.findByRole('button', { name: '按当前模板追加 Run' }))
  expect(post.mock.calls[1][1].challenge_id).toBe('same_challenge')
})

it('only shows shutdown readiness from the backend receipt', async () => {
  get.mockResolvedValue({ items: [] })
  post.mockResolvedValue({ can_shutdown: false, message: '暂停尚未确认，暂不能关机', remote_jobs: [{ status: 'unknown' }], remote_sandboxes: [] })
  render(<CompetitionPage />)
  await userEvent.setup().click(screen.getByRole('button', { name: '安全关机' }))
  expect(await screen.findByText('暂停尚未确认，暂不能关机')).toBeTruthy()
  expect(screen.getByText('远程任务继续运行和计费。')).toBeTruthy()
  expect(post.mock.calls[0][0]).toBe('/api/v1/system/safe-shutdown')
})

it('confirms native provider, effort and PI note overrides for a specific topic', async () => {
  get.mockImplementation(async (path: string) => path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : detail)
  post.mockResolvedValue({ ...detail, status: 'running' })
  render(<CompetitionPage />)
  await screen.findByText(/easy · deepseek-flash/)
  const user = userEvent.setup()
  await user.selectOptions(screen.getByLabelText('PI 提供方'), 'kimi')
  await user.selectOptions(screen.getByLabelText('PI 思考强度'), 'high')
  await user.selectOptions(screen.getByLabelText('测试题求解者 提供方'), 'kimi')
  await user.selectOptions(screen.getByLabelText('测试题求解者 思考强度'), 'medium')
  await user.type(screen.getByLabelText('测试题给 PI 的备注'), '需要明确推导步骤')
  await user.click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  const body = post.mock.calls[0][1]
  expect(body.template.model_config.brain).toMatchObject({ runtime: 'kimi', reasoning_effort: 'high' })
  expect(body.overrides.same_challenge.model_config.executor).toMatchObject({ runtime: 'kimi', reasoning_effort: 'medium' })
  expect(body.overrides.same_challenge.solver_note).toBe('需要明确推导步骤')
})

it('uses a concrete roster entry and clears its selection after a manual executor edit', async () => {
  const entry = { id: 'cheap', name: '便宜条目', runtime: 'codex', provider: 'deepseek', model_id: 'deepseek-flash', reasoning_effort: 'high', note: '具体派活' }
  get.mockImplementation(async (path: string) => path === '/api/v1/settings' ? { solver_roster: [entry] } : path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : detail)
  post.mockResolvedValue({ ...detail, status: 'running' })
  render(<CompetitionPage />)
  await screen.findByText(/easy · deepseek-flash/)
  const user = userEvent.setup()
  await user.selectOptions(screen.getByLabelText('整轮求解者条目'), 'cheap')
  expect((screen.getByLabelText('求解者 模型') as HTMLInputElement).value).toBe('deepseek-flash')
  await user.selectOptions(screen.getByLabelText('求解者 提供方'), 'codex')
  await user.clear(screen.getByLabelText('求解者 模型'))
  await user.type(screen.getByLabelText('求解者 模型'), 'gpt-6.1-sol')
  await user.click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  expect(post.mock.calls[0][1].template.solver_id).toBeUndefined()
  expect(post.mock.calls[0][1].template.model_config.executor).toMatchObject({ provider: 'codex', model_id: 'gpt-6.1-sol' })
})
