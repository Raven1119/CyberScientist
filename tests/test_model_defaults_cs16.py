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
