import json
from pathlib import Path
import pytest
from cyberscientist import (challenge_models, competition, config, db,
                            model_providers, model_usage, resource_coordinator)
from cyberscientist.controller import RunController
from cyberscientist.codex_protocol import thread_params
READ_KEY = config.deepseek_key


def seed():
    db.execute('INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo) VALUES(?,?,?,?,?,?,1)',
               ('provider-c', 'fixture', 'Synthetic provider', 'Fixture', 'h', db.utcnow()))


def test_native_config_key_only_in_process_and_no_global_write(monkeypatch, tmp_path):
    secret = 'fixture-provider-credential-928374'
    monkeypatch.setattr(config, 'deepseek_key', lambda: secret)
    global_home = tmp_path / 'global-codex'
    global_home.mkdir()
    (global_home / 'config.toml').write_text('global_marker = true')
    env = model_providers.prepare('deepseek', {'CODEX_HOME': str(global_home), 'OPENAI_API_KEY': 'old-key'})
    assert env['DEEPSEEK_API_KEY'] == secret
    assert 'OPENAI_API_KEY' not in env
    assert Path(env['CODEX_HOME']).is_relative_to(config.DATA_DIR)
    public = ''.join(p.read_text() for p in Path(env['CODEX_HOME']).iterdir())
    assert secret not in public and 'experimental_bearer_token' not in public
    assert 'env_key = "DEEPSEEK_API_KEY"' in public
    assert (global_home / 'config.toml').read_text() == 'global_marker = true'
    params = thread_params({'env': {'PATH': '/bin', 'CS_TOOL_TOKEN': 'fixture-capability'}}, 'deepseek-flash', 'high', writable=True)
    model_providers.thread_provider(params, 'deepseek')
    assert params['modelProvider'] == 'deepseek'
    assert 'DEEPSEEK_API_KEY' not in params['config']['shell_environment_policy.include_only']
    assert secret not in json.dumps(params)
    with pytest.raises(ValueError, match='静默'):
        model_providers.verify_provider({'modelProvider': 'openai'}, 'deepseek')


def test_missing_key_does_not_create_config():
    with pytest.raises(ValueError, match='DEEPSEEK_API_KEY'):
        model_providers.prepare('deepseek', {})
    assert not (config.DATA_DIR / 'codex-deepseek').exists()


def test_four_roles_and_legacy_override_normalize_provider():
    settings = config.load_settings()
    for role in ('brain', 'executor', 'reviewer', 'post_review'):
        choice = {'runtime': 'codex', 'provider': 'deepseek', 'model_id': 'deepseek-flash', 'reasoning_effort': 'high'}
        if role == 'brain':
            with pytest.raises(ValueError, match='PI只能'): challenge_models.choose(role, choice, settings)
        else:
            assert challenge_models.choose(role, choice, settings)['provider'] == 'deepseek'
    settings['executor'].update(provider='deepseek', model_id='deepseek-flash')
    config.save_settings(settings)
    seed()
    run = RunController().create_run('provider-c', model_config={'executor': {
        'runtime': 'codex', 'model_id': 'gpt-6.1-sol', 'reasoning_effort': 'high'}})
    frozen = json.loads(db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (run['id'],))[0])['settings']
    assert frozen['executor']['provider'] == 'codex'


def test_roster_frozen_on_confirm_and_append_and_no_client_entry_override():
    settings = config.load_settings()
    entry = {'id': 'cheap', 'name': 'Cheap', 'runtime': 'codex', 'provider': 'deepseek',
             'model_id': 'deepseek-flash', 'reasoning_effort': 'high', 'note': '写死任务'}
    settings['solver_roster'] = [entry]
    config.save_settings(settings)
    seed()
    rnd = competition.import_round(['provider-c'], mode='demo')
    result = competition.confirm(rnd['id'], {'solver_id': 'cheap'})
    assert result['items'][0]['template']['solver_entry']['note'] == '写死任务'
    settings['solver_roster'][0]['model_id'] = 'changed-later'
    config.save_settings(settings)
    appended = competition.append_run(rnd['id'], 'provider-c')
    assert appended['items'][-1]['template']['model_config']['executor']['model_id'] == 'deepseek-flash'
    with pytest.raises(competition.CompetitionError):
        competition._template({'solver_id': 'cheap', 'solver_entry': {**entry, 'private': 'x'}}, 'demo')


def test_usage_latest_cumulative_per_session_price_bounds_and_unknown():
    seed()
    settings = config.load_settings()
    settings['executor'].update(provider='deepseek', model_id='deepseek-flash')
    config.save_settings(settings)
    rid = RunController().create_run('provider-c')['id']
    for counts in (100, 200, 200):
        db.append_event(rid, 'prime', 'prime.usage.updated', {'session_id': 'native-a', 'usage': {
            'total': {'inputTokens': counts, 'cachedInputTokens': 50, 'outputTokens': 20},
            'last': {'inputTokens': 50, 'outputTokens': 5}}})
    db.append_event(rid, 'brain', 'maintenance.usage', {'kind': 'postreview', 'usage': {
        'session_id': 'native-b', 'usage': {'total': {'inputTokens': 80, 'outputTokens': 10}}}})
    db.append_event(rid, 'brain', 'brain.usage.updated', {'usage': {'last': {'inputTokens': 1}}})
    result = model_usage.summarize(rid)
    assert len(result['sessions']) == 2
    executor = next(s for s in result['sessions'] if s['role'] == 'executor')
    assert executor['tokens']['input'] == 200
    assert executor['estimate']['lower'] < executor['estimate']['upper']
    assert executor['estimate']['source'].startswith('https://api-docs.deepseek.com/')
    assert result['unknown_observations'] and result['invoice_status'] == 'unknown'
    bad = {**settings['model_pricing']['deepseek/deepseek-flash'], 'billing_tier': 'peak'}
    bad.pop('peak')
    with pytest.raises(ValueError, match='缺少价格'):
        model_usage.validate({'deepseek/deepseek-flash': bad})


