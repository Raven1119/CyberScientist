import asyncio
import io
import json
import sys
import pytest
from cyberscientist import config, db, features, environment_catalog, score_wait, shared_artifacts, protocol_drift, planning, strategies, experiences, experience_context
from cyberscientist.controller import RunController, executor_instruction_suffix


@pytest.mark.asyncio
@pytest.mark.parametrize('name', features.NAMES)
async def test_every_switch_on_off_http_restart_and_partial_save(name):
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://t') as client:
        for enabled in (False, True):
            current=(await client.get('/api/v1/features')).json()
            response=await client.put('/api/v1/features/'+name,json={'enabled':enabled,'expected_revision':current['revision']})
            assert response.status_code==200 and features.enabled(name) is enabled
            after=(await client.get('/api/v1/settings')).json()
            assert (await client.put('/api/v1/settings',json={'settings':{'harvest':{'score_threshold':87}},'base_revision':after['revision']})).status_code==200
            assert config.load_settings()['features'][name] is enabled
            if name=='environment_catalog': assert environment_catalog.enabled() is enabled
            if name=='await_score': assert score_wait.enabled() is enabled
            if name=='shared_area': assert shared_artifacts.enabled() is enabled
            if name=='protocol_drift': assert (protocol_drift.check()['status'] == 'disabled') is (not enabled)
        assert (await client.put('/api/v1/features/'+name,json={'enabled':'false'})).status_code==422
        assert (await client.put('/api/v1/features/'+name,json={'enabled':False,'expected_revision':-1})).status_code==409
        assert features.enabled(name)
        assert (await client.put('/api/v1/features/not-known',json={'enabled':True})).status_code==422


@pytest.mark.parametrize('name', features.NAMES)
@pytest.mark.parametrize('state',['on','off'])
def test_cli_switch_uses_backend_without_raw_secret_output(monkeypatch,capsys,name,state):
    from cyberscientist import cli
    calls=[]
    def urlopen(request,timeout):
        calls.append(request)
        return io.BytesIO(json.dumps({'name':name,'enabled':state=='on'}).encode())
    monkeypatch.setattr(cli.urllib.request,'urlopen',urlopen)
    monkeypatch.setattr(sys,'argv',['cyberscientist','ops','switch',name,state])
    cli.main()
    assert json.loads(capsys.readouterr().out)['enabled'] is (state=='on')
    assert calls[0].method=='PUT' and json.loads(calls[0].data)['enabled'] is (state=='on')


def test_strategy_off_preserves_revisions_and_prior_frozen_context():
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo) VALUES('sw','fixture','x','x','h',?,1)",(db.utcnow(),))
    rid=RunController().create_run('sw')['id']
    event=db.append_event(rid,'brain','research.brief_written',{'brief':{}})
    strategies.update(rid,brief={'route_md':'候选路线'},event=event)
    frozen=experience_context.freeze(rid,None,'switch-before')
    before=experiences.get_experience(strategies.card_id(rid))
    features.switch('strategy_cards',False)
    assert not experience_context.effective('sw') and not planning.strategy_cards('sw')
    assert strategies.update(rid,brief={'route_md':'不得改写'},event=event) is None
    assert experiences.get_experience(strategies.card_id(rid))['revision_id']==before['revision_id']
    assert json.loads(db.query_one('SELECT content_json FROM experience_contexts WHERE id=?',(frozen['id'],))[0])==frozen
    features.switch('strategy_cards',True)
    assert planning.strategy_cards('sw')


def test_auto_harvest_off_preserves_source_and_on_resumes_new_intent():
    from test_auto_harvest import seed
    from cyberscientist import auto_harvest
    rid,_=seed()
    before=[dict(r) for r in db.query('SELECT * FROM submissions')]
    features.switch('auto_harvest',False); auto_harvest.advance_sync()
    assert not db.query('SELECT * FROM automatic_harvests') and before==[dict(r) for r in db.query('SELECT * FROM submissions')]
    features.switch('auto_harvest',True); auto_harvest.advance_sync()
    assert db.query_one('SELECT status FROM automatic_harvests')[0]=='done'


