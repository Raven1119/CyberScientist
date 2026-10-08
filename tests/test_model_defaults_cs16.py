import pytest
from cyberscientist import config,competition,competition_triage,db
from test_competition import challenges,template

@pytest.mark.parametrize('level,model',[('easy','gpt-5.6-terra'),('medium','gpt-5.6-terra'),('hard','gpt-6-astra'),('unknown','unknown')])
def test_default_triage_without_roster_never_keeps_deepseek(level,model):
    settings=config.load_settings();settings['solver_roster']=[]
    result=competition_triage.recommend({'difficulty':level,'recommended_model':'deepseek-flash','recommended_solver_id':'old'},settings)
    assert result['recommended_model']==model and result['recommended_solver_id'] is None


def test_defaults_and_explicit_adoption_work_without_roster():
    assert config.DEFAULT_SETTINGS['brain']['model_id']=='gpt-6-astra'
    assert config.DEFAULT_SETTINGS['brain']['reasoning_effort']=='xhigh'
    assert config.DEFAULT_SETTINGS['executor']['model_id']=='gpt-5.6-terra'
    assert config.DEFAULT_SETTINGS['executor']['fast_mode'] is True
    rnd=competition.import_round(challenges(1),mode='demo')
    row=db.query_one('SELECT * FROM eval_results WHERE eval_id=?',(rnd['id'],))
    import json
    advice=competition_triage.recommend({'difficulty':'hard'},config.load_settings())
    db.execute('UPDATE eval_results SET triage_json=? WHERE id=?',(json.dumps(advice),row['id']))
    competition.adopt_suggestions(rnd['id'])
    competition.confirm(rnd['id'],template())
    selected=json.loads(db.query_one('SELECT template_json FROM eval_results WHERE id=?',(row['id'],))[0])
    assert selected['model_config']['executor']['model_id']=='gpt-6-astra'
    assert selected['model_config']['executor']['fast_mode'] is True


def test_science_first_default_never_routes_to_automatic_deepseek(monkeypatch):
    from cyberscientist import model_fallback
    settings=config.load_settings();settings['science_first_flow']=True;settings['app']['mode']='connected'
    settings['features']['deepseek_fallback']=True
    settings['solver_roster']=[{'id':'ds','name':'manual DS','runtime':'codex','provider':'deepseek','model_id':'deepseek-flash','reasoning_effort':'high'}]
    monkeypatch.setattr(model_fallback,'validate',lambda *a:(_ for _ in ()).throw(AssertionError('no automatic fallback')))
    original={'runtime':'codex','provider':'codex','model_id':'gpt-5.6-terra','reasoning_effort':'xhigh','fast_mode':True}
    selected,receipt=model_fallback.select(original,settings)
    assert selected==original and receipt['status']=='manual_only'
    manual=settings['solver_roster'][0]
    assert model_fallback.select(manual,settings)[0]['provider']=='deepseek'
