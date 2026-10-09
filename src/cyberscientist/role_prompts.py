"""Required runtime prompt files; missing guidance is a startup error."""
from pathlib import Path

PROMPT_ROOT = Path(__file__).resolve().parents[2] / 'prompts'


def read(path: Path) -> str:
    try:
        text = path.read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError('无法读取运行时提示词：' + str(path)) from exc
    if not text:
        raise RuntimeError('运行时提示词为空：' + str(path))
    return text


def role(name: str) -> str:
    if name not in ('pi', 'executor'):
        raise ValueError('未知运行时角色')
    return read(PROMPT_ROOT / 'roles' / (name + '.md'))


def validate_roles() -> None:
    for name in ('pi', 'executor'):
        role(name)


def validate_runtime(settings: dict) -> None:
    from . import runtime_layout
    if runtime_layout.version() is None:
        return
    for name in ('brain', 'executor'):
        if settings[name].get('runtime') != 'codex':
            raise ValueError('比赛角色开发者指令目前仅验证Codex原生协议；' + name + '需选择Codex')
