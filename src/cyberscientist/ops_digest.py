"""Small ledger projections for low-frequency operator monitoring."""
from __future__ import annotations
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from . import auto_harvest, backend_identity, config, db, observation, track_clock


def tracks():
    result=[]
    for row in db.query("SELECT id,label,status,updated_at,json_extract(config_json,'$.track_clock') AS clock,"
                        "json_extract(config_json,'$.submission_transport') AS transport,"
                        "COALESCE(json_extract(config_json,'$.public_round.roundEndAt'),json_extract(config_json,'$.entries[0].challenge_snapshot.platform.roundEndAt')) AS platform_end,"
                        "json_extract(config_json,'$.template.authorization.unlimited_resources') AS unlimited"
                        " FROM eval_runs WHERE suite='competition' ORDER BY created_at"):
        clock=json.loads(row['clock'] or '{}')
        clock['end']=clock.get('end') or row['platform_end']
        transport=json.loads(row['transport'] or '{}')
        prompt=db.query_one('SELECT version,sha256 FROM competition_prompt_versions WHERE eval_id=? ORDER BY version DESC LIMIT 1',(row['id'],))
        topics=[dict(item) | {'harvest_scores':auto_harvest.topic_facts(row['id'],item['challenge_id'])}
                for item in db.query('SELECT id,challenge_id,launch_state,status,run_id,updated_at FROM eval_results WHERE eval_id=? ORDER BY priority DESC,repeat_index',(row['id'],))]
        result.append({k:row[k] for k in ('id','label','status','updated_at')} | {
            'clock':track_clock.facts({'track_clock':clock}), 'harvest_window':auto_harvest.window(clock),
            'prompt_version':prompt['version'] if prompt else 0,'prompt_sha256':prompt['sha256'] if prompt else None,
            'unlimited_resources':row['unlimited']==1,
            'transport_verified':transport.get('verified') is True,
            'transport_status':transport.get('status','unknown'),'topics':topics})
    return result


def rates():
    native=db.query_one("SELECT payload_json,observed_at FROM runtime_observations WHERE kind='codex_rate_limits'")
    return {'codex':{'status':'observed' if native else 'unknown','observed_at':native['observed_at'] if native else None,
                     'windows':json.loads(native['payload_json']) if native else {}},
            'provider_backoff':[dict(r) for r in db.query('SELECT provider,first_at,retry_at FROM model_provider_backoff')],
            'native_throttle':[dict(r) for r in db.query("SELECT json_extract(payload_json,'$.provider') AS provider,"
                "json_extract(payload_json,'$.model_id') AS model,json_extract(payload_json,'$.status') AS status,"
                "json_extract(payload_json,'$.first_at') AS first_at,observed_at FROM runtime_observations WHERE kind LIKE 'native_throttle:%'")]}


def sessions(run_id):
    rows=db.query("SELECT payload,recorded_at FROM events WHERE run_id=? AND type='session.configuration' ORDER BY seq",(run_id,))
    latest={}
    for row in rows:
        value=json.loads(row['payload']);key=(value['role'],value['session_id'])
        latest[key]=value | {'observed_at':row['recorded_at']}
    return list(latest.values())


def record_session(run_id,role,session_id,raw):
    value={key:raw.get(key) for key in ('model','provider','reasoning_effort','fast_mode')}
    try:
        db.append_event(run_id,'controller','session.configuration',value | {'role':role,'session_id':session_id})
    except Exception as exc:
        # Monitoring is advisory. It must never orphan an accepted native thread.
        logging.getLogger(__name__).warning('Session observation unavailable (%s)',type(exc).__name__)
        return False
    return True


