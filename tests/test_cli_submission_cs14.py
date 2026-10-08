import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile
import pytest
from cyberscientist import cli_submission, config, db, mailboxes, native_logs, ops_digest
from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform, PlatformError, submit_once


def bundle(trial='trial-final'):
    native = (json.dumps({'type': 'session_meta', 'payload': {'id': 'native-final'}})+'\n').encode()
    manifest = {'arm_version': '1.1', 'raw_messages': 'raw_messages.jsonl', 'expected_outputs': [{'path':'outputs/answer.json'}]}
    proof = {'sha256': hashlib.sha256(native).hexdigest(), 'session_id': 'native-final', 'model': 'gpt-5.6-terra', 'trial_id': trial}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('outputs/answer.json', '{"answer":1}')
        archive.writestr('arm_manifest.json', json.dumps(manifest))
        archive.writestr('raw_messages.jsonl', native)
        archive.writestr('provenance/native_session.json', json.dumps(proof))
    return output.getvalue(), native


def fake_build(argv):
    package=Path(argv[argv.index('--bundle-out')+1]);out=Path(argv[argv.index('--outputs')+1])
    with zipfile.ZipFile(package,'w') as archive:
        for f in out.rglob('*'):
            if f.is_file(): archive.writestr('outputs/'+f.relative_to(out).as_posix(),f.read_bytes())
    return subprocess.CompletedProcess(argv,0,json.dumps({'status':'dry_run','bundle_sha256':hashlib.sha256(package.read_bytes()).hexdigest()}),'')


def prepare(tmp_path, monkeypatch):
    exe = tmp_path/'official-cli-fixture'; exe.write_text('fixture')
    settings = config.load_settings(); settings['submission_transport']='cli'; settings['playground']['cli_executable']=str(exe); config.save_settings(settings)
    monkeypatch.setattr(cli_submission.platform_contracts, 'validate_bundle', lambda *a: {'valid': True})
    platform = BohriumPlaygroundPlatform('https://play.bohrium.com/api')
    monkeypatch.setattr(platform, '_http', lambda method, path, **k: {'id':'owner'} if path=='/auth/me' else {'attempts':[],'total':0})
    return platform


def test_native_bytes_and_token_env_only_one_official_invocation(tmp_path, monkeypatch):
    platform = prepare(tmp_path, monkeypatch); content, native = bundle(); calls=[]; homes=[]
    def process(argv, env, **kwargs):
        calls.append(argv); home=Path(env['HOME']); homes.append(home)
        assert env['CS_PLAYGROUND_SUBMIT_TOKEN']=='fake-private-token' and 'fake-private-token' not in str(argv)
        assert not (home/'absent-config.json').exists() and not (home/'absent-credentials.env').exists()
        assert '--bundle' not in argv
        built=fake_build(argv)
        if '--dry-run' in argv: return built
        assert Path(argv[argv.index('--trace')+1]).read_bytes()==native
        assert all(b'fake-private-token' not in p.read_bytes() for p in home.rglob('*') if p.is_file())
        return subprocess.CompletedProcess(argv,0,json.dumps({'schema_version':'playground-cli-submission/v0','status':'submitted','challenge_id':'ended','attempt_id':'123','bundle_sha256':hashlib.sha256(Path(argv[argv.index('--bundle-out')+1]).read_bytes()).hexdigest(),'worker_api_base':cli_submission.WORKER,'bundle_response':{'accepted':True}}),'')
    monkeypatch.setattr(cli_submission.subprocess,'run',process)
    result=submit_once(platform,'fixture','fake-private-token','unused.zip','ended',{'package_bytes':content})
    assert result['accepted'] and result['transport']=='cli' and len(calls)==2
    assert all(not home.exists() for home in homes)


