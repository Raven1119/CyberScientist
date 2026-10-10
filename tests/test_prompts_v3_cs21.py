from cyberscientist import role_prompts
from cyberscientist.brains.codex import CodexBrain


def test_v3_scoring_and_numerical_targets_reach_pi():
    pi = role_prompts.role('pi')
    assert 'roles/pi v3' in pi
    for text in ('评分在查什么', '对应不上就不设', '第一版直接用，不做收敛扫描',
                 '查不出硬错误就照常提交', '不换成探索中试过的更贵设置',
                 '原文和文献里的结果只用于你自己核对合理性', '耗时的 2 倍'):
        assert text in pi
    assert '最终收敛参数' not in pi
    assert '精度目标以题面和 PI 的要求为准，不自己另设更严的目标' in role_prompts.role('executor')
    rendered = CodexBrain._render_prompt({'trigger': 'run_start', 'run_id': 'render-only',
        'challenge': {'content': 'Ca3Co2O6; cutoff >=100 Ry; k grid >=3x3x3; smearing <=0.02 Ry'},
        'sparse_brain_version': 1})
    assert '评分在查什么' in rendered
    assert 'Ca3Co2O6' in rendered
