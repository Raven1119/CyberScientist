import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import GlobalApprovals from './GlobalApprovals'
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('./api', () => ({ api: { get, post } }))
vi.mock('./components', () => ({ Modal: ({ title, children }: { title: string; children: ReactNode }) => <div role="dialog" aria-label={title}>{children}</div> }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
const draft = { id: 'draft', title: '保底经验', scope: 'global', kind: 'heuristic', status: 'candidate', revision_id: 'rev1', evidence_status: 'observed', evidence_refs: ['event:old:1'], body_md: '先保留已知成果。' }
it('reminds again after refresh and approves the displayed revision', async () => {
  get.mockResolvedValue({ items: [draft] }); post.mockResolvedValue({})
  const view = render(<GlobalApprovals />); await screen.findByText('先保留已知成果。')
  fireEvent.click(screen.getByText('稍后处理')); expect(screen.getByText('待审批全局经验（1）')).toBeTruthy()
  view.unmount(); render(<GlobalApprovals />); await screen.findByText('先保留已知成果。')
  fireEvent.click(screen.getByText('批准此版本'))
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/experiences/draft/approve', { expected_revision: 'rev1' }))
  await waitFor(() => expect(screen.queryByText('先保留已知成果。')).toBeNull())
})
it('rejects with a note and retains a conflicted draft until reread', async () => {
  get.mockResolvedValue({ items: [draft] }); post.mockRejectedValueOnce(new Error('409 版本改变')).mockResolvedValue({})
  render(<GlobalApprovals />); await screen.findByText('先保留已知成果。')
  fireEvent.click(screen.getByText('批准此版本'))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '审批未保存：409 版本改变')
  get.mockResolvedValue({ items: [{ ...draft, revision_id: 'rev2', body_md: '新版事务建议' }] })
  fireEvent.click(screen.getByText('重新读取')); await screen.findByText('新版事务建议')
  fireEvent.click(screen.getByText('驳回此版本'))
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/experiences/draft/reject', { expected_revision: 'rev2', note: '用户在审批队列驳回此版本' }))
})