def test_timeout_keeps_unknown_no_retry_and_cleans_temp(tmp_path, monkeypatch):
    platform=prepare(tmp_path,monkeypatch);content,_=bundle();calls=[];homes=[]
    def process(argv,env,**kwargs):
        calls.append(argv);homes.append(Path(env['HOME']))
        if '--dry-run' in argv: return fake_build(argv)
        raise subprocess.TimeoutExpired(argv,600)
    monkeypatch.setattr(cli_submission.subprocess,'run',process)
    with pytest.raises(PlatformError) as exc:submit_once(platform,'fixture','fake-private-token','unused.zip','ended',{'package_bytes':content})
    assert not exc.value.no_side_effect and len(calls)==2 and all(not p.exists() for p in homes)


def test_missing_raw_stops_before_process_and_releases_unsent(tmp_path,monkeypatch):
    from test_mailbox_platform import valid_arm_zip
    platform=prepare(tmp_path,monkeypatch)
    monkeypatch.setattr(cli_submission.subprocess,'run',lambda *a,**k:pytest.fail('no invocation'))
    with pytest.raises(PlatformError) as exc:submit_once(platform,'fixture','fake-private-token','unused.zip','ended',{'package_bytes':valid_arm_zip()})
    assert exc.value.no_side_effect


@pytest.mark.parametrize('transport',['api','cli'])
def test_transport_dispatch_is_explicit(tmp_path,monkeypatch,transport):
    platform=prepare(tmp_path,monkeypatch);settings=config.load_settings();settings['submission_transport']=transport;config.save_settings(settings);calls=[]
    monkeypatch.setattr(platform,'submit_package',lambda *a,**k:calls.append('api') or {})
    monkeypatch.setattr(cli_submission,'submit',lambda *a,**k:calls.append('cli') or {})
    submit_once(platform,'fixture','private','p','topic',{})
    assert calls==[transport]


def test_trial_native_binding_snapshot_exact_and_rejects_secret(tmp_path):
    from test_auto_harvest import seed
    rid,_=seed(10);path=tmp_path/'native.jsonl';content=(json.dumps({'type':'session_meta','payload':{'id':'session-final'}})+'\n').encode();path.write_bytes(content)
    ops_digest.record_session(rid,'executor','session-final',{'native_log_path':str(path),'model':'gpt-5.6-terra'})
    native_logs.bind_trial(rid,'trial-final','session-final');snapshot=native_logs.snapshot(rid,'trial-final')
    assert snapshot['bytes']==content and path.read_bytes()==content
    config.update_secret('native-test','native-secret-value')
    path.write_bytes(content+b'{"type":"message","text":"native-secret-value"}\n')
    with pytest.raises(ValueError,match='不得改写'):native_logs.snapshot(rid,'trial-final')


def test_unknown_reconciles_account_topic_and_same_hash_never_sends(monkeypatch):
    from test_auto_harvest import seed
    rid,source=seed(10);db.execute("UPDATE submissions SET status='unknown',platform_ref=NULL WHERE id=?",(source['id'],))
    db.append_event(rid,'controller','submission.cli_baseline',{'submission_id':source['id'],'owner_id':'owner','attempt_ids':['old']})
    platform=BohriumPlaygroundPlatform('https://play.bohrium.com/api');monkeypatch.setattr(cli_submission,'account_attempts',lambda *a:{'owner_id':'owner','attempts':[{'id':'new'}],'complete':True})
    monkeypatch.setattr(platform,'fetch_attempt',lambda *a:{'challengeId':'ended','authorId':'owner','bundleSha256':source['package_sha256']})
    result=cli_submission.reconcile_unknown(source['id'],platform,'private','ended')
    assert result['status']=='matched' and not result['retry_allowed']
    row=db.query_one('SELECT * FROM submissions WHERE id=?',(source['id'],));assert row['platform_ref']=='new' and row['status']=='unknown'
    monkeypatch.setattr(cli_submission,'account_attempts',lambda *a:{'owner_id':'owner','attempts':[],'complete':True})
    assert cli_submission.reconcile_unknown(source['id'],platform,'private','ended')['status']=='absence_observed'


