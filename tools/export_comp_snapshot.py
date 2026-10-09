"""Export the published runtime, never its credentials or research state."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cyberscientist import observation, config, runtime_release


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
        if any(p.is_symlink() for p in (source, *source.parents)) or digest(source.read_bytes()) != expected:
            raise ValueError('Published bytes mismatch: ' + name)
        output = target / relative; output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output); output.chmod(source.stat().st_mode & 0o777)
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
    write('snapshot/export-manifest.json', {'development_commit': version['commit'], 'files': inventory})
    return {'commit': version['commit'], 'runtime_files': len(manifest['files']), 'export_files': len(inventory) + 1, 'skills': len(skills)}


def scan(root: Path) -> dict:
    # Match credential-shaped values, not source code mentioning their prefixes.
    patterns = {
        'agent_token': re.compile(rb'asp_[0-9a-fA-F]{32,}'),
        'api_token': re.compile(rb'sk-[A-Za-z0-9_-]{20,}'),
        'bearer': re.compile(rb'Bearer[ \t]+[A-Za-z0-9_.-]{24,}', re.I),
        'access_key': re.compile(rb'(?:AccessKey|access_key)[ \t]*[=:][ \t]*(?:[\"\x27][A-Za-z0-9_/+-]{24,}[\"\x27]|[A-Za-z0-9_/+-]{24,}(?=[ \t]*(?:\r?\n|$)))', re.I),
        'base64': re.compile(rb'(?<![A-Za-z0-9+/])(?:eyJ[A-Za-z0-9_=-]{40,}|[A-Za-z0-9+/]{80,}={1,2})(?![A-Za-z0-9+/=])'),
        'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    }
    sensitive = [v.encode() for v in config.sensitive_values() if len(v) > 7]
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = export(args.root, args.output)
    result['scan'] = scan(args.output)
    print(json.dumps(result, ensure_ascii=False))
    if result['scan']['hit_count']:
        raise SystemExit(1)
