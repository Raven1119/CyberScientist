"""Allowlisted releases and runtime-content checks for a single competition tree."""
from __future__ import annotations

import hashlib
import fcntl
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

from . import config

PREFIXES=('src/cyberscientist/','prompts/','skills/','environments/','challenges/',
          'contracts/','vendor/playground_contracts/','evals/','templates/',
          'tools/playground-cli/0.1.40/')
FILES={'pyproject.toml','uv.lock','.env.example','config/workspace.example.yaml',
       'start-runtime.sh','tools/playground-cli/0.1.40/package.json',
       'tools/playground-cli/0.1.40/integrity.json'}
_NUMBER=re.compile(r'(?<!\w)(?:CS-UP-\d+[A-Za-z]*|D-\d+)(?!\w)')


def allowed(name: str) -> bool:
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:return False
    if any(part in ('.git','.package-checks','__pycache__','node_modules') for part in path.parts):return False
    if path.name in ('AGENTS.md','STATUS.md','DECISIONS.md') or path.suffix in ('.pyc','.pyo'):return False
    return name in FILES or name.startswith(PREFIXES)


def runtime_path(name: str) -> bool:
    path=PurePosixPath(name)
    return not path.is_absolute() and '..' not in path.parts and (
        allowed(name) or name.startswith('apps/web/dist/'))


def content_violations(text: str, location: str, development_roots) -> list[dict]:
    patterns=[('development_number',_NUMBER),('development_checks',re.compile(r'\.package-checks'))]
    patterns.extend(('development_path',re.compile(re.escape(str(root))+r'(?![A-Za-z0-9_.-])'))
                    for root in development_roots)
    hits=[]
    for reason,pattern in patterns:
        for match in pattern.finditer(text):
            hits.append({'location':location,'line':text.count('\n',0,match.start())+1,
                         'reason':reason,'token':match.group()})
    # Public documentation URLs remain useful references; a local docs/ path is
    # a development dependency. Never exempt a development absolute path or ID.
    urls=[match.span() for match in re.finditer(r'https?://[^\s<>"\)\]]+',text)]
    for match in re.finditer(r'(?<![A-Za-z0-9_])docs/',text):
        if not any(start<=match.start()<end for start,end in urls):
            hits.append({'location':location,'line':text.count('\n',0,match.start())+1,
                         'reason':'development_docs','token':'docs/'})
    return hits


def scan_content(root: Path, development_roots, *, experience_root: Path | None = None,
                 capability_content: str = '') -> list[dict]:
    hits=[]
    roots=[root/'prompts',root/'skills']
    if experience_root is not None:roots.append(experience_root)
    for directory in roots:
        for path in sorted(directory.rglob('*')):
            if not path.is_file():continue
            if path.is_symlink():
                hits.append({'location':str(path),'line':1,'reason':'runtime_symlink','token':path.name});continue
            try:text=path.read_text('utf-8')
            except UnicodeError:continue
            hits.extend(content_violations(text,str(path),development_roots))
    hits.extend(content_violations(capability_content,'capability_index',development_roots))
    return hits


def export(commit: str, stage: Path, *, source: Path | None = None) -> dict:
    source=source or config.WORKSPACE_ROOT
    if not commit or commit.startswith('-') or any(char.isspace() for char in commit):
        raise ValueError('无效发布引用')
    def git(*args,raw=False):
        result=subprocess.run(['git',*args],cwd=source,capture_output=True,check=True,timeout=60)
        return result.stdout if raw else result.stdout.decode().strip()
    sha=git('rev-parse','--verify',commit+'^{commit}')
    names=[name for name in git('ls-tree','-r','--name-only',sha).splitlines() if allowed(name)]
    if not names or 'src/cyberscientist/cli.py' not in names:raise ValueError('指定提交缺少应用运行文件')
    if stage.exists() and any(stage.iterdir()):raise ValueError('发布暂存目录必须为空')
    stage.mkdir(parents=True,exist_ok=True)
    raw=git('archive','--format=tar',sha,'--',*names,raw=True)
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for member in archive:
            if member.isdir():continue
            if not member.isfile() or not allowed(member.name):raise ValueError('发布包含非白名单常规文件：'+member.name)
            target=stage/member.name;target.parent.mkdir(parents=True,exist_ok=True)
            stream=archive.extractfile(member)
            if stream is None:raise ValueError('发布文件无法读取：'+member.name)
            target.write_bytes(stream.read());target.chmod(member.mode & 0o777)
    files={path.relative_to(stage).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
           for path in sorted(stage.rglob('*')) if path.is_file()}
    return {'commit':sha,'files':files}


