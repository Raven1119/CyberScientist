"""PI permissions are observed through the actual scoped API/MCP and file pages."""
import hashlib
import json
import asyncio
import threading
import pytest
from httpx import ASGITransport, AsyncClient
from cyberscientist import api, collab, config, codex_protocol, db, mcp_bridge, pi_files, skills
from cyberscientist.controller import RunController
from test_compute_gateway import run


def fixture_files(run, monkeypatch):
    rid, source = run
    root = source.parent
    db.execute('INSERT INTO trials(id,run_id,goal,success_check,created_at) VALUES(?,?,?,?,?)',
               ('trial_fixture', rid, 'read-only fixture', 'no science', db.utcnow()))
    skill_root = config.DATA_DIR / 'fixture-skills'
    skill = skill_root / 'example'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: Example\n---\nFixture skill full body\n')
    (skill / 'reference.md').write_text('Referenced fixture instructions')
    monkeypatch.setattr(skills, 'SKILL_DIRS', (skill_root,))
    return rid, root, skill


def test_scoped_skill_trial_resources_and_event_receipts(run, monkeypatch):
    rid, root, skill = fixture_files(run, monkeypatch)
    (root / 'result.txt').write_text('Actual fixture output 42')
    resource = config.WORKSPACE_DIR / 'challenges' / 'COLLAB_CH'
    resource.mkdir(parents=True, exist_ok=True);(resource / 'public.txt').write_text('public fixture resource')
    assert pi_files.access(rid, {'action':'list','scope':'skills'})['entries'][0]['name']=='example'
    for scope, path, text in [('skills','example/SKILL.md',(skill/'SKILL.md').read_text()),
                              ('skills','example/reference.md','Referenced fixture instructions'),
                              ('trials','trial_fixture/result.txt','Actual fixture output 42'),
                              ('resources','public.txt','public fixture resource')]:
        result = pi_files.access(rid, {'action':'read','scope':scope,'path':path})
        assert result['content']==text and result['sha256']==hashlib.sha256(text.encode()).hexdigest()
        assert result['source_path'] and result['next_offset'] is None and result['content_is_untrusted']
    events=db.query("SELECT payload FROM events WHERE run_id=? AND type='brain.file_read'", (rid,))
    assert len(events)==4 and all('content' not in json.loads(event['payload']) for event in events)
    assert not db.query('SELECT * FROM compute_jobs') and not db.query('SELECT * FROM submissions')


@pytest.mark.parametrize('path',['../secrets.json','/etc/passwd','trial_other/result.txt','trial_fixture/.env','trial_fixture/secrets.json'])
def test_private_or_other_run_paths_never_open(run,monkeypatch,path):
    rid,root,_=fixture_files(run,monkeypatch)
    monkeypatch.setattr(pi_files,'_open',lambda *a:pytest.fail('invalid identity/path must reject before opening'))
    with pytest.raises(ValueError):pi_files.access(rid,{'action':'read','scope':'trials','path':path})


def test_symlink_component_and_secret_in_later_page_rejected(run,monkeypatch):
    rid,root,_=fixture_files(run,monkeypatch)
    target=config.DATA_DIR/'outside.txt';target.write_text('private fixture')
    (root/'alias').symlink_to(target)
    with pytest.raises(ValueError,match='符号链接'):pi_files.access(rid,{'action':'read','scope':'trials','path':'trial_fixture/alias'})
    (root/'folder').symlink_to(config.DATA_DIR,target_is_directory=True)
    with pytest.raises(ValueError,match='符号链接'):pi_files.access(rid,{'action':'read','scope':'trials','path':'trial_fixture/folder/outside.txt'})
    secret='fixture-key-for-scoped-reader-boundary'
    monkeypatch.setattr(config,'sensitive_values',lambda:[secret])
    (root/'log.txt').write_bytes(b'x'*(1024*1024-8)+secret.encode())
    with pytest.raises(ValueError,match='密钥'):pi_files.access(rid,{'action':'read','scope':'trials','path':'trial_fixture/log.txt','limit':100})
    assert not db.query("SELECT * FROM events WHERE run_id=? AND type='brain.file_read'", (rid,))


def test_large_pages_hash_binding_and_no_write_action(run,monkeypatch):
    rid,root,_=fixture_files(run,monkeypatch);raw=b'abcdefghijklmnopqrstuvwxyz'*3000
    (root/'large.txt').write_bytes(raw);pages=[];offset=0;sha=hashlib.sha256(raw).hexdigest()
    while True:
        page=pi_files.access(rid,{'action':'read','scope':'trials','path':'trial_fixture/large.txt','offset':offset,'limit':4096,'expected_sha256':sha})
        assert page['sha256']==sha and page['bytes']<=4096;pages.append(page['content'].encode())
        if page['next_offset'] is None:break
        offset=page['next_offset']
    assert b''.join(pages)==raw
    (root/'large.txt').write_text('new version')
    with pytest.raises(ValueError,match='版本'):pi_files.access(rid,{'action':'read','scope':'trials','path':'trial_fixture/large.txt','expected_sha256':sha})
    with pytest.raises(ValueError):pi_files.access(rid,{'action':'write','scope':'trials','path':'trial_fixture/large.txt'})


