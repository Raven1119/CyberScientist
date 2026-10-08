import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { vi, test, expect, afterEach } from 'vitest'
import { AccountRoles } from './AccountRoles'
import { api } from './api'
afterEach(cleanup)
vi.mock('./api', () => ({api: {get:vi.fn(),put:vi.fn()}}))
test('shows pending owner claim, changes role and controls harvest through API', async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith('mailboxes') ? {items:[{id:'a',email:'test',status:'active',role:'experiment',claim_status:'pending'}]} : {features:{auto_harvest:false}} as never)
  vi.mocked(api.put).mockResolvedValue({} as never)
  render(<AccountRoles />)
  await screen.findByText('等待主人认领')
  fireEvent.change(screen.getByLabelText('test账号角色'),{target:{value:'harvest'}})
  await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/v1/mailboxes/a/role',{role:'harvest'}))
  await waitFor(() => expect((screen.getByLabelText('切换收割开关') as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByLabelText('切换收割开关'))
  await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/v1/features/auto_harvest',{enabled:true}))
})
test('checks latest version and only offers a manual update notice', async () => {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith('official-cli') ? {version:'0.1.40',latest:'0.1.41',update_available:true} : path.endsWith('mailboxes') ? {items:[]} : {features:{}} as never)
  render(<AccountRoles />)
  fireEvent.click(screen.getByLabelText('检查官方CLI更新'))
  await screen.findByText('官方CLI有新版本 0.1.41，当前 0.1.40；需人工升级')
})
