import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SettingsPage from './SettingsPage'

const { get, put, post, listSkills, putAlwaysOnSkills, toast } = vi.hoisted(() => ({
  get: vi.fn(), put: vi.fn(), post: vi.fn(), listSkills: vi.fn(), putAlwaysOnSkills: vi.fn(), toast: vi.fn(),
}))
vi.mock('../api', () => ({ api: { get, put, post }, listSkills, putAlwaysOnSkills }))
vi.mock('../app-context', () => ({ useApp: () => ({ toast }) }))

const defaults = {
  revision: 0,
  app: { mode: 'demo' },
  brain: { runtime: 'codex', executable: '', model_id: 'brain', reasoning_effort: 'high' },
  executor: { runtime: 'codex', executable: '', model_id: 'executor', reasoning_effort: 'high' },
  prime: { executable: '', llm_profile_id: '' }, llm_profiles: [],
  playground: { base_url: '', token_secret_ref: '' },
  bohrium: { executable: '', project_id: '', access_key_secret_ref: '', wenyon_executable: '', wenyon_home: '' },
  run_defaults: { max_active_runs: 3, stall_seconds: 300, max_brain_wait_seconds: 3600,
    brain_review_timeout_seconds: 900, rate_limit_max_seconds: 3600 },
  shadow: { max_reviews: 8, min_interval_seconds: 60 }, mailbox: { platform: 'demo' },
  skills: { always_on: [] as string[] },
}
let stored = structuredClone(defaults)
beforeEach(() => {
  stored = structuredClone(defaults)
  get.mockImplementation(async () => structuredClone(stored))
  listSkills.mockImplementation(async () => ({
    skills: [{ id: 'bohrium-job', name: 'Bohrium Job', description: 'Jobs', source: '/skills' }],
    always_on: [...stored.skills.always_on], bound: [],
  }))
  put.mockImplementation(async (_url, body) => {
    if (body.base_revision !== stored.revision) throw new Error('REVISION_CONFLICT')
    stored = { ...structuredClone(body.settings), revision: stored.revision + 1 }
    return structuredClone(stored)
  })
  // Model the old independent writer so the regression reaches both save paths.
  putAlwaysOnSkills.mockImplementation(async (ids: string[]) => {
    stored.skills.always_on = [...ids]
    stored.revision += 1
    return { always_on: ids, revision: stored.revision }
  })
})
afterEach(() => { cleanup(); vi.resetAllMocks() })

