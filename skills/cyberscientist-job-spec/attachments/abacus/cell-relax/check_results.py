"""Convergence and finite-output checks, not a scientific accuracy assertion."""
import json
import hashlib
from pathlib import Path
from check_relaxation import final_relaxation

params={parts[0]:parts[1] for line in Path('INPUT').read_text().splitlines()
        if len(parts:=line.split('#')[0].split())>1}
mode=params['calculation'];folder=Path('OUT.'+params.get('suffix','ABACUS'))
log=(folder/('running_'+mode+'.log')).read_text()
if mode not in ('relax','cell-relax'):raise SystemExit('Relaxation template requires relax or cell-relax')
result=final_relaxation(log,params)
result['original_log_sha256']=hashlib.sha256(log.encode()).hexdigest()
Path('convergence.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print('ABACUS_CONVERGENCE_CHECK_PASSED')