async def test_actual_api_brain_only_and_mcp_dispatch(run,monkeypatch):
    rid,root,_=fixture_files(run,monkeypatch);(root/'result.txt').write_text('API receipt')
    with db.transaction() as conn:
        brain=collab.issue_token(conn,rid,'brain','read-fixture',1)
        executor=collab.issue_token(conn,rid,'executor','exe-fixture',1)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()),base_url='http://127.0.0.1') as client:
        payload={'action':'read','scope':'trials','path':'trial_fixture/result.txt'}
        denied=await client.post('/api/v1/tools/files',json=payload,headers={'Authorization':'Bearer '+executor})
        assert denied.status_code==403
        result=await client.post('/api/v1/tools/files',json=payload,headers={'Authorization':'Bearer '+brain})
        assert result.status_code==200 and result.json()['content']=='API receipt'
    monkeypatch.setenv('CS_TOOL_ROLE','brain')
    assert 'research_files' in {tool['name'] for tool in mcp_bridge._handle({'id':1,'method':'tools/list'})['result']['tools']}
    calls=[];monkeypatch.setattr(mcp_bridge,'_post',lambda path,args,**kw:calls.append((path,args)) or {'content':'MCP read'})
    mcp_bridge._handle({'id':2,'method':'tools/call','params':{'name':'research_files','arguments':payload}})
    assert calls==[('/api/v1/tools/files',payload)]
    monkeypatch.setenv('CS_TOOL_ROLE','executor')
    assert 'research_files' not in {tool['name'] for tool in mcp_bridge._handle({'id':1,'method':'tools/list'})['result']['tools']}


def test_pi_native_shell_disabled_and_lkm_body_not_inlined(run,monkeypatch):
    rid,_,_=fixture_files(run,monkeypatch)
    controller=RunController();spec=controller._brain_spec(rid,config.load_settings(),config.DATA_DIR)
    params=codex_protocol.thread_params(spec,'gpt-6-astra','xhigh',writable=False)
    assert params['config']['features.shell_tool'] is False and params['config']['features.unified_exec'] is False
    assert params['config']['features.multi_agent'] is False and params['config']['features.multi_agent_v2'] is False
    assert 'research_files' in params['config']['mcp_servers']['cyberscientist']['enabled_tools']
    assert '优先' in spec['instructions'] and '实际结果' in spec['instructions']
    segment=skills.brain_prompt_segment([{'id':'example','name':'Example','description':'fixture','source':str(config.DATA_DIR/'fixture-skills')}])
    assert 'Fixture skill full body' not in segment and 'research_files' in segment
    # Legacy PI also receives the scoped reader without changing its snapshot.
    snapshot=db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(rid,))[0]
    legacy=json.loads(snapshot);legacy.pop('sparse_brain_version',None)
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(legacy),rid))
    assert controller._brain_spec(rid,config.load_settings(),config.DATA_DIR)['pi_files_readonly']


def test_nested_system_skill_and_reference_have_stable_scoped_ids(run, monkeypatch):
    rid, _, skill = fixture_files(run, monkeypatch)
    nested = skill.parent / '.system' / 'fixture-docs'
    nested.mkdir(parents=True)
    (nested / 'SKILL.md').write_text('Nested system skill full body')
    (nested / 'references').mkdir()
    (nested / 'references' / 'guide.md').write_text('Nested referenced guide')
    outside = config.DATA_DIR / 'unregistered-skill'
    outside.mkdir(); (outside / 'SKILL.md').write_text('Unregistered private fixture')
    (skill.parent / 'linked-skill').symlink_to(outside, target_is_directory=True)
    names = [item['name'] for item in pi_files.access(rid, {'action':'list', 'scope':'skills'})['entries']]
    assert names == ['.system/fixture-docs', 'example']
    for path, text in [('SKILL.md','Nested system skill full body'), ('references/guide.md','Nested referenced guide')]:
        read = pi_files.access(rid, {'action':'read', 'scope':'skills', 'path':'.system/fixture-docs/'+path})
        assert read['content'] == text and read['source_path'] == str(nested/path)
    with pytest.raises(ValueError):
        pi_files.access(rid, {'action':'read', 'scope':'skills', 'path':'linked-skill/SKILL.md'})


