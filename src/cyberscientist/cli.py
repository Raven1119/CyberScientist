"""CLI：start/serve and persistent local-only evaluation suites."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[2] / "apps" / "web"


def _ensure_frontend_build() -> Path | None:
    dist = WEB_DIR / "dist"
    if dist.exists():
        return dist
    if not (WEB_DIR / "package.json").exists():
        return None
    print("未找到前端构建产物，正在执行 npm run build …", flush=True)
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    try:
        proc = subprocess.run([npm, "run", "build"], cwd=WEB_DIR,
                              capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"前端构建失败: {exc}", flush=True)
        return None
    if proc.returncode != 0 or not dist.exists():
        print(f"前端构建失败:\n{proc.stdout[-800:]}\n{proc.stderr[-800:]}",
              flush=True)
        return None
    return dist


def _open_browser_when_ready(url: str) -> None:
    """Open the local UI only after the backend has finished startup."""
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{url}/api/v1/health", timeout=0.5) as response:
                if response.status == 200 and json.load(response).get("ok") is True:
                    break
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    else:
        print(f"服务尚未就绪；就绪后请打开 {url}", flush=True)
        return

    import webbrowser
    try:
        if webbrowser.open(url):
            return
    except Exception:
        pass
    # WSL may have no Linux desktop opener. This opens the Windows browser;
    # the backend, brain, and executor remain Linux processes.
    try:
        is_wsl = "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
    except OSError:
        is_wsl = False
    if is_wsl:
        from shutil import which
        cmd = which("cmd.exe")
        if cmd is None and Path("/mnt/c/Windows/System32/cmd.exe").exists():
            cmd = "/mnt/c/Windows/System32/cmd.exe"
        if cmd:
            try:
                subprocess.run([cmd, "/C", "start", "", url],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5, check=True)
                return
            except (OSError, subprocess.SubprocessError):
                pass
    print(f"浏览器未自动打开，请访问 {url}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="cyberscientist")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="一键启动：前端构建 + 后端 + 打开浏览器")
    start.add_argument("--port", type=int, default=None)
    start.add_argument("--mode", choices=["demo", "connected"], default=None)
    serve = sub.add_parser("serve", help="仅启动本地后端（127.0.0.1）")
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--mode", choices=["demo", "connected"], default=None)
    serve.add_argument("--brain-executable", default=None,
                       help="大脑 CLI 可执行文件路径（默认自动探测）")
    sub.add_parser("shutdown", help="安全暂停、备份并列出远程任务")
    preflight = sub.add_parser('preflight', help='只读赛前自检（不启动Run或模型turn）')
    preflight.add_argument('--json', action='store_true')
    preflight.add_argument('--port', type=int, default=None)
    ops = sub.add_parser('ops', help='运维接口')
    ops_sub = ops.add_subparsers(dest='ops_command', required=True)
    ops_switch = ops_sub.add_parser('switch', help='随时开关新功能，保留旧数据')
    ops_switch.add_argument('name')
    ops_switch.add_argument('state', choices=('on', 'off'))
    ops_switch.add_argument('--port', type=int, default=None)
    ops_status = ops_sub.add_parser('status', help='运行状态和最近错误')
    ops_status.add_argument('--json', action='store_true')
    ops_digest = ops_sub.add_parser('digest', help='不超过60行的低频监控摘要')
    ops_digest.add_argument('--since', default=None)
    ops_events = ops_sub.add_parser('events', help='Run最近公开事件')
    ops_events.add_argument('run_id')
    ops_events.add_argument('--tail', type=int, default=20)
    ops_alerts = ops_sub.add_parser('alerts', help='未处理提醒和经验审批')
    ops_shutdown = ops_sub.add_parser('shutdown', help='安全关机屏障和备份')
    ops_resume = ops_sub.add_parser('resume', help='远程只读对账后恢复安全关机意图')
    ops_redeploy = ops_sub.add_parser('redeploy', help='安全关机、只换代码、对账恢复和自检')
    ops_redeploy.add_argument('--commit', default=None)
    ops_redeploy.add_argument('--timeout', type=float, default=180)
    ops_release=ops_sub.add_parser('release',help='按提交白名单发布比赛目录，保留运行数据')
    ops_release.add_argument('--commit',required=True)
    ops_release.add_argument('--timeout',type=float,default=180)
    ops_submit = ops_sub.add_parser('submit', help='应用内统一提交路径；支持有界旧题验证授权')
    for name in ('run-id', 'trial-id', 'package-path', 'operation-id'):
        ops_submit.add_argument('--' + name, required=True)
    ops_submit.add_argument('--authorization-file')
    ops_submit.add_argument('--mailbox-id')
    ops_submit.add_argument('--retry-of')
    ops_submit.add_argument('--dry-run',action='store_true',help='仅官方CLI试构建，不预占、不提交')
    for command in (ops_redeploy, ops_status, ops_digest, ops_events, ops_alerts, ops_shutdown, ops_resume, ops_submit): command.add_argument('--port', type=int, default=None)
    ops_release.add_argument('--port',type=int,default=None)
    for command in (ops_switch,ops_redeploy,ops_release,ops_status,ops_digest,ops_events,ops_alerts,ops_shutdown,ops_resume,ops_submit):
        command.add_argument('--target',choices=('dev','comp'),default='comp' if command==ops_release else 'dev')
    evaluation = sub.add_parser('eval', help='运行或生成本地评测报告')
    evaluation_sub = evaluation.add_subparsers(dest='eval_command', required=True)
    eval_run = evaluation_sub.add_parser('run', help='启动一层评测')
    eval_run.add_argument('--suite', choices=('fast', 'hard'), required=True)
    eval_run.add_argument('--repeats', type=int, default=2)
    eval_run.add_argument('--label', default='')
    eval_report = evaluation_sub.add_parser('report', help='重建 Markdown 和 JSON 报告')
    eval_report.add_argument('eval_id')
    eval_rescore = evaluation_sub.add_parser('rescore', help='原 Run 封存包的一次受控补评分')
    eval_rescore.add_argument('result_id')
    args = parser.parse_args()

    if args.command == 'ops':
        from . import config, features, observation
        from . import runtime_layout,runtime_release
        root=runtime_layout.competition_root() if args.target=='comp' else config.WORKSPACE_ROOT
        if args.target=='comp':
            settings_path=root/'.cyberscientist/settings.json'
            if not settings_path.is_file():parser.error('比赛设置尚未迁移，拒绝回退开发端口')
            port=args.port or json.loads(settings_path.read_text())['app']['port']
        else:port=args.port or config.load_settings()['app']['port']
        if args.ops_command=='release' or (args.ops_command=='redeploy' and args.target=='comp'):
            if args.target!='comp':parser.error('release只发布比赛目录')
            current=runtime_layout.version(root)
            commit=args.commit or (current or {}).get('commit')
            if not commit:parser.error('比赛版本未知，请给出commit')
            result=runtime_release.release(commit,root=root,port=port,timeout=args.timeout,
                source=root if args.ops_command=='redeploy' else None)
            print(observation.strip_secrets(json.dumps(result,ensure_ascii=False)))
            raise SystemExit(0 if result['status']=='completed' else 1)
        if args.ops_command == 'redeploy':
            from .redeploy import redeploy
            result = redeploy(port, args.commit, timeout=args.timeout)
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0 if result['status'] == 'completed' else 1)
        method = 'GET'; body = None
        if args.target=='comp':
            from . import redeploy
            try:redeploy.process_identity(redeploy.request(port,'/api/v1/health',timeout=5),root=root)
            except (OSError,ValueError,RuntimeError) as exc:
                print(observation.strip_secrets('比赛后端身份未确认：'+str(exc)),file=sys.stderr)
                raise SystemExit(2)
        if args.ops_command == 'submit':
            path = '/api/v1/ops/submit'; method = 'POST'
            body = {k: getattr(args,k) for k in ('run_id','trial_id','package_path','operation_id','mailbox_id','retry_of')}
            if args.dry_run:body['dry_run']=True
            if args.authorization_file:
                body['authorization'] = json.loads(Path(args.authorization_file).read_text())
        elif args.ops_command == 'switch':
            if args.name not in features.NAMES: parser.error('未知功能开关：' + args.name)
            path = '/api/v1/features/' + args.name; method = 'PUT'; body = {'enabled': args.state == 'on'}
        elif args.ops_command == 'events':
            if not 1 <= args.tail <= 1000: parser.error('tail须为1–1000')
            path = '/api/v1/ops/events/' + urllib.parse.quote(args.run_id, safe='') + '?tail=' + str(args.tail)
        elif args.ops_command == 'digest':
            path='/api/v1/ops/digest'+('?'+urllib.parse.urlencode({'since':args.since}) if args.since else '')
        elif args.ops_command == 'shutdown': path = '/api/v1/system/safe-shutdown'; method = 'POST'; body = {}
        elif args.ops_command == 'resume': path = '/api/v1/ops/resume'; method = 'POST'; body = {}
        else: path = '/api/v1/ops/' + args.ops_command
        request = urllib.request.Request(f'http://127.0.0.1:{port}' + path, data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=180 if method == 'POST' else 30) as response: result = json.load(response)
        except (OSError, ValueError) as exc:
            print(observation.strip_secrets(str(exc)), file=sys.stderr); raise SystemExit(2)
        print(observation.strip_secrets(result['text'] if args.ops_command=='digest' else json.dumps(result, ensure_ascii=False)))
        if args.ops_command == 'shutdown' and result.get('can_shutdown') is not True: raise SystemExit(1)
        if args.ops_command == 'resume' and result.get('status') != 'ready': raise SystemExit(1)
        return

    if args.command == 'preflight':
        from . import config, observation
        port = args.port or config.load_settings()['app']['port']
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/v1/preflight', data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                result = json.load(response)
        except (OSError, ValueError) as exc:
            print(observation.strip_secrets('赛前自检未完成：' + str(exc)), file=sys.stderr)
            raise SystemExit(2)
        print(json.dumps(result, ensure_ascii=False) if args.json else '\n'.join(item['status'].upper() + ' · ' + item['name'] + ' · ' + item['detail'] for item in result['items']))
        raise SystemExit(1 if result['status'] == 'fail' else 0)

    if args.command == 'shutdown':
        from . import config
        port = config.load_settings()['app']['port']
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/v1/system/safe-shutdown', data=b'{}',
                                         headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.load(response)
        print(json.dumps(result, ensure_ascii=False))
        if not result['can_shutdown']:
            raise SystemExit(1)
        return
    if args.command == 'eval':
        if args.eval_command == 'report':
            from . import db, evaluations
            db.init_db()
            try:
                markdown, structured = evaluations.write_report(args.eval_id)
            except evaluations.EvaluationError as exc:
                parser.error(str(exc))
            print(json.dumps({'markdown': str(markdown), 'json': str(structured)},
                             ensure_ascii=False))
            return
        if args.eval_command == 'rescore':
            from . import db, evaluations
            db.init_db()
            try:
                updated = evaluations.retry_unavailable_score(args.result_id)
            except evaluations.EvaluationError as exc:
                parser.error(str(exc))
            print(json.dumps({'eval_id': updated['id'], 'result_id': args.result_id,
                              'status': updated['status']}, ensure_ascii=False))
            return
        from . import config
        settings = config.load_settings()
        port = settings['app']['port']
        root = f'http://127.0.0.1:{port}'
        health = root + '/api/v1/health'
        try:
            urllib.request.urlopen(health, timeout=2).close()
        except OSError:
            # A detached backend keeps the evaluation progressing after the
            # initiating shell closes. Its log remains local and ignored.
            log_dir = config.WORKSPACE_ROOT / '.package-checks' / 'eval-server'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '.log')
            with log_file.open('ab') as output:
                subprocess.Popen([sys.executable, '-m', 'cyberscientist.cli', 'serve',
                                  '--port', str(port)], cwd=config.WORKSPACE_ROOT,
                                 stdout=output, stderr=subprocess.STDOUT,
                                 start_new_session=True)
            for _ in range(60):
                try:
                    urllib.request.urlopen(health, timeout=1).close()
                    break
                except OSError:
                    time.sleep(.5)
            else:
                parser.error(f'后端未就绪；检查 {log_file}')
        request = urllib.request.Request(root + '/api/v1/evals',
            data=json.dumps({'suite': args.suite, 'repeats': args.repeats,
                             'label': args.label}).encode(),
            headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                created = json.load(response)
        except urllib.error.HTTPError as exc:
            parser.error(f'评测创建失败 HTTP {exc.code}: {exc.read(1000).decode(errors="replace")}')
        print(json.dumps({'eval_id': created['id'], 'status': created['status'],
                          'url': root + '/api/v1/evals/' + created['id']}, ensure_ascii=False))
        return
    if args.command in ("start", "serve"):
        from . import config
        if (config.DATA_DIR/'runtime-migrated.json').exists():
            parser.error('此开发后端已迁移并禁用；请使用比赛启动脚本或ops --target comp')
        config.acquire_workspace_lock()
        settings = config.load_settings()
        if args.mode:
            settings["app"]["mode"] = args.mode
        if getattr(args, "brain_executable", None):
            settings["brain"]["executable"] = args.brain_executable
        settings["app"]["port"] = args.port or settings["app"]["port"]
        config.save_settings(settings)

        web_dist = None
        if args.command == "start":
            web_dist = _ensure_frontend_build()
            if web_dist is None:
                print("前端构建不可用；可改用 serve 仅启动后端，或手动 "
                      "cd apps/web && npm install && npm run build", flush=True)
                sys.exit(1)
        else:
            web_dist = (WEB_DIR / "dist") if (WEB_DIR / "dist").exists() else None

        from .api import create_app
        app = create_app(web_dist)

        import uvicorn
        url = f"http://127.0.0.1:{settings['app']['port']}"
        print(f"CyberScientist  {url}  模式={settings['app']['mode']}",
              flush=True)
        if web_dist:
            print("前端由后端同端口直接提供；单用户本地工具，仅监听 127.0.0.1。",
                  flush=True)
        else:
            print("未找到 apps/web/dist；前端开发模式见 docs/BUILD.md"
                  "（vite dev 代理 /api 到本端口）。", flush=True)
        if args.command == "start":
            import threading
            threading.Thread(target=_open_browser_when_ready, args=(url,),
                             daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=settings["app"]["port"],
                    log_level="warning", timeout_graceful_shutdown=5)
    else:  # pragma: no cover
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