describe('settings and skills persist together', () => {
  it('keeps both PI forms fixed to native Astra and saves the migrated choice', async () => {
    const user = userEvent.setup()
    render(<SettingsPage />)
    const model = await screen.findByLabelText('PI模型 ID') as HTMLInputElement
    expect(model.value).toBe('gpt-6-astra')
    expect(model.readOnly).toBe(true)
    expect((screen.getByLabelText('PI提供方') as HTMLSelectElement).options.length).toBe(1)
    expect((screen.getByLabelText('原生代理') as HTMLSelectElement).disabled).toBe(true)
    expect((document.getElementById('brain-model') as HTMLInputElement).readOnly).toBe(true)
    await user.click(screen.getAllByRole('button', { name: '保存设置' })[0])
    await waitFor(() => expect(stored.brain).toMatchObject({runtime:'codex',model_id:'gpt-6-astra',reasoning_effort:'xhigh'}))
  })
  it.each([0, 1])('saves checked skills through page save button %i and survives remount', async (index) => {
    const user = userEvent.setup()
    const view = render(<SettingsPage />)
    await user.click(await screen.findByRole('checkbox', { name: /常驻/ }))
    await user.click(screen.getAllByRole('button', { name: '保存设置' })[index])
    await waitFor(() => expect(stored.skills.always_on).toEqual(['bohrium-job']))
    view.unmount()
    render(<SettingsPage />)
    expect((await screen.findByRole('checkbox', { name: /常驻/ }) as HTMLInputElement).checked).toBe(true)
  })

  it('saves from the skills card then saves other settings without stale revisions or lost drafts', async () => {
    const user = userEvent.setup()
    render(<SettingsPage />)
    await user.click(await screen.findByRole('checkbox', { name: /常驻/ }))
    const limit = screen.getByLabelText('同时活跃的 Run 上限')
    await user.clear(limit)
    await user.type(limit, '5')
    await user.click(screen.getByRole('button', { name: /保存常驻技能|保存设置与技能/ }))
    await waitFor(() => expect(stored.skills.always_on).toEqual(['bohrium-job']))
    expect((limit as HTMLInputElement).value).toBe('5')
    await user.click(screen.getAllByRole('button', { name: '保存设置' })[0])
    await waitFor(() => expect(stored.run_defaults.max_active_runs).toBe(5))
    expect(stored.skills.always_on).toEqual(['bohrium-job'])
    expect(toast.mock.calls.flat().join(' ')).not.toContain('失败')
  })

  it('prevents edits and duplicate saves while the settings write is pending', async () => {
    let resolve!: (value: unknown) => void
    put.mockImplementationOnce(() => new Promise(r => { resolve = r }))
    const user = userEvent.setup()
    render(<SettingsPage />)
    const checkbox = await screen.findByRole('checkbox', { name: /常驻/ })
    await user.click(checkbox)
    await user.click(screen.getAllByRole('button', { name: '保存设置' })[0])
    expect(checkbox.matches(':disabled')).toBe(true)
    expect(screen.getByLabelText('同时活跃的 Run 上限').matches(':disabled')).toBe(true)
    await act(async () => { resolve({ ...structuredClone(stored), revision: 1, skills: { always_on: ['bohrium-job'] } }) })
    await waitFor(() => expect(checkbox.matches(':disabled')).toBe(false))
  })

  it('keeps the draft after a save conflict and allows an explicit reload', async () => {
    const user = userEvent.setup()
    render(<SettingsPage />)
    const checkbox = await screen.findByRole('checkbox', { name: /常驻/ })
    await user.click(checkbox)
    stored.revision += 1 // Another tab saved first.
    await user.click(screen.getAllByRole('button', { name: '保存设置' })[0])
    expect((checkbox as HTMLInputElement).checked).toBe(true)
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('REVISION_CONFLICT'))
    expect(stored.skills.always_on).toEqual([])
    await user.click(screen.getByRole('button', { name: '放弃本页修改并重新加载' }))
    await waitFor(() => expect((checkbox as HTMLInputElement).checked).toBe(false))
  })

  it('recovers a failed catalog load without discarding other setting edits', async () => {
    listSkills.mockRejectedValueOnce(new Error('catalog unavailable'))
    const user = userEvent.setup()
    render(<SettingsPage />)
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('catalog unavailable'))
    const limit = screen.getByLabelText('同时活跃的 Run 上限')
    await user.clear(limit)
    await user.type(limit, '4')
    await user.click(screen.getByRole('button', { name: '重试加载技能' }))
    await screen.findByRole('checkbox', { name: /常驻/ })
    expect((limit as HTMLInputElement).value).toBe('4')
  })

  it('offers a retry instead of an endless spinner when loading settings fails', async () => {
    get.mockRejectedValueOnce(new Error('backend unavailable'))
    const user = userEvent.setup()
    render(<SettingsPage />)
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('backend unavailable'))
    await user.click(screen.getByRole('button', { name: '重新加载设置' }))
    await screen.findByRole('heading', { name: '技能管理' })
  })
})

it('persists separate DeepSeek reviewer choice and a named solver with its PI note', async () => {
  const user = userEvent.setup()
  render(<SettingsPage />)
  await user.selectOptions(await screen.findByLabelText('审查者提供方'), 'deepseek')
  await user.click(screen.getByRole('button', { name: '添加求解者' }))
  await user.clear(screen.getByLabelText('条目名称'))
  await user.type(screen.getByLabelText('条目名称'), '便宜求解者')
  await user.selectOptions(screen.getByLabelText('条目提供方'), 'deepseek')
  await user.type(screen.getByLabelText('给 PI 的备注'), '写死算法和测试')
  await user.click(screen.getAllByRole('button', { name: '保存设置' })[0])
  await waitFor(() => expect(put).toHaveBeenCalled())
  const value = put.mock.calls[0][1].settings
  expect(value.reviewer).toMatchObject({ provider: 'deepseek', runtime: 'codex', model_id: 'deepseek-flash' })
  expect(value.solver_roster[0]).toMatchObject({ name: '便宜求解者', provider: 'deepseek', note: '写死算法和测试' })
})

