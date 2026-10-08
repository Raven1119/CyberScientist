"""Keep developer findings and design conflicts out of maintenance experience."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import re


INSTRUCTION = (
    '系统缺陷只写开发者队列，不放进经验。经验仅为科学策略或可照做的操作方法。'
    '每条教训必须做反事实分析：原来得了什么分，怎样做本可以得更高分；'
    '分别对照题面分档、已观察榜首和已知结果，缺失的比较如实写unknown。'
    'ABC必须核对是否放弃已知纪录这个保底，不能把科学分档等同通用ARM分。'
    '逐条对照design_decisions的D-24–D-61，后来的决定优先；'
    '冲突教训保留报告、列出conflicts，禁止进入候选。unknown绝不重发违反D-31，'
    '不确定就停违反D-28/D-33；但不得重复同一unknown操作。'
    '每条提议review必须注明classification、decision_sha256、conflicts、counterfactual_md、'
    'score_bands_md、leaderboard_md、known_results_md。模型对符合性的声明仍是待验证分析。'
)
INSTRUCTION = re.sub(r'\bD-(\d+)\b', r'policy-\1', INSTRUCTION)


def decisions() -> dict:
    path = Path(__file__).resolve().parents[2] / 'contracts' / 'experience-policy.txt'
    lines = [line for line in path.read_text(encoding='utf-8').splitlines()
             if (match := re.match(r'\| policy-(\d+) \|', line)) and 24 <= int(match[1]) <= 61]
    if len(lines) != 38:
        raise ValueError('复盘设计决定D-24–D-61不完整，不能生成经验候选')
    text = '\n'.join(lines)
    return {'source': 'contracts/experience-policy.txt', 'text': text,
            'sha256': hashlib.sha256(text.encode()).hexdigest()}


def proposals_schema(base: dict) -> dict:
    schema = copy.deepcopy(base)
    schema['items']['required'].append('review')
    schema['items']['properties']['review'] = {
        'type': 'object', 'additionalProperties': False,
        'required': ['classification', 'decision_sha256', 'conflicts', 'counterfactual_md',
                     'score_bands_md', 'leaderboard_md', 'known_results_md'],
        'properties': {
            'classification': {'enum': ['scientific_strategy', 'operation', 'developer_defect']},
            'decision_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
            'conflicts': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}},
            **{key: {'type': 'string', 'minLength': 1} for key in
               ('counterfactual_md', 'score_bands_md', 'leaderboard_md', 'known_results_md')}}}
    return schema


def split(proposals: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fail closed for absent analysis, while retaining every finding in reports."""
    current = decisions()['sha256']
    accepted, excluded = [], []
    for proposal in proposals:
        review = proposal.get('review', {})
        reasons = []
        if review.get('classification') not in ('scientific_strategy', 'operation'):
            reasons.append('系统缺陷或未分类：仅进开发者报告')
        if review.get('decision_sha256') != current:
            reasons.append('未核对现行D-24–D-61')
        if review.get('conflicts'):
            reasons.append('设计决定冲突：' + ', '.join(review['conflicts']))
        if any(not str(review.get(key, '')).strip() for key in
               ('counterfactual_md', 'score_bands_md', 'leaderboard_md', 'known_results_md')):
            reasons.append('缺少反事实得分、分档、榜首或已知结果比较')
        text = '\n'.join([proposal.get('title', ''), proposal.get('body_md', '')] +
                         [str(review.get(key, '')) for key in
                          ('counterfactual_md', 'score_bands_md', 'leaderboard_md', 'known_results_md')])
        # Reports may quote a rejected rule explicitly AS a conflict. Keep
        # those quotations in the report/body, but do not treat the marked
        # negative example as an instruction to the next agent.
        text = re.sub(r'(?:相反表述|被观察到的|冲突(?:规则|表述|教训))\s*[“「][^”」\n]+[”」]\s*'
                      r'(?:才是冲突版本|按\s*D-61\s*只作冲突报告)', '', text)
        if re.search(r'(?<!不能)(?<!不要)(?:把|将)原(?:预留|预约)标记|每次对账只保留一条结论', text):
            reasons.append('D-24/D-41：控制器账本或原始轨迹的修改只进开发者队列')
        # A prohibition on replaying the SAME operation is compatible with
        # D-31 only when the rule also explicitly permits a new operation
        # after ten minutes. Absolute/only-read rules remain excluded.
        for match in re.finditer(r'unknown[^。\n]{0,90}(?:绝不|永不|一律不|不能|不得|禁止)[^。\n]{0,12}(?:重发|重试|提交)', text, re.I):
            rule = text[match.start():].split('\n', 1)[0]
            same_target = re.match(r'\s*(?:原|同一)\s*(?:operation_id|操作(?:ID|id)?|op\b)', text[match.end():], re.I)
            bounded = (same_target and
                not re.search(r'unknown[^。\n]{0,90}(?:绝不|永不|一律不|只能)', rule, re.I) and
                re.search(r'10\s*分钟(?:后)?[^。\n]{0,30}(?<!不)(?<!不得)(?:可以|允许|可用)[^。\n]{0,30}新\s*(?:operation_id|操作|op\b)', rule, re.I))
            if not bounded:
                reasons.append('D-31：unknown不是永久禁止新操作')
                break
        if re.search(r'不确定就停|状态不明就停|unknown就停', text, re.I):
            reasons.append('D-28/D-33：应换已授权路径继续')
        if reasons:
            excluded.append({'proposal': proposal, 'reasons': reasons})
        else:
            clean = {key: value for key, value in proposal.items() if key != 'review'}
            clean['body_md'] += '\n\n反事实得分分析：\n' + review['counterfactual_md']
            clean['body_md'] += '\n分档：' + review['score_bands_md']
            clean['body_md'] += '\n榜首：' + review['leaderboard_md']
            clean['body_md'] += '\n已知结果：' + review['known_results_md']
            accepted.append(clean)
    return accepted, excluded
