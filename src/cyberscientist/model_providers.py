"""Public native provider configuration; authentication exists only in env."""
from __future__ import annotations
import json
import os
import uuid
from . import config


def prepare(provider: str | None, environment: dict | None) -> dict | None:
    if provider in (None, 'codex'):
        return environment
    if provider != 'deepseek':
        raise ValueError('未知 Codex 提供方')
    key = config.deepseek_key()
    if not key:
        raise ValueError('缺少 DEEPSEEK_API_KEY（环境变量或根目录 .env）')
    home = config.DATA_DIR / 'codex-deepseek'
    home.mkdir(parents=True, exist_ok=True)
    catalog = home / 'models.json'
    model = {
        'slug': 'deepseek-flash', 'display_name': 'DeepSeek Flash',
        'description': 'Native responses provider', 'visibility': 'list',
        'priority': 1, 'supported_in_api': True, 'minimal_client_version': '0.144.0',
        'base_instructions': 'Follow the task instructions. Use tools and report observed evidence accurately.',
        'default_reasoning_level': 'high',
        'supported_reasoning_levels': [{'effort': e, 'description': e} for e in ('low', 'high', 'max')],
        'shell_type': 'shell_command', 'context_window': 1048576,
        'max_context_window': 1048576, 'effective_context_window_percent': 95,
        'supports_parallel_tool_calls': True, 'supports_reasoning_summaries': True,
        'default_reasoning_summary': 'none', 'reasoning_summary_format': 'experimental',
        'support_verbosity': True, 'default_verbosity': 'low', 'prefer_websockets': False,
        'apply_patch_tool_type': 'freeform', 'web_search_tool_type': 'text',
        'input_modalities': ['text', 'image'], 'supports_image_detail_original': True,
        'truncation_policy': {'mode': 'tokens', 'limit': 10000},
        'experimental_supported_tools': [], 'supports_search_tool': True,
    }
    _write_public(catalog, json.dumps({'models': [model]}))
    public = ('model_provider = "deepseek"\nmodel = "deepseek-flash"\n'
              'model_reasoning_effort = "high"\n'
              f'model_catalog_json = {json.dumps(str(catalog))}\n'
              '[model_providers.deepseek]\nname = "DeepSeek"\n'
              'base_url = "https://api.deepseek.com/"\nwire_api = "responses"\n'
              'env_key = "DEEPSEEK_API_KEY"\nrequires_openai_auth = false\n'
              'supports_websockets = false\n')
    _write_public(home / 'config.toml', public)
    env = dict(environment if environment is not None else os.environ)
    for name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_ACCESS_TOKEN'):
        env.pop(name, None)
    env.update(CODEX_HOME=str(home), DEEPSEEK_API_KEY=key)
    return env


def thread_provider(params: dict, provider: str | None) -> None:
    if provider == 'deepseek':
        params['modelProvider'] = 'deepseek'


def verify_provider(result: dict, provider: str | None) -> None:
    if provider == 'deepseek' and result.get('modelProvider') != 'deepseek':
        raise ValueError('原生会话未确认 DeepSeek 提供方，拒绝静默切换')


def record_throttle(choice: dict, error) -> None:
    from datetime import datetime, timezone
    from . import model_limits, resource_coordinator
    info = model_limits.classify(error)
    if info:
        resource_coordinator.throttle(resource_coordinator.provider(choice),
            model_limits.retry_at(datetime.now(timezone.utc), model_limits.retry_delay(1, info)))


def _write_public(path, text: str) -> None:
    with config.mutation_lock:
        if path.exists() and path.read_text(encoding='utf-8') == text:
            return
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(text, encoding='utf-8')
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
