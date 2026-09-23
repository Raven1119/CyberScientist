import subprocess
import sys

import pytest

from cyberscientist import config


@pytest.mark.skipif(sys.platform == 'win32', reason='Linux native flock regression')
def test_second_controller_preserves_live_owner_pid(tmp_path, monkeypatch):
    lock_path = tmp_path / 'controller.lock'
    monkeypatch.setattr(config, 'LOCK_PATH', lock_path)
    code = '''import fcntl,sys
with open(sys.argv[1], 'w') as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    f.write('live-owner-pid')
    f.flush()
    print('ready', flush=True)
    sys.stdin.read()
'''
    proc = subprocess.Popen([sys.executable, '-c', code, str(lock_path)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == 'ready'
        with pytest.raises(RuntimeError, match='另一个 CyberScientist'):
            config.acquire_workspace_lock()
        assert lock_path.read_text() == 'live-owner-pid'
    finally:
        proc.communicate(timeout=5)
