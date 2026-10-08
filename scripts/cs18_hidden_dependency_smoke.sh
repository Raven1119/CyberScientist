#!/usr/bin/env bash
# One bounded acceptance pass. Preparation installs the private helpers in ROOT/.runtime.
# No scientific Run, Job, submission, registration, or resource replay is authorized here.
set -u -o pipefail
ROOT="${1:-/home/wmywb/CyberScientist-comp}"
DEV="${2:-/home/wmywb/CyberScientist}"
BASE="lightchaser-runtime-base-1009-v2"
AREA="$ROOT/.runtime/validation/hidden"
mkdir -p "$AREA"
if [[ -e "$AREA/started" ]]; then
  printf '%s\n' 'Acceptance pass already started; inspect receipts, do not replay.' >&2
  exit 2
fi
for helper in validate-native.py validate-tools.py validate-sandbox.py validate-identities.py validate-preview.py validate-audit.py validate-browser.py; do
  test -f "$ROOT/.runtime/$helper" || exit 2
done
export PATH="/home/wmywb/.local/bin:$PATH"
export HOME="$ROOT/.runtime/home" CODEX_HOME="$ROOT/.runtime/codex"
export XDG_CONFIG_HOME="$HOME/.config" XDG_DATA_HOME="$HOME/.local/share" XDG_CACHE_HOME="$HOME/.cache"
unset PYTHONPATH
cd "$ROOT" || exit 2
PY="$ROOT/.venv/bin/python"
CURRENT="$($PY -c 'import json;print(json.load(open(".runtime/version.json"))["commit"])')" || exit 2
HIDDEN="${DEV}.hidden-dependency-$(date +%s)"
RENAMED=0
restore() {
  rc=$?
  if [[ "$RENAMED" == 1 ]]; then
    if [[ -e "$DEV" ]]; then
      printf '%s\n' 'Cannot restore: original path unexpectedly exists; hidden tree preserved.' >&2
      exit 3
    fi
    mv -- "$HIDDEN" "$DEV" || exit 3
    RENAMED=0
    printf '%s\n' 'development_directory_restored' >> "$AREA/progress.log"
  fi
  exit "$rc"
}
trap restore EXIT
trap 'exit 130' INT TERM HUP
step() {
  name="$1"; shift
  printf '%s %s\n' "$(date -Iseconds)" "$name:start" >> "$AREA/progress.log"
  "$@" > "$AREA/$name.log" 2>&1
  code=$?
  printf '%s\t%s\n' "$name" "$code" >> "$AREA/exit-codes.tsv"
  printf '%s %s exit=%s\n' "$(date -Iseconds)" "$name:end" "$code" >> "$AREA/progress.log"
  return 0
}
"$PY" -c 'from cyberscientist.runtime_release import stop_runtime;from pathlib import Path;stop_runtime(Path.cwd(),8765,300)' > "$AREA/stop.log" 2>&1 || exit 2
test ! -e "$HIDDEN" || exit 2
date -Iseconds > "$AREA/started"
mv -- "$DEV" "$HIDDEN" || exit 2
RENAMED=1
printf '%s\n' 'development_directory_hidden' >> "$AREA/progress.log"
step start "$PY" .runtime/cyberscientist_launch.py ops redeploy --target comp --commit "$CURRENT" --timeout 300
step browser "$PY" .runtime/validate-browser.py
step native "$PY" .runtime/validate-native.py
step tools "$PY" .runtime/validate-tools.py
step preview "$PY" .runtime/validate-preview.py
step sandbox_and_job_preflight "$PY" .runtime/validate-sandbox.py
step identities_and_versions "$PY" .runtime/validate-identities.py
step redeploy "$PY" .runtime/cyberscientist_launch.py ops redeploy --target comp --commit "$CURRENT" --timeout 300
step rollback "$PY" .runtime/cyberscientist_launch.py ops release --target comp --commit "$BASE" --timeout 300
step restore_current "$PY" .runtime/cyberscientist_launch.py ops release --target comp --commit "$CURRENT" --timeout 300
step audit "$PY" .runtime/validate-audit.py
printf '%s\n' 'all_steps_attempted; consult structured evidence, exit 0 is not acceptance PASS' >> "$AREA/progress.log"
