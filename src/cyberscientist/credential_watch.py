"""Watch recorded credential-read attempts; never open credentials or edit logs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import re

from . import config, db, runtime_layout

_READ = re.compile(r'(?:\b|_)(?:cat|head|tail|sed|grep|awk|jq|source|open|read_text|read_bytes|readFile(?:Sync)?|read_file|load_dotenv)\b', re.I)
_FILES = ('.codex/auth.json', '.playground/config.json', '.config/playground/credentials.env')
_DIRECTORIES = ('.config/playground', '.bohr', '.bohrium', '.config/bohr', '.config/bohrium')


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():yield from _strings(child)
    elif isinstance(value, list):
        for child in value:yield from _strings(child)


def referenced_paths(item: dict, *, cwd: str | None = None,
                     home: str | None = None, codex_home: str | None = None) -> list[str]:
    """Inspect native tool INPUTS, including code-mode calls, before output arrives.

    This is an alert for explicit paths, not an OS access monitor or isolation.
    Outputs, assistant text and opaque indirect/constructed paths are not read.
    """
    kind = item.get('type')
    if kind not in ('commandExecution', 'mcpToolCall', 'dynamicToolCall'):
        return []
    inputs = {key: item[key] for key in ('command', 'commandActions', 'arguments') if key in item}
    text = '\n'.join(_strings(inputs))
    tool = str(item.get('tool') or '')
    read_action = any(action.get('type') == 'read' for action in item.get('commandActions', []) if isinstance(action, dict))
    if not (_READ.search(text) or 'read' in tool.lower() or read_action):
        return []
    global_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    competition = runtime_layout.competition_root()
    active_home = Path(home or os.environ.get('HOME') or global_home)
    homes = {global_home, competition / '.runtime/home', active_home}
    paths = {competition / '.cyberscientist/secrets.json': False, competition / '.env': False,
             competition / '.runtime/codex/auth.json': False,
             config.WORKSPACE_ROOT / '.cyberscientist/secrets.json': False,
             config.WORKSPACE_ROOT / '.env': False}
    for base in homes:
        paths.update({base / rel: False for rel in _FILES})
        paths.update({base / rel: True for rel in _DIRECTORIES})
    if codex_home:
        paths[Path(codex_home) / 'auth.json'] = False
    arguments = item.get('arguments')
    if isinstance(arguments, str):
        try:arguments = json.loads(arguments)
        except ValueError:arguments = {}
    arguments = arguments if isinstance(arguments, dict) else {}
    current = Path(item.get('cwd') or arguments.get('workdir') or arguments.get('cwd')
        or cwd or config.WORKSPACE_ROOT).resolve()
    directories = {current}
    # Code-mode embeds tool arguments inside JavaScript, not a direct JSON call.
    for match in re.finditer(r'\b(?:workdir|cwd)\s*:\s*[\"\x27]([^\"\x27\r\n]+)[\"\x27]', text):
        path = Path(match.group(1))
        directories.add((path if path.is_absolute() else current / path).resolve())
    for match in re.finditer(r'(?:^|[;\n&|])\s*(?:cd|pushd)\s+(?:"([^"]+)"|\x27([^\x27]+)\x27|([^\s;&|]+))', text):
        path = Path(next(value for value in match.groups() if value is not None))
        directories.add((path if path.is_absolute() else current / path).resolve())
    found = set()
    for path, directory in paths.items():
        spellings = {str(path)}
        if path.is_relative_to(active_home):
            relative = str(path.relative_to(active_home))
            spellings.update(('~/' + relative, '$HOME/' + relative, '${HOME}/' + relative))
        if codex_home and path == Path(codex_home) / 'auth.json':
            spellings.update(('$CODEX_HOME/auth.json', '${CODEX_HOME}/auth.json'))
        # Include lexical ../ paths, without touching file contents.
        for directory_base in directories:
            relative = os.path.relpath(path, directory_base)
            spellings.update((relative, './' + relative))
        end = r'(?![\w.-])' if directory else r'(?![\w./-])'
        if any(re.search(r'(?<![\w/.-])' + re.escape(value) + end, text) for value in spellings):
            found.add(str(path))
    return sorted(found)


def record(run_id: str, trial_id: str | None, payload: dict) -> None:
    safe = {key: payload.get(key) for key in ('paths', 'session_id', 'item_id', 'turn_id')}
    if not safe['paths']:
        return
    safe['notice'] = '执行者工具调用可能读取凭据；请核对原生记录并改用干净 Trial。此告警不确认读取成功，不修改会话。'
    with db.transaction() as conn:
        previous = conn.execute("SELECT 1 FROM events WHERE run_id=? AND type='credentials_touched'"
            " AND json_extract(payload,'$.session_id') IS ? AND json_extract(payload,'$.item_id') IS ?",
            (run_id, safe['session_id'], safe['item_id'])).fetchone()
        if not previous:
            db.append_event_tx(conn, run_id, 'controller', 'credentials_touched', safe, trial_id=trial_id)
