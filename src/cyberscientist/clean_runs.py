"""A narrow method handoff for a newly created native executor thread."""
import json
import re
from . import config, observation, skills

FIELDS = ('method_md', 'parameters_md', 'validation_md', 'pitfalls_md')
PARAMETER_POLICY = '交接可以包含方法与计算设置（网格、步长、截断、收敛阈值、随机种子、超参数、镜像等）及其选择依据；不得包含探索得到的结果数值（最终答案、拟合系数、指标值、物理量等）。'

def validate(handoff):
    if not isinstance(handoff, dict) or set(handoff) != set(FIELDS):
        raise ValueError('干净复跑必须仅提供流程、参数、验证、故障四段')
    if any(not isinstance(handoff[k], str) or not handoff[k].strip() or len(handoff[k]) > 12000 for k in FIELDS):
        raise ValueError('干净复跑交接字段为空或过长')
    text = '\n'.join(handoff.values())
    if re.search(r'```|^\s*(?:import |from \w+ import|def \w+\(|class \w+[:(])', text, re.M):
        raise ValueError('干净复跑交接不得包含代码')
    if observation.strip_secrets(text) != text:
        raise ValueError('干净复跑交接不得包含凭据')
    return handoff


def prompt(challenge, handoff, enabled_skills, capability_index, *, run_id, trial_id,
           delivery_directory, environment_index):
    validate(handoff)
    return ('方法来自本方此前的探索。\n按方法真实重算，不读取此前探索代码或数值产物。'
            + PARAMETER_POLICY + '\n'
            f'Run ID：{run_id}；Trial ID：{trial_id}。\n'
            f'交付目录：{delivery_directory}；结果包名：result_package.zip。\n'
            '真实原生轨迹由系统绑定，禁止编造。\n'
            '固定完成判据：产出题面输出契约中的全部文件，写好结果包，用 research_checkpoint 报 stage=trial_complete。\n'
            '题面：\n' + json.dumps(challenge, ensure_ascii=False) + '\n'
            + '\n'.join(f'{label}（{key}）：{handoff[key]}' for key, label in zip(FIELDS, ('流程', '参数', '验证', '故障'))) + '\n'
            + skills.prompt_segment(enabled_skills) + '\n能力索引：\n' + capability_index
            + '\n环境索引（镜像与本题沙箱）：\n' + json.dumps(environment_index, ensure_ascii=False))


def offer(run_id):
    from . import db
    policy=config.load_settings().get('clean_run_policy','when_not_accepted')
    latest=db.query_one("SELECT id,harbor_score,trace_decision FROM submissions WHERE run_id=? AND harbor_score IS NOT NULL ORDER BY harbor_score DESC,created_at DESC,rowid DESC LIMIT 1",(run_id,))
    recommended = bool(latest and (policy=='always_after_science' or latest['trace_decision'] not in (None,'accept')))
    result = {'policy':policy,'recommended':recommended,
              'best_science':dict(latest) if latest else None,'decision_owner':'PI','automatic_execution':False}
    if recommended:
        result['handoff_fields'] = list(FIELDS)
        result['parameter_policy'] = PARAMETER_POLICY
    return result


def should_offer(run_id):
    return offer(run_id)['recommended']
