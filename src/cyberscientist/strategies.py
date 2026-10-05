"""One versioned, Run-owned strategy card per topic; plans are distinct from scores."""
from __future__ import annotations

import json

from . import config, db, experiences
from .observation import strip_secrets


def card_id(run_id: str) -> str:
    return 'strategy_' + run_id


def maintain(run_id: str, **kwargs) -> dict | None:
    """Knowledge bookkeeping must not prevent a valid research action."""
    try:
        return update(run_id, **kwargs)
    except (experiences.ExperienceError, OSError, ValueError, TypeError) as exc:
        db.append_event(run_id, 'controller', 'strategy.update_unknown',
                        {'reason': getattr(exc, 'code', type(exc).__name__)})
        return None


@config.serialized_mutation
def update(run_id: str, *, brief: dict | None = None, event: dict | None = None) -> dict | None:
    from . import features
    if not features.enabled('strategy_cards'): return None
    run = db.query_one('SELECT * FROM runs WHERE id=?', (run_id,))
    if not run:
        return None
    try:
        prior = experiences.get_experience(card_id(run_id))
    except experiences.ExperienceError as exc:
        if exc.code != 'NOT_FOUND':
            raise
        prior = None
    if prior and (prior['frontmatter'].get('challenge_id') != run['challenge_id'] or
                  prior['frontmatter'].get('owner_run_id') != run_id):
        raise experiences.ExperienceError('REVISION_CONFLICT', '策略卡归属已改变，保留现场')
    if brief is None and prior is None:
        return None
    plan = prior['frontmatter'].get('plan', {}) if prior else {}
    import jsonschema
    from . import decision
    try:
        jsonschema.validate(plan, decision.load_schema()['properties']['research_brief'])
    except jsonschema.ValidationError as exc:
        raise experiences.ExperienceError('INVALID_EXPERIENCE', '策略卡计划字段损坏，保留原修订') from exc
    plan = dict(plan)
    if brief:
        plan.update(json.loads(strip_secrets(json.dumps(brief, ensure_ascii=False))))
    score = db.query_one("SELECT id,science_score,score_source FROM local_scores WHERE run_id=?"
                         " AND score_source IN ('system','executor_verified') AND science_score IS NOT NULL"
                         ' ORDER BY science_score DESC,created_at DESC LIMIT 1', (run_id,))
    evidence = list(prior['frontmatter'].get('evidence_refs', [])) if prior else []
    if event:
        evidence.append(f"event:{run_id}:{event['seq']}")
    if score:
        evidence.append('local_score:' + score['id'])
    body = ('先照做：\n\n' + plan.get('advice_md', plan.get('acceptance_md', '按本卡路线做最小验证，再比较真实分数。')) +
            '\n\n选择的路线与理由（PI 计划）：\n' + plan.get('route_md', '') + '\n' +
            json.dumps(plan.get('ranked_methods', []), ensure_ascii=False, indent=2) +
            '\n\n与已有路线的区别：\n' + plan.get('difference_md', '尚未说明；后续 PI 先比较已有策略。') +
            '\n\n当前本 Run 最佳正式验证分：\n' +
            (f"{score['science_score']}，来源 {score['score_source']}，local_score:{score['id']}" if score else 'unknown；尚无正式本地评分') +
            '\n\nPI 判定走不通的路线及证据（判断保留其不确定性）：\n' +
            json.dumps(plan.get('failed_routes', []), ensure_ascii=False, indent=2) +
            '\n\n关键科学与验收：\n' + plan.get('science_md', '') + '\n' + plan.get('acceptance_md', '') +
            '\n\n证据引用：\n' + '\n'.join(sorted(set(evidence))) + '\n')
    body = strip_secrets(body)
    if prior and prior['body_md'].strip() == body.strip() and prior['frontmatter'].get('plan') == plan:
        return {'id': card_id(run_id), 'revision_id': prior['revision_id'], 'unchanged': True}
    fm = {'id': card_id(run_id), 'title': '策略卡：' + run_id, 'scope': 'challenge',
          'challenge_id': run['challenge_id'], 'status': 'active', 'kind': 'strategy',
          'evidence_status': 'hypothesis', 'audience': 'both', 'tags': ['strategy'],
          'owner_run_id': run_id, 'plan': plan, 'evidence_refs': sorted(set(evidence)),
          'applicability': '本题后续 Run 开局交接；计划不等于已验证科学结论'}
    saved = experiences.save_experience(card_id(run_id), fm, body, 'brain_strategy',
                                       'PI 路线与真实评分里程碑', prior['current_hash'] if prior else None)
    db.append_event(run_id, 'controller', 'strategy.updated', {
        'experience_id': card_id(run_id), 'revision_id': saved['revision_id'],
        'best_local_score_id': score['id'] if score else None})
    return saved


def ensure_trial_plan(run_id: str, goal: str, success_check: str, event: dict) -> None:
    try:
        experiences.get_experience(card_id(run_id))
    except (experiences.ExperienceError, OSError, ValueError, TypeError) as exc:
        if getattr(exc, 'code', None) != 'NOT_FOUND':
            db.append_event(run_id, 'controller', 'strategy.update_unknown',
                            {'reason': getattr(exc, 'code', type(exc).__name__)})
            return
        maintain(run_id, brief={'route_md': goal, 'acceptance_md': success_check}, event=event)