def test_polling_unknown_without_reference_reaches_readonly_reconciliation(monkeypatch):
    from test_auto_harvest import seed
    rid, source = seed(10)
    db.execute("UPDATE submissions SET status='unknown',platform_ref=NULL WHERE id=?", (source['id'],))
    platform = BohriumPlaygroundPlatform('https://play.bohrium.com/api')
    monkeypatch.setattr(mailboxes, '_platform', lambda: platform)
    monkeypatch.setattr(mailboxes, '_platform_for_run', lambda *a: platform)
    seen = []
    def reconcile(*args):
        seen.append(args[0])
        return {'status': 'absence_observed', 'retry_allowed': False}
    monkeypatch.setattr(cli_submission, 'reconcile_unknown', reconcile)
    mailboxes.poll_scores(rid, manual=True)
    assert seen == [source['id']]
    assert db.query_one('SELECT status FROM submissions WHERE id=?', (source['id'],))['status'] == 'unknown'


def test_failed_cli_preserves_bounded_redacted_process_diagnostics(tmp_path, monkeypatch):
    platform = prepare(tmp_path, monkeypatch)
    content, _ = bundle()
    secret = 'fixture-process-private-token'
    calls, feedback = [], []
    def process(argv, **kwargs):
        calls.append(argv)
        if '--dry-run' in argv: return fake_build(argv)
        return subprocess.CompletedProcess(argv, 1, 'not JSON ' + secret,
            'HTTP 403 specific upstream cause ' + secret + 'x' * 3930 + secret)
    monkeypatch.setattr(cli_submission.subprocess, 'run', process)
    with pytest.raises(PlatformError) as error:
        submit_once(platform, 'fixture', secret, 'unused.zip', 'ended',
            {'package_bytes': content, 'on_feedback': lambda kind, value: feedback.append((kind, value))})
    assert not error.value.no_side_effect and len(calls) == 2
    diagnostic = next(value for kind, value in feedback if kind == 'cli_process')
    assert diagnostic['exit_code'] == 1 and diagnostic['diagnostic_only'] is True
    assert 'HTTP 403 specific upstream cause' in diagnostic['stderr']
    assert len(diagnostic['stderr']) <= 4000
    assert secret not in json.dumps(feedback) and secret not in str(error.value)
    assert 'fixture-process-private' not in json.dumps(feedback)


def test_operator_submission_caps_survive_unlimited_compute():
    from test_auto_harvest import seed
    rid,_=seed(10);row=db.query_one('SELECT * FROM runs WHERE id=?',(rid,));snapshot=json.loads(row['config_snapshot']);snapshot['operator_submission_limits']={'experimental':1,'harvest':0};db.execute('UPDATE runs SET config_snapshot=? WHERE id=?',(json.dumps(snapshot),rid));db.execute('UPDATE authorizations SET unlimited_resources=1,max_submissions=0 WHERE run_id=?',(rid,))
    with db.transaction() as conn:
        with pytest.raises(mailboxes.MailboxError,match='独立提交上限'):mailboxes._check_budget(conn,rid)
        with pytest.raises(mailboxes.MailboxError,match='独立提交上限'):mailboxes._check_budget(conn,rid,terminal_harvest=True)


def test_frozen_policy_caps_are_visible_to_pi_and_enforced():
    from test_auto_harvest import seed
    from cyberscientist import observation
    rid, _ = seed(10)
    row = db.query_one('SELECT config_snapshot FROM runs WHERE id=?', (rid,))
    snapshot = json.loads(row[0]); snapshot['settings']['policy']['submission_limits'] = {'experimental': 1, 'harvest': 1}
    db.execute('UPDATE runs SET config_snapshot=? WHERE id=?', (json.dumps(snapshot), rid))
    facts = observation.authority_facts(rid)['authorization']
    assert facts['submission_limits'] == {'experimental': 1, 'harvest': 1}
    assert facts['submission_reservations']['experimental'] == 1
    with db.transaction() as conn:
        with pytest.raises(mailboxes.MailboxError, match='独立提交上限'): mailboxes._check_budget(conn, rid)


