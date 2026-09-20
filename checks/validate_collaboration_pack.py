"""验证本施工包的静态文档与协议；不运行 CyberScientist 应用测试。"""
from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:
    raise SystemExit('缺少 jsonschema；在项目依赖环境中安装后重试。')

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'collaboration'


def main() -> int:
    schema = json.loads((DOCS / 'contract.schema.json').read_text(encoding='utf-8'))
    samples = json.loads((DOCS / 'examples.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    markdown = [ROOT / 'START_KIMI_SHADOW.md']
    markdown += sorted(DOCS.glob('*.md'))
    markdown += sorted((ROOT / 'prompts' / 'collaboration').glob('*.md'))
    errors: list[str] = []
    link_count = 0
    for path in markdown:
        text = path.read_text(encoding='utf-8')
        if '\ufffd' in text:
            errors.append(f'{path.name}: 含解码替换字符')
        fences = re.findall(r'^\s*```', text, re.MULTILINE)
        if len(fences) % 2:
            errors.append(f'{path.name}: 代码围栏未闭合')
        for href in re.findall(r'\[[^\]\n]+\]\(([^)\s]+)\)', text):
            parts = urlparse(href)
            if parts.scheme or not parts.path:
                continue
            target = (path.parent / unquote(parts.path)).resolve()
            link_count += 1
            if not target.is_relative_to(ROOT) or not target.is_file():
                errors.append(f'{path.name}: 无效本地链接 {href}')

    valid: list[str] = []
    by_name: dict[str, dict] = {}
    for item in samples['write_messages']:
        validator.validate(item['payload'])
        valid.append(item['name'])
        by_name[item['name']] = item['payload']

    invalid: dict[str, dict] = {}
    x = deepcopy(by_name['silent_review'])
    x['guidance'] = deepcopy(by_name['observe_intervention']['guidance'])
    invalid['silent_cannot_carry_guidance'] = x
    x = deepcopy(by_name['observe_intervention'])
    x['guidance'] = None
    invalid['intervention_requires_guidance'] = x
    x = deepcopy(by_name['progress_checkpoint'])
    x['run_id'] = 'forged-run'
    invalid['agent_cannot_select_run_identity'] = x
    x = deepcopy(by_name['silent_review'])
    x['watchlist'] = x['watchlist'] * 4
    invalid['watchlist_has_bound'] = x
    x = deepcopy(by_name['stop_intervention'])
    x['guidance']['kind'] = 'submit_competition'
    invalid['unknown_control_action_rejected'] = x
    x = deepcopy(by_name['guidance_ack'])
    x['disposition'] = 'applied_and_score_verified'
    invalid['ack_is_not_application_or_score'] = x

    rejected: list[str] = []
    for name, payload in invalid.items():
        try:
            validator.validate(payload)
            errors.append(f'反例未被拒绝: {name}')
        except ValidationError:
            rejected.append(name)

    report = {
        'scope': 'documentation_and_message_schema_only',
        'reference_commit': '27609e6afcc4f9987ec8459e87ff365b650d790c',
        'markdown_files_checked': len(markdown),
        'local_links_checked': link_count,
        'schema_valid': True,
        'valid_messages': valid,
        'invalid_messages_rejected': rejected,
        'application_tests_run': False,
        'real_model_calls_made': 0,
        'scientific_or_competition_results_verified': False,
        'errors': errors,
        'passed': not errors,
    }
    (DOCS / 'PACKAGE_CHECK.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
