"""Collect all S4 topics/lists/scored details; resume from redacted GET receipts."""
from __future__ import annotations

import argparse
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

from .common import DEFAULT_DATA, MAIN, PublicClient, atomic, sha, utcnow, write_json, zstd
from .tables import attempt_row, number, write_csv


class IncompleteTopic(ValueError):
    def __init__(self, message, topic, attempts, pages):
        super().__init__(message)
        self.topic, self.attempts, self.pages = topic, attempts, pages


def observed(client, path):
    meta = client.cache / (sha(('https://play.bohrium.com' + path).encode()) + '.meta.json')
    return json.loads(meta.read_text())['fetched_at']


def ownership(client):
    mapping, evidence = {}, []
    source = MAIN / '.package-checks/trace-all-20260928/owned_lists_summary.json'
    if source.exists():
        for entry in json.loads(source.read_text()):
            if entry.get('source') in ('operator_confirmed', 'db_mailbox'):
                ident = str(entry['author_id']); mapping[ident] = 'cached_operator_confirmed_20260928'
                evidence.append({'author_id':ident,'label':'ours','source':'cached_operator_confirmed',
                                 'source_sha256':sha(source.read_bytes())})
    snapshot = MAIN / '.package-checks/cs-up-12/preflight-warmup-final/current.sqlite'
    if snapshot.exists():
        with sqlite3.connect('file:' + str(snapshot) + '?mode=ro&immutable=1', uri=True) as conn:
            refs = [r[0] for r in conn.execute("SELECT platform_ref FROM submissions WHERE platform_ref IS NOT NULL AND platform_ref!=''")]
        for ref in refs:
            if not str(ref).isdigit(): continue
            aid = str(ref)
            try:
                body = client.get('/api/attempts/' + aid)
                ident = str(body['authorId']); mapping[ident] = 'configured_mailbox_owned_attempt_snapshot'
                evidence.append({'author_id':ident,'label':'ours','attempt_id':aid,
                                 'source':'existing_local_mailbox_submission_snapshot'})
            except Exception as exc:
                evidence.append({'attempt_id':aid,'source':'local_mailbox_snapshot',
                                 'status':'unresolved','error':str(exc)})
    write_json(client.root / 'data/ownership_sources.json', evidence)
    return mapping


def collect_topic(client, slug, seq):
    path = '/api/challenges/' + quote(slug, safe='')
    topic = client.get(path)
    if not isinstance(topic, dict) or topic.get('id') != slug:
        raise ValueError('Topic response identity mismatch')
    topic['_round_seq_from_season'] = seq
    topic['_observed_at'] = observed(client, path)
    write_json(client.root / 'data/topics' / (slug + '.json'), topic)
    attempts, seen, totals = [], set(), []
    for page in range(1, 10001):
        route = path + f'/attempts?page={page}&limit=100&sort=newest'
        body = client.get(route)
        if not isinstance(body, dict) or not isinstance(body.get('attempts'), list):
            raise ValueError('Unexpected attempt list schema')
        totals.append({'page':page,'total':body.get('total'),'total_non_draft':body.get('totalNonDraft'),
                       'observed_at':observed(client, route),'returned':len(body['attempts'])})
        new = 0
        for row in body['attempts']:
            if str(row.get('challengeId')) != slug: raise ValueError('Attempt belongs to another topic')
            aid = str(row['id'])
            if aid not in seen:
                seen.add(aid); new += 1
                row['_observed_at'] = observed(client, route)
                if str(row.get('status','')).lower() != 'draft': attempts.append(row)
        total = body.get('total')
        if not body['attempts']:
            if not isinstance(total,int) or len(seen) != total:
                raise IncompleteTopic('Pagination ended before declared total',topic,attempts,totals)
            break
        if isinstance(total,int) and len(seen) >= total: break
        if not new: raise IncompleteTopic('Pagination repeated without progress',topic,attempts,totals)
    else: raise ValueError('Pagination safety bound exceeded')
    declared = {p['total'] for p in totals}
    non_draft = {p['total_non_draft'] for p in totals if p['total_non_draft'] is not None}
    if declared != {len(seen)} or non_draft and non_draft != {len(attempts)}:
        raise IncompleteTopic('Pagination totals changed or do not match unique coverage',topic,attempts,totals)
    write_json(client.root / '.raw/topic-lists' / (slug + '.json'), {'attempts':attempts,'pages':totals})
    return topic, attempts, totals


def has_score(attempt):
    card = attempt.get('scorecard'); results = attempt.get('resultsJson')
    state = attempt.get('scoringState')
    card = card if isinstance(card,dict) else {}
    results = results if isinstance(results,dict) else {}
    state = state if isinstance(state,dict) else {}
    return any(number(value) is not None for value in [attempt.get('score'),
        state.get('displayScore'),card.get('trace_score'),results.get('trace_score'),
        card.get('harbor_score'),results.get('harbor_score')])


