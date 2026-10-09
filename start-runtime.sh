#!/usr/bin/env bash
set -euo pipefail
runtime_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$runtime_root"
test -f .runtime/version.json
test -f .runtime/codex/auth.json
test -f .runtime/codex/config.toml
export HOME="$runtime_root/.runtime/home"
export CODEX_HOME="$runtime_root/.runtime/codex"
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export PATH="$runtime_root/.runtime/bin:$PATH"
unset PYTHONPATH
exec .venv/bin/python .runtime/cyberscientist_launch.py serve "$@"
