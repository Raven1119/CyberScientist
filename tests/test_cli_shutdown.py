"""A real open SSE response must not indefinitely block CLI SIGTERM shutdown."""
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import pytest

from cyberscientist import config, db


@pytest.mark.skipif(sys.platform == "win32", reason="Linux SIGTERM lifecycle")
def test_cli_sigterm_exits_with_sse_client_still_connected(tmp_path):
    # A terminal fixture Run is sufficient: its event stream remains open.
    db.execute(
        "INSERT INTO challenges(id, origin, title, content, content_hash, imported_at, is_demo)"
        " VALUES('shutdown-fixture', 'demo://local', 'fixture', '', 'hash', ?, 1)",
        (db.utcnow(),),
    )
    db.execute(
        "INSERT INTO runs(id, challenge_id, mode, phase, config_snapshot, created_at)"
        " VALUES('shutdown-run', 'shutdown-fixture', 'demo', 'finished', '{}', ?)",
        (db.utcnow(),),
    )
    paths = {name: str(getattr(config, name)) for name in (
        "DATA_DIR", "DB_PATH", "SECRETS_PATH", "SETTINGS_PATH", "LOCK_PATH",
        "WORKSPACE_DIR", "EXPERIENCE_DIR",
    )}
    child = """
import json, sys
from pathlib import Path
from cyberscientist import config
for name, value in json.loads(sys.argv[1]).items():
    setattr(config, name, Path(value))
port = sys.argv[2]
sys.argv = ['cyberscientist', 'serve', '--port', port, '--mode', 'demo']
from cyberscientist.cli import main
main()
"""
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path),
        "LANG": "C.UTF-8", "PYTHONPATH": str(Path(config.__file__).resolve().parents[1]),
    }
    process = subprocess.Popen(
        [sys.executable, "-c", child, json.dumps(paths), str(port)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    sse = None
    response = None
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            assert process.poll() is None, "isolated CLI exited before becoming healthy"
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=.2)
            try:
                connection.request("GET", "/api/v1/health")
                if connection.getresponse().status == 200:
                    break
            except OSError:
                time.sleep(.05)
            finally:
                connection.close()
        else:
            pytest.fail("isolated CLI did not become healthy")

        sse = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        sse.request("GET", "/api/v1/runs/shutdown-run/events")
        response = sse.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type").startswith("text/event-stream")
        assert response.readline() == b": heartbeat\n"

        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        # Deliberately keep the client connection open throughout shutdown.
        stdout, stderr = process.communicate(timeout=9)
        elapsed = time.monotonic() - started
        assert process.returncode in (0, -signal.SIGTERM), (stdout, stderr)
        assert elapsed < 8, f"SSE shutdown took {elapsed:.3f}s"
        assert "Task was destroyed" not in stderr
        assert "async_generator_asend" not in stderr
    finally:
        if response is not None:
            response.close()
        if sse is not None:
            sse.close()
        if process.poll() is None:
            process.kill()  # Reap only this isolated test process on regression.
        process.communicate(timeout=3)
