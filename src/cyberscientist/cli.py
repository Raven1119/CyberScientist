"""CLI：uv run cyberscientist serve [--port N] [--mode demo|connected]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="cyberscientist")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="启动本地后端（127.0.0.1）")
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--mode", choices=["demo", "connected"], default=None)
    serve.add_argument("--brain-executable", default=None,
                       help="codex 可执行文件路径（默认自动探测）")
    args = parser.parse_args()

    if args.command == "serve":
        from . import config
        config.acquire_workspace_lock()
        settings = config.load_settings()
        if args.mode:
            settings["app"]["mode"] = args.mode
        if args.brain_executable:
            settings["brain"]["executable"] = args.brain_executable
        settings["app"]["port"] = args.port or settings["app"]["port"]
        config.save_settings(settings)

        from .api import _pairing_code, create_app
        web_dist = Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"
        app = create_app(web_dist if web_dist.exists() else None)

        import uvicorn
        print(f"CyberScientist 后端  http://127.0.0.1:{settings['app']['port']}"
              f"  模式={settings['app']['mode']}", flush=True)
        if web_dist.exists():
            print("前端构建产物已找到，由后端直接提供。", flush=True)
        else:
            print("未找到 apps/web/dist；前端开发模式见 docs/BUILD.md"
                  "（vite dev 代理 /api 到本端口）。", flush=True)
        print(f"本地配对码（仅本次安装有效，勿外传）: {_pairing_code()}", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=settings["app"]["port"],
                    log_level="warning")
    else:  # pragma: no cover
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
