"""Text-only ABACUS input guard; execute alongside the supplied INPUT/STRU."""
from pathlib import Path

params={parts[0]:parts[1] for line in Path('INPUT').read_text().splitlines()
        if len(parts:=line.split('#')[0].split())>1}
required={'calculation','basis_type','ecutwfc','scf_thr','scf_nmax'}
missing=required-params.keys()
if missing:raise SystemExit('Missing INPUT parameters: '+','.join(sorted(missing)))
if params['calculation'] in ('relax','cell-relax'):
    lines=Path('STRU').read_text().split('ATOMIC_POSITIONS',1)
    if len(lines)!=2:raise SystemExit('Missing ATOMIC_POSITIONS')
    flags=[]
    for line in lines[1].splitlines():
        parts=line.split('#')[0].split()
        if len(parts)<6:continue
        try:[float(x) for x in parts[:3]]
        except ValueError:continue
        move=parts[4:7] if parts[3]=='m' else parts[3:6]
        if len(move)==3 and all(x in ('0','1') for x in move):flags.append(any(x=='1' for x in move))
    if not flags or not any(flags):raise SystemExit('Relaxation has no movable atoms')
print('ABACUS_INPUT_CHECK_PASSED')
