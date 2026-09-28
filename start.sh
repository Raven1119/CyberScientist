#!/usr/bin/env bash
# Build the frontend, then run the Linux backend that serves it on one port.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"
export PATH="$HOME/.local/bin:$PATH"

if [[ ! -x .venv/bin/cyberscientist ]]; then
    echo "缺少项目 Linux Python 环境。请先在此目录执行：uv sync --locked" >&2
    exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "缺少 Linux Node/npm。请按 docs/BUILD.md 安装，不要使用 Windows 版本。" >&2
    exit 1
fi
if [[ ! -d apps/web/node_modules ]]; then
    echo "缺少前端依赖。请先执行：npm --prefix apps/web ci" >&2
    exit 1
fi

echo "正在构建前端…"
npm --prefix apps/web run build
echo "正在启动 CyberScientist；关闭此终端或按 Ctrl+C 可停止本地服务。"
exec .venv/bin/cyberscientist start "$@"
