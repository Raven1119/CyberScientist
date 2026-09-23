"""CLI：uv run cyberscientist start|serve [--port N] [--mode demo|connected]"""
from __future__ import annotations

import argparse
import subprocess
import sys
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
    args = parser.parse_args()

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
            import webbrowser
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        uvicorn.run(app, host="127.0.0.1", port=settings["app"]["port"],
                    log_level="warning", timeout_graceful_shutdown=5)
    else:  # pragma: no cover
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
