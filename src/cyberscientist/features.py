"""Live operational switches gate new work and preserve accepted work/history."""
from . import config

NAMES = ('auto_harvest', 'reviewer', 'scorer_audit', 'strategy_cards', 'deepseek_fallback',
         'protocol_drift', 'await_score', 'shared_area', 'environment_catalog', 'system_triage', 'local_calculation')


def validate(values):
    if not isinstance(values, dict) or set(values) - set(NAMES) or any(type(v) is not bool for v in values.values()):
        raise ValueError('功能开关只接受已知名称与布尔值')
    return values


def enabled(name):
    if name not in NAMES: raise ValueError('未知功能开关：' + name)
    return config.load_settings().get('features', {}).get(name, True)


@config.serialized_mutation
def switch(name, enabled_value, expected_revision=None):
    validate({name: enabled_value})
    settings = config.load_settings()
    if expected_revision is not None and expected_revision != settings['revision']:
        raise ValueError('配置版本冲突，请重新读取')
    settings['features'][name] = enabled_value
    settings['revision'] += 1
    config.save_settings(settings)
    return {'name': name, 'enabled': enabled_value, 'revision': settings['revision'], 'features': settings['features']}


def science_instruction():
    return ('秒级小计算允许本地执行；执行器的命令、输出、耗时与local来源必须留在真实轨迹中，PI委派并审阅证据；重计算使用已授权Bohrium Job 或沙箱，批量分析和科学作图也走该通道。\n'
            if enabled('local_calculation') else
            '本地计算功能已关闭；新的科学计算、统计分析和科学作图必须使用已授权Bohrium Job 或沙箱，PI只读审阅证据。\n')


def render_science_policy(text):
    if enabled('local_calculation'): return text
    import re
    return re.sub(r'按D-49，[^\n]*?(?=计费Job核对|$)', science_instruction().strip() + ' ', text, flags=re.MULTILINE)
