"""Reject new PI overrides while preserving historical source snapshots."""
import json
import pytest
from httpx import AsyncClient, ASGITransport
from cyberscientist import api, challenge_models, config, db
from cyberscientist.controller import RunController, ControllerError
from test_collaboration import _seed_challenge

@pytest.mark.parametrize('choice', [
 {'runtime':'codex','provider':'deepseek','model_id':'deepseek-flash','reasoning_effort':'high'},
 {'runtime':'codex','model_id':'gpt-6.1-sol','reasoning_effort':'xhigh'},
 {'runtime':'kimi','model_id':'k3','reasoning_effort':'high'},
 {'runtime':'codex','model_id':'gpt-6-astra','reasoning_effort':'high'},
])
async def test_pi_rejected_by_settings_topic_and_run_apis(choice):
    settings=config.load_settings()
    with pytest.raises(ValueError):challenge_models.choose('brain',choice,settings)
    _seed_challenge()
    with pytest.raises(ControllerError):RunController().create_run('COLLAB_CH',model_config={'brain':choice})
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://local') as client:
        settings['brain'].update(choice)
        assert (await client.put('/api/v1/settings',json={'settings':settings,'base_revision':settings['revision']})).status_code==422
        assert (await client.put('/api/v1/challenges/COLLAB_CH/models',json={'model_config':{'brain':choice}})).status_code==422
        assert (await client.post('/api/v1/challenges/import',json={'mode':'manual','title':'bad PI','content':'fixture','model_config':{'brain':choice}})).status_code==422
    assert not db.query('SELECT * FROM runs')


def test_file_and_live_legacy_pi_migrate_without_mutating_snapshots():
    settings=config.load_settings();settings['brain'].update(runtime='kimi',model_id='legacy-pi',provider='kimi',reasoning_effort='max',executable='/legacy/kimi')
    config.save_settings(settings)
    current=config.load_settings()['brain']
    assert current['runtime']=='codex' and current['model_id']=='gpt-6-astra' and current['reasoning_effort']=='xhigh' and current['executable']==''
    _seed_challenge();controller=RunController();rid=controller.create_run('COLLAB_CH')['id']
    snapshot=json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0])
    snapshot['settings']['brain'].update(runtime='codex',model_id='gpt-6.1-sol',reasoning_effort='high')
    raw=json.dumps(snapshot);db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(raw,rid))
    assert controller._runtime_settings(rid)['brain']['model_id']=='gpt-6-astra'
    assert db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0]==raw
    assert config.load_settings()['reviewer']['model_id']=='gpt-6.1-sol'
    assert config.load_settings()['post_review']['provider']=='deepseek'


def test_sparse_pi_receives_lkm_index_and_scoped_reader_without_general_shell():
    _seed_challenge()
    controller = RunController()
    rid = controller.create_run('COLLAB_CH')['id']
    spec = controller._brain_spec(rid, config.load_settings(), config.DATA_DIR)
    assert '没有读取必要时直接判断；不使用通用Shell' in spec['instructions']
    assert 'bohrium-lkm' in spec['instructions'] and 'SKILL.md' in spec['instructions']
    assert 'research_files' in spec['instructions'] and spec['pi_files_readonly']
    assert '受控公开检索技能正文' not in spec['instructions']
    assert '排序不是可信度' not in spec['instructions']  # D-56 reads the full skill on demand.


async def test_legacy_round_append_and_queue_project_pi_without_rewriting_source():
    from cyberscientist import competition, evaluations
    from test_competition import FakeController, challenges, template
    challenges(1)
    rnd = competition.import_round(['c0'], mode='demo')
    competition.confirm(rnd['id'], template())
    evaluation = db.query_one('SELECT * FROM eval_runs WHERE id=?', (rnd['id'],))
    frozen = json.loads(evaluation['config_json'])
    old = {'runtime': 'kimi', 'provider': 'kimi', 'model_id': 'legacy-pi', 'reasoning_effort': 'high'}
    frozen['template']['model_config']['brain'] = old
    source = json.dumps(frozen)
    db.execute('UPDATE eval_runs SET config_json=? WHERE id=?', (source, rnd['id']))
    row = db.query_one('SELECT * FROM eval_results WHERE eval_id=?', (rnd['id'],))
    old_template = json.loads(row['template_json']); old_template['model_config']['brain'] = old
    item_source = json.dumps(old_template)
    db.execute('UPDATE eval_results SET template_json=? WHERE id=?', (item_source, row['id']))
    appended = competition.append_run(rnd['id'], 'c0')
    assert appended['items'][-1]['template']['model_config']['brain']['model_id'] == 'gpt-6-astra'
    ctl = FakeController(); ctl.throttled = True
    await evaluations.advance(ctl)
    assert ctl.started
    assert all(ctl._runtime_settings(rid)['brain']['model_id'] == 'gpt-6-astra' for rid in ctl.started)
    assert db.query_one('SELECT config_json FROM eval_runs WHERE id=?', (rnd['id'],))[0] == source
    assert db.query_one('SELECT template_json FROM eval_results WHERE id=?', (row['id'],))[0] == item_source