def test_long_unregistered_private_key_crossing_chunks_is_rejected(run, monkeypatch):
    rid, root, _ = fixture_files(run, monkeypatch)
    # Deliberately invalid synthetic PEM, longer than the overlap window.
    raw = b'x'*(1024*1024-6000) + b'-----BEGIN RSA PRIVATE KEY-----\n' + b'A'*12000 + b'\n-----END RSA PRIVATE KEY-----'
    (root/'long.txt').write_bytes(raw)
    with pytest.raises(ValueError, match='密钥'):
        pi_files.access(rid, {'action':'read', 'scope':'trials', 'path':'trial_fixture/long.txt', 'limit':100})


@pytest.mark.parametrize('prefix', [b'plain', b'PK'])
def test_growing_file_stops_after_first_changed_chunk(run, monkeypatch, prefix):
    rid, root, _ = fixture_files(run, monkeypatch)
    path = root/'growing.txt'; path.write_bytes(prefix+b'x'*(2*1024*1024))
    original = pi_files.os.fdopen
    reads = []
    class GrowingReader:
        def __init__(self, fd, mode): self.stream = original(fd, mode)
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def fileno(self): return self.stream.fileno()
        def read(self, count):
            reads.append(count)
            raw = self.stream.read(count)
            with path.open('ab') as writer: writer.write(b'x'*(17*1024*1024))
            return raw
    monkeypatch.setattr(pi_files.os, 'fdopen', GrowingReader)
    with pytest.raises(ValueError, match='变化'):
        pi_files.access(rid, {'action':'read', 'scope':'trials', 'path':'trial_fixture/growing.txt'})
    assert reads == [1024*1024]


async def test_cancelled_http_reader_is_drained_before_safe_shutdown(run, monkeypatch):
    from cyberscientist import power, resource_coordinator
    rid, _, _ = fixture_files(run, monkeypatch)
    db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    def blocked_read(*args):
        entered.set()
        assert release.wait(5)
        closed.set()
        return {'content':'bounded fixture'}
    monkeypatch.setattr(pi_files, 'access', blocked_read)
    with db.transaction() as conn:
        token = collab.issue_token(conn, rid, 'brain', 'cancel-fixture', 1)
    async with AsyncClient(transport=ASGITransport(app=api.create_app()), base_url='http://127.0.0.1') as client:
        request = asyncio.create_task(client.post('/api/v1/tools/files', json={'action':'read','scope':'trials','path':'trial_fixture/result.txt'}, headers={'Authorization':'Bearer '+token}))
        shutdown = None
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            request.cancel()
            with pytest.raises(asyncio.CancelledError): await request
            assert resource_coordinator.auxiliary_tasks()
            shutdown = asyncio.create_task(power.safe_shutdown(api.controller, timeout=.2))
            await asyncio.sleep(.02)
            assert not shutdown.done() and not closed.is_set()
            release.set()
            result = await asyncio.wait_for(shutdown, 2)
            assert closed.is_set() and result['can_shutdown'] and not resource_coordinator.auxiliary_tasks()
            denied = await client.post('/api/v1/tools/files', json={}, headers={'Authorization':'Bearer '+token})
            assert denied.status_code == 409 and '安全关机' in denied.text
        finally:
            release.set()
            if shutdown: await asyncio.gather(shutdown, return_exceptions=True)


@pytest.mark.parametrize('abnormal', [False, True])
async def test_production_lifespan_drains_cancelled_file_reader(run, monkeypatch, abnormal):
    from cyberscientist import machine_catalog, resource_coordinator
    rid, _, _ = fixture_files(run, monkeypatch)
    db.execute("UPDATE runs SET phase='paused' WHERE id=?", (rid,))
    monkeypatch.setattr(machine_catalog, 'refresh', lambda: None)
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    exiting = asyncio.Event()
    def blocked_read(*args):
        entered.set(); assert release.wait(5); closed.set(); return {}
    monkeypatch.setattr(pi_files, 'access', blocked_read)
    with db.transaction() as conn:
        token=collab.issue_token(conn,rid,'brain','lifespan-fixture',1)
    app=api.create_app()
    async def host():
        try:
            async with app.router.lifespan_context(app):
                async with AsyncClient(transport=ASGITransport(app=app),base_url='http://127.0.0.1') as client:
                    request=asyncio.create_task(client.post('/api/v1/tools/files',json={},headers={'Authorization':'Bearer '+token}))
                    assert await asyncio.to_thread(entered.wait,1)
                    request.cancel()
                    with pytest.raises(asyncio.CancelledError): await request
                exiting.set()
                if abnormal: raise RuntimeError('fixture host failure')
        except RuntimeError:
            assert abnormal
    task=asyncio.create_task(host())
    try:
        await asyncio.wait_for(exiting.wait(),2)
        await asyncio.sleep(.02)
        assert not task.done() and not closed.is_set()
        release.set(); await asyncio.wait_for(task,2)
        assert closed.is_set() and not resource_coordinator.auxiliary_tasks()
    finally:
        release.set(); await asyncio.gather(task,return_exceptions=True)
