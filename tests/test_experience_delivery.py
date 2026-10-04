"""Chinese selection, complete indexes and live reads preserve approved versions."""
import asyncio
import pytest
from httpx import ASGITransport,AsyncClient
from cyberscientist import api,collab,config,db,experience_context,experiences
from test_collaboration import _seed_challenge
from cyberscientist.controller import RunController


def entry(identifier,title,body,**extra):
    fm={'title':title,'scope':'challenge','challenge_id':'COLLAB_CH','status':'active',
        'evidence_status':'hypothesis','kind':'procedure','audience':'both','tags':[],
        'applicability':title,'evidence_refs':[],**extra}
    return experiences.save_experience(identifier,fm,body,'user',None,None)


def test_chinese_lean_and_environment_rank_before_unrelated_methodology():
    _seed_challenge()
    entry('aaa-unrelated','社会学访谈方法','抽象的方法论与调查技巧')
    entry('zzz-lean','Lean 数学证明与环境','用固定工具链构建证明，先验证版本再编译。',tags=['Lean','环境'])
    entry('yyy-env','搭建环境并验证依赖','准备环境和依赖版本。')
    selected=experience_context.select('COLLAB_CH',goal='用Lean证明定理并搭建环境')
    assert selected[0]['id']=='zzz-lean'
    assert selected[-1]['id']=='aaa-unrelated'
    assert config.load_settings()['memory']['max_injected_characters']==24000


def test_index_includes_every_effective_title_and_role_while_text_is_bounded():
    _seed_challenge()
    for i in range(8):entry(f'e{i}',f'经验{i}',('可执行配方。'*600),audience='executor' if i%2 else 'brain')
    entry('expired','旧平台','旧事实',expires_at='2000-01-01T00:00:00+00:00')
    ctl=RunController();rid=ctl.create_run('COLLAB_CH')['id']
    settings=config.load_settings();settings['memory']['max_injected_characters']=2500;config.save_settings(settings)
    context=experience_context.freeze(rid,None,'Chinese-index',role='brain')
    assert len(context['index'])==8
    assert all(item['audience']=='brain' for item in context['items'])
    assert len(experience_context.encode(context['items']))+len(experience_context.encode(context['index']))<=2500
    assert len(context['index_sha256'])==64


@pytest.mark.asyncio
async def test_read_tool_returns_updated_active_revision_and_never_activates_candidate():
    _seed_challenge();saved=entry('live','Lean 环境','第一版本')
    experiences.save_experience('global-draft',{'title':'候选','scope':'global','status':'candidate',
        'evidence_status':'hypothesis','kind':'procedure','tags':[],'evidence_refs':[]},'待用户审批','brain',None,None)
    ctl=RunController();rid=ctl.create_run('COLLAB_CH')['id']
    with db.transaction() as conn:token=collab.issue_token(conn,rid,'brain','fixture',1)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://test') as client:
        headers={'Authorization':'Bearer '+token}
        first=(await client.post('/api/v1/tools/experience',headers=headers,json={'action':'read','experience_id':'live'})).json()
        assert first['entry']['body_md'].strip()=='第一版本'
        detail=experiences.get_experience('live')
        experiences.save_experience('live',detail['frontmatter'],'第二版本','user',None,detail['current_hash'])
        second=(await client.post('/api/v1/tools/experience',headers=headers,json={'action':'read','experience_id':'live'})).json()
        assert second['entry']['body_md'].strip()=='第二版本' and second['revision_id']!=first['revision_id']
        assert second['context_id']!=first['context_id']
        assert (await client.post('/api/v1/tools/experience',headers=headers,json={'action':'read','experience_id':'global-draft'})).status_code==404
    assert experiences.get_experience('global-draft')['frontmatter']['status']=='candidate'


def test_real_pi_packet_and_executor_trial_use_chinese_topic_and_trial_goals():
    _seed_challenge()
    db.execute("UPDATE challenges SET content='用 Lean 证明中文定理并搭建环境' WHERE id='COLLAB_CH'")
    entry('aaa-unrelated','访谈方法论','社会学调查')
    entry('zzz-lean','Lean 定理证明','Lean 工具链与证明验证')
    entry('yyy-env','搭建环境','环境依赖和版本')
    ctl=RunController();rid=ctl.create_run('COLLAB_CH')['id']
    assert db.query_one('SELECT intention FROM runs WHERE id=?',(rid,))[0] is None
    packet=ctl._lifecycle_packet(db.query_one('SELECT * FROM runs WHERE id=?',(rid,)),'startup',sparse=True)
    assert packet['experience_manifest'][0]['id']=='zzz-lean'
    assert packet['experience_manifest'][-1]['id']=='aaa-unrelated'
    tid='lean-trial'
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,created_at) VALUES(?,?,?,?,?)',
               (tid,rid,'用 Lean 搭建环境后验证定理','编译证明',db.utcnow()))
    db.execute('UPDATE runs SET current_trial_id=? WHERE id=?',(tid,rid))
    ctl._snapshot_memory(rid,tid,config.load_settings())
    context=experience_context.for_trial(rid,tid)
    assert context['items'][0]['id']=='zzz-lean'
    assert context['items'][-1]['id']=='aaa-unrelated'
    assert len(context['index'])==3
