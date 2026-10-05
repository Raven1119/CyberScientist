"""Live public aggregates and own confirmed scores for the competition panel."""
import asyncio
import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone
from . import config, db, observation, platform_contracts, platform_scores, power, resource_coordinator

TTL_SECONDS = 30
ACTIVE = {}


def fetch(slug, base_url):
    from .mailbox_platform import BohriumPlaygroundPlatform
    client = BohriumPlaygroundPlatform(base_url=base_url, operator_token=None, timeout=5)
    def page(slug, number):
        path = '/challenges/' + urllib.parse.quote(slug, safe='') + '/attempts?page=' + str(number) + '&limit=100&sort=newest'
        return client._http('GET', path, token=None)
    return platform_scores._collect(slug, fetch_page=page)


def _key(slug, origin):
    return 'leaderboard:' + hashlib.sha256((origin + '|' + slug).encode()).hexdigest()


def cached(slug):
    if not slug: return {'status': 'unknown', 'reason': '没有真实平台题目ID'}
    try: origin = platform_contracts._origin(config.load_settings()['playground']['base_url'])
    except ValueError: return {'status': 'unknown', 'reason': '平台地址无效'}
    row = db.query_one('SELECT payload_json FROM runtime_observations WHERE kind=?', (_key(slug, origin),))
    if not row: return {'status': 'unknown', 'reason': '尚未读取公开榜单'}
    result = json.loads(row['payload_json'])
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(result['observed_at'])).total_seconds()
    if age >= TTL_SECONDS:
        return {'status': 'unknown', 'reason': '公开榜单快照已过期，等待刷新', 'last_observation': result}
    return result


def own_best(challenge_id):
    challenge = db.query_one('SELECT platform_challenge_id FROM challenges WHERE id=?', (challenge_id,))
    slug = challenge['platform_challenge_id'] if challenge else None
    condition, value = ('c.platform_challenge_id=?', slug) if slug else ('c.id=?', challenge_id)
    try: origin = platform_contracts._origin(config.load_settings()['playground']['base_url'])
    except ValueError: return None
    rows = db.query('SELECT s.score,r.mode,r.config_snapshot FROM submissions s JOIN runs r ON r.id=s.run_id'
                    ' JOIN challenges c ON c.id=r.challenge_id WHERE ' + condition + " AND s.status='submitted' AND s.score_status='scored'"
                    " AND s.score_confidence='confirmed' AND (s.score_anomaly IS NULL OR s.score_anomaly='')", (value,))
    scores = []
    for row in rows:
        if row['mode'] != 'connected': continue
        snap = json.loads(row['config_snapshot'])
        try: source = platform_contracts._origin(snap['settings']['playground']['base_url'])
        except (KeyError, ValueError): continue
        if source == origin and snap.get('challenge_platform_id') == slug:
            score = platform_scores._number(row['score'])
            if score is not None: scores.append(score)
    return max(scores) if scores else None


def facts(challenge_id):
    row = db.query_one('SELECT platform_challenge_id,is_demo FROM challenges WHERE id=?', (challenge_id,))
    public = cached(row['platform_challenge_id']) if row and not row['is_demo'] else {'status':'unknown', 'reason':'Demo或本地题目没有真实榜单'}
    best = own_best(challenge_id)
    highest = public.get('leaderboard_best_score') if public.get('status') == 'ok' else None
    return {'leaderboard_best': highest, 'our_best': best, 'score_gap': highest - best if highest is not None and best is not None else None, 'leaderboard_observation': public}


async def _refresh(round_id):
    owner = 'leaderboard-' + round_id
    resource_coordinator.register_auxiliary(owner, asyncio.current_task())
    try:
        base_url = config.load_settings()['playground']['base_url']
        origin = platform_contracts._origin(base_url)
        rows = db.query('SELECT DISTINCT c.platform_challenge_id FROM eval_results e JOIN challenges c ON c.id=e.challenge_id'
                        ' WHERE e.eval_id=? AND c.is_demo=0 AND c.platform_challenge_id IS NOT NULL', (round_id,))
        for row in rows:
            slug = row['platform_challenge_id']
            if power.shutdown_requested(): break
            if cached(slug).get('status') == 'ok': continue
            key = _key(slug, origin)
            old = db.query_one('SELECT payload_json,observed_at FROM runtime_observations WHERE kind=?', (key,))
            # Unknown attempts back off as well; a 5s UI poll is not a new request.
            if old and (datetime.now(timezone.utc) - datetime.fromisoformat(old['observed_at'])).total_seconds() < TTL_SECONDS: continue
            cancelled = False
            result = None
            for attempt in range(3):
                if power.shutdown_requested(): break
                task = asyncio.create_task(asyncio.to_thread(fetch, slug, base_url))
                while not task.done():
                    try: await asyncio.shield(task)
                    except asyncio.CancelledError: cancelled = True
                    except Exception: break
                try: result = task.result()
                except Exception as exc:
                    code = re.search(r'HTTP[ :]+([1-5][0-9]{2})', str(exc))
                    result = {'status':'unknown', 'reason': '公开榜单读取失败：' + type(exc).__name__ + (' HTTP ' + code.group(1) if code else '')}
                if result.get('status') == 'ok' or cancelled: break
                if attempt < 2: await asyncio.sleep(2 ** attempt)
            if result is None: break
            if platform_contracts._origin(config.load_settings()['playground']['base_url']) != origin:
                result = {'status':'unknown', 'reason':'读取期间平台配置改变，未确认当前榜单'}
            result.update(observed_at=db.utcnow(), platform_origin=origin)
            if result['status'] != 'ok' and old:
                previous = json.loads(old['payload_json'])
                verified = previous if previous.get('status') == 'ok' else previous.get('last_verified')
                if verified: result['last_verified'] = verified
            # Only aggregate output is stored, never public author IDs or traces.
            db.execute('INSERT OR REPLACE INTO runtime_observations VALUES(?,?,?)', (key, json.dumps(result, ensure_ascii=False), result['observed_at']))
            if cancelled: break
    finally:
        resource_coordinator.unregister_auxiliary(owner)


def start_round(round_id):
    if power.shutdown_requested() or round_id in ACTIVE and not ACTIVE[round_id].done(): return
    task = asyncio.create_task(_refresh(round_id)); ACTIVE[round_id] = task
    def finished(task):
        if ACTIVE.get(round_id) is task: ACTIVE.pop(round_id, None)
        if not task.cancelled(): task.exception()
    task.add_done_callback(finished)


async def drain():
    tasks = list(ACTIVE.values())
    for task in tasks: task.cancel()
    if tasks: await asyncio.gather(*tasks, return_exceptions=True)
