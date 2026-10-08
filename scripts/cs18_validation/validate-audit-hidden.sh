#!/usr/bin/env bash
set -euo pipefail
DEV=/home/wmywb/CyberScientist
HIDDEN="${DEV}.hidden-audit-$(date +%s)"
restore() { code=$?; if [[ -d "$HIDDEN" ]]; then test ! -e "$DEV"; mv -- "$HIDDEN" "$DEV"; fi; exit "$code"; }
test -d "$DEV"
test ! -e "$HIDDEN"
trap restore EXIT
trap 'exit 130' INT TERM HUP
mv -- "$DEV" "$HIDDEN"
export PATH=/home/wmywb/.local/bin:$PATH
export HOME=/home/wmywb/CyberScientist-comp/.runtime/home
export CODEX_HOME=/home/wmywb/CyberScientist-comp/.runtime/codex
unset PYTHONPATH
cd /home/wmywb/CyberScientist-comp
.venv/bin/python .runtime/validate-audit.py
