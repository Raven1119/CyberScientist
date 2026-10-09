"""Preview seals a source bundle before the official dry build; no platform calls."""
import hashlib
import json
import io
import zipfile

from cyberscientist import config, db, native_logs, ops_digest, ops_submission, mailboxes, cli_submission
from test_trace_narrative import _fixture
from test_cli_submission_cs14 import fake_build, prepare


def test_source_bundle_preview_uses_bound_native_bytes_without_reserving(tmp_path, monkeypatch):
    rid, tid, source, *rest = _fixture()
    trial_dir=rest[-1]
    output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(output,'w') as edited:
        for name in original.namelist():
            data=original.read(name)
            if name=='arm_manifest.json':
                manifest=json.loads(data);manifest['expected_outputs']=[{'path':'outputs/answer.json'}]
                data=json.dumps(manifest).encode()
            edited.writestr(name,data)
        edited.writestr('outputs/answer.json','{"answer":42}')
    source=output.getvalue()
    native=(json.dumps({'type':'session_meta','payload':{'id':'preview-native'}})+'\n').encode()
    log=tmp_path/'native.jsonl';log.write_bytes(native)
    ops_digest.record_session(rid,'executor','preview-native',{'native_log_path':str(log),'model':'gpt-6.1-sol'})
    native_logs.bind_trial(rid,tid,'preview-native')
    path=trial_dir/'result_package.zip';path.write_bytes(source)
    platform=prepare(tmp_path,monkeypatch)
    monkeypatch.setattr(mailboxes,'_platform_for_run',lambda rid:platform)
    db.execute("INSERT INTO mailboxes(id,email,role,status,secret_ref,platform,created_at) VALUES('preview','fixture@example.invalid','experiment','active','local:preview',?,?)",(platform.name,db.utcnow()))
    config.update_secret('preview','fixture-private-preview')
    calls=[]
    def process(argv,**kwargs):
        assert '--dry-run' in argv
        assert '--model' in argv
        calls.append(argv)
        from pathlib import Path
        assert Path(argv[argv.index('--trace')+1]).read_bytes()==native
        return fake_build(argv)
    monkeypatch.setattr(cli_submission.subprocess,'run',process)
    before=db.query_one('SELECT COUNT(*) FROM submissions')[0]
    result=ops_submission.preview({'run_id':rid,'trial_id':tid,'package_path':str(path),'mailbox_id':'preview'})
    assert result['status']=='built' and not result['submission_created']
    assert result['source_package_sha256']==hashlib.sha256(source).hexdigest()
    assert result['native_sha256']==hashlib.sha256(native).hexdigest()
    assert len(calls)==1 and db.query_one('SELECT COUNT(*) FROM submissions')[0]==before
    assert path.read_bytes()==source
