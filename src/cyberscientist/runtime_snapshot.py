"""Export the published runtime, never its credentials or research state."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from . import observation, config, runtime_release


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact_settings(value, key=''):
    if isinstance(value, dict):
        return {k: redact_settings(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_settings(v, key) for v in value]
    if re.search(r'(token|password|secret|access.?key|api.?key|credential)', key, re.I):
        return value if key.endswith('secret_ref') else '[REDACTED]'
    return observation.strip_secrets(value) if isinstance(value, str) else value


def export(root: Path, target: Path) -> dict:
    import fcntl
    with (root / '.runtime/release.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        return _export(root, target)


def _export(root: Path, target: Path) -> dict:
    root = root.resolve(); target = target.resolve()
    if target == root or root in target.parents:
        raise ValueError('Export must be outside the competition tree')
    if target.exists() and any(target.iterdir()):
        raise ValueError('Export target must be empty')
    target.mkdir(parents=True, exist_ok=True)
    version = json.loads((root / '.runtime/version.json').read_text())
    manifest_path = root / '.runtime/releases' / version['commit'] / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest['files'].items():
        relative = Path(name)
        if not runtime_release.runtime_path(name):
            raise ValueError('Invalid manifest path')
        source = root / relative
        data = source.read_bytes()
        if any(p.is_symlink() for p in (source, *source.parents)) or digest(data) != expected:
            raise ValueError('Published bytes mismatch: ' + name)
        output = target / relative; output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data); output.chmod(source.stat().st_mode & 0o777)
    def write(name, data):
        path = target / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    write('.runtime/version.json', version)
    write('.runtime/releases/' + version['commit'] + '/manifest.json', manifest)
    settings = json.loads((root / '.cyberscientist/settings.json').read_text())
    write('snapshot/settings.json', redact_settings(settings))
    text = (root / '.runtime/codex/config.toml').read_text()
    text = re.sub(r'(?im)^(\s*(?:[\w.-]*(?:token|password|secret|access_key|api_key|credential)[\w.-]*)\s*=).*$', r'\1 "[REDACTED]"', text)
    path = target / 'snapshot/codex/config.toml'; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(observation.strip_secrets(text))
    skills = []
    for name in sorted(settings['skills']['always_on']):
        path = root / 'skills' / name / 'SKILL.md'
        if path.is_symlink() or not path.is_file():
            raise ValueError('Enabled skill missing: ' + name)
        skills.append({'name': name, 'path': str(path.relative_to(root)), 'skill_sha256': digest(path.read_bytes())})
    write('snapshot/active-skills.json', skills)
    tree = []
    for path in sorted(root.iterdir()):
        children = sorted(path.iterdir()) if path.is_dir() and not path.is_symlink() else []
        for item in [path, *children]:
            tree.append({'name': str(item.relative_to(root)), 'kind': 'directory' if item.is_dir() else 'file', 'size': item.lstat().st_size})
    write('snapshot/directory-tree.json', tree)
    inventory = {str(p.relative_to(target)): digest(p.read_bytes()) for p in sorted(target.rglob('*')) if p.is_file()}
    from datetime import datetime, timezone
    write('snapshot/export-manifest.json', {'development_commit': version['commit'],
        'exported_at': datetime.now(timezone.utc).isoformat(), 'files': inventory})
    return {'commit': version['commit'], 'runtime_files': len(manifest['files']), 'export_files': len(inventory) + 1, 'skills': len(skills)}


def scan(root: Path, *, known_values=()) -> dict:
    # Match credential-shaped values, not source code mentioning their prefixes.
    patterns = {
        'agent_token': re.compile(rb'asp_[0-9a-fA-F]{32,}'),
        'api_token': re.compile(rb'sk-[A-Za-z0-9_-]{20,}'),
        'bearer': re.compile(rb'Bearer[ \t]+[A-Za-z0-9_.-]{24,}', re.I),
        'access_key': re.compile(rb'(?:AccessKey|access_key)[ \t]*[=:][ \t]*(?:[\"\x27][A-Za-z0-9_/+-]{24,}[\"\x27]|[A-Za-z0-9_/+-]{24,}(?=[ \t]*(?:\r?\n|$)))', re.I),
        'base64': re.compile(rb'(?<![A-Za-z0-9+/])(?:eyJ[A-Za-z0-9_=-]{40,}|[A-Za-z0-9+/]{80,}={1,2})(?![A-Za-z0-9+/=])'),
        'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    }
    sensitive = [v.encode() for v in [*config.sensitive_values(), *known_values]
                 if isinstance(v, str) and len(v) > 7]
    hits = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '.git' in path.relative_to(root).parts:
            continue
        data = path.read_bytes(); name = str(path.relative_to(root))
        if any(v in data for v in sensitive):
            hits.append({'path': name, 'pattern': 'existing_known_secret'})
        for label, pattern in patterns.items():
            for match in pattern.finditer(data):
                hits.append({'path': name, 'pattern': label, 'line': data.count(b'\n', 0, match.start()) + 1})
    return {'files_scanned': sum(1 for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts), 'hit_count': len(hits), 'hits': hits}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = export(args.root, args.output)
    result['scan'] = scan(args.output)
    print(json.dumps(result, ensure_ascii=False))
    if result['scan']['hit_count']:
        raise SystemExit(1)


def push(root: Path) -> dict:
    """Update only the verified snapshot repository after a successful release."""
    import fcntl
    import subprocess
    import tempfile
    repository = root.parent / 'CyberScientist-comp-export'
    if not (repository / '.git').is_dir():
        raise ValueError('私有比赛快照仓库尚未初始化')
    gh = shutil.which('gh') or '/mnt/c/Program Files/GitHub CLI/gh.exe'
    if not Path(gh).is_file():
        raise ValueError('GitHub CLI不可用；发布已完成，快照尚未推送')
    def command(argv):
        result = subprocess.run(argv, cwd=repository, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError('快照命令失败：' + argv[0] + '，exit=' + str(result.returncode))
        return result.stdout.strip()
    with (repository / '.git/comp-snapshot.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        expected = 'https://github.com/Raven1119/CyberScientist-comp'
        if command(['git', 'remote', 'get-url', 'origin']).removesuffix('.git') != expected:
            raise ValueError('快照origin不是授权私库')
        profile = json.loads(command([gh, 'repo', 'view', 'Raven1119/CyberScientist-comp', '--json', 'isPrivate,url']))
        if profile.get('isPrivate') is not True or profile.get('url') != expected:
            raise ValueError('比赛快照私有性未确认，拒绝推送')
        if command(['git', 'status', '--porcelain']):
            raise ValueError('快照仓库有未提交变更，拒绝覆盖')
        tracked = set(command(['git', 'ls-files']).splitlines())
        prior = json.loads((repository / 'snapshot/export-manifest.json').read_text())
        if tracked != set(prior['files']) | {'snapshot/export-manifest.json'}:
            raise ValueError('快照仓库含清单外文件，拒绝覆盖')
        with tempfile.TemporaryDirectory(prefix='comp-snapshot-', dir=root.parent) as temporary:
            stage = Path(temporary) / 'export'
            result = export(root, stage)
            store = root / '.cyberscientist/secrets.json'
            known_values = json.loads(store.read_text()).values() if store.is_file() else ()
            scanned = scan(stage, known_values=known_values)
            if scanned['hit_count']:
                raise ValueError('快照扫描未通过，拒绝推送：' + json.dumps(scanned, ensure_ascii=False))
            files = {str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file()}
            for name in tracked - files:
                (repository / name).unlink()
            for name in files:
                destination = repository / name; destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(destination.name + '.snapshot-pending')
                shutil.copy2(stage / name, temporary)
                temporary.replace(destination)
            command(['git', 'add', '--', *sorted(tracked | files)])
            command(['git', 'diff', '--cached', '--check'])
            command(['git', 'commit', '-m', 'snapshot: publish competition runtime ' + result['commit'] + ' CS-UP-20'])
            helper = '!"' + gh + '" auth git-credential'
            git = ['git', '-c', 'credential.helper=', '-c', 'credential.helper=' + helper]
            command([*git, 'push', 'origin', 'main'])
            sha = command(['git', 'rev-parse', 'HEAD'])
            if command([*git, 'ls-remote', 'origin', 'refs/heads/main']).split()[0] != sha:
                raise RuntimeError('快照远端提交未核对')
            return {**result, 'scan': scanned, 'repository': expected, 'snapshot_commit': sha, 'private': True}
