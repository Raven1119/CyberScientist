"""Read-only readiness checks. No login, model turn, Run or submission."""
from __future__ import annotations
import asyncio
import json
import shutil
import subprocess
import time
import uuid
import urllib.error
import urllib.request
from . import backend_identity, config, db, observation, platform_contracts, protocol_drift, public_research, resource_coordinator

_NATIVE_HANDLES = {}
_CLOSE_TASKS = {}


def _item(name, status, detail, **facts):
    return {'name': name, 'status': status, 'detail': detail, 'facts': facts}


def _json_get(url: str, key: str):
    # A configured HTTPS origin is explicit; credentials never follow redirects.
    if not key: return None, None
    if not url.startswith('https://'): raise ValueError('认证检查要求HTTPS')
    platform_contracts._origin(url)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000: raise ValueError('检查响应过大')
                return response.status, json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429: return exc.code, None
            if attempt == 2: return exc.code, None
        except OSError:
            if attempt == 2: return None, None
        if attempt < 2: time.sleep(2 ** attempt)
    return None, None


def _identity(base, ref):
    code, body = _json_get(base.rstrip('/') + '/auth/me', config.resolve_secret(ref) or '')
    profile = body.get('user') if isinstance(body, dict) and isinstance(body.get('user'), dict) else body
    valid = code == 200 and isinstance(profile, dict) and type(profile.get('id')) in (str, int) and bool(profile['id'])
    return valid, code, {key: profile.get(key) for key in ('id', 'email', 'name')} if valid else {}


def mailbox_checks(settings):
    platform = settings['mailbox']['platform']
    rows = db.query('SELECT role,email,platform,status,secret_ref FROM mailboxes')
    items, identities = [], []
    for role, label in (('harvest', '收割邮箱'), ('experiment', '实验邮箱')):
        active = [row for row in rows if row['role'] == role and row['status'] == 'active']
        matched = [row for row in active if row['platform'] == platform]
        if platform != 'bohrium_playground':
            items.append(_item(role + '_mailbox', 'fail', label + '当前平台为Demo，不能证明参赛可用', platform=platform)); continue
        if not active or len(matched) != len(active):
            items.append(_item(role + '_mailbox', 'fail', label + '未启用或绑定平台不符', platform=platform, active=len(active))); continue
        results = [_identity(settings['playground']['base_url'], row['secret_ref']) for row in matched]
        binding = []
        for row, (ok, code, profile) in zip(matched, results):
            expected = row['email'].strip()
            actual = (profile.get('email') or profile.get('name')) if '@' in expected else profile.get('name')
            binding.append(actual.strip().casefold() == expected.casefold() if isinstance(actual, str) else None)
            if ok: identities.append((role, str(profile['id'])))
        valid = all(ok for ok, _, _ in results) and all(value is True for value in binding)
        definitive = False in binding or any(code in (401, 403) or code is None and not config.resolve_secret(row['secret_ref']) for row, (_, code, _) in zip(matched, results))
        items.append(_item(role + '_mailbox', 'pass' if valid else 'fail' if definitive else 'warn', label + ('已认证，身份及平台匹配' if valid else '身份不符、凭据无效或认证未知'), platform=platform, active=len(matched), identity_matches=binding, http_statuses=[code for _, code, _ in results]))
    duplicate = len({identity for _, identity in identities}) != len(identities)
    if duplicate:
        for item in items:
            if item['status'] == 'pass': item.update(status='fail', detail='多个邮箱绑定同一平台账号，需检查凭据归属')
            item['facts']['duplicate_identity'] = True
    return items


def playground_check(settings):
    ref = settings['playground']['token_secret_ref']
    valid, code, _ = _identity(settings['playground']['base_url'], ref)
    return _item('playground', 'pass' if valid else 'fail' if not config.resolve_secret(ref) or code in (401, 403) else 'warn', '操作者密钥' + ('已认证' if valid else '缺失、无效或认证未知'), http_status=code)


def deepseek_check():
    key = config.deepseek_key()
    code, body = _json_get('https://api.deepseek.com/models', key or '')
    models = body.get('data') if isinstance(body, dict) else None
    available = isinstance(models, list) and any(isinstance(model, dict) and model.get('id') == 'deepseek-flash' for model in models)
    valid = code == 200 and available
    return _item('deepseek', 'pass' if valid else 'fail' if not key or code in (401, 403) or code == 200 else 'warn', 'DeepSeek密钥及Flash模型' + ('可用（只读目录）' if valid else '未确认可用'), http_status=code, flash_listed=available, model_turns=0)


