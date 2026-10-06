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
it('imports transactional JSON and preserves solver and notes through manual edits and confirmation', async () => {
  const entry = { id: 'cheap', name: '便宜条目', runtime: 'codex', provider: 'deepseek', model_id: 'deepseek-flash', reasoning_effort: 'high', note: '明确步骤' }
  const imported = { platform_challenge_id: 'public-topic', solver_entry: entry, pi_notes: '用户报告数据风险', data_status: '用户报告可下载' }
  get.mockImplementation(async (path: string) => path === '/api/v1/settings' ? { solver_roster: [entry] } : path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : detail)
  post.mockImplementation(async (path: string) => path.endsWith('/triage-import') ? { ...detail, items: [{ ...detail.items[0], user_triage: imported }] } : { ...detail, status: 'running' })
  render(<CompetitionPage />)
  await screen.findByText(/easy · deepseek-flash/)
  const user = userEvent.setup()
  const items = [{ platform_challenge_id: 'public-topic', priority: 10, solver_entry: 'cheap', data_status: imported.data_status, pi_notes: imported.pi_notes }]
  await user.click(screen.getByLabelText('事务性分诊 JSON'))
  await user.paste(JSON.stringify(items))
  await user.click(screen.getByRole('button', { name: '导入用户分诊' }))
  expect(post.mock.calls[0]).toEqual(['/api/v1/rounds/round_one/triage-import', { items }])
  expect((screen.getByLabelText('测试题求解者条目') as HTMLSelectElement).value).toBe('cheap')
  await user.type(screen.getByLabelText('测试题给 PI 的备注'), '补充环境建议')
  await user.click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  expect(post.mock.calls[1][1].overrides.same_challenge).toMatchObject({ solver_id: 'cheap', pi_notes: imported.pi_notes, data_status: imported.data_status, model_config: { executor: { provider: 'deepseek' } } })
})

it('rejects malformed pasted JSON without calling backend or changing the draft', async () => {
  get.mockImplementation(async (path: string) => path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : detail)
  render(<CompetitionPage />)
  await screen.findByText(/easy · deepseek-flash/)
  const user = userEvent.setup()
  await user.click(screen.getByLabelText('事务性分诊 JSON')); await user.paste('malformed')
  await user.click(screen.getByRole('button', { name: '导入用户分诊' }))
  expect(post).not.toHaveBeenCalled(); expect(toast).toHaveBeenCalled()
  expect(screen.getByText(/轮次 round_one · draft/)).toBeTruthy()
})
it('sends an explicit null when manually replacing an imported solver entry', async () => {
  const entry = { id: 'cheap', name: '便宜条目', runtime: 'codex', provider: 'deepseek', model_id: 'deepseek-flash', reasoning_effort: 'high', note: '明确步骤' }
  const imported = { platform_challenge_id: 'public-topic', solver_entry: entry, pi_notes: '风险提示', data_status: '待核验' }
  const draft = { ...detail, items: [{ ...detail.items[0], user_triage: imported }] }
  get.mockImplementation(async (path: string) => path === '/api/v1/settings' ? { solver_roster: [entry] } : path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : draft)
  post.mockResolvedValue({ ...draft, status: 'running' })
  render(<CompetitionPage />)
  await screen.findByText(/easy · deepseek-flash/)
  const user = userEvent.setup()
  await user.selectOptions(screen.getByLabelText('测试题求解者 提供方'), 'codex')
  await user.clear(screen.getByLabelText('测试题求解者 模型')); await user.type(screen.getByLabelText('测试题求解者 模型'), 'gpt-6.1-sol')
  await user.click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  const override = JSON.parse(JSON.stringify(post.mock.calls[0][1])).overrides.same_challenge
  expect(override.solver_id).toBeNull()
  expect(override.model_config.executor).toMatchObject({ provider: 'codex', model_id: 'gpt-6.1-sol' })
  expect(override.pi_notes).toBe('风险提示')
})
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
  expect((screen.getByLabelText('PI 提供方') as HTMLSelectElement).disabled).toBe(true)
  expect((screen.getByLabelText('PI 思考强度') as HTMLSelectElement).value).toBe('xhigh')
  expect((screen.getByLabelText('PI 模型') as HTMLInputElement).value).toBe('gpt-6-astra')
  await user.selectOptions(screen.getByLabelText('测试题求解者 提供方'), 'kimi')
  await user.selectOptions(screen.getByLabelText('测试题求解者 思考强度'), 'medium')
  await user.type(screen.getByLabelText('测试题给 PI 的备注'), '需要明确推导步骤')
  await user.click(screen.getByRole('button', { name: '确认模板与授权，开始排队' }))
  const body = post.mock.calls[0][1]
  expect(body.template.model_config.brain).toMatchObject({ runtime: 'codex', model_id: 'gpt-6-astra', reasoning_effort: 'xhigh' })
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
  expect(post.mock.calls[0][1].template.solver_id).toBeNull()
  expect(JSON.parse(JSON.stringify(post.mock.calls[0][1])).template.solver_id).toBeNull()
  expect(post.mock.calls[0][1].template.model_config.executor).toMatchObject({ provider: 'codex', model_id: 'gpt-6.1-sol' })
})

it('shows provider cooldown and native request model throttle facts', async () => {
  const changed = { ...detail, resources: { ...detail.resources, provider_backoff: [{ provider: 'codex', retry_at: 'future' }], native_throttle: [{ provider: 'codex', model_id: 'gpt-6.1-sol', status: 'waiting' }] } }
  get.mockImplementation(async (path: string) => path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : changed)
  render(<CompetitionPage />); await screen.findByText(/easy · deepseek-flash/)
  await userEvent.setup().click(screen.getByText('提供方速率状态'))
  expect(screen.getByText(/"retry_at": "future"/)).toBeTruthy()
  expect(screen.getByText(/"model_id": "gpt-6.1-sol"/)).toBeTruthy()
})

it('sorts known score gaps descending and leaves unknown last without replacing zero', async () => {
  const base = detail.items[0]
  const changed = { ...detail, items: [
    { ...base, id: 'a', challenge_id: 'a', title: '未知题', score_gap: null, leaderboard_best: null, our_best: null },
    { ...base, id: 'b', challenge_id: 'b', title: '小差距题', score_gap: 5, leaderboard_best: 90, our_best: 85 },
    { ...base, id: 'c', challenge_id: 'c', title: '大差距题', score_gap: 80, leaderboard_best: 80, our_best: 0 },
  ] }
  get.mockImplementation(async (path: string) => path === '/api/v1/rounds' ? { items: [{ id: 'round_one', status: 'draft' }] } : changed)
  render(<CompetitionPage />); await screen.findByText('大差距题')
  const rows = screen.getAllByRole('row').slice(1)
  expect(rows[0].textContent).toContain('大差距题')
  expect(rows[1].textContent).toContain('小差距题')
  expect(rows[2].textContent).toContain('未知题')
  expect(rows[0].querySelectorAll('td')[4].textContent).toBe('0')
  expect(rows[2].querySelectorAll('td')[5].textContent).toBe('unknown')
})
