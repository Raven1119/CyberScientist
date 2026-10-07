"""Local, fail-closed maintenance of the identified backend process."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import uuid

from . import config, observation


def request(port, path, body=None, timeout=180):
    req = urllib.request.Request(f'http://127.0.0.1:{port}' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json'}, method='POST' if body is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def git(*args):
    return subprocess.run(['git', *args], cwd=config.WORKSPACE_ROOT,
                          capture_output=True, text=True, timeout=30, check=True).stdout.strip()


def process_identity(health):
    pid = health.get('process_id')
    root = config.WORKSPACE_ROOT.resolve()
    if type(pid) is not int or pid <= 1 or pid == os.getpid():
        raise RuntimeError('后端没有可核实的进程身份；保留安全关机状态')
    proc = Path('/proc') / str(pid)
    command = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode()
    if ((proc / 'cwd').resolve() != root or health.get('workspace_root') != str(root)
            or 'cyberscientist' not in command):
        raise RuntimeError('后端PID、工作区或命令不匹配；拒绝停止进程')
    # Bind the Linux process start tick to prevent PID reuse while polling.
    return pid, (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]


def alive(identity):
    pid, start = identity
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] != 'Z' and fields[19] == start
    except FileNotFoundError:
        return False


def redeploy(port, commit=None, *, timeout=180):
    root = config.WORKSPACE_ROOT
    directory = root / '.package-checks' / 'redeploy'
    directory.mkdir(parents=True, exist_ok=True)
    journal = directory / (uuid.uuid4().hex + '.json')
    result = {'status': 'running', 'steps': [], 'journal': str(journal)}
    stopped_at = None

    def save(step, value):
        result['steps'].append({'step': step, 'at': time.time(), 'result': value})
        journal.write_text(json.dumps(observation.redact_structure(result), ensure_ascii=False, indent=2))

    try:
        result['phase'] = 'target'
        target = git('rev-parse', '--verify', (commit or 'HEAD') + '^{commit}')
        if git('status', '--porcelain', '--untracked-files=no'):
            raise RuntimeError('已跟踪文件未提交；请先封存代码，账本不受此检查影响')
        if git('diff', '--name-only', 'HEAD', target, '--', 'experience'):
            raise RuntimeError('目标会改变经验文件；拒绝代码回退，需使用含当前经验的兼容提交')
        save('target', {'commit': target})
        result['phase'] = 'shutdown'
        deadline = time.monotonic() + timeout
        while True:
            shutdown = request(port, '/api/v1/system/safe-shutdown', {})
            save('shutdown', shutdown)
            if shutdown.get('can_shutdown') is True:
                break
            if shutdown.get('errors') or time.monotonic() >= deadline:
                raise RuntimeError('安全关机未确认：' + str(shutdown.get('message')))
            time.sleep(.5)
        result['phase'] = 'stop'
        identity = process_identity(request(port, '/api/v1/health'))
        os.kill(identity[0], signal.SIGTERM)
        stopped_at = time.monotonic()
        deadline = stopped_at + timeout
        while alive(identity):
            if time.monotonic() >= deadline:
                raise RuntimeError('后端未退出；不强杀、不继续部署')
            time.sleep(.1)
        save('stop', {'pid': identity[0]})
        result['phase'] = 'checkout'
        if git('rev-parse', 'HEAD') != target:
            git('switch', '--detach', target)
        if git('rev-parse', 'HEAD') != target:
            raise RuntimeError('磁盘commit与目标不符')
        save('checkout', {'commit': target})
        result['phase'] = 'start'
        log_path = journal.with_suffix('.log')
        with log_path.open('ab') as output:
            process = subprocess.Popen([sys.executable, '-m', 'cyberscientist.cli', 'serve', '--port', str(port)],
                cwd=root, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + timeout
        while True:
            if process.poll() is not None:
                raise RuntimeError('新后端已退出；检查部署日志')
            try:
                health = request(port, '/api/v1/health', timeout=2)
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('新后端健康检查超时')
                time.sleep(.2)
                continue
            if (health.get('ok') is not True or health.get('process_id') != process.pid
                    or health.get('backend', {}).get('commit') != target):
                raise RuntimeError('新后端健康检查身份或目标版本不符')
            break
        result['downtime_seconds'] = time.monotonic() - stopped_at
        save('start', health)
        result['phase'] = 'resume'
        resumed = request(port, '/api/v1/ops/resume', {})
        save('resume', resumed)
        if resumed.get('status') != 'ready':
            raise RuntimeError('只读对账或恢复尚未完成，保留当前状态')
        result['phase'] = 'preflight'
        checked = request(port, '/api/v1/preflight', {}, timeout=600)
        save('preflight', checked)
        if checked.get('status') not in ('pass', 'warn'):
            raise RuntimeError('自检失败；未继续到digest，请查看自检项目')
        result['phase'] = 'digest'
        digest = request(port, '/api/v1/ops/digest')
        save('digest', digest)
        result.update(status='completed', preflight_status=checked['status'], digest=digest.get('text'))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result.update(status='failed', reason=str(exc))
    result['maintenance_seconds'] = (time.monotonic() - stopped_at) if stopped_at else None
    journal.write_text(json.dumps(observation.redact_structure(result), ensure_ascii=False, indent=2))
    return observation.redact_structure(result)
