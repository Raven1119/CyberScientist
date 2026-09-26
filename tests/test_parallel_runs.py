"""W1 HTTP contract and native model selection, all with fake sessions."""
import json

from httpx import ASGITransport, AsyncClient

from cyberscientist import api, compute, config, db
from cyberscientist.brains.base import RuntimeHealth, SessionRef
from cyberscientist.prime import PrimeHealth


def _models(executor: str = 'model-exec'):
    return {'brain': {'runtime':'codex','model_id':'model-brain','reasoning_effort':'xhigh'},
            'executor': {'runtime':'codex','model_id':executor,'reasoning_effort':'high'}}


async def test_import_and_edit_models_only_affects_new_runs():
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),
                           base_url='http://local') as client:
        imported = await client.post('/api/v1/challenges/import', json={
            'mode':'manual','title':'Model task','content':'fixture task',
            'model_config':_models()})
        assert imported.status_code == 200, imported.text
        cid = imported.json()['challenge']['id']
        first = await client.post('/api/v1/runs', json={'challenge_id':cid})
        assert first.status_code == 200, first.text
        changed = await client.put(f'/api/v1/challenges/{cid}/models', json={
            'model_config':_models('model-later')})
        assert changed.status_code == 200
        second = await client.post('/api/v1/runs', json={'challenge_id':cid})
        assert second.status_code == 200
        snap_a = first.json()['config_snapshot']['settings']['executor']
        snap_b = second.json()['config_snapshot']['settings']['executor']
        assert snap_a['model_id'] == 'model-exec'
        assert snap_b['model_id'] == 'model-later'
        assert changed.json()['model_config']['executor']['model_id'] == 'model-later'
        invalid = await client.put(f'/api/v1/challenges/{cid}/models', json={
            'model_config':_models('')})
        assert invalid.status_code == 422
        assert db.query_one('SELECT executor_config_json FROM challenges WHERE id=?',
                            (cid,))['executor_config_json'] == json.dumps(_models('model-later')['executor'])


async def test_model_selection_check_opens_native_session_without_turn(monkeypatch):
    seen = []
    class FakeBrain:
        async def inspect(self):
            return RuntimeHealth(installed=True)
        async def open(self, spec):
            seen.append(('open', spec['working_directory']))
            return SessionRef('fake','session')
        async def close(self, session):
            seen.append(('close',session.session_id))
    monkeypatch.setattr(api.controller, '_make_brain', lambda settings: FakeBrain())
    class FakeExecutor:
        async def inspect(self):
            return PrimeHealth(installed=True)
        async def start(self, spec):
            seen.append(('start', spec['working_directory']))
            return 'executor-session'
        async def close(self, session_id):
            seen.append(('executor-close', session_id))
    monkeypatch.setattr(api.controller, '_make_prime', lambda settings: FakeExecutor())
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),
                           base_url='http://local') as client:
        response = await client.post('/api/v1/connections/brain/test', json={
            'kind':'model_selection','model_choice':_models()['brain']})
        executor = await client.post('/api/v1/connections/executor/test', json={
            'kind':'model_selection','model_choice':_models()['executor']})
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
    assert executor.status_code == 200 and executor.json()['status'] == 'ok'
    assert [kind for kind, _ in seen] == ['open','close','start','executor-close']
    assert 'turn' not in response.text.lower() or '未发起模型 turn' in response.text


async def test_overview_lists_every_active_run_and_its_scoped_counts():
    for idx in range(2):
        db.execute("INSERT INTO challenges(id,platform_challenge_id,origin,title,content,"
                   "content_hash,imported_at,is_demo) VALUES(?,?,?,?,'text','hash',?,1)",
                   (f'overview-{idx}',f'demo-{idx}','demo://local',f'Task {idx}',db.utcnow()))
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),
                           base_url='http://local') as client:
        ids = []
        for idx in range(2):
            result = await client.post('/api/v1/runs', json={'challenge_id':f'overview-{idx}'})
            ids.append(result.json()['id'])
        overview = await client.get('/api/v1/runs/overview')
    assert overview.status_code == 200
    items = overview.json()['items']
    assert {item['id'] for item in items} == set(ids)
    assert {item['challenge_title'] for item in items} == {'Task 0','Task 1'}
    assert all(item['job_count'] == 0 and item['sandbox_count'] == 0 for item in items)


def test_pending_job_recovery_is_isolated_per_run(monkeypatch):
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo)"
               " VALUES('recovery','demo://local','Recovery','text','hash',?,1)",
               (db.utcnow(),))
    from cyberscientist.controller import RunController
    controller = RunController()
    runs = [controller.create_run('recovery')['id'] for _ in range(2)]
    for idx, rid in enumerate(runs):
        db.execute("INSERT INTO compute_jobs(operation_id,run_id,trial_id,request_hash,"
                   "spec_json,input_directory,status,created_at,updated_at)"
                   " VALUES(?,?,?,'hash','{}','.', 'submitting',?,?)",
                   (f'job-{idx}',rid,f'trial-{idx}',db.utcnow(),db.utcnow()))
    original = db.append_event_tx
    def fail_first(conn, run_id, *args, **kwargs):
        if run_id == runs[0]:
            raise RuntimeError('synthetic recovery failure')
        return original(conn, run_id, *args, **kwargs)
    monkeypatch.setattr(db, 'append_event_tx', fail_first)
    compute.recover_pending()
    states = [db.query_one('SELECT status FROM compute_jobs WHERE operation_id=?',
                           (f'job-{idx}',))['status'] for idx in range(2)]
    assert states == ['unknown','unknown']