it('sends replacement semantics for an empty full price editor', async () => {
  const user = userEvent.setup()
  render(<SettingsPage />)
  const editor = await screen.findByLabelText('模型价格表（每百万 token，保留来源和日期）')
  fireEvent.change(editor, { target: { value: '{}' } })
  await user.click(screen.getAllByRole('button', { name: '保存设置' })[0])
  await waitFor(() => expect(put).toHaveBeenCalledWith('/api/v1/settings', expect.objectContaining({
    settings: expect.objectContaining({ model_pricing: {} }), replace_paths: ['model_pricing', 'bohrium.host_overrides'],
  })))
})

it('requires one explicit tool-probe authorization and sends the selected role provider', async () => {
  post.mockResolvedValue({ status: 'ok', tool_receipt: { exit_code: 0 } })
  const user = userEvent.setup()
  render(<SettingsPage />)
  await user.selectOptions(await screen.findByLabelText('复盘提供方'), 'deepseek')
  const button = screen.getByRole('button', { name: '验证复盘工具调用' })
  expect(button.matches(':disabled')).toBe(true)
  await user.click(screen.getByLabelText('授权复盘一次真实工具探针'))
  await user.click(button)
  expect(post.mock.calls[0]).toEqual(['/api/v1/connections/post_review/test', expect.objectContaining({
    kind: 'tool_call_probe', confirm_spend: true, model_choice: expect.objectContaining({ provider: 'deepseek' }),
  })])
  expect(button.matches(':disabled')).toBe(true)
})

it('saves a configured DeepSeek fallback wait and roster entry with the settings', async () => {
  const entry = { id: 'flash', name: '限速后备', runtime: 'codex', provider: 'deepseek', model_id: 'deepseek-flash', reasoning_effort: 'high' }
  get.mockImplementation(async () => ({ ...structuredClone(stored), solver_roster: [entry], deepseek_fallback: { after_minutes: 5, solver_id: '' } }))
  const user = userEvent.setup(); render(<SettingsPage />)
  await user.clear(await screen.findByLabelText('后备等待分钟')); await user.type(screen.getByLabelText('后备等待分钟'), '2')
  await user.selectOptions(screen.getByLabelText('DeepSeek 后备条目'), 'flash')
  await user.click(screen.getAllByRole('button', { name: '保存设置' })[0])
  await waitFor(() => expect(put.mock.calls[put.mock.calls.length - 1]?.[1].settings.deepseek_fallback).toEqual({ after_minutes: 2, solver_id: 'flash' }))
})

it('saves every operational switch off and on and retains each value after refresh', async () => {
  const labels = ['自动收割', '审查者', '评分器审计', '策略卡', 'DeepSeek切换', '协议检测', '等待评分', '共享区', '环境目录', '系统分诊', '本地计算']
  const user = userEvent.setup(); const view = render(<SettingsPage />)
  await screen.findByLabelText('启用自动收割')
  for (const label of labels) await user.click(screen.getByLabelText('启用'+label))
  await user.click(screen.getAllByRole('button', { name: '保存设置' })[0])
  await waitFor(() => expect(put).toHaveBeenCalled())
  expect(Object.values(put.mock.calls[0][1].settings.features)).toEqual(Array(11).fill(false))
  view.unmount(); render(<SettingsPage />); await screen.findByLabelText('启用自动收割')
  for (const label of labels) {
    expect((screen.getByLabelText('启用'+label) as HTMLInputElement).checked).toBe(false)
    await user.click(screen.getByLabelText('启用'+label))
  }
  await user.click(screen.getAllByRole('button', { name: '保存设置' })[0])
  await waitFor(() => expect(Object.values(put.mock.calls[put.mock.calls.length-1][1].settings.features)).toEqual(Array(11).fill(true)))
})
