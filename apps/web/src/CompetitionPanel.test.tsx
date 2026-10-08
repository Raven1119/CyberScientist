import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react'
import {test,expect,vi,afterEach} from 'vitest'
import {CompetitionPanel} from './CompetitionPanel'
import {api} from './api'
vi.mock('./api',()=>({api:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}))
vi.mock('./MethodApproval',()=>({MethodApproval:()=>null}))
vi.mock('./AccountRoles',()=>({AccountRoles:()=>null}))
afterEach(()=>{cleanup();vi.clearAllMocks()})
const row={run_id:'run',challenge_id:'topic',title:'题',track:'赛道',phase:'探索',run_phase:'running',current_trial_id:'trial',method_summary:'完整方法摘要',scoring_seconds:null,next_step:'继续研究',submission_held:false,mailbox_id:null,executor:{model_id:'gpt-5.6-terra'},receipt:null}
function setup(phase='running'){
 vi.mocked(api.get).mockImplementation(async path=>path.endsWith('mailboxes')?{items:[{id:'account',email:'本人账号',role:'experiment',status:'active'}]}:{items:[{...row,run_phase:phase}],auto_submission:true,distributions:[],repairs:[],alerts:[]} as never)
 vi.mocked(api.post).mockResolvedValue({} as never);vi.mocked(api.put).mockResolvedValue({} as never)
 render(<CompetitionPanel/>);return screen.findByText('完整方法摘要')
}
for(const [label,phase,path,body] of [
 ['启动','created','/api/v1/runs/run/start',{}],
 ['暂停','running','/api/v1/runs/run/control',{action:'pause'}],
 ['恢复','paused','/api/v1/runs/run/control',{action:'resume'}],
 ['停止','running','/api/v1/runs/run/control',{action:'terminate'}],
 ['立即提交','running','/api/v1/runs/run/submissions',{trial_id:'trial'}],
 ['切换暂缓提交','running','/api/v1/runs/run/panel',{action:'submission_hold',value:true}],
] as const){test(`labelled ${label}`,async()=>{await setup(phase);fireEvent.click(screen.getByLabelText('题'+label));await waitFor(()=>expect(api.post).toHaveBeenCalledWith(path,expect.objectContaining(body)))})}
test('global submission switch',async()=>{await setup();fireEvent.click(screen.getByLabelText('切换全局提交'));await waitFor(()=>expect(api.put).toHaveBeenCalledWith('/api/v1/features/auto_submission',{enabled:false}))})
test('account and executor selections are audited backend controls',async()=>{await setup();fireEvent.change(screen.getByLabelText('题账号分配'),{target:{value:'account'}});await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/runs/run/panel',expect.objectContaining({action:'mailbox',value:'account'})));await waitFor(()=>expect((screen.getByLabelText('题停止') as HTMLButtonElement).disabled).toBe(false));fireEvent.change(screen.getByLabelText('题执行者档位'),{target:{value:'gpt-6-astra'}});await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/runs/run/panel',expect.objectContaining({action:'executor',value:expect.objectContaining({model_id:'gpt-6-astra',fast_mode:true})})))})
test('guidance and clean rerun only enter the PI control route',async()=>{await setup();fireEvent.change(screen.getByLabelText('题给PI指导'),{target:{value:'按科学检查继续'}});fireEvent.click(screen.getByLabelText('题发送PI指导'));await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/runs/run/control',expect.objectContaining({action:'steer',text:'按科学检查继续'})));fireEvent.click(screen.getByLabelText('转干净复跑'));await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/runs/run/control',expect.objectContaining({action:'steer',text:expect.stringContaining('fresh_executor_session=true')})))})

test('renders persisted real-receipt deduction codes',async()=>{
 vi.mocked(api.get).mockImplementation(async path=>path.endsWith('mailboxes')?{items:[]}:{items:[{...row,receipt:{harbor_score:100,trace_score:82.425,trace_decision:'accept',receipt_details_json:JSON.stringify({deductions:[{code:'N11',reason:'fixture'},{code:'N14',reason:'fixture'}]}),email:'本人账号'}}],auto_submission:true,distributions:[],repairs:[],alerts:[]} as never)
 render(<CompetitionPanel/>);expect((await screen.findByText(/N11/)).textContent).toContain('N14')
})
