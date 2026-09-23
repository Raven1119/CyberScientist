#!/usr/bin/env python3
"""Offline integrity and structure checks. Python 3.9+, no third-party dependencies."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parent

def verify(root=ROOT):
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    problems = []
    for name, expected in manifest['files'].items():
        p = root / name
        if not p.is_file():
            problems.append('Missing: ' + name)
        elif hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            problems.append('Changed: ' + name)
    html = (root / 'assets/reference.html').read_text(encoding='utf-8')
    sha = hashlib.sha256((root / 'assets/reference.html').read_bytes()).hexdigest()
    tokens = json.loads((root / 'assets/tokens.json').read_text(encoding='utf-8'))
    motions = json.loads((root / 'assets/motion-map.json').read_text(encoding='utf-8'))
    if len(motions['items']) != 15 or len({x['id'] for x in motions['items']}) != 15:
        problems.append('Motion registry must contain 15 unique selected sources.')
    for data in [manifest, tokens, motions]:
        if data.get('reference_sha256') != sha:
            problems.append('Reference SHA mismatch.')
    style = (root / 'assets/tokens.css').read_text(encoding='utf-8')
    for theme, values in tokens['colors'].items():
        pattern = r':root, \[data-theme="paper"\] \{([^}]+)\}' if theme == 'paper' else r'\[data-theme="night"\] \{([^}]+)\}'
        block = re.search(pattern, style, re.S)
        if not block:
            problems.append('Missing theme: ' + theme)
            continue
        for key, value in values.items():
            if f'--ril-{key}: {value};' not in block.group(1):
                problems.append('CSS/JSON mismatch: ' + theme + '.' + key)
    for item in motions['items']:
        if item['reference']['anchor'] not in html:
            problems.append('Missing anchor: ' + item['id'])
    if not (root / 'SKILL.md').read_text(encoding='utf-8').startswith('---\nname: research-interface-language\n'):
        problems.append('Skill frontmatter invalid.')
    fonts = [p for p in root.rglob('*') if p.suffix.lower() in {'.ttf', '.otf', '.woff', '.woff2', '.ttc'}]
    if fonts:
        problems.append('Font files must not be included.')
    return problems, len(manifest['files'])

if __name__ == '__main__':
    try:
        issues, count = verify()
    except (OSError, ValueError, KeyError) as exc:
        print('FAIL:', str(exc))
        raise SystemExit(1)
    if issues:
        print('\n'.join('FAIL: ' + x for x in issues))
        raise SystemExit(1)
    print(f'PASS: {count} files; exact V9 reference; 15 motion locators; matching theme tokens; no font assets.')
