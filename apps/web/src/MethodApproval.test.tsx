import { render,screen,fireEvent,waitFor,cleanup } from '@testing-library/react'
import { vi,test,expect,afterEach } from 'vitest'
import { MethodApproval } from './MethodApproval'
import { api } from './api'
vi.mock('./api',()=>({api:{get:vi.fn(),post:vi.fn()}}))
afterEach(()=>{cleanup();vi.clearAllMocks()})
const proposal={method_md:'全量方法正文',parameters_md:'参数',basis_md:'依据',outputs_md:'产物',capabilities:['Bohrium']}
for(const [action,label] of [['approve','批准初始方法'],['modify','修改后批准初始方法'],['reject','驳回初始方法']]) {
 test(`durable ${action} through labelled control`,async()=>{
  vi.mocked(api.get).mockResolvedValue({status:'pending',version:2,proposal} as never)
  vi.mocked(api.post).mockResolvedValue({} as never)
  render(<MethodApproval runId="r" />)
  await screen.findByText('全量方法正文')
  fireEvent.change(screen.getByLabelText('方法批准人'),{target:{value:'monitor'}})
  fireEvent.change(screen.getByLabelText('方法修改或驳回理由'),{target:{value:'遵守题面'}})
  fireEvent.click(screen.getByLabelText(label))
  await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/runs/r/method',expect.objectContaining({action,actor:'monitor',text:'遵守题面',version:2})))
 })
}
test('copy preserves the entire method proposal',async()=>{
 const writeText=vi.fn().mockResolvedValue(undefined)
 Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText}})
 vi.mocked(api.get).mockResolvedValue({status:'pending',version:1,proposal} as never)
 render(<MethodApproval runId="r" />);await screen.findByText('全量方法正文')
 fireEvent.click(screen.getByLabelText('复制方法提案'))
 expect(JSON.parse(writeText.mock.calls[0][0])).toEqual(proposal)
})
