import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
import pytest
from cyberscientist import competition, config, db, leaderboards, platform_contracts, platform_scores, resource_coordinator
from cyberscientist.controller import RunController

PUBLIC_FETCH = leaderboards.fetch


def round_fixture():
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo) VALUES('lb','fixture','榜单题','x','h',?,1)", (db.utcnow(),))
    rnd = competition.import_round(['lb'], mode='demo')
    db.execute("UPDATE challenges SET is_demo=0,platform_challenge_id='lb-slug' WHERE id='lb'")
    return rnd['id']


def saved(result, age=0):
    origin = platform_contracts._origin(config.load_settings()['playground']['base_url'])
    when = (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()
    result = {**result, 'observed_at':when, 'platform_origin':origin}
    db.execute('INSERT OR REPLACE INTO runtime_observations VALUES(?,?,?)', (leaderboards._key('lb-slug',origin),json.dumps(result),when))


def own(score, *, confidence='confirmed', anomaly=None):
    rid = RunController().create_run('lb', 'connected')['id']
    if not db.query_one("SELECT id FROM mailboxes WHERE id='lb-mb'"):
        db.execute("INSERT INTO mailboxes(id,role,email,platform,status,created_at) VALUES('lb-mb','experiment','fixture@example.test','demo','active',?)", (db.utcnow(),))
    db.execute("INSERT INTO submissions(id,run_id,mailbox_id,package_path,package_sha256,status,score,score_status,score_confidence,score_anomaly,created_at) VALUES(?,?,'lb-mb','fixture','h','submitted',?,'scored',?,?,?)", ('sub-'+rid,rid,score,confidence,anomaly,db.utcnow()))
    return rid


def test_confirmed_best_spans_runs_and_zero_is_known():
    rnd = round_fixture(); own(0); own(99,confidence='provisional'); own(100,anomaly='scoring error')
    saved({'status':'ok','leaderboard_best_score':80})
    item = competition.get_round(rnd)['items'][0]
    assert item['run_id'] is None
    assert item['our_best'] == 0 and item['leaderboard_best'] == 80 and item['score_gap'] == 80
    db.execute("UPDATE submissions SET score=70 WHERE score=0")
    assert leaderboards.facts('lb')['score_gap'] == 10
    saved({'status':'unknown','reason':'404'})
    assert leaderboards.facts('lb')['score_gap'] is None


def test_public_highest_uses_terminal_nonanomalous_scores_only():
    def attempt(score, final=True, **kwargs):
        return {'authorId':'other-account', 'answerRedacted':'other-trace', 'scoringState':{'displayScore':score, 'scoreIsFinal':final, **kwargs}}
    got = platform_scores._aggregate([attempt(100,False),attempt(90,workerStatus='failed'),attempt(80,provisionalScore=80),attempt(60),attempt(0)],5)
    assert got['leaderboard_best_score'] == 60
    assert 'other-account' not in str(got) and 'other-trace' not in str(got)
    assert platform_scores._aggregate([attempt(100,False)],1)['leaderboard_best_score'] is None


@pytest.mark.asyncio
async def test_refresh_ttl_failure_preserves_confirmed_history_and_platform_binding(monkeypatch):
    rnd = round_fixture(); calls=[]
    monkeypatch.setattr(leaderboards,'fetch',lambda slug, base_url: calls.append(slug) or {'status':'ok','leaderboard_best_score':95})
    await leaderboards._refresh(rnd); await leaderboards._refresh(rnd)
    assert calls == ['lb-slug'] and leaderboards.facts('lb')['leaderboard_best'] == 95
    saved(leaderboards.cached('lb-slug'),60)
    assert leaderboards.facts('lb')['leaderboard_best'] is None
    monkeypatch.setattr(leaderboards,'fetch',lambda slug, base_url: {'status':'unknown','reason':'HTTP 404'})
    # Keep backoff behavior, but make test sleeps immediate.
    original_sleep=asyncio.sleep
    async def fast_sleep(seconds): await original_sleep(0)
    monkeypatch.setattr(leaderboards.asyncio,'sleep',fast_sleep)
    await leaderboards._refresh(rnd)
    got=leaderboards.cached('lb-slug')
    assert got['status']=='unknown' and got['last_verified']['leaderboard_best_score']==95
    assert leaderboards.facts('lb')['score_gap'] is None
    settings=config.load_settings(); settings['playground']['base_url']='https://other.example/api'; config.save_settings(settings)
    assert leaderboards.cached('lb-slug')['status']=='unknown'
    assert not resource_coordinator.auxiliary_tasks()


@pytest.mark.asyncio
async def test_slow_http_does_not_block_round_and_cancel_tracks_actual_thread(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app
    rnd=round_fixture(); entered=threading.Event(); released=threading.Event()
    def slow(slug, base_url):
        entered.set(); released.wait(5)
        return {'status':'ok','leaderboard_best_score':50}
    monkeypatch.setattr(leaderboards,'fetch',slow)
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://t') as client:
        response=await asyncio.wait_for(client.get('/api/v1/rounds/'+rnd),1)
        assert response.status_code==200 and response.json()['items'][0]['leaderboard_best'] is None
        assert await asyncio.to_thread(entered.wait,1)
        task=leaderboards.ACTIVE[rnd]; task.cancel(); await asyncio.sleep(.01)
        assert not task.done() and task in resource_coordinator.auxiliary_tasks()
        released.set(); await asyncio.wait_for(task,1)
        assert leaderboards.facts('lb')['leaderboard_best']==50
        assert not resource_coordinator.auxiliary_tasks()


def test_same_slug_other_origin_and_demo_do_not_become_our_score():
    round_fixture(); original = config.load_settings(); own(30)
    changed = config.load_settings(); changed['playground']['base_url']='https://other.example/api'; config.save_settings(changed)
    own(90)
    config.save_settings(original)
    rid=own(100); db.execute("UPDATE runs SET mode='demo' WHERE id=?", (rid,))
    assert leaderboards.own_best('lb') == 30
    config.save_settings(changed)
    assert leaderboards.own_best('lb') == 90


@pytest.mark.asyncio
async def test_error_body_not_persisted_and_fetch_origin_frozen(monkeypatch):
    rnd=round_fixture(); original=config.load_settings()['playground']['base_url']; calls=[]
    from cyberscientist.mailbox_platform import PlatformError
    def fetch(slug, base_url):
        calls.append(base_url)
        raise PlatformError('HTTP 503: {"authorId":"private-id","answerRedacted":"private-trajectory"}')
    monkeypatch.setattr(leaderboards,'fetch',fetch)
    original_sleep=asyncio.sleep
    async def fast_sleep(seconds): await original_sleep(0)
    monkeypatch.setattr(leaderboards.asyncio,'sleep',fast_sleep)
    await leaderboards._refresh(rnd)
    stored=db.query_one("SELECT payload_json FROM runtime_observations WHERE kind LIKE 'leaderboard:%'")[0]
    assert 'HTTP 503' in stored and 'private-id' not in stored and 'private-trajectory' not in stored
    assert calls == [original]*3


def test_fetch_freezes_client_and_never_persists_attempt_details(monkeypatch):
    from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform
    calls=[]
    def http(client, method, path, token=None):
        calls.append(client.base_url)
        return {'total':1,'attempts':[{'id':'1','authorId':'private-id','answerRedacted':'private-trace','scoringState':{'displayScore':42,'scoreIsFinal':True}}]}
    monkeypatch.setattr(BohriumPlaygroundPlatform,'_http',http)
    got=PUBLIC_FETCH('lb-slug','https://fixed.example/api')
    assert got['leaderboard_best_score']==42 and calls==['https://fixed.example/api']
    assert 'private' not in json.dumps(got)


@pytest.mark.asyncio
@pytest.mark.parametrize("exceptional", [False, True])
async def test_backend_lifespan_waits_for_actual_leaderboard_http(monkeypatch, exceptional):
    from cyberscientist.api import create_app
    rnd=round_fixture(); entered=threading.Event(); released=threading.Event()
    def slow(slug, base_url):
        entered.set(); released.wait(5)
        return {'status':'ok','leaderboard_best_score':1}
    monkeypatch.setattr(leaderboards,'fetch',slow)
    app=create_app(); lifespan=app.router.lifespan_context(app)
    await lifespan.__aenter__(); leaderboards.start_round(rnd)
    assert await asyncio.to_thread(entered.wait,1)
    error=RuntimeError('fixture exit') if exceptional else None
    closing=asyncio.create_task(lifespan.__aexit__(type(error) if error else None,error,None)); await asyncio.sleep(.03)
    assert not closing.done() and resource_coordinator.auxiliary_tasks()
    released.set()
    if exceptional:
        assert await asyncio.wait_for(closing,2) is False  # caller retains original exception
    else: await asyncio.wait_for(closing,2)
    assert not resource_coordinator.auxiliary_tasks()
