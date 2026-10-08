from cyberscientist import db, submission_downloads
from test_auto_harvest import seed


def test_no_remote_download_url_is_unknown_and_not_repeated():
    rid,source=seed(10)
    class Platform:
        base_url='https://platform.invalid/api'
        calls=0
        def fetch_attempt(self,*a):
            self.calls+=1
            return {'bundleAvailable':False,'bundlePath':None}
    p=Platform()
    first=submission_downloads.audit(source['id'],p,'fixture')
    assert first['status']=='unknown' and first['bundle_available'] is False
    assert submission_downloads.audit(source['id'],p,'fixture')==first
    assert p.calls==1
    assert db.query_one('SELECT COUNT(*) FROM submission_daily_audits')[0]==1
