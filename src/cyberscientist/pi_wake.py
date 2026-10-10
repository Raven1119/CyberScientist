"""Durable PI notifications; no model calls during directory monitoring."""
import hashlib
import json
from datetime import datetime, timezone
from . import config, db, submission_outputs, track_clock


def _duration(seconds):
    return 'unknown' if seconds is None else f'{max(0, int(seconds)) // 60} 分钟'


def deliveries(run):
    tid = run['current_trial_id']
    paths = (submission_outputs.contract_for_run(run['id']) or {}).get('paths') or []
    root = config.WORKSPACE_DIR / 'runs' / run['id'] / 'trials' / (tid or '')
    files = {}
    for name in paths if tid else []:
        try:
            relative = submission_outputs.source_path(name)
        except ValueError:
            continue
        candidates = [root / relative]
        if not relative.startswith('outputs/'):
            candidates.append(root / 'outputs' / relative)
        for path in candidates:
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()):
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b''):
                        digest.update(chunk)
                files[name] = {'sha256': digest.hexdigest(), 'bytes': path.stat().st_size}
                break
    return {'complete': bool(tid and paths) and len(files) == len(paths), 'files': files}


def cadence(run_id, *, now=None):
    now = now or datetime.now(timezone.utc)
    run = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    if not run:
        return {}
    approval = db.query_one("SELECT approved_at FROM method_approvals WHERE run_id=? AND status='approved'", (run_id,))
    approved = track_clock.instant(approval['approved_at']) if approval else None
    sent = db.query("SELECT id,submitted_at,platform_status,harbor_score AS science_score,score FROM submissions WHERE run_id=? AND status='submitted' ORDER BY submitted_at DESC", (run_id,))
    recent = sent[0] if sent else None
    last = track_clock.instant(recent['submitted_at']) if recent else None
    end = track_clock.for_run(run)['end']
    elapsed = (now-approved).total_seconds() if approved else None
    since = (now-last).total_seconds() if last else None
    remaining = (end-now).total_seconds() if end else None
    receipt = (f"{recent['id']}：{recent['platform_status'] or 'unknown'}，科学分={recent['science_score'] if recent['science_score'] is not None else 'unknown'}，展示分={recent['score'] if recent['score'] is not None else 'unknown'}" if recent else '尚无')
    delivery = deliveries(run)
    due = elapsed is not None and elapsed >= 5400 and delivery['complete'] and not sent
    text = f'节奏：方法批准后已 {_duration(elapsed)}；上次提交在 {_duration(since)} 前（共 {len(sent)} 次）；最近回执：{receipt}；比赛剩余 {_duration(remaining)}。'
    if due:
        text += f'\n首次提交待办：批准后已 {_duration(elapsed)}，交付文件已齐，尚未提交。'
    return {'cadence_md': text, 'first_submission_due': due, 'elapsed_seconds': elapsed,
            'since_last_submission_seconds': since, 'submission_count': len(sent),
            'receipt_summary': receipt, 'remaining_seconds': remaining, 'deliverables': delivery}


