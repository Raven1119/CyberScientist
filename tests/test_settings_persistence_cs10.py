"""Cross-page partial saves and an actual new backend app preserve settings."""
import json
import pytest
from httpx import ASGITransport, AsyncClient
from cyberscientist import api, config, db

CHANGES = {
    'app': {'port': 8899, 'host': '127.0.0.1', 'mode': 'demo'},
    'brain': {'executable': '/fixture/codex', 'runtime': 'codex', 'model_id': 'gpt-6-astra', 'reasoning_effort': 'xhigh'},
    'executor': {'executable': '/fixture/solver', 'model_id': 'gpt-6.1-sol', 'reasoning_effort': 'xhigh'},
    'reviewer': {'provider': 'deepseek', 'model_id': 'deepseek-flash', 'reasoning_effort': 'high'},
    'post_review': {'executable': '/fixture/review', 'reasoning_effort': 'max'},
    'solver_roster': [{'id': 'ds-fallback', 'name': 'DeepSeek', 'runtime': 'codex', 'provider': 'deepseek', 'model_id': 'deepseek-flash', 'reasoning_effort': 'high', 'note': '事务性环境建议'}],
    'prime': {'executable': '/fixture/prime', 'llm_profile_id': 'fixture'},
    'llm_profiles': [{'id': 'fixture', 'label': 'Fixture', 'protocol': 'openai_chat_completions', 'base_url': 'https://invalid.example', 'model_id': 'fixture', 'secret_ref': 'local:fixture'}],
    'playground': {'base_url': 'https://invalid.example/api', 'token_secret_ref': 'local:fixture'},
    'bohrium': {'executable': '/fixture/bohr', 'project_id': 88474, 'wenyon_executable': '/fixture/new-bohr', 'wenyon_home': '/fixture/home', 'access_key_secret_ref': 'local:fixture', 'host_overrides': {'OPENAPI_HOST': 'https://invalid.example'}},
    'harvest': {'score_threshold': 99, 'experiments_done_at_leader': False, 'deadline_check_hours': 3},
    'run_defaults': {'max_active_runs': 7, 'stall_seconds': 421, 'max_brain_wait_seconds': 801, 'brain_review_timeout_seconds': 991, 'rate_limit_max_seconds': 1021},
    'shadow': {'enabled': True, 'max_reviews': 11, 'min_interval_seconds': 77, 'max_interval_seconds': 901},
    'mailbox': {'platform': 'bohrium_playground', 'submission_limit': 9},
    'skills': {'always_on': ['bohrium-job', 'bohrium-lkm']},
    'resources': {'provider_sessions': {'codex': 12, 'deepseek': 13}, 'max_concurrent_jobs': 4, 'max_concurrent_sandboxes': 5},
    'memory': {'max_global_entries': 21, 'max_challenge_entries': 12, 'max_injected_characters': 25000},
    'features': {'environment_catalog': False, 'scorer_audit': False, 'await_score': False, 'shared_area': False},
    'model_pricing': {'deepseek/deepseek-flash': {'billing_tier': 'peak'}},
}


@pytest.mark.parametrize('namespace', list(CHANGES))
async def test_each_config_namespace_survives_refresh_restart_and_other_page_save(namespace):
    before = config.load_settings()
    change = CHANGES[namespace]
    # Exact historical failure: defaults + the other page loses this namespace.
    old_write = json.loads(json.dumps(config.DEFAULT_SETTINGS)); old_write.update({'harvest': {'score_threshold': 88}})
    if namespace != 'harvest': assert old_write[namespace] != config.merge_settings(before, {namespace: change})[namespace]
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        res = await client.put('/api/v1/settings', json={'settings': {namespace: change}, 'base_revision': before['revision']})
        assert res.status_code == 200, res.text
        saved = res.json(); refreshed = (await client.get('/api/v1/settings')).json()
        assert refreshed[namespace] == saved[namespace]
    db.get_db().close(); del db._local.conn
    db.init_db()
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as restarted:
        after = (await restarted.get('/api/v1/settings')).json()
        assert after[namespace] == saved[namespace]
        other = 'shadow' if namespace == 'harvest' else 'harvest'
        other_patch = {'enabled': True} if other == 'shadow' else {'score_threshold': 88}
        response = await restarted.put('/api/v1/settings', json={'settings': {other: other_patch}, 'base_revision': after['revision']})
        assert response.status_code == 200
        assert response.json()[namespace] == saved[namespace]
        assert '_status' not in json.loads(config.SETTINGS_PATH.read_text())


async def test_nested_partial_save_keeps_siblings_and_stale_revision_cannot_clobber():
    current = config.load_settings(); current['resources']['provider_sessions']['kimi'] = 17; config.save_settings(current)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        res = await client.put('/api/v1/settings', json={'settings': {'resources': {'provider_sessions': {'codex': 22}}}, 'base_revision': 0})
        assert res.status_code == 200
        assert res.json()['resources']['provider_sessions']['kimi'] == 17
        assert res.json()['resources']['provider_sessions']['codex'] == 22
        res = await client.put('/api/v1/settings', json={'settings': {'resources': {'provider_sessions': {'kimi': 1}}}, 'base_revision': 0})
        assert res.status_code == 409 and config.load_settings()['resources']['provider_sessions']['kimi'] == 17


@pytest.mark.parametrize('replacement', [{}, {'deepseek/deepseek-flash': {'currency': 'USD', 'source': 'https://invalid.example/prices', 'observed_on': '2026-10-06', 'billing_tier': 'unknown', 'peak': {'input': 1, 'cached_input': 0, 'output': 2}}}])
async def test_full_price_editor_can_delete_model_or_tier_and_empty_survives_restart(replacement):
    initial = config.load_settings()
    initial['model_pricing']['custom/model'] = dict(initial['model_pricing']['deepseek/deepseek-flash'])
    config.save_settings(initial)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        response = await client.put('/api/v1/settings', json={'settings': {'model_pricing': replacement}, 'replace_paths': ['model_pricing'], 'base_revision': 0})
        assert response.status_code == 200
        assert (await client.get('/api/v1/settings')).json()['model_pricing'] == replacement
    db.get_db().close(); del db._local.conn; db.init_db()
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as restarted:
        after = (await restarted.get('/api/v1/settings')).json()
        response = await restarted.put('/api/v1/settings', json={'settings': {'harvest': {'score_threshold': 88}}, 'base_revision': after['revision']})
        assert response.status_code == 200 and response.json()['model_pricing'] == replacement


async def test_explicit_host_map_clear_and_replacement_path_validation():
    initial = config.load_settings(); initial['bohrium']['host_overrides'] = {'OPENAPI_HOST': 'https://invalid.example'}; config.save_settings(initial)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://fixture') as client:
        response = await client.put('/api/v1/settings', json={'settings': {'bohrium': {'host_overrides': {}}}, 'replace_paths': ['bohrium.host_overrides'], 'base_revision': 0})
        assert response.status_code == 200 and config.load_settings()['bohrium']['host_overrides'] == {}
        for path in ('brain', 'resources', 'secret_ref'):
            response = await client.put('/api/v1/settings', json={'settings': {}, 'replace_paths': [path], 'base_revision': 1})
            assert response.status_code == 422 and config.load_settings()['revision'] == 1