async def codex_check(settings):
    from .brains.codex import default_executable
    from .codex_protocol import initialize, native_brain_environment
    from .jsonrpc_stdio import JsonRpcStdio
    exe = settings['brain'].get('executable') or default_executable()
    if not exe: return _item('codex', 'fail', '未找到Linux原生Codex')
    rpc = JsonRpcStdio([exe, 'app-server'], env=native_brain_environment(), name='preflight-codex')
    owner = 'preflight-codex-' + uuid.uuid4().hex
    resource_coordinator.reserve_auxiliary(owner, settings)
    _NATIVE_HANDLES[owner] = rpc
    try:
        await rpc.start(); await initialize(rpc)
        account = await rpc.request('account/read', {'refreshToken': False}, timeout=30)
        identity = account.get('account')
        authenticated = isinstance(identity, dict) and (identity.get('type') == 'apiKey' or identity.get('type') == 'amazonBedrock' or identity.get('type') == 'chatgpt' and 'email' in identity and isinstance(identity.get('planType'), str))
        identity_unknown = identity is not None and not authenticated
        found, cursor, seen = {}, None, set()
        for _ in range(20):
            page = await rpc.request('model/list', {'includeHidden': True, 'limit': 100, 'cursor': cursor}, timeout=30)
            if not isinstance(page.get('data'), list): raise ValueError('模型目录格式未知')
            for model in page['data']:
                if model.get('model') in ('gpt-6-astra', 'gpt-6.1-sol'):
                    found[model['model']] = [entry.get('reasoningEffort') for entry in model.get('supportedReasoningEfforts', [])]
            cursor = page.get('nextCursor')
            if not cursor: break
            if cursor in seen: raise ValueError('模型目录分页重复')
            seen.add(cursor)
        else: raise ValueError('模型目录分页未完成')
        ready = authenticated and 'xhigh' in found.get('gpt-6-astra', []) and 'high' in found.get('gpt-6.1-sol', [])
        return _item('codex', 'pass' if ready else 'warn' if identity_unknown else 'fail', '原生认证与Astra xhigh / Sol high目录' + ('通过' if ready else '未满足'), authenticated=authenticated, models=found, model_turns=0)
    finally:
        await _close_native(owner, rpc)


def _start_close(owner, rpc):
    existing = _CLOSE_TASKS.get(owner)
    if existing is not None and not existing.done(): return existing
    task = asyncio.create_task(_close_work(owner, rpc))
    _CLOSE_TASKS[owner] = task
    resource_coordinator.register_auxiliary(owner, task)
    def finished(task):
        if task.cancelled():
            resource_coordinator.close_failed(owner, asyncio.CancelledError())
            resource_coordinator.unregister_auxiliary(owner)
        else: task.exception()  # A timed-out waiter may have left; evidence is persisted below.
    task.add_done_callback(finished)
    return task


async def _close_native(owner, rpc):
    close = _start_close(owner, rpc)
    while not close.done():
        try: await asyncio.shield(close)
        except asyncio.CancelledError: continue
        except Exception: break
    return close.result()


async def _close_work(owner, rpc):
    stop = asyncio.create_task(rpc.stop())
    while not stop.done():
        try: await asyncio.shield(stop)
        except asyncio.CancelledError: continue
        except Exception: break
    try: stop.result()
    except BaseException as exc:
        resource_coordinator.close_failed(owner, exc)
        resource_coordinator.unregister_auxiliary(owner)
        raise
    else:
        _NATIVE_HANDLES.pop(owner, None)
        _CLOSE_TASKS.pop(owner, None)
        db.execute('DELETE FROM system_state WHERE key=?', ('native_close_unknown:' + owner,))
        resource_coordinator.release_sessions(owner)


async def retry_closes(timeout=0):
    tasks = []
    for owner, rpc in list(_NATIVE_HANDLES.items()):
        task = resource_coordinator.auxiliary_task(owner)
        if owner not in _CLOSE_TASKS and task is not None and not task.done(): continue
        tasks.append(_start_close(owner, rpc))
    if tasks: await asyncio.wait(tasks, timeout=max(0, timeout))


def research_check(name, function, value):
    result = function(value)
    # Do not expose returned papers, identity or arbitrary remote response bodies.
    return _item(name, 'pass' if result.get('status') == 'received' else 'warn', '只读公开工具' + ('收到回执' if result.get('status') == 'received' else '未确认'), http_status=result.get('http_status'), sha256=result.get('sha256'), source=result.get('source'))


def drift_check():
    result = protocol_drift.check()
    ready = result.get('status') == 'unchanged' and result.get('complete') is True
    return _item('protocol_drift', 'pass' if ready else 'warn', '公开协议无变化' if ready else '协议变化、关闭或检查未知；请核对', observation=result)


