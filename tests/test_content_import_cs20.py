"""Authorized runtime text and domain-neutral clean handoffs."""
import hashlib
from pathlib import Path

from cyberscientist import clean_runs, role_prompts


def test_authorized_skill_and_user_prompt_bytes():
    root=Path(__file__).resolve().parents[1]
    hashes={
        'skills/cyberscientist-submission-gate/SKILL.md':'d9b111ed8d72942dc74476c1ee9d16716444cd3171ce46cc73266e9172a60085',
        'skills/cyberscientist-trace-writing/SKILL.md':'2d6e59ead73f0344cbbd3b4869b914c7a7d7a87871b6702252c61853ad046ee6',
        'skills/cyberscientist-clean-rerun/SKILL.md':'286aad8844c669dbf3d969dc13a8acad4d4212d667f26bcaf421cd8bc2f967bc',
        'skills/cyberscientist-job-spec/SKILL.md':'c69faf8a23b5f27054886baeb6bfec65adde1b8500871020f99a7ad635770782',
        'skills/cyberscientist-sandbox/SKILL.md':'1d721ada77d6f15cc8045eccc7e57b70501c59d59e599e9878cf66967f623383',
        'templates/lightchaser-user-prompt.md':'4433fa198ed7a3a6600d892e2218d6932883af10fd42f306ebc91b4c22d12d89',
    }
    for name,sha in hashes.items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha


def test_clean_handoff_policy_is_consistent_across_native_providers():
    from cyberscientist.brains import codex, kimi
    policy='交接可以包含方法与计算设置（网格、步长、截断、收敛阈值、随机种子、超参数、镜像等）及其选择依据；不得包含探索得到的结果数值（最终答案、拟合系数、指标值、物理量等）。'
    assert clean_runs.PARAMETER_POLICY==policy
    for provider in (codex,kimi):
        assert policy in Path(provider.__file__).read_text()
    assert 'roles/pi v3' in role_prompts.role('pi')
    assert 'roles/executor v3' in role_prompts.role('executor')