def collect(controller, run_id, *, now=None):
    now = now or datetime.now(timezone.utc)
    run = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    if not run or run['phase'] != 'running' or run['gate'] in ('awaiting_method_approval', 'awaiting_budget', 'stopped'):
        return None
    key = 'pi_watch:' + run_id
    with db.transaction() as conn:
        row = conn.execute('SELECT value FROM system_state WHERE key=?', (key,)).fetchone()
        state = json.loads(row['value']) if row else {'cursor': 0, 'files': {}, 'last_wake': run['started_at'] or run['created_at']}
        cursor = conn.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE run_id=?', (run_id,)).fetchone()[0]
        events = conn.execute('SELECT * FROM events WHERE run_id=? AND seq>? AND seq<=? ORDER BY seq', (run_id,state['cursor'],cursor)).fetchall()
        texts = []; reasons = []; current = deliveries(run)
        for event in events:
            payload = json.loads(event['payload']); kind = event['type']
            terminal = (kind == 'job.observed' and payload.get('status') in ('Finished','Failed','Stopped') or
                        kind in ('sandbox.background_polled','sandbox.background_observed') and payload.get('status') in ('completed','failed','cancelled'))
            if not terminal:
                continue
            ident = payload.get('operation_id') or payload.get('platform_job_id')
            if conn.execute("SELECT 1 FROM events WHERE run_id=? AND type='compute.finished' AND json_extract(payload,'$.id')=?", (run_id,ident)).fetchone():
                continue
            remote = payload.get('remote') or {}
            seconds = payload.get('elapsed_seconds', remote.get('spendTime'))
            if seconds is None and kind.startswith('sandbox.'):
                op = conn.execute('SELECT started_at,completed_at FROM compute_sandbox_operations WHERE operation_id=?', (ident,)).fetchone()
                if op and track_clock.instant(op['started_at']) and track_clock.instant(op['completed_at']):
                    seconds = (track_clock.instant(op['completed_at'])-track_clock.instant(op['started_at'])).total_seconds()
            operation_delivery = deliveries(dict(run) | {'current_trial_id': event['trial_id']}) if event['trial_id'] else {'files': {}}
            files = payload.get('files') or list(operation_delivery['files'])
            fact = {'source_seq': event['seq'], 'kind': 'Job' if kind.startswith('job.') else '沙箱后台命令', 'id': ident,
                    'platform_job_id': payload.get('platform_job_id'), 'exit_code': payload.get('exit_code',remote.get('exitCode','unknown')),
                    'duration_seconds': seconds, 'files': files, 'files_status': 'observed' if files else 'unknown'}
            db.append_event_tx(conn,run_id,'controller','compute.finished',fact,trial_id=event['trial_id'])
            reasons.append('compute.finished')
            texts.append(f"计算已结束：{fact['kind']} {ident}，退出码 {fact['exit_code']}，耗时 {_duration(seconds)}，产出 {files or 'unknown（尚未观察到产出文件）'}。\n请判断：现在是否已有一个可以提交的完整结果？有就先提交。")
        previous = state.get('files',{}) if state.get('trial_id') == run['current_trial_id'] else {}
        changed = [name for name,value in current['files'].items() if name in previous and value != previous[name]]
        ready = current['complete'] and (not state.get('complete') or current['files'] != previous or state.get('trial_id') != run['current_trial_id'])
        if changed or ready:
            fact = {'files': list(current['files']), 'updated': changed, 'complete': current['complete']}
            db.append_event_tx(conn,run_id,'controller','deliverables.ready',fact,trial_id=run['current_trial_id'])
            reasons.append('deliverables.ready')
            texts.append(f"交付目录中，题面输出契约要求的文件已齐（或有更新）：{fact['files']}。\n如果这是一个完整结果，请提交；更细的验证可以在提交之后做。")
        review = conn.execute("SELECT updated_at,through_seq FROM review_requests WHERE run_id=? AND status='done' ORDER BY updated_at DESC LIMIT 1", (run_id,)).fetchone()
        last = max(filter(None, (track_clock.instant(state.get('last_wake')), track_clock.instant(review['updated_at']) if review else None)), default=now)
        quiet = (now-last).total_seconds()
        interval = config.load_settings()['run_defaults'].get('pi_review_interval_seconds',1800)
        pending = conn.execute("SELECT id,frame_json FROM review_requests WHERE run_id=? AND status='pending' ORDER BY blocking DESC,created_at LIMIT 1", (run_id,)).fetchone()
        running = conn.execute("SELECT 1 FROM review_requests WHERE run_id=? AND status='running'", (run_id,)).fetchone()
        if not reasons and not pending and not running and quiet >= interval:
            since = review['through_seq'] or 0 if review else 0
            summary = [dict(r) for r in conn.execute("SELECT seq,type FROM events WHERE run_id=? AND seq>? AND source!='brain' ORDER BY seq DESC LIMIT 100", (run_id,since))]
            facts = {'actions': summary, 'compute': [dict(r) for r in conn.execute('SELECT operation_id,status FROM compute_jobs WHERE run_id=?', (run_id,))], 'deliverables': current, 'receipts': cadence(run_id,now=now)['receipt_summary']}
            reasons.append('pi.periodic_review')
            texts.append(f'定时审阅：距上次审阅 {quiet/60:.1f} 分钟。自上次以来：{json.dumps(facts,ensure_ascii=False)}。\n请判断是否需要提交、改向或停止某项工作。')
        bits = cadence(run_id,now=now)
        if bits.get('first_submission_due') and not state.get('due_alert'):
            db.append_event_tx(conn,run_id,'controller','submission.first_due',bits,trial_id=run['current_trial_id'])
            state['due_alert'] = True
        request_id = None
        if reasons:
            from . import collab
            request_id = pending['id'] if pending else collab._enqueue_request_tx(conn,run_id,source='executor',blocking=False,trigger='pi_proactive_review')
            extra = json.loads(pending['frame_json'] or '{}') if pending else {}
            extra.setdefault('wake_reasons',[]).extend(reasons)
            extra.setdefault('wake_messages',[]).extend(texts)
            conn.execute('UPDATE review_requests SET frame_json=? WHERE id=?',(json.dumps(extra,ensure_ascii=False),request_id))
            state['last_wake'] = now.isoformat()
        state.update(cursor=cursor,files=current['files'],complete=current['complete'],trial_id=run['current_trial_id'])
        conn.execute('INSERT OR REPLACE INTO system_state VALUES(?,?)',(key,json.dumps(state,ensure_ascii=False)))
    if request_id:
        controller._wake(run_id)
    return request_id
