"""Optional parallel transactional triage helpers, separate from research PIs."""
import asyncio
import json
import uuid
import jsonschema
from . import challenge_models, config, db, features, observation, platform_scores, power, resource_coordinator
from .brains.base import SessionRef

PARALLEL = 3
TIMEOUT = 900
ACTIVE = {}
HANDLES = {}
CLOSERS = {}


def contract(settings):
    return {'type':'object','additionalProperties':False,
            'required':['difficulty','estimated_minutes','estimated_cost_cny','recommended_model','recommended_solver_id','reason'],
            'properties':{'difficulty':{'enum':['easy','medium','hard','unknown']},
                          'estimated_minutes':{'type':['number','null'],'minimum':0},
                          'estimated_cost_cny':{'type':['number','null'],'minimum':0},
                          'recommended_model':{'type':'string'},'reason':{'type':'string'},
                          'recommended_solver_id':{'enum':[None,*[s['id'] for s in challenge_models.roster(settings)]]}}}


async def _close_work(owner):
    brain,session=HANDLES[owner]
    try: await brain.close(session or SessionRef('triage','open-unknown'))
    except BaseException as exc:
        resource_coordinator.close_failed(owner,exc);raise
    else:
        HANDLES.pop(owner,None);CLOSERS.pop(owner,None);resource_coordinator.release_sessions(owner)
        db.execute('DELETE FROM system_state WHERE key=?',('native_close_unknown:'+owner,))
    finally: resource_coordinator.unregister_auxiliary(owner)


def _closer(owner):
    task=CLOSERS.get(owner)
    if task is None or task.done():
        task=asyncio.create_task(_close_work(owner));CLOSERS[owner]=task
        resource_coordinator.register_auxiliary(owner,task)
        task.add_done_callback(lambda t:t.exception() if not t.cancelled() else None)
    return task


async def close(owner):
    task=_closer(owner);cancelled=False
    while not task.done():
        try: await asyncio.shield(task)
        except asyncio.CancelledError: cancelled=True
        except Exception: break
    task.result()
    if cancelled: raise asyncio.CancelledError


async def retry_closes(timeout=0):
    tasks=[_closer(owner) for owner in list(HANDLES) if owner in CLOSERS]
    if tasks and timeout>0: await asyncio.wait(tasks,timeout=timeout)


async def _scores(slug):
    task=asyncio.create_task(asyncio.to_thread(platform_scores._collect,slug));cancelled=False
    while not task.done():
        try: await asyncio.shield(task)
        except asyncio.CancelledError: cancelled=True
        except Exception: break
    result=task.result()
    if cancelled: raise asyncio.CancelledError
    return result


def _persist(owner, item_id, result, attempts):
    output=result or {'difficulty':'unknown','estimated_minutes':None,'estimated_cost_cny':None,'recommended_model':'unknown','recommended_solver_id':None,'reason':'分诊未确认；请查看助手尝试状态或导入用户事务性分诊'}
    output=observation.strip_secrets(json.dumps({**output,'source':'system_helper','attempts':attempts},ensure_ascii=False))
    now=db.utcnow()
    with db.transaction() as conn:
        conn.execute('UPDATE competition_triage_attempts SET status=?,ended_at=?,output_json=? WHERE id=?',
                     (attempts[-1]['status'] if attempts else 'unknown',now,output,owner))
        conn.execute('UPDATE eval_results SET triage_json=?,updated_at=? WHERE id=?',(output,now,item_id))


