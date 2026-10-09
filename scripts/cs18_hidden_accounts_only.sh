#!/usr/bin/env bash
# Read-only account acceptance; no native turns, jobs, sandboxes or submissions.
set -euo pipefail
umask 077
runtime_root="${1:-/home/wmywb/CyberScientist-comp}"
development_root="${2:-/home/wmywb/CyberScientist}"
area="$runtime_root/.runtime/validation/post-accept-1009"
hidden_root="${development_root}.account-hidden-$(date +%s)"
test -d "$runtime_root/src"
test -d "$development_root"
test ! -e "$hidden_root"
mkdir -p "$area"
cd "$runtime_root"
restore() {
  rc=$?
  if [[ -d "$hidden_root" ]]; then
    test ! -e "$development_root" || exit 4
    mv -- "$hidden_root" "$development_root" || exit 4
    printf '%s\n' development_directory_restored >> "$area/account-hidden-progress.log"
  fi
  exit "$rc"
}
trap restore EXIT
trap 'exit 130' INT TERM HUP
export HOME="$runtime_root/.runtime/home" CODEX_HOME="$runtime_root/.runtime/codex"
export XDG_CONFIG_HOME="$HOME/.config" XDG_DATA_HOME="$HOME/.local/share" XDG_CACHE_HOME="$HOME/.cache"
unset PYTHONPATH
mv -- "$development_root" "$hidden_root"
printf '%s\n' development_directory_hidden >> "$area/account-hidden-progress.log"
"$runtime_root/.venv/bin/python" - "$runtime_root" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'src'))
from cyberscientist import config,db,mailboxes
platform=mailboxes._platform();accounts=[]
try:
    owner=platform._http('GET','/auth/me',token=platform.operator_token)
    owner_ok=owner.get('userType')=='human' and bool(owner.get('id'))
except Exception as exc:
    owner={};owner_ok=False
for row in db.query("SELECT * FROM mailboxes WHERE status='active' AND is_demo=0 ORDER BY role,id"):
    fact={'mailbox_id':row['id'],'role':row['role'],'email':row['email']}
    try:
        who=platform._http('GET','/auth/me',token=config.resolve_secret(row['secret_ref']))
        matches=str(who.get('id'))==str(row['platform_account_id'])
        credential_ok=matches and who.get('userType')==('agent' if row['role']=='experiment' else 'human')
        if row['role']=='experiment':
            matches=matches and who.get('userType')=='agent' and str(who.get('operatorId'))==str(owner.get('id')) and who.get('operatorConfirmed') is True
        else:
            matches=matches and who.get('userType')=='human' and str(who.get('id'))==str(owner.get('id'))
        fact.update(http_status=200,credential_authenticated=credential_ok,identity_valid=owner_ok and matches,user_type=who.get('userType'),operator_confirmed=who.get('operatorConfirmed'))
    except Exception as exc:
        fact.update(http_status=None,credential_authenticated=False,identity_valid=False,error_type=type(exc).__name__)
    accounts.append(fact)
result={'timestamp':db.utcnow(),'scope':'accounts_only','development_path_hidden':True,
        'accounts':accounts,'operator_valid':owner_ok,'configured_count':len(accounts),
        'credential_authenticated_count':sum(a['credential_authenticated'] for a in accounts),
        'authenticated_count':sum(a['identity_valid'] for a in accounts),
        'all_configured_passed':owner_ok and bool(accounts) and all(a['identity_valid'] for a in accounts),
        'five_accounts_passed':owner_ok and len(accounts)==5 and all(a['identity_valid'] for a in accounts),
        'external_mutations':0}
(root/'.runtime/validation/post-accept-1009/account-hidden-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='accounts'}))
raise SystemExit(0 if result['five_accounts_passed'] else 3)
PY