def build_frontend(source: Path, commit: str, stage: Path):
    """Build the selected commit; never publish a potentially stale current dist."""
    directory=source/'.package-checks/release-build';directory.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        work=Path(temporary)
        result=subprocess.run(['git','archive','--format=tar',commit,'apps/web'],cwd=source,
                              capture_output=True,check=True,timeout=60)
        with tarfile.open(fileobj=io.BytesIO(result.stdout),mode='r:') as archive:
            for member in archive:
                path=PurePosixPath(member.name)
                if member.isdir() and path in (PurePosixPath('apps'),PurePosixPath('apps/web')):
                    continue
                if path.is_absolute() or '..' in path.parts or not path.is_relative_to('apps/web'):
                    raise ValueError('前端归档路径越界')
                if member.isdir():continue
                if not member.isfile():raise ValueError('前端归档含链接或特殊文件')
                target=work/member.name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
        web=work/'apps/web'
        for args in (['npm','ci'],['npm','run','build']):
            process=subprocess.run(args,cwd=web,capture_output=True,text=True,timeout=600)
            if process.returncode:raise RuntimeError('指定提交的前端构建失败：'+process.stderr[-1500:])
        shutil.copytree(web/'dist',stage/'apps/web/dist')


def port_free(port: int) -> bool:
    with socket.socket() as sock:return sock.connect_ex(('127.0.0.1',port))!=0


def stop_runtime(root: Path, port: int, timeout: float):
    from . import redeploy
    if port_free(port):return None
    health=redeploy.request(port,'/api/v1/health',timeout=5)
    identity=redeploy.process_identity(health,root=root)
    deadline=time.monotonic()+timeout
    while True:
        result=redeploy.request(port,'/api/v1/system/safe-shutdown',{})
        if result.get('can_shutdown') is True:break
        if result.get('errors') or time.monotonic()>=deadline:
            raise RuntimeError('安全关机未确认；未停止或替换代码')
        time.sleep(.5)
    # Revalidate after the asynchronous barrier before signaling this PID.
    if redeploy.process_identity(redeploy.request(port,'/api/v1/health'),root=root)!=identity:
        raise RuntimeError('关机后端身份发生变化，拒绝停止')
    os.kill(identity[0],signal.SIGTERM)
    while redeploy.alive(identity):
        if time.monotonic()>=deadline:raise RuntimeError('后端没有退出，拒绝启动第二个进程')
        time.sleep(.1)
    if not port_free(port):raise RuntimeError('端口仍被占用，拒绝启动')
    return identity[0]


def _launcher(root: Path):
    code='''import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
from cyberscientist.cli import main
main()
'''
    path=root/'.runtime/cyberscientist_launch.py';path.write_text(code)
    return hashlib.sha256(code.encode()).hexdigest()


def sync_dependencies(root: Path):
    """Install only the selected frozen production lock into the runtime venv."""
    digest=hashlib.sha256((root/'uv.lock').read_bytes()).hexdigest()
    marker=root/'.runtime/installed-lock.sha256'
    if marker.exists() and marker.read_text().strip()==digest and (root/'.venv/bin/python').is_file():
        return {'lock_sha256':digest,'changed':False}
    uv=root/'.runtime/bin/uv'
    if not uv.is_file():raise RuntimeError('比赛uv运行时缺失，未启动后端')
    environment=dict(os.environ);environment.pop('PYTHONPATH',None)
    environment.update(UV_PROJECT_ENVIRONMENT=str(root/'.venv'),UV_CACHE_DIR=str(root/'.runtime/uv-cache'))
    with (root/'.runtime/dependency-install.log').open('ab') as output:
        result=subprocess.run([str(uv),'sync','--frozen','--no-dev'],cwd=root,env=environment,
                              stdout=output,stderr=subprocess.STDOUT,timeout=600)
    if result.returncode:raise RuntimeError('比赛锁文件安装失败，未启动后端；查看私有dependency-install.log')
    marker.write_text(digest+'\n')
    return {'lock_sha256':digest,'changed':True}


