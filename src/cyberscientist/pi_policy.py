"""D-51 fixed scientific PI; auxiliary reviewers remain independently configured."""
PI = {'runtime': 'codex', 'provider': 'codex', 'model_id': 'gpt-6-astra', 'reasoning_effort': 'xhigh'}


def validate(choice: dict) -> None:
    if any(choice.get(key, choice.get('runtime') if key == 'provider' else None) != value for key, value in PI.items()):
        raise ValueError('PI只能使用原生Codex的gpt-6-astra，思考强度xhigh')


def migrated(choice: dict) -> dict:
    result = dict(choice)
    if choice.get('runtime') != 'codex':
        result['executable'] = ''
    result.update(PI)
    result.update(auth_mode='native', custom_profile_id=None)
    return result
