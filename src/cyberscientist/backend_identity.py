"""The deployed backend identity is captured once, independent of later Git HEAD."""
import hashlib
import json
from pathlib import Path

from . import config

_loaded = None


def _commit(root):
    """Read the checked-out ref without launching an unrelated CLI at startup."""
    from . import runtime_layout
    deployed=runtime_layout.version(root)
    if deployed is not None:return deployed['commit']
    gitdir = root / '.git'
    try:
        if gitdir.is_file():
            pointer = gitdir.read_text().strip()
            if not pointer.startswith('gitdir: '):
                return None
            gitdir = (root / pointer[8:]).resolve()
        head = (gitdir / 'HEAD').read_text().strip()
        if not head.startswith('ref: '):
            return head if len(head) == 40 and all(c in '0123456789abcdef' for c in head) else None
        ref = head[5:]
        if not ref.startswith('refs/') or '..' in Path(ref).parts:
            return None
        common = (gitdir / (gitdir / 'commondir').read_text().strip()).resolve() if (gitdir / 'commondir').exists() else gitdir
        if (common / ref).is_file():
            candidate = (common / ref).read_text().strip()
        else:
            candidate = next((line.split()[0] for line in (common / 'packed-refs').read_text().splitlines()
                              if not line.startswith(('#', '^')) and line.endswith(' ' + ref)), '')
        return candidate if len(candidate) == 40 and all(c in '0123456789abcdef' for c in candidate) else None
    except OSError:
        return None


def capture():
    root = config.WORKSPACE_ROOT
    files = {}
    for directory in ('src/cyberscientist', 'environments', 'challenges'):
        for path in sorted((root / directory).rglob('*')):
            if (not path.is_file() or path.is_symlink() or '__pycache__' in path.parts
                    or path.suffix in ('.pyc', '.pyo')):
                continue
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    commit = _commit(root)
    return {'commit': commit, 'runtime_sha256': hashlib.sha256(json.dumps(
        files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


def loaded():
    return dict(_loaded) if _loaded is not None else capture()


def record_startup():
    global _loaded
    _loaded = capture()


def matches(expected):
    return expected == loaded() and expected.get('runtime_sha256') == capture()['runtime_sha256']
