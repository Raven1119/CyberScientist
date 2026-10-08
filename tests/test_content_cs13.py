import json
from pathlib import Path
from cyberscientist import capabilities, competition, competition_prompts, competition_triage, config, db, skills
from test_competition import challenges


def test_imported_round_starts_with_editable_versioned_template():
    rnd = competition.import_round(challenges(1), mode='demo')
    value = competition_prompts.latest(rnd['id'])
    assert value['version'] == 1
    assert value['content_md'] == (config.WORKSPACE_ROOT/'templates/lightchaser-user-prompt.md').read_text()
    competition_prompts.publish(rnd['id'], '用户修改', 1)
    assert competition_prompts.latest(rnd['id'])['content_md'] == '用户修改'


def test_executor_required_skills_bypass_audience_but_other_skills_do_not():
    catalog = [{'id': sid, 'audience': 'brain'} for sid in
               ('bohrium-job', 'cyberscientist-submission-gate', 'unrelated')]
    selected = skills.effective_for(db.get_db(), {'skills': {'always_on': ['unrelated']}}, None, catalog, 'executor')
    assert {x['id'] for x in selected} == {'bohrium-job', 'cyberscientist-submission-gate'}


def test_capability_summary_is_bounded_and_has_authority_and_usage():
    value = capabilities.summary()
    assert len(value) <= 2000
    assert '尚无Run授权' in value and '受控bohr' in value


def test_three_levels_and_one_data_complete_fastest_candidate():
    settings = config.load_settings()
    settings['solver_roster'] = [dict(id=sid, name=sid, runtime='codex', provider=provider,
                                    model_id=model, reasoning_effort='high', fast_mode=True)
        for sid, provider, model in [('easy', 'deepseek', 'deepseek-flash'),
            ('medium', 'codex', 'gpt-5.6-terra'), ('hard', 'codex', 'gpt-6-astra')]]
    for level in ('easy', 'medium', 'hard'):
        assert competition_triage.recommend({'difficulty': level}, settings)['recommended_solver_id'] == level
    rnd = competition.import_round(challenges(3), mode='demo')
    rows = db.query('SELECT id FROM eval_results WHERE eval_id=? ORDER BY id', (rnd['id'],))
    for row, duration, complete in zip(rows, (1, 5, 2), (False, True, True)):
        db.execute('UPDATE eval_results SET triage_json=? WHERE id=?',
                   (json.dumps({'difficulty': 'easy', 'estimated_minutes': duration, 'data_complete': complete}), row['id']))
    competition_triage.select_minimum_loop(rnd['id'])
    picked = [row['id'] for row in db.query('SELECT id,triage_json FROM eval_results')
              if json.loads(row['triage_json'])['minimum_loop_candidate']]
    assert picked == [rows[2]['id']]


def test_capability_summary_unlimited_sentinel_and_recent_environment_visibility(monkeypatch):
    from test_auto_harvest import seed
    rid, _ = seed(10)
    db.execute('UPDATE authorizations SET unlimited_resources=1,max_jobs=0,max_sandboxes=0 WHERE run_id=?', (rid,))
    entries = [dict(id=f'old-{i}', image=f'old-image-{i}', last_verified_at='2026-01-01', restore_seconds={}) for i in range(6)]
    entries += [dict(id='cs13-materials-v1', image='materials-image', last_verified_at='2026-10-07', restore_seconds={}), dict(id='cs13-abacus-v2', image='abacus-image', last_verified_at='2026-10-08', restore_seconds={})]
    monkeypatch.setattr(capabilities.environment_catalog, 'items', lambda: entries)
    value = capabilities.summary(rid)
    assert len(value) <= 2000
    assert '"unlimited_resources": true' in value and '"max_jobs": null' in value
    assert '"max_sandboxes": null' in value and '"max_jobs": 0' not in value
    assert 'cs13-materials-v1=materials-image' in value and 'cs13-abacus-v2=abacus-image' in value
    assert 'GPU job=' in value and 'GPU sandbox=' in value
