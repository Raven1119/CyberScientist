"""Serve the native application with an isolated, credential-free Demo workspace.

    .venv/bin/python checks/serve_ui_demo.py --port 8765

The default workspace is a new temporary directory. This helper never reads the
user's settings/secrets or substitutes protocol fixtures for the built-in Demo
brain/executor. All UI actions still go through the production FastAPI routes.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    root = (args.data_root or Path(tempfile.mkdtemp(prefix="cs-ui-demo-"))).resolve()
    marker = root / "UI_DEMO_WORKSPACE.json"
    if root.exists() and any(root.iterdir()) and not marker.is_file():
        parser.error("Refusing a nonempty directory without the UI Demo marker")
    root.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"purpose": "CyberScientist UI acceptance", "mode": "demo"}), encoding="utf-8")

    from cyberscientist import config

    config.DATA_DIR = root / ".cyberscientist"
    config.DB_PATH = config.DATA_DIR / "demo.db"
    config.SECRETS_PATH = config.DATA_DIR / "secrets.json"
    config.SETTINGS_PATH = config.DATA_DIR / "settings.json"
    config.LOCK_PATH = config.DATA_DIR / "controller.lock"
    config.WORKSPACE_DIR = root / "workspace"
    config.EXPERIENCE_DIR = root / "experience"
    config.acquire_workspace_lock()
    settings = json.loads(json.dumps(config.DEFAULT_SETTINGS))
    settings["app"].update(mode="demo", port=args.port, data_dir=str(config.DATA_DIR))
    settings["memory"]["root"] = str(config.EXPERIENCE_DIR)
    settings["run_defaults"].update(max_jobs=0, max_submissions=0)
    config.save_settings(settings)

    # Import only after redirecting every mutable path. create_app uses native
    # DemoBrain/DemoPrime; an empty llm_profiles list also prevents global writes.
    from cyberscientist.api import create_app
    import uvicorn

    print(f"UI DEMO ONLY — data: {root}", flush=True)
    print(f"API and built frontend: http://127.0.0.1:{args.port}", flush=True)
    app = create_app(web_dist=ROOT / "apps" / "web" / "dist")

    @app.middleware("http")
    async def identify_isolated_demo(request, call_next):
        response = await call_next(request)
        response.headers["X-CyberScientist-UI-Demo"] = "isolated-native-demo"
        return response

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
