"""A narrow method handoff for a newly created native executor thread."""
import json
import re
from . import config, observation, skills

FIELDS = ('method_md', 'parameters_md', 'pitfalls_md')

def validate(handoff):
    if not isinstance(handoff, dict) or set(handoff) != set(FIELDS):
        raise ValueError('干净复跑必须仅提供方法、参数和坑')
    if any(not isinstance(handoff[k], str) or not handoff[k].strip() or len(handoff[k]) > 12000 for k in FIELDS):
        raise ValueError('干净复跑交接字段为空或过长')
    text = '\n'.join(handoff.values())
    if re.search(r'```|^\s*(?:import |from \w+ import|def \w+\(|class \w+[:(])', text, re.M):
        raise ValueError('干净复跑交接不得包含代码')
    if observation.strip_secrets(text) != text:
        raise ValueError('干净复跑交接不得包含凭据')
    return handoff


def prompt(challenge, handoff, enabled_skills, capability_index):
    validate(handoff)
    return ('方法来自本方此前的探索。\n按方法真实重算，不读取此前探索代码或数值产物。'
            '方法说明中的数值只能是题面要求或确定的输入参数，不能是探索结果。\n'
            '题面：\n' + json.dumps(challenge, ensure_ascii=False) + '\n'
            + '\n'.join(f'{key}：{handoff[key]}' for key in FIELDS) + '\n'
            + skills.prompt_segment(enabled_skills) + '\n能力索引：\n' + capability_index)


def should_offer(run_id):
    from . import db
    latest = db.query_one("SELECT harbor_score,trace_decision FROM submissions WHERE run_id=? AND harbor_score IS NOT NULL ORDER BY harbor_score DESC,created_at DESC LIMIT 1", (run_id,))
    return bool(latest and (config.load_settings().get('clean_run_policy','when_not_accepted') == 'always_after_science' or latest['trace_decision'] not in (None,'accept')))
