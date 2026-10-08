import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, test, expect } from 'vitest'
import { AccountRoles } from './AccountRoles'
import { api } from './api'
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