def export(client, topics, attempts, owners, failures, coverage):
    root = client.root / 'data'
    rows, deductions, missing = [], [], []
    topic_rows = []
    for topic in topics.values():
        row = {key: value for key,value in topic.items()
               if key not in ('content','topicContent','abstract','attempts','figures','figureData','datasets','submittedBy')}
        row = flatten_topic(row)
        row.update(challenge_id=topic['id'], topic_type=topic.get('disc'),
                   statement_path='data/topics/' + topic['id'] + '.json',
                   statement_chars=len(topic.get('content') or ''),
                   datasets_json=json.dumps(topic.get('datasets'),ensure_ascii=False),
                   figures_json=json.dumps(topic.get('figures'),ensure_ascii=False),
                   material_relevant=None, material_classification_source=None)
        topic_rows.append(row)
    write_csv(root / 'challenges.csv', topic_rows)
    ordered = sorted(attempts.values(), key=lambda row:int(row['id']))
    # Shard full sanitized details; CSV omits large narratives but links here.
    for start in range(0, len(ordered), 250):
        part = 'data/attempt_details/part-' + str(start//250).zfill(5) + '.jsonl.zst'
        chunk = ordered[start:start+250]
        for item in chunk: item['_snapshot_path'] = part
        raw = ''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in chunk).encode()
        compressed = zstd(raw)
        if len(compressed) >= 90_000_000: raise ValueError('Detail shard exceeds repository limit')
        atomic(client.root / part, compressed)
    for item in ordered:
        topic = topics.get(str(item.get('challengeId')))
        if not topic: continue
        row = attempt_row(item, topic, owners); rows.append(row)
        results = item.get('resultsJson') or {}
        if not isinstance(results,dict): continue
        for index, reason in enumerate(results.get('trace_low_score_reasons') or []):
            reason = reason if isinstance(reason,dict) else {'description':str(reason)}
            deductions.append({'attempt_id':row['attempt_id'],'challenge_id':row['challenge_id'],
                'ours':row['ours'],'reason_index':index, **{'raw.'+k:v for k,v in reason.items()}})
        for index, reason in enumerate(results.get('trace_missing_evidence') or []):
            missing.append({'attempt_id':row['attempt_id'],'challenge_id':row['challenge_id'],
                'ours':row['ours'],'evidence_index':index,'text':reason if isinstance(reason,str) else json.dumps(reason,ensure_ascii=False),
                'category':None,'classification_status':'pending_W2'})
    write_csv(root / 'attempts.csv', rows)
    write_csv(root / 'deductions.csv', deductions, fields=None if deductions else ['attempt_id','challenge_id','ours','reason_index'])
    write_csv(root / 'missing_evidence.csv', missing, fields=['attempt_id','challenge_id','ours','evidence_index','text','category','classification_status'])
    write_csv(root / 'collection_failures.csv', failures, fields=['kind','id','error'])
    coverage.update(topics_collected=len(topics), attempts_non_draft=len(rows),
        scored_details_collected=sum(a.get('_detail_status')=='ok' for a in attempts.values()),
        deduction_rows=len(deductions), missing_evidence_rows=len(missing),
        ours_attempts=sum(row['ours'] for row in rows), failed_items=len(failures), exported_at=utcnow())
    write_json(root / 'coverage.json', coverage)


def flatten_topic(row):
    from .tables import flatten
    return flatten(row)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,default=DEFAULT_DATA)
    parser.add_argument('--workers',type=int,default=8);args=parser.parse_args()
    client=PublicClient(args.data_root); owners=ownership(client)
    seasons=client.get('/api/hackathon/seasons')
    season=next(s for s in seasons if s.get('slug')=='s4')
    rounds=client.get('/api/hackathon/seasons/by-slug/s4/rounds')
    write_json(client.root / 'data/snapshots/season.json',season)
    write_json(client.root / 'data/snapshots/rounds.json',rounds)
    write_json(client.root / 'data/snapshots/protocol.json',client.get('/api/protocol'))
    slugs={slug:row['seq'] for row in rounds['rounds'] for slug in row['challengeIds']}
    if len(slugs)!=60 or len(rounds['rounds'])!=6: raise ValueError('Unexpected S4 topic/round coverage')
    topics, attempts, failures, page_audit = {}, {}, [], {}
    coverage={'collection_started_at':utcnow(),'expected_topics':60,'phase':'topic_lists'}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(collect_topic,client,slug,seq):slug for slug,seq in slugs.items()}
        for future in as_completed(futures):
            slug=futures[future]
            try:
                topic, items, pages=future.result();topics[slug]=topic;page_audit[slug]=pages
                for a in items: attempts[str(a['id'])]=a
            except Exception as exc:
                failures.append({'kind':'topic_list','id':slug,'error':str(exc)})
                if isinstance(exc,IncompleteTopic):
                    topics[slug]=exc.topic;page_audit[slug]=exc.pages
                    for a in exc.attempts:attempts[str(a['id'])]=a
            write_json(client.root / '.raw/current.json',{'phase':'topic_lists','topics':len(topics),'attempts':len(attempts),'failures':len(failures),'time':utcnow()})
            print(json.dumps({'phase':'topic_lists','topics':len(topics),'attempts':len(attempts),'failures':len(failures)}),flush=True)
    write_json(client.root / 'data/snapshots/pagination_audit.json', page_audit)
    coverage['phase']='details'; export(client,topics,attempts,owners,failures,coverage)
    scored=[a for a in attempts.values() if has_score(a)];coverage['scored_details_expected']=len(scored)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(client.get,'/api/attempts/'+str(a['id'])):str(a['id']) for a in scored}
        done=0
        for future in as_completed(futures):
            aid=futures[future];done+=1
            try:
                item=future.result()
                if str(item.get('id'))!=aid: raise ValueError('Detail identity mismatch')
                item['_observed_at']=observed(client,'/api/attempts/'+aid);item['_detail_status']='ok';attempts[aid]=item
            except Exception as exc:
                attempts[aid]['_detail_status']='failed';failures.append({'kind':'attempt_detail','id':aid,'error':str(exc)})
            if done%100==0 or done==len(scored):
                write_json(client.root / '.raw/current.json',{'phase':'details','completed':done,'expected':len(scored),'failures':len(failures),'time':utcnow()})
                print(json.dumps({'phase':'details','completed':done,'expected':len(scored),'failures':len(failures)}),flush=True)
    coverage['phase']='metadata_complete' if not failures else 'metadata_with_failures'
    coverage['collection_finished_at']=utcnow();export(client,topics,attempts,owners,failures,coverage)


if __name__=='__main__': main()
