import io
import json
import sys

import pytest

from cyberscientist import cli, config, redeploy, cli_submission, capabilities


def migrated(tmp_path, monkeypatch):
    dev = tmp_path / 'CyberScientist'; dev.mkdir()
    comp = tmp_path / 'CyberScientist-comp'; (comp / '.cyberscientist').mkdir(parents=True)
    (comp / '.cyberscientist/settings.json').write_text(json.dumps({'app': {'port': 9999}}))
    (config.DATA_DIR / 'runtime-migrated.json').write_text('{}')
    monkeypatch.setattr(config, 'WORKSPACE_ROOT', dev)
    return dev, comp


def test_migrated_ops_default_targets_competition_and_checks_identity(tmp_path, monkeypatch):
    dev, comp = migrated(tmp_path, monkeypatch); identities = []; requests = []
    monkeypatch.setattr(redeploy, 'request', lambda port, *a, **k: {'port': port})
    monkeypatch.setattr(redeploy, 'process_identity', lambda health, root: identities.append((health['port'], root)))
    def fetch(request, **kwargs):
        requests.append(request); return io.BytesIO(b'{"status":"ok"}')
    monkeypatch.setattr(cli.urllib.request, 'urlopen', fetch)
    monkeypatch.setattr(sys, 'argv', ['cyberscientist', 'ops', 'status'])
    cli.main()
    assert identities == [(9999, comp)]
    assert requests[0].full_url.startswith('http://127.0.0.1:9999/')


def test_explicit_dev_rejects_competition_pid_before_mutation(tmp_path, monkeypatch, capsys):
    dev, comp = migrated(tmp_path, monkeypatch)
    monkeypatch.setattr(redeploy, 'request', lambda *a, **k: {})
    def mismatch(health, root):
        assert root == dev
        raise RuntimeError('fixture wrong backend root')
    monkeypatch.setattr(redeploy, 'process_identity', mismatch)
    monkeypatch.setattr(cli.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('no mutating HTTP allowed'))
    monkeypatch.setattr(sys, 'argv', ['cyberscientist', 'ops', 'shutdown', '--target', 'dev'])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2 and '开发后端未运行或身份不匹配' in capsys.readouterr().err


def test_runtime_node_does_not_depend_on_home_or_callers_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'WORKSPACE_ROOT', tmp_path)
    node = tmp_path / '.runtime/bin/node'; node.parent.mkdir(parents=True); node.write_text('fixture')
    monkeypatch.setattr(cli_submission.shutil, 'which', lambda name: None)
    assert cli_submission.node_executable() == str(node)
    node.unlink()
    with pytest.raises(ValueError, match='Node'):
        cli_submission.node_executable()


def test_compute_capabilities_tell_pi_to_delegate():
    items = {x['id']: x for x in capabilities.index()}
    for name in ('research_job', 'research_sandbox', 'research_environment'):
        assert '执行者工具，PI 在简报中选择、由执行者使用' in items[name]['use']
