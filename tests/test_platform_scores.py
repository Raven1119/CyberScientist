"""Public score aggregation is complete-or-unknown and brain-only."""
from __future__ import annotations

import pytest

from cyberscientist import collab, db, mcp_bridge, platform_scores
from cyberscientist.controller import RunController


def _run() -> str:
    db.execute("INSERT INTO challenges(id,platform_challenge_id,origin,title,content,"
               "content_hash,contract_status,imported_at,is_demo)"
               " VALUES('SCORE_CH','score-slug','demo://score','Score','test','h',"
               "'unknown',?,1)",(db.utcnow(),))
    rid=RunController().create_run('SCORE_CH',shadow_enabled=False)['id']
    db.execute("INSERT INTO mailboxes(id,role,email,platform,status,created_at)"
               " VALUES('score_mb','experiment','fixture@example.com','demo','active',?)",
               (db.utcnow(),))
    db.execute("INSERT INTO submissions(id,run_id,mailbox_id,package_path,package_sha256,"
               "status,score,score_status,score_confidence,created_at)"
               " VALUES('our_score',?,'score_mb','fixture','hash','submitted',85,"
               "'scored','confirmed',?)",(rid,db.utcnow()))
    platform_scores._cache.clear()
    return rid


def _attempt(ident, author, display, harbor, trace):
    return {'id':ident,'authorId':author,'author_name':'must never leave aggregator',
            'answerRedacted':'private attempt content',
            'scoringState':{'displayScore':display},
            'scorecard':{'harbor_score':harbor,'trace_score':trace}}


def test_paginates_aggregates_and_caches_without_identity(monkeypatch):
    rid=_run()
    calls=[]
    pages={1:{'attempts':[_attempt(1,10,100,100,70),
                          _attempt(2,20,90,80,50)],'total':3},
           2:{'attempts':[_attempt(3,10,0,60,0)],'total':3}}
    def fetch(slug,page):
        calls.append((slug,page))
        return pages[page]
    monkeypatch.setattr(platform_scores,'_fetch_page',fetch)
    got=platform_scores.get(rid)
    assert got['status']=='ok' and got['submission_count']==3
    assert got['author_count']==2 and got['scored_count']==3
    assert got['display_score_bins']=={'100':1,'90-99.9':1,'70-89.9':0,
        '50-69.9':0,'1-49.9':0,'0':1}
    assert got['harbor_score_quantiles']['p50']==80
    assert got['trace_score_quantiles']['p75']==60
    assert got['top_10_scores']==[100,90,0] and got['our_best_score']==85
    assert 'author_name' not in str(got) and 'private attempt content' not in str(got)
    db.execute("UPDATE submissions SET score=95 WHERE id='our_score'")
    assert platform_scores.get(rid)['our_best_score']==95
    assert calls==[('score-slug',1),('score-slug',2)]


def test_incomplete_page_or_failure_is_unknown(monkeypatch):
    rid=_run()
    monkeypatch.setattr(platform_scores,'_fetch_page',lambda slug,page:
        {'attempts':[_attempt(1,10,100,100,100)],'total':2} if page==1 else
        {'attempts':[_attempt(1,10,100,100,100)],'total':2})
    got=platform_scores.get(rid)
    assert got['status']=='unknown' and 'reason' in got
    assert 'display_score_bins' not in got
    platform_scores._cache.clear()
    def fail(*args): raise OSError('network unavailable')
    monkeypatch.setattr(platform_scores,'_fetch_page',fail)
    assert platform_scores.get(rid)['status']=='unknown'


@pytest.mark.asyncio
async def test_executor_cannot_call_platform_scores(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app
    rid=_run()
    with db.transaction() as conn:
        executor=collab.issue_token(conn,rid,'executor','sess',1)
        brain=collab.issue_token(conn,rid,'brain','brain',1)
    monkeypatch.setenv('CS_TOOL_ROLE','executor')
    listed=mcp_bridge._handle({'jsonrpc':'2.0','id':1,'method':'tools/list'})
    assert 'platform_scores' not in [t['name'] for t in listed['result']['tools']]
    monkeypatch.setenv('CS_TOOL_ROLE','brain')
    listed=mcp_bridge._handle({'jsonrpc':'2.0','id':2,'method':'tools/list'})
    assert 'platform_scores' in [t['name'] for t in listed['result']['tools']]
    app=create_app()
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://t') as client:
        denied=await client.post('/api/v1/tools/platform_scores',json={},
            headers={'Authorization':f'Bearer {executor}'})
        assert denied.status_code==403
        monkeypatch.setattr(platform_scores,'_fetch_page',lambda slug,page:
            {'attempts':[],'total':0})
        allowed=await client.post('/api/v1/tools/platform_scores',json={},
            headers={'Authorization':f'Bearer {brain}'})
        assert allowed.status_code==200 and allowed.json()['status']=='ok'


def test_unknown_tool_result_does_not_close_mcp_bridge(monkeypatch):
    monkeypatch.setattr(mcp_bridge,'_post',lambda path,args:
        {'status':'unknown','reason':'network unavailable'} if path.endswith('platform_scores')
        else {'status':'ok','items':[]})
    failed=mcp_bridge._handle({'jsonrpc':'2.0','id':1,'method':'tools/call',
        'params':{'name':'platform_scores','arguments':{}}})
    assert failed['result']['isError'] is True
    next_call=mcp_bridge._handle({'jsonrpc':'2.0','id':2,'method':'tools/call',
        'params':{'name':'research_trace','arguments':{'action':'list'}}})
    assert next_call['result']['isError'] is False
