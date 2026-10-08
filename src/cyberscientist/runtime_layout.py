"""Competition paths are determined by the deployed tree, never global settings."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config


def version(root: Path | None = None) -> dict | None:
    path=(root or config.WORKSPACE_ROOT)/'.runtime/version.json'
    if not path.is_file():return None
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or not re.fullmatch('[a-f0-9]{40}',str(data.get('commit',''))):
        raise ValueError('比赛版本文件缺少有效commit SHA')
    return data


def competition_root() -> Path:
    return config.WORKSPACE_ROOT.parent/'CyberScientist-comp'


def native_environment(values: dict[str,str]) -> dict[str,str]:
    if version() is None:return values
    root=config.WORKSPACE_ROOT.resolve()
    home=root/'.runtime/home';codex=root/'.runtime/codex'
    if not (codex/'config.toml').is_file() or not (codex/'auth.json').is_file():
        raise ValueError('比赛原生配置/复制的登录凭据尚未准备，拒绝回退全局HOME')
    result=dict(values)
    result.update(HOME=str(home),CODEX_HOME=str(codex),
                  XDG_CONFIG_HOME=str(home/'.config'),XDG_DATA_HOME=str(home/'.local/share'),
                  XDG_CACHE_HOME=str(home/'.cache'))
    return result


def skill_roots(defaults):
    return (config.WORKSPACE_ROOT/'skills',) if version() is not None else defaults


def run_directory(run_id: str) -> Path:
    """Historical files live outside the directory used by new native sessions."""
    base=config.WORKSPACE_DIR/'runs'
    archive=config.WORKSPACE_ROOT/'.runtime/run-archive.json'
    if version() is not None and archive.is_file():
        record=json.loads(archive.read_text())
        if run_id in record['run_ids']:
            base=Path(record['root'])
    if not re.fullmatch(r'run_[A-Za-z0-9_-]+',run_id):raise ValueError('无效Run标识')
    return base/run_id


def archived_run(run_id: str) -> bool:
    return version() is not None and run_directory(run_id).parent != config.WORKSPACE_DIR/'runs'
