import io
import zipfile

from . import collect_bundles,common


def test_crc_error_cannot_persist_raw_secret_in_member_name(tmp_path,monkeypatch):
    token='sk-'+'A'*30;data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_STORED) as z:z.writestr(token+'.txt',b'hello-world')
    corrupted=data.getvalue().replace(b'hello-world',b'Hello-world')
    monkeypatch.setattr(common,'credentials',lambda:({},'',{}))
    monkeypatch.setattr(collect_bundles,'download',lambda *_:corrupted)
    class Client:
        root=tmp_path
        redactor=common.Redactor()
    result=collect_bundles.fetch_bundle(Client(),{'attempt_id':'1','challenge_id':'c','ours':False,'bundle_reason':'test'})
    assert result['status']=='failed' and result['reason']=='bundle_processing_failed:BadZipFile'
    assert token not in str(result) and not list(tmp_path.rglob('*.zip'))
