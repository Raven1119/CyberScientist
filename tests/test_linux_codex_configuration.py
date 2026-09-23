import json
import pytest

from cyberscientist import config, db, skills
from cyberscientist.controller import RunController


def seed_run():
    db.execute(
        "INSERT INTO challenges(id,platform_challenge_id,origin,title,content,"
        "content_hash,contract_status,imported_at,is_demo) VALUES(?,?,?,?,?,?,?,?,0)",
        ('ch-linux', 'slug', 'https://example.org', 'Linux research', 'Problem', 'hash', 'unknown', db.utcnow()))
    controller = RunController()
    run = controller.create_run('ch-linux', mode='connected')
    return controller, run


def test_codex_receives_bohrium_environment_and_rotated_collaboration_capability(monkeypatch):
    settings = config.load_settings()
    settings['executor']['runtime'] = 'codex'
    settings['bohrium'].update(executable='/opt/bohr/bin/bohr', project_id='123',
                               access_key_secret_ref='local:test-bohr')
    config.save_settings(settings)
    config.update_secret('test-bohr', 'private-test-key')
    monkeypatch.setenv('ACCESS_KEY', 'stale-key')
    monkeypatch.setenv('OPENAPI_HOST', 'https://environment-api.example')
    monkeypatch.setenv('TIEFBLUE_HOST', 'https://environment-files.example')
    controller, run = seed_run()
    first = controller._prime_spec(run['id'], settings)
    settings['bohrium']['host_overrides'] = {'OPENAPI_HOST': 'https://configured-api.example'}
    second = controller._prime_spec(run['id'], settings)
    assert not {'BOHR_ACCESS_KEY', 'ACCESS_KEY', 'CS_BOHR_EXECUTABLE'} & first['env'].keys()
    assert 'private-test-key' not in json.dumps(first)
    assert first['env']['PATH'].startswith(str(config.WORKSPACE_DIR / 'runs' / run['id'] / 'bin') + ':')
    assert first['env']['CS_TOOL_TOKEN'] == first['mcp_servers'][0]['env'][0]['value']
    assert first['network_access'] is True
    assert first['mcp_servers'][0]['name'] == 'cyberscientist'
    assert first['mcp_servers'][0]['env'][0]['value'] != second['mcp_servers'][0]['env'][0]['value']
    persisted = dict(db.query_one('SELECT * FROM runs WHERE id=?', (run['id'],)))
    assert 'private-test-key' not in json.dumps(persisted)


def test_brain_packet_contains_selected_skill_path_and_authorization_goal(tmp_path, monkeypatch):
    root = tmp_path / 'installed'
    skill = root / 'bohrium-job'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: bohrium-job\ndescription: jobs\n---\n')
    monkeypatch.setattr(skills, 'SKILL_DIRS', (root,))
    settings = config.load_settings()
    settings['skills']['always_on'] = ['bohrium-job']
    config.save_settings(settings)
    controller, run = seed_run()
    controller.authorize(run['id'], 'experiment', True, 100, 120, 3,
                         'Stop after submission, feedback, and experience extraction.', max_jobs=10)
    packet = controller._lifecycle_packet(controller._require_run(run['id']), 'run_start')
    assert str(skill / 'SKILL.md') in packet['enabled_skills']
    assert packet['authorization']['max_jobs'] == 10
    assert 'experience extraction' in packet['authorization']['note']


@pytest.mark.asyncio
async def test_url_import_preserves_platform_status_without_claiming_eligibility(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app
    from cyberscientist import mailbox_platform

    data = {'title': 'Closed challenge', 'content': 'Actual scientific statement',
            'status': 'closed', 'roundEndAt': '2026-08-01T00:00:00Z',
            'scoring': {'grader_name': None, 'strategy': 'arm_v1_1_generic'}}
    monkeypatch.setattr(mailbox_platform, 'fetch_platform_challenge', lambda *a: data)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url='http://local') as client:
        response = await client.post('/api/v1/challenges/import', json={
            'mode': 'url', 'url': 'https://play.bohrium.com/challenge/example-12345678'})
        assert response.status_code == 200, response.text
        challenge = response.json()['challenge']
        assert challenge['content'] == data['content']
        assert challenge['platform_snapshot']['status'] == 'closed'
        assert challenge['platform_snapshot']['scoring']['grader_name'] is None
        assert challenge['eligibility'] is None
        assert challenge['contract_status'] == 'unknown'