@pytest.mark.asyncio
async def test_reviewer_off_no_new_call_on_and_saved_report_preserved(monkeypatch):
    from test_package_reviews import seed, Reviewer
    from cyberscientist import package_reviews
    rid=seed(); calls=[]; ctl=RunController()
    monkeypatch.setattr(ctl,'_make_brain',lambda settings:Reviewer(calls))
    features.switch('reviewer',False)
    assert (await package_reviews.review(ctl,rid,'trial_mb1','review-off'))['status']=='disabled'
    assert not calls and not db.query('SELECT * FROM package_reviews')
    features.switch('reviewer',True)
    assert (await package_reviews.review(ctl,rid,'trial_mb1','review-on'))['status']=='done'
    count=len(calls); features.switch('reviewer',False)
    assert (await package_reviews.review(ctl,rid,'trial_mb1','review-on'))['status']=='done' and len(calls)==count


@pytest.mark.asyncio
async def test_system_triage_off_does_not_call_and_on_uses_original_task():
    from test_competition import challenges
    from cyberscientist import competition
    rnd=competition.import_round(challenges(1),mode='demo');ctl=RunController()
    features.switch('system_triage',False)
    with pytest.raises(competition.CompetitionError,match='关闭'): await competition.triage(rnd['id'],ctl)
    assert not db.query('SELECT * FROM model_session_leases')
    features.switch('system_triage',True)
    assert (await competition.triage(rnd['id'],ctl))['items'][0]['triage']['difficulty']=='unknown'


def test_local_calculation_off_updates_actual_role_prompts_without_deleting_evidence():
    from cyberscientist.brains.codex import CodexBrain
    from cyberscientist.brains.kimi import KimiBrain
    packet={'trigger':'run_start','authorization':{},'research_startup':{}}
    for enabled in (False,True):
        features.switch('local_calculation',enabled)
        prompts=[features.science_instruction(),executor_instruction_suffix(),CodexBrain._render_prompt(packet),KimiBrain._render_prompt(packet)]
        if enabled: assert all('秒级小计算' in p for p in prompts)
        else: assert all('本地计算功能已关闭' in p and '秒级小计算' not in p for p in prompts)


@pytest.mark.parametrize('runtime',['codex','kimi'])
@pytest.mark.parametrize('protocol',['review_result','executor_question'])
@pytest.mark.parametrize('enabled',[False,True])
def test_local_calculation_policy_also_covers_shadow_and_question(runtime,protocol,enabled):
    from cyberscientist.brains.codex import CodexBrain
    from cyberscientist.brains.kimi import KimiBrain
    features.switch('local_calculation',enabled)
    prompt=(CodexBrain if runtime=='codex' else KimiBrain)._render_prompt({'protocol':protocol,'sparse_brain_version':1,'frame_id':'fixture'})
    assert ('秒级小计算' in prompt) is enabled
    assert ('本地计算功能已关闭' in prompt) is (not enabled)


def test_harvest_switch_closed_after_reservation_never_posts_and_manual_still_works(monkeypatch):
    from test_auto_harvest import seed
    from cyberscientist import mailboxes,auto_harvest
    _,source=seed(); platform=mailboxes._platform(); calls=[]; original_submit=platform.submit_package
    monkeypatch.setattr(platform,'submit_package',lambda *a,**k: calls.append(a) or original_submit(*a,**k))
    monkeypatch.setattr(mailboxes,'_platform',lambda:platform)
    original_guard=mailboxes._guard_submission_target
    def target(*args):
        original_guard(*args); features.switch('auto_harvest',False)
    monkeypatch.setattr(mailboxes,'_guard_submission_target',target)
    auto_harvest.advance_sync()
    assert not calls
    row=db.query_one('SELECT * FROM submissions WHERE is_harvest=1')
    assert row['status']=='failed' and row['reservation_released']==1 and row['stage']=='prepared'
    assert '未发送' in row['error'] and db.query_one('SELECT status FROM automatic_harvests')[0]=='failed'
    manual=mailboxes.harvest_submit(source['id'],'manual-after-switch',True,True)
    assert manual['status']=='submitted' and len(calls)==1


def test_local_calculation_off_keeps_job_authority_and_submission_instructions():
    features.switch('local_calculation',False)
    prompt=executor_instruction_suffix()
    assert '计费Job核对当前Run授权' in prompt and '平台提交由控制器持久化门禁' in prompt and '不直接创建 Attempt' in prompt
