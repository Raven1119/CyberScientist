"""CLI：start/serve and persistent local-only evaluation suites."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
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