def digest(since=None):
    cutoff=track_clock.instant(since) if since else None
    if since and cutoff is None: raise ValueError('since须为ISO时间（包含日期和时间）')
    if since and ('T' not in since and ' ' not in since): raise ValueError('since须包含时间')
    stamp=cutoff.isoformat() if cutoff else None
    now=datetime.now(timezone.utc)
    loaded=backend_identity.loaded();checkout=backend_identity.capture()
    barrier=db.query_one("SELECT value FROM system_state WHERE key='shutdown_requested'")
    closing=db.query_one("SELECT COUNT(*) FROM system_state WHERE key LIKE 'native_close_unknown:%'")[0]
    lines=[f"OPS {now.isoformat()} since={stamp or 'all'}",
           f"code loaded={loaded.get('commit')} checkout={checkout.get('commit')} matches={loaded==checkout}",
           f"barrier shutdown={bool(barrier and barrier[0]=='1')} native_close_unknown={closing}"]
    alerts=db.query_one('SELECT COUNT(*) FROM alerts WHERE acknowledged_at IS NULL'+(" AND julianday(created_at)>=julianday(?)" if stamp else ''),(stamp,) if stamp else ())[0]
    lines.append(f'pending alerts={alerts}')
    track_map={t['id']:t for t in tracks()}
    rows=db.query("SELECT r.id,r.challenge_id,r.phase,r.created_at,json_extract(r.config_snapshot,'$.competition.round_id') AS track,"
                  "(SELECT MAX(recorded_at) FROM events e WHERE e.run_id=r.id) AS last_event,"
                  "(SELECT MAX(science_score) FROM local_scores l WHERE l.run_id=r.id AND l.score_source IN ('system','executor_verified')) AS local_best,"
                  "(SELECT MAX(COALESCE(score_last_changed_at,scored_at,created_at)) FROM submissions s WHERE s.run_id=r.id) AS last_score"
                  " FROM runs r ORDER BY CASE WHEN r.phase IN ('finished','cancelled','failed') THEN 1 ELSE 0 END,"
                  "COALESCE((SELECT MAX(recorded_at) FROM events e WHERE e.run_id=r.id),r.created_at) DESC,track,r.challenge_id")
    omitted=0;shown_tracks=set()
    for row in rows:
        changed=max((track_clock.instant(row[key]) for key in ('created_at','last_event','last_score') if track_clock.instant(row[key])),default=None)
        track=track_map.get(row['track'])
        if cutoff and (changed is None or changed<cutoff) and (not track or not track_clock.instant(track['updated_at']) or track_clock.instant(track['updated_at'])<cutoff):continue
        if len(lines)>=42:omitted+=1;continue
        tid=row['track'] or 'standalone'
        if tid not in shown_tracks:
            shown_tracks.add(tid)
            if track:
                w=track['harvest_window'];lines.append(f"track {tid} {track['label']} prompt=v{track['prompt_version']} unlimited={track['unlimited_resources']} end_s={w['remaining_seconds']} window={w['state']} window_in_s={w['until_window_seconds']}")
            else:lines.append('track standalone clock=unknown')
        quiet=(now-track_clock.instant(row['last_event'] or row['created_at'])).total_seconds()
        scores=auto_harvest.topic_facts(row['track'],row['challenge_id'])
        lines.append(f"  {row['challenge_id']} {row['id']} {row['phase']} quiet_s={max(0,int(quiet))} local={row['local_best']} main={scores['main_best']} exp={scores['experiment_best']} score_pending={len(scores['pending_submission_ids'])}")
    # Deferred/skipped tracks still have clock/prompt information without a Run.
    for tid,track in track_map.items():
        track_changed=not cutoff or (track_clock.instant(track['updated_at']) or now)>=cutoff
        topics=[item for item in track['topics'] if not item['run_id'] and
                (track_changed or (track_clock.instant(item['updated_at']) or now)>=cutoff)]
        if tid not in shown_tracks and (track_changed or topics):
            if len(lines)>=43:omitted+=1+len(topics);continue
            w=track['harvest_window'];lines.append(f"track {tid} {track['label']} no_changed_runs prompt=v{track['prompt_version']} end_s={w['remaining_seconds']} window={w['state']}")
        for item in topics:
            if len(lines)>=43:omitted+=1;continue
            scores=item['harvest_scores']
            lines.append(f"  {item['challenge_id']} {item['launch_state']} no_run local=None main={scores['main_best']} exp={scores['experiment_best']} score_pending={len(scores['pending_submission_ids'])}")
    if omitted:lines.append(f'additional run/track rows={omitted}; use targeted ops events/status for detail')
    errors=db.query("SELECT type,json_extract(payload,'$.error') AS error,json_extract(payload,'$.message') AS message FROM events WHERE (type LIKE '%.error' OR type LIKE '%.failed' OR type IN ('run.runtime_error','submission.unknown'))"+(" AND julianday(recorded_at)>=julianday(?)" if stamp else '')+' ORDER BY rowid DESC LIMIT 1000',(stamp,) if stamp else ())
    counts=Counter((e['type'],observation.strip_secrets(str(e['error'] or e['message'] or ''))[:120]) for e in errors)
    for (kind,message),count in counts.most_common(4):lines.append(f'error x{count} {kind} {message}')
    for table,column,states in [('compute_jobs','operation_id',"'unknown','stop_unknown'"),('compute_sandboxes','operation_id',"'unknown'"),('submissions','id',"'unknown'")]:
        field='updated_at' if table!='submissions' else "COALESCE((SELECT MAX(e.recorded_at) FROM events e WHERE json_extract(e.payload,'$.submission_id')=submissions.id AND e.type LIKE 'submission.%'),created_at)"
        items=db.query(f'SELECT {column} AS id,run_id FROM {table} WHERE status IN ({states})'+(f' AND julianday({field})>=julianday(?)' if stamp else ''),(stamp,) if stamp else ())
        lines.append(f"unknown {table} count={len(items)} ids="+','.join(i['id'] for i in items[:6]))
    rate=rates()
    lines.append('rates codex='+observation.strip_secrets(json.dumps(rate['codex'],ensure_ascii=False,separators=(',',':')))[:700])
    lines.append('provider_backoff='+observation.strip_secrets(json.dumps(rate['provider_backoff'],ensure_ascii=False,separators=(',',':')))[:500])
    lines.append('native_throttle='+observation.strip_secrets(json.dumps(rate['native_throttle'],ensure_ascii=False,separators=(',',':')))[:700])
    # Each logical record is one line, including untrusted remote error messages.
    result='\n'.join(observation.strip_secrets(line).replace('\r',' ').replace('\n',' ') for line in lines)
    return {'observed_at':now.isoformat(),'since':stamp,'line_count':len(lines),'text':result}
