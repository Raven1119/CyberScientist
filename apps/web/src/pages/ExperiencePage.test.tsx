import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ExperiencePage from './ExperiencePage'

const { get, post, toast } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), toast: vi.fn() }))
vi.mock('../api', () => ({ api: { get, post }, ApiError: class extends Error {} }))
vi.mock('../app-context', () => ({ useApp: () => ({ toast, currentChallengeId: null }) }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

const entry = (id: string) => ({ id, title: id, scope: 'global', status: 'candidate',
  evidence_status: 'hypothesis', kind: 'heuristic', tags: [], evidence_refs: [],
  revision_id: `rev_${id}`, current_hash: `hash_${id}`, applicability: '' })
const detail = (id: string) => ({ id, frontmatter: entry(id), body_md: `body_${id}`,
  revision_id: `rev_${id}`, current_hash: `hash_${id}`, revisions: [] })

describe('experience editor integrity', () => {
  it.each([{ items: [] }, { items: [entry('A')] }])('keeps a new draft when the list refreshes: %j', async ({ items }) => {
    get.mockImplementation(async (url: string) => url.includes('/experiences/') ? detail('A') : { items })
    const user = userEvent.setup()
    render(<ExperiencePage />)
    if (items.length) await waitFor(() => expect((screen.getByLabelText('标题') as HTMLInputElement).value).toBe('A'))
    await user.click(screen.getByRole('button', { name: '新建经验' }))
    await user.type(screen.getByLabelText('标题'), '我的草稿')
    await user.click(screen.getByRole('button', { name: '刷新' }))
    expect((screen.getByLabelText('标题') as HTMLInputElement).value).toBe('我的草稿')
    expect((screen.getByLabelText('ID') as HTMLInputElement).disabled).toBe(false)
  })

  it('ignores the slow A response after the user selects B or creates a draft', async () => {
    let resolveA!: (value: unknown) => void
    const slow = new Promise(resolve => { resolveA = resolve })
    get.mockImplementation((url: string) => url.endsWith('/A') ? slow :
      Promise.resolve(url.endsWith('/B') ? detail('B') : { items: [entry('A'), entry('B')] }))
    const user = userEvent.setup()
    render(<ExperiencePage />)
    await user.click(await screen.findByRole('button', { name: /B ·/ }))
    await waitFor(() => expect((screen.getByLabelText('标题') as HTMLInputElement).value).toBe('B'))
    await act(async () => { resolveA(detail('A')); await slow })
    await waitFor(() => expect((screen.getByLabelText('标题') as HTMLInputElement).value).toBe('B'))
    await user.click(screen.getByRole('button', { name: '新建经验' }))
    expect((screen.getByLabelText('ID') as HTMLInputElement).disabled).toBe(false)
  })

  it('lets users choose delivery audience and keeps environment facts read only', async () => {
    get.mockImplementation(async (url: string) => url.includes('/experiences/') ?
      { ...detail('env_A'), frontmatter: { ...entry('env_A'), kind: 'environment', audience: 'both' } } :
      { items: [{ ...entry('env_A'), kind: 'environment', audience: 'both' }] })
    const user = userEvent.setup()
    render(<ExperiencePage />)
    await user.click(await screen.findByRole('button', { name: /env_A ·/ }))
    await waitFor(() => expect((screen.getByLabelText('投递对象') as HTMLSelectElement).value).toBe('both'))
    expect(screen.getByLabelText('投递对象').matches(':disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '保存新修订' }).matches(':disabled')).toBe(true)
    await user.click(screen.getByRole('button', { name: '新建经验' }))
    await user.selectOptions(screen.getByLabelText('投递对象'), 'executor')
    expect((screen.getByLabelText('投递对象') as HTMLSelectElement).value).toBe('executor')
  })
})