def test_provider_backoff_independent_and_key_scrubbed_every_persistence_boundary(monkeypatch):
    from cyberscientist import observation, planning
    secret = 'fixture-ds-only-key-774411'
    monkeypatch.setattr(config, 'deepseek_key', lambda: secret)
    assert secret not in observation.strip_secrets('value=' + secret)
    model_providers.record_throttle({'provider': 'deepseek', 'runtime': 'codex'}, 'HTTP 429 Too Many Requests Retry-After: 20')
    with db.transaction() as conn:
        resource_coordinator.reserve_sessions_tx(conn, 'ordinary', {'brain': {'provider': 'codex'}})
        with pytest.raises(resource_coordinator.ResourceWait):
            resource_coordinator.reserve_sessions_tx(conn, 'limited', {'brain': {'provider': 'deepseek'}})
    settings = config.load_settings()
    with pytest.raises(ValueError, match='密钥'):
        challenge_models.choose('executor', {**settings['executor'], 'note': secret}, settings)


@pytest.mark.asyncio
async def test_probe_rejects_prime_before_any_native_call(monkeypatch):
    from cyberscientist import model_probe
    settings = config.load_settings()
    settings['executor'].update(runtime='prime', provider='prime', model_id='prime-fixture')
    settings['prime']['llm_profile_id'] = 'fixture'
    settings['llm_profiles'] = [{'id': 'fixture', 'model_id': 'prime-fixture'}]
    config.save_settings(settings)
    controller = RunController()
    monkeypatch.setattr(controller, '_make_brain', lambda _: pytest.fail('不能调用其他原生运行时'))
    with pytest.raises(ValueError, match='没有发起'):
        await model_probe.run(controller, 'executor')
    assert not db.query('SELECT * FROM model_session_leases')


@pytest.mark.asyncio
async def test_deepseek_native_fake_frames_and_secret_environment(monkeypatch, tmp_path):
    from test_codex_runtime import FakeRpc
    from cyberscientist.brains.codex import CodexBrain
    captured = []
    secret = 'fixture-native-env-key-885522'
    monkeypatch.setattr(config, 'deepseek_key', lambda: secret)
    class ProviderRpc(FakeRpc):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.environment = kwargs['env']
            captured.append(self)
        async def request(self, method, params=None, **kwargs):
            result = await super().request(method, params, **kwargs)
            if method == 'thread/start':
                result['modelProvider'] = params['modelProvider']
            return result
    monkeypatch.setattr('cyberscientist.brains.codex.JsonRpcStdio', ProviderRpc)
    brain = CodexBrain('/bin/true', 'deepseek-flash', 'high', 'deepseek')
    session = await brain.open({'working_directory': str(tmp_path)})
    assert session.raw['provider'] == 'deepseek'
    assert captured[0].environment['DEEPSEEK_API_KEY'] == secret
    assert secret not in json.dumps(captured[0].calls)
    await brain.close(session)


def test_key_read_source_env_then_root_dotenv_without_copy(monkeypatch):
    class Dotenv:
        def exists(self): return True
        def read_text(self, **kwargs): return 'DEEPSEEK_API_KEY="fixture-dotenv-only"\n'
    class Root:
        def __truediv__(self, name):
            assert name == '.env'
            return Dotenv()
    monkeypatch.setattr(config, 'WORKSPACE_ROOT', Root())
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'fixture-env-first')
    assert READ_KEY() == 'fixture-env-first'
    monkeypatch.delenv('DEEPSEEK_API_KEY')
    assert READ_KEY() == 'fixture-dotenv-only'


@pytest.mark.asyncio
async def test_untrusted_rpc_errors_and_stderr_redacted_before_diagnostics(monkeypatch, caplog):
    import asyncio
    import logging
    from types import SimpleNamespace
    from cyberscientist.jsonrpc_stdio import JsonRpcStdio, ProtocolError
    secret = 'fixture-untrusted-ds-key-887766'
    monkeypatch.setattr(config, 'deepseek_key', lambda: secret)
    rpc = JsonRpcStdio(['/bin/true'])
    future = asyncio.get_running_loop().create_future()
    rpc._pending[1] = future
    await rpc._dispatch({'id': 1, 'error': {'message': secret}})
    with pytest.raises(ProtocolError) as failure:
        await future
    assert secret not in str(failure.value)
    reader = asyncio.StreamReader()
    reader.feed_data((secret + '\n').encode())
    reader.feed_eof()
    rpc.proc = SimpleNamespace(stderr=reader)
    with caplog.at_level(logging.DEBUG):
        await rpc._drain_stderr()
    assert secret not in repr(rpc.stderr_tail()) and secret not in caplog.text