async def test_submission_transport_settings_roundtrip():
    from httpx import ASGITransport,AsyncClient
    from cyberscientist.api import create_app
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://fixture') as client:
        for mode in ('cli','api','cli'):
            before=(await client.get('/api/v1/settings')).json()
            saved=await client.put('/api/v1/settings',json={'base_revision':before['revision'],'settings':{'submission_transport':mode}})
            assert saved.status_code==200 and (await client.get('/api/v1/settings')).json()['submission_transport']==mode
        before=(await client.get('/api/v1/settings')).json()
        assert (await client.put('/api/v1/settings',json={'base_revision':before['revision'],'settings':{'submission_transport':'bad'}})).status_code==422
    db.init_db();assert config.load_settings()['submission_transport']=='cli' and config.DEFAULT_SETTINGS['submission_transport']=='cli'


def test_harvest_pipeline_dispatches_cli_with_identical_frozen_bytes(monkeypatch):
    from test_auto_harvest import seed
    rid, source = seed(100)
    db.execute("UPDATE mailboxes SET platform='bohrium_playground',is_demo=0 WHERE role='harvest'")
    settings = config.load_settings(); settings['submission_transport'] = 'cli'; config.save_settings(settings)
    platform = BohriumPlaygroundPlatform('https://play.bohrium.com/api')
    monkeypatch.setattr(mailboxes, '_platform_for_run', lambda *a: platform)
    monkeypatch.setattr(mailboxes, '_guard_submission_target', lambda *a: None)
    calls = []
    def upload(platform, email, secret, path, challenge_id, meta):
        calls.append((email, meta))
        assert meta['package_bytes'] == (config.WORKSPACE_DIR/source['package_path']).read_bytes()
        assert hashlib.sha256(meta['package_bytes']).hexdigest() == source['package_sha256']
        return {'accepted': True, 'receipt': 'harvest-fixture', 'transport': 'cli'}
    monkeypatch.setattr(cli_submission, 'submit', upload)
    result = mailboxes.harvest_submit(source['id'], 'cli-harvest', True)
    assert result['status'] == 'submitted' and len(calls) == 1
    assert calls[0][0] == 'owned@example.com' and calls[0][1]['trial_id'] == source['trial_id']
    assert mailboxes.harvest_submit(source['id'], 'cli-harvest', True)['deduplicated']
    assert len(calls) == 1


def test_seal_includes_exact_bound_native_bytes_and_hash(tmp_path):
    from test_auto_harvest import seed
    from test_ev_upgrade import _bundle
    from cyberscientist import package_seal
    rid, _ = seed(10)
    path = tmp_path/'native.jsonl'
    raw = b'{"type":"session_meta","payload":{"id":"final-session"}}\n'
    path.write_bytes(raw)
    ops_digest.record_session(rid, 'executor', 'final-session', {'native_log_path': str(path), 'model': 'gpt-5.6-terra'})
    native_logs.bind_trial(rid, 'final-trial', 'final-session')
    sealed, _ = package_seal.seal(_bundle(), rid, 'final-trial', 0)
    manifest, stored, proof = cli_submission._files(sealed)
    assert stored == raw == path.read_bytes() and proof['trial_id'] == 'final-trial'
    assert manifest['raw_messages'] == 'raw_messages.jsonl'
    assert package_seal.seal(_bundle(), rid, 'final-trial', 0)[0] == sealed


def test_readonly_failure_before_cli_is_definitively_unsent(tmp_path, monkeypatch):
    platform = prepare(tmp_path, monkeypatch); content, _ = bundle()
    monkeypatch.setattr(platform, '_http', lambda *a, **k: (_ for _ in ()).throw(PlatformError('GET unavailable')))
    monkeypatch.setattr(cli_submission.subprocess, 'run', lambda *a, **k: pytest.fail('not sent'))
    with pytest.raises(PlatformError) as caught:
        submit_once(platform, 'fixture', 'private', 'unused', 'ended', {'package_bytes': content})
    assert caught.value.no_side_effect
