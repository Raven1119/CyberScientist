"""Brain-only, public-score distribution for the current challenge.

Only aggregate numbers leave this module. The public list response and author
identifiers are never persisted or returned to the model.
"""
from __future__ import annotations

import math
import threading
import time
import urllib.parse

from . import config, db
from .mailbox_platform import BohriumPlaygroundPlatform

_TTL_SECONDS = 600
_PAGE_LIMIT = 100
_MAX_PAGES = 200
_FETCH_BUDGET_SECONDS = 15
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _number(value) -> float | None:
    if isinstance(value,bool): return None
    try: number=float(value)
    except (ValueError,TypeError): return None
    return number if math.isfinite(number) else None


def _quantiles(values: list[float]) -> dict[str,float] | None:
    if not values: return None
    ordered=sorted(values)
    def at(p):
        pos=(len(ordered)-1)*p
        lower=math.floor(pos)
        upper=math.ceil(pos)
        return ordered[lower]+(ordered[upper]-ordered[lower])*(pos-lower)
    return {key:at(p) for key,p in [('p0',0),('p25',.25),('p50',.5),
                                   ('p75',.75),('p100',1)]}


def _fetch_page(slug: str, page: int) -> dict:
    pg=config.load_settings().get('playground') or {}
    client=BohriumPlaygroundPlatform(
        base_url=pg.get('base_url') or 'https://play.bohrium.com/api',
        operator_token=None,timeout=5)
    path=(f"/challenges/{urllib.parse.quote(slug,safe='')}/attempts?"
          f"page={page}&limit={_PAGE_LIMIT}&sort=newest")
    return client._http('GET',path,token=None)


def _collect(slug: str) -> dict:
    deadline=time.monotonic()+_FETCH_BUDGET_SECONDS
    attempts=[]
    seen=set()
    total=None
    for page in range(1,_MAX_PAGES+1):
        if time.monotonic()>=deadline:
            raise TimeoutError('公开尝试列表分页超过读取时限')
        body=_fetch_page(slug,page)
        if time.monotonic()>=deadline:
            raise TimeoutError('公开尝试列表分页超过读取时限')
        if not isinstance(body,dict) or not isinstance(body.get('attempts'),list) \
                or isinstance(body.get('total'),bool) or not isinstance(body.get('total'),int):
            raise ValueError('公开尝试列表缺少 attempts/total')
        if body['total']<0: raise ValueError('公开尝试列表 total 无效')
        if total is None: total=body['total']
        elif total!=body['total']:
            raise ValueError('分页期间提交总数变化；本次分布未判定')
        added=0
        for item in body['attempts']:
            if not isinstance(item,dict) or item.get('id') is None:
                raise ValueError('公开尝试条目缺少 id')
            ident=str(item['id'])
            if ident in seen: continue
            seen.add(ident)
            attempts.append(item)
            added+=1
        if len(attempts)>=total: break
        if added==0: raise ValueError('分页没有新增条目；本次分布未判定')
    else:
        raise ValueError('分页超过安全上限；本次分布未判定')
    if len(attempts)!=total:
        raise ValueError('分页条目数与 total 不一致；本次分布未判定')
    return _aggregate(attempts,total)


def _aggregate(attempts: list[dict], total: int) -> dict:
    bins={'100':0,'90-99.9':0,'70-89.9':0,'50-69.9':0,
          '1-49.9':0,'0':0}
    scores=[]
    harbor=[]
    trace=[]
    authors=set()
    author_complete=True
    unbinned=0
    for attempt in attempts:
        author=attempt.get('authorId')
        if author is None: author_complete=False
        else: authors.add(str(author))
        score=_number((attempt.get('scoringState') or {}).get('displayScore')) \
            if isinstance(attempt.get('scoringState'),dict) else None
        if score is not None:
            scores.append(score)
            if score>=100: bins['100']+=1
            elif score>=90: bins['90-99.9']+=1
            elif score>=70: bins['70-89.9']+=1
            elif score>=50: bins['50-69.9']+=1
            elif score>=1: bins['1-49.9']+=1
            elif score==0: bins['0']+=1
            else: unbinned+=1
        card=attempt.get('scorecard')
        if isinstance(card,dict):
            h=_number(card.get('harbor_score'))
            t=_number(card.get('trace_score'))
            if h is not None: harbor.append(h)
            if t is not None: trace.append(t)
    return {'status':'ok','submission_count':total,
            'author_count':len(authors) if author_complete else None,
            'scored_count':len(scores),'display_score_bins':bins,
            'unbinned_score_count':unbinned,
            'harbor_score_quantiles':_quantiles(harbor),
            'trace_score_quantiles':_quantiles(trace),
            'top_10_scores':sorted(scores,reverse=True)[:10]}


def get(run_id: str, *, fresh: bool = False) -> dict:
    run=db.query_one('SELECT challenge_id,config_snapshot FROM runs WHERE id=?',(run_id,))
    if not run: return {'status':'unknown','reason':'Run 不存在'}
    own=db.query_one("SELECT MAX(s.score) AS best FROM submissions s JOIN runs r ON r.id=s.run_id"
                     " WHERE r.challenge_id=? AND s.score_status='scored'"
                     " AND s.score_confidence='confirmed'",(run['challenge_id'],))
    best=own['best'] if own else None
    challenge=db.query_one('SELECT platform_challenge_id FROM challenges WHERE id=?',
                           (run['challenge_id'],))
    import json
    slug=json.loads(run['config_snapshot']).get('challenge_platform_id', challenge['platform_challenge_id'] if challenge else None)
    if not slug or str(slug).startswith(('demo://','local:')):
        return {'status':'unknown','reason':'题目没有真实平台 slug','our_best_score':best}
    with _lock:
        cached=_cache.get(str(slug))
        now=time.monotonic()
        if not fresh and cached and now-cached[0]<_TTL_SECONDS:
            result=dict(cached[1])
        else:
            try:
                result=_collect(str(slug))
            except Exception as exc:
                from .observation import strip_secrets
                return {'status':'unknown','reason':f'公开尝试列表读取失败：{type(exc).__name__}: {strip_secrets(str(exc))[:180]}',
                        'our_best_score':best}
            _cache[str(slug)]=(now,dict(result))
    result['our_best_score']=best
    return result
