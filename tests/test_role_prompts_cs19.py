from pathlib import Path

import pytest

from cyberscientist import config, role_prompts
from cyberscientist.api import create_app
from cyberscientist.brains import kimi
from cyberscientist.codex_protocol import thread_params
from cyberscientist.controller import RunController, executor_instruction_suffix
from test_mailboxes import _seed_challenge, _make_run


@pytest.mark.parametrize('name', ['pi', 'executor'])
@pytest.mark.parametrize('empty', [False, True])
def test_missing_or_empty_role_prevents_startup_and_new_run(tmp_path, monkeypatch, name, empty):
    root = tmp_path / 'prompts'; (root / 'roles').mkdir(parents=True)
    for role in ('pi', 'executor'):
        (root / 'roles' / (role + '.md')).write_text('role')
    path = root / 'roles' / (name + '.md')
    if empty:
        path.write_text(' \n')
    else:
        path.unlink()
    monkeypatch.setattr(role_prompts, 'PROMPT_ROOT', root)
    with pytest.raises(RuntimeError):
        create_app()
    with pytest.raises(RuntimeError):
        RunController().create_run('unused')


def test_new_and_resumed_specs_keep_roles_as_developer_instructions(tmp_path):
    _seed_challenge(); rid = _make_run(); controller = RunController()
    settings = config.load_settings(); settings['executor']['runtime'] = 'codex'
    for role, spec, writable in (
        ('pi', controller._brain_spec(rid, settings, tmp_path / 'brain'), False),
        ('executor', controller._prime_spec(rid, settings), True),
    ):
        for resumed in (False, True):
            if resumed:
                spec['resume_thread_id'] = 'old-native-thread'
            params = thread_params(spec, 'fixture-model', 'xhigh', writable=writable)
            assert 'roles/' + role + ' v3' in params['developerInstructions']


def test_legacy_prompt_read_failures_are_not_silenced(tmp_path, monkeypatch):
    monkeypatch.setattr(kimi, '_BRAIN_PROMPT_PATH', tmp_path / 'missing.md')
    with pytest.raises(RuntimeError):
        kimi._brain_instruction()
    assert executor_instruction_suffix().strip()


def test_competition_rejects_engines_without_confirmed_native_role_injection(monkeypatch):
    from cyberscientist import runtime_layout
    settings = config.load_settings()
    settings['brain']['runtime'] = settings['executor']['runtime'] = 'codex'
    monkeypatch.setattr(runtime_layout, 'version', lambda: {'commit': 'fixture'})
    role_prompts.validate_runtime(settings)
    for role in ('brain', 'executor'):
        original = settings[role]['runtime']
        settings[role]['runtime'] = 'kimi'
        with pytest.raises(ValueError, match='仅验证Codex'):
            role_prompts.validate_runtime(settings)
        settings[role]['runtime'] = original


def test_role_bodies_match_authorized_appendices():
    import hashlib
    expected = {'pi': '0051df58a4da17ce12a8dd01f994d00aa1fc847c87b5c7e09d8d83092054e718', 'executor': 'fee759c8c83c1e37532fcf04a9b7fab36967e6d053013ab991eab856d3379354'}
    for name, sha in expected.items():
        assert hashlib.sha256(role_prompts.role(name).encode()).hexdigest() == sha