def cached():
    row = db.query_one("SELECT payload_json FROM runtime_observations WHERE kind='preflight'")
    return json.loads(row['payload_json']) if row else None


async def _run(connection_checker, health_checker):
    settings = config.load_settings()
    async def bohrium_check():
        result = await connection_checker('bohrium')
        health = result.get('health', {})
        ready = health.get('authenticated') is True and '不在可访问列表' not in result.get('detail', '')
        return _item('bohrium', 'pass' if ready else 'fail' if not config.resolve_secret(settings['bohrium']['access_key_secret_ref']) else 'warn', result.get('detail', '认证未确认'), version=health.get('version'), authenticated=health.get('authenticated'))
    checks = [asyncio.to_thread(mailbox_checks, settings), asyncio.to_thread(playground_check, settings), bohrium_check(), codex_check(settings), asyncio.to_thread(deepseek_check), asyncio.to_thread(research_check, 'web_search', public_research.web_search, 'Bohrium public documentation'), asyncio.to_thread(research_check, 'web_read', public_research.web_read, 'https://play.bohrium.com/api/protocol'), asyncio.to_thread(research_check, 'lkm', public_research.lkm_search, 'water hydrogen bonding'), asyncio.to_thread(drift_check)]
    names = ['mailboxes', 'playground', 'bohrium', 'codex', 'deepseek', 'web_search', 'web_read', 'lkm', 'protocol_drift']
    values = await asyncio.gather(*checks, return_exceptions=True)
    items = []
    for name, value in zip(names, values):
        if isinstance(value, BaseException): items.append(_item(name, 'warn', '检查未确认：' + observation.strip_secrets(type(value).__name__ + ': ' + str(value))[:300]))
        elif isinstance(value, list): items.extend(value)
        else: items.append(value)
    free = shutil.disk_usage(config.DATA_DIR).free
    items.append(_item('disk', 'pass' if free >= 5 * 1024**3 else 'warn', '可用磁盘空间', free_bytes=free, warning_threshold_bytes=5 * 1024**3))
    health = await health_checker()
    items.append(_item('backend', 'pass' if health.get('ok') is True else 'fail', '后端健康检查', backend=health.get('backend'), mode=health.get('mode')))
    loaded = backend_identity.loaded(); checkout = backend_identity.capture()
    proc = await asyncio.to_thread(subprocess.run, ['git', 'tag', '--points-at', checkout['commit'] or 'HEAD'], cwd=config.WORKSPACE_ROOT, capture_output=True, text=True, timeout=10)
    items.append(_item('code', 'pass' if loaded == checkout and checkout.get('commit') else 'warn', '后端与工作区版本' + ('一致' if loaded == checkout else '不同，部署需重启后端'), loaded=loaded, checkout=checkout, tags=proc.stdout.splitlines() if proc.returncode == 0 else None))
    if config.load_settings()['revision'] != settings['revision']:
        items.append(_item('configuration', 'warn', '检查期间配置变化，请重新检查'))
    result = {'observed_at': db.utcnow(), 'status': 'fail' if any(item['status'] == 'fail' for item in items) else 'warn' if any(item['status'] == 'warn' for item in items) else 'pass', 'items': items, 'checked_revision': settings['revision'], 'platform': settings['mailbox']['platform'], 'model_turns': 0, 'notice': '只读检查不等于科学结果、评分或参赛有效性验收。'}
    result = json.loads(observation.strip_secrets(json.dumps(result, ensure_ascii=False)))
    db.execute('INSERT OR REPLACE INTO runtime_observations VALUES(?,?,?)', ('preflight', json.dumps(result, ensure_ascii=False), result['observed_at']))
    return result


async def run(connection_checker, health_checker):
    from . import power
    if power.shutdown_requested(): raise resource_coordinator.ResourceWait('安全关机期间不能开始自检')
    owner = 'preflight-readonly-' + uuid.uuid4().hex
    async def worker():
        resource_coordinator.register_auxiliary(owner, asyncio.current_task())
        try:
            if power.shutdown_requested(): raise resource_coordinator.ResourceWait('安全关机期间不能开始自检')
            task = asyncio.create_task(_run(connection_checker, health_checker))
            while not task.done():
                try: await asyncio.shield(task)
                except asyncio.CancelledError: continue
            return task.result()
        finally: resource_coordinator.release_sessions(owner)
    task = asyncio.create_task(worker())
    task.add_done_callback(lambda finished: None if finished.cancelled() else finished.exception())
    return await asyncio.shield(task)