async def _item(round_id, item, snapshot, settings, controller, semaphore, first_owner=None):
    async with semaphore:
        result=None;attempts=[]
        for attempt in range(2):
            if power.shutdown_requested() or not features.enabled('system_triage'): return
            owner=first_owner if attempt==0 and first_owner else 'triage-'+round_id+'-'+item['id']+'-'+uuid.uuid4().hex
            projected=json.loads(json.dumps(settings))
            if attempt: projected['brain']['reasoning_effort']={'xhigh':'high','high':'medium','medium':'low','max':'xhigh'}.get(projected['brain']['reasoning_effort'],'low')
            brain=None;timed_out=False
            previous=db.query_one('SELECT triage_json FROM eval_results WHERE id=?',(item['id'],))[0]
            db.execute('INSERT INTO competition_triage_attempts(id,eval_id,item_id,helper_effort,status,started_at,previous_result_json) VALUES(?,?,?,?,?,?,?)',
                       (owner,round_id,item['id'],projected['brain']['reasoning_effort'],'started',db.utcnow(),previous))
            try:
                resource_coordinator.reserve_auxiliary(owner,projected)
                brain=controller._make_brain(projected);HANDLES[owner]=(brain,None)
                scratch=config.WORKSPACE_DIR/'rounds'/round_id/owner;scratch.mkdir(parents=True,exist_ok=True)
                async with asyncio.timeout(TIMEOUT):
                    session=await brain.open({'working_directory':str(scratch)});HANDLES[owner]=(brain,session)
                    challenge=db.query_one('SELECT * FROM challenges WHERE id=?',(item['challenge_id'],))
                    try: scores=await _scores(challenge['platform_challenge_id']) if snapshot['mode']!='demo' and challenge['platform_challenge_id'] else {'status':'unknown'}
                    except Exception as exc: scores={'status':'unknown','reason':type(exc).__name__}
                    if power.shutdown_requested() or not features.enabled('system_triage'):
                        attempts.append({'status':'not_dispatched','helper_effort':projected['brain']['reasoning_effort']});return
                    packet={'protocol':'role_task','task':'competition_triage',
                            'instructions':'你是事务性分诊助手，不是科研PI。只读题面/资源/公开分布，估计难度、耗时、费用及推荐条目；判断标为建议，不推断已验证数据或授予运行权限。',
                            'challenge':next(e.get('challenge_snapshot') for e in snapshot['entries'] if e['challenge_id']==item['challenge_id']),
                            'public_scores':scores,'solver_roster':challenge_models.roster(projected),'output_contract':contract(projected)}
                    async for event in brain.review(session,packet):
                        if event.type=='task_result': result=event.payload['result']
                        if event.type=='error': raise ValueError(event.payload.get('message','分诊失败'))
                    jsonschema.validate(result,packet['output_contract'])
                attempts.append({'status':'done','helper_effort':projected['brain']['reasoning_effort']})
            except TimeoutError:
                result=None;timed_out=True;attempts.append({'status':'timeout','helper_effort':projected['brain']['reasoning_effort']})
            except asyncio.CancelledError:
                result=None;attempts.append({'status':'interrupted','helper_effort':projected['brain']['reasoning_effort']});raise
            except Exception as exc:
                from .model_providers import record_throttle
                record_throttle(projected['brain'],exc)
                attempts.append({'status':'unknown','helper_effort':projected['brain']['reasoning_effort'],'error':type(exc).__name__});result=None
            finally:
                try:
                    if brain is not None:
                        try: await close(owner)
                        except Exception as exc:
                            attempts.append({'status':'close_unknown','error':type(exc).__name__});timed_out=False;result=None
                    else: resource_coordinator.release_sessions(owner)
                finally: _persist(owner,item['id'],result,attempts)
            if not timed_out: break


async def _run(round_id, snapshot, settings, controller, owner):
    root='triage-root-'+owner
    resource_coordinator.register_auxiliary(root,asyncio.current_task())
    try:
        semaphore=asyncio.Semaphore(PARALLEL)
        rows=db.query('SELECT * FROM eval_results WHERE eval_id=?',(round_id,))
        await asyncio.gather(*[_item(round_id,item,snapshot,settings,controller,semaphore,owner if index==0 else None)
                              for index,item in enumerate(rows)])
    finally:
        resource_coordinator.unregister_auxiliary(root)
        if owner not in HANDLES: resource_coordinator.release_sessions(owner)


async def run(round_id, snapshot, settings, controller, operation_id=None):
    if operation_id is not None and (not isinstance(operation_id,str) or not 1<=len(operation_id)<=100):
        raise ValueError('分诊operation_id须为1–100字字符串')
    key=(round_id,operation_id or uuid.uuid4().hex)
    task=ACTIVE.get(key)
    if task is None:
        owner='triage-'+round_id+'-'+uuid.uuid4().hex
        # Legacy requests are independent grants; explicit IDs join the same
        # in-process operation after a lost HTTP reply, without extra calls.
        resource_coordinator.reserve_auxiliary(owner,settings)
        resource_coordinator.unregister_auxiliary(owner)
        task=asyncio.create_task(_run(round_id,snapshot,settings,controller,owner));ACTIVE[key]=task
        resource_coordinator.register_auxiliary('triage-root-'+owner,task)
        def finished(t):
            resource_coordinator.unregister_auxiliary('triage-root-'+owner)
            if owner not in HANDLES:resource_coordinator.release_sessions(owner)
            if not t.cancelled():t.exception()
            if operation_id is None: ACTIVE.pop(key,None)
            # Keep only a bounded set of completed explicit requests. Live
            # requests are never evicted; IDs do not survive backend restart.
            completed=[k for k,v in ACTIVE.items() if v.done()]
            for old in completed[:-128]: ACTIVE.pop(old,None)
        task.add_done_callback(finished)
    await asyncio.shield(task)


async def drain():
    tasks=[t for t in ACTIVE.values() if not t.done()]
    for t in tasks:t.cancel()
    if tasks:await asyncio.gather(*tasks,return_exceptions=True)
    await retry_closes(timeout=15)