def start_runtime(root: Path, port: int, commit: str, timeout: float):
    from . import redeploy
    if not port_free(port):raise RuntimeError('启动前端口已被占用')
    codex=root/'.runtime/codex';home=root/'.runtime/home'
    if not (codex/'auth.json').is_file() or not (codex/'config.toml').is_file():
        raise RuntimeError('比赛原生凭据或配置尚未准备')
    executable=root/'.venv/bin/python'
    if not executable.is_file():raise RuntimeError('比赛独立Python环境尚未安装')
    environment=dict(os.environ);environment.update(HOME=str(home),CODEX_HOME=str(codex),
        XDG_CONFIG_HOME=str(home/'.config'),XDG_DATA_HOME=str(home/'.local/share'),XDG_CACHE_HOME=str(home/'.cache'))
    environment.pop('PYTHONPATH',None)
    output=(root/'.runtime/backend.log').open('ab')
    try:process=subprocess.Popen([str(executable),str(root/'.runtime/cyberscientist_launch.py'),
        'serve','--port',str(port)],cwd=root,env=environment,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    finally:output.close()
    (root/'.runtime/backend.pid').write_text(str(process.pid)+'\n')
    deadline=time.monotonic()+timeout
    while True:
        if process.poll() is not None:raise RuntimeError('比赛后端已退出，检查私有backend.log')
        try:health=redeploy.request(port,'/api/v1/health',timeout=2)
        except OSError:
            if time.monotonic()>=deadline:raise RuntimeError('比赛后端健康检查超时')
            time.sleep(.2);continue
        if (health.get('ok') is not True or health.get('process_id')!=process.pid
                or health.get('backend',{}).get('commit')!=commit):
            raise RuntimeError('比赛后端身份或版本不匹配')
        return health


def publish(stage: Path, root: Path, manifest: dict):
    """Only release-owned paths move; mutable data/experience/HOME never move."""
    if any(not runtime_path(name) for name in manifest['files']):
        raise ValueError('发布清单包含白名单之外文件')
    for name,digest in manifest['files'].items():
        path=stage/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('暂存文件与封存清单不匹配：'+name)
    backup=root/'.runtime/previous'/uuid.uuid4().hex;backup.mkdir(parents=True)
    owned=set()
    for path in manifest['files']:
        if path.startswith('tools/'):owned.add('tools/playground-cli/0.1.40')
        elif path.startswith('config/'):owned.add(path)
        else:owned.add(PurePosixPath(path).parts[0])
    metadata={name:(root/'.runtime'/name).read_bytes() if (root/'.runtime'/name).exists() else None
              for name in ('version.json','cyberscientist_launch.py')}
    changed=[]
    try:
        for name in sorted(owned):
            target=root/name
            if target.exists():
                (backup/name).parent.mkdir(parents=True,exist_ok=True);shutil.move(str(target),str(backup/name))
            changed.append(name)
            source=stage/name
            target.parent.mkdir(parents=True,exist_ok=True)
            if source.is_dir():shutil.copytree(source,target)
            else:shutil.copy2(source,target)
        version={'commit':manifest['commit'],'manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
                 'launcher_sha256':_launcher(root)}
        pending=root/'.runtime/version.pending'
        pending.write_text(json.dumps(version,indent=2))
        os.replace(pending,root/'.runtime/version.json')
    except OSError:
        for name in reversed(changed):
            target=root/name
            if target.is_dir():shutil.rmtree(target)
            elif target.exists():target.unlink()
            previous=backup/name
            if previous.exists():shutil.move(str(previous),str(target))
        for name,content in metadata.items():
            path=root/'.runtime'/name
            if content is None:path.unlink(missing_ok=True)
            else:path.write_bytes(content)
        raise
    return version


def compatible(stage: Path):
    required=('src/cyberscientist/runtime_layout.py','contracts/collaboration.schema.json',
              'contracts/experience-policy.txt','start-runtime.sh')
    if any(not (stage/name).is_file() for name in required):
        raise ValueError('目标早于比赛发布协议，未停止现后端；仅可回退到首个兼容比赛版本或更新版本')


def release(commit: str, *, root: Path, port: int, timeout=180, source: Path | None = None):
    runtime=root/'.runtime';runtime.mkdir(parents=True,exist_ok=True)
    with (runtime/'release.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status':'failed','phase':'lock','reason':'另一发布正在运行；未停止或修改比赛代码'}
        try:return _release_locked(commit,root=root,port=port,timeout=timeout,source=source)
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def _release_locked(commit: str, *, root: Path, port: int, timeout=180, source: Path | None = None):
    from . import redeploy
    source=source or config.WORKSPACE_ROOT;runtime=root/'.runtime';runtime.mkdir(parents=True,exist_ok=True)
    journal=runtime/'release-journal'/str(uuid.uuid4());journal.parent.mkdir(parents=True,exist_ok=True)
    result={'status':'running','phase':'prepare','steps':[]}
    def save(step,value):
        result['steps'].append({'step':step,'result':value});journal.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    try:
        with tempfile.TemporaryDirectory(dir=runtime,prefix='staging-') as temporary:
            stage=Path(temporary)
            if (source/'.git').exists():
                manifest=export(commit,stage,source=source)
                build_frontend(source,manifest['commit'],stage)
            else:
                aliases=json.loads((runtime/'release-aliases.json').read_text()) if (runtime/'release-aliases.json').exists() else {}
                sha=aliases.get(commit,commit)
                if not re.fullmatch('[a-f0-9]{40}',sha):raise ValueError('无Git运行时只允许已缓存发布SHA/标签')
                cached=runtime/'releases'/sha
                manifest=json.loads((cached/'manifest.json').read_text())
                if manifest['commit']!=sha:raise ValueError('发布缓存版本不匹配')
                for name,digest in manifest['files'].items():
                    if not runtime_path(name):raise ValueError('发布缓存路径越界')
                    path=cached/'tree'/name
                    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('缓存哈希不匹配：'+name)
                    target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
            compatible(stage)
            # External competition skill directories were copied in full at
            # migration. Keep them on later releases; repository skills win.
            for directory in sorted((root/'skills').glob('bohrium-*')):
                if not (stage/'skills'/directory.name).exists():shutil.copytree(directory,stage/'skills'/directory.name)
            capability=''
            database=root/'.cyberscientist/cyberscientist.db'
            if database.exists():
                import sqlite3
                with sqlite3.connect(f'file:{database}?mode=ro',uri=True) as conn:
                    row=conn.execute("SELECT payload_json FROM runtime_observations WHERE kind='competition_toolchain'").fetchone()
                    capability=row[0] if row else ''
            development=[source] if source.resolve()!=root.resolve() else [root.parent/'CyberScientist']
            development+=list(root.parent.glob('CyberScientist-night-*'))
            hits=scan_content(stage,development,experience_root=root/'experience',capability_content=capability)
            if hits:raise ValueError('运行时内容含开发引用：'+json.dumps(hits,ensure_ascii=False))
            manifest['files']={path.relative_to(stage).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in sorted(stage.rglob('*')) if path.is_file()}
            cached=runtime/'releases'/manifest['commit']
            if not cached.exists():
                cached.parent.mkdir(parents=True,exist_ok=True)
                with tempfile.TemporaryDirectory(dir=cached.parent,prefix='cache-') as temporary_cache:
                    prepared=Path(temporary_cache)/'complete';prepared.mkdir()
                    shutil.copytree(stage,prepared/'tree')
                    (prepared/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2))
                    prepared.rename(cached)
            if (source/'.git').exists():
                tags=subprocess.run(['git','tag','--points-at',manifest['commit']],cwd=source,capture_output=True,text=True,check=True,timeout=30).stdout.splitlines()
                aliases=json.loads((runtime/'release-aliases.json').read_text()) if (runtime/'release-aliases.json').exists() else {}
                aliases.update({tag:manifest['commit'] for tag in tags})
                (runtime/'release-aliases.json').write_text(json.dumps(aliases,sort_keys=True))
            save('manifest',manifest)
            result['phase']='shutdown';save('stop',stop_runtime(root,port,timeout))
            result['phase']='publish';save('version',publish(stage,root,manifest))
            result['phase']='dependencies';save('dependencies',sync_dependencies(root))
            result['phase']='start';save('health',start_runtime(root,port,manifest['commit'],timeout))
            result['phase']='resume';resumed=redeploy.request(port,'/api/v1/ops/resume',{});save('resume',resumed)
            if resumed.get('status')!='ready':raise RuntimeError('只读对账/恢复未完成')
            result['phase']='preflight';checked=redeploy.request(port,'/api/v1/preflight',{},timeout=600);save('preflight',checked)
            if checked.get('status') not in ('pass','warn'):raise RuntimeError('比赛目录自检失败')
            save('digest',redeploy.request(port,'/api/v1/ops/digest'))
            result.update(status='completed',commit=manifest['commit'])
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        result.update(status='failed',reason=str(exc))
    journal.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
