"""Daily remote artifact audit; missing download metadata remains unknown."""
import hashlib
import io
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from . import config, db


def audit(submission_id, platform, secret):
    row = db.query_one('SELECT * FROM submissions WHERE id=?', (submission_id,))
    day = datetime.now(timezone.utc).date().isoformat()
    prior = db.query_one('SELECT * FROM submission_daily_audits WHERE mailbox_id=? AND day=?', (row['mailbox_id'], day))
    if prior: return json.loads(prior['result_json'])
    result = {'status': 'unknown', 'submission_id': submission_id, 'day_utc': day}
    try:
        item = platform.fetch_attempt('', secret, row['platform_ref'])
        address = item.get('bundleUrl') or item.get('bundlePath')
        base = urllib.parse.urlparse(platform.base_url)
        remote = urllib.parse.urlparse(address or '')
        if remote.scheme not in ('http', 'https') or (remote.scheme, remote.netloc) != (base.scheme, base.netloc):
            result.update(reason='平台未提供可核验的同源下载URL；不猜测私有存储路由', bundle_available=item.get('bundleAvailable'))
        else:
            request = urllib.request.Request(address, headers={'Authorization': 'Bearer ' + secret})
            # Refuse cross-origin redirect before forwarding credentials.
            class SameOrigin(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    if (urllib.parse.urlparse(newurl).scheme, urllib.parse.urlparse(newurl).netloc) != (base.scheme, base.netloc): raise ValueError('跨源下载跳转')
                    return super().redirect_request(req, fp, code, msg, headers, newurl)
            with urllib.request.build_opener(SameOrigin()).open(request, timeout=60) as response:
                content = response.read(512 * 1024**2 + 1)
            if len(content) > 512 * 1024**2: raise ValueError('远端包超过下载上限')
            local = (config.WORKSPACE_DIR / row['official_package_path']).read_bytes()
            def entries(raw):
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    names=archive.namelist()
                    if len(names)!=len(set(names)): raise ValueError('重复ZIP成员')
                    return sorted(names)
            result.update(sha256=hashlib.sha256(content).hexdigest(), file_list=entries(content),
                          same_file_list=entries(content)==entries(local), same_hash=content==local)
            result['status']='verified' if result['same_hash'] and result['same_file_list'] else 'mismatch'
            path=config.WORKSPACE_DIR/'submissions'/submission_id/'platform-download.zip'
            path.write_bytes(content)
    except Exception as exc: result.update(reason=type(exc).__name__)
    with db.transaction() as conn:
        conn.execute('INSERT OR IGNORE INTO submission_daily_audits VALUES(?,?,?,?,?)', (row['mailbox_id'],day,submission_id,json.dumps(result),db.utcnow()))
        db.append_event_tx(conn,row['run_id'],'controller','submission.daily_download_audit',result,trial_id=row['trial_id'])
    return result
