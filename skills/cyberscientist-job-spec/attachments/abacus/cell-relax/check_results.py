"""Convergence and finite-output checks, not a scientific accuracy assertion."""
import json
import hashlib
import tempfile
import shutil
from pathlib import Path
from check_termination import require_terminal
import dpdata
import numpy as np

params={parts[0]:parts[1] for line in Path('INPUT').read_text().splitlines()
        if len(parts:=line.split('#')[0].split())>1}
mode=params['calculation'];folder=Path('OUT.'+params.get('suffix','ABACUS'))
log=(folder/('running_'+mode+'.log')).read_text()
require_terminal(log,mode)
# Parse a disposable compatibility view; keep the original ABACUS evidence intact.
# The pinned reader predates the current SCF energy/stress headings.
with tempfile.TemporaryDirectory(prefix='abacus-reader-') as temporary:
    target=Path(temporary)
    for name in ('INPUT','STRU'):shutil.copy2(name,target/name)
    shutil.copytree(folder,target/folder)
    adapted=log.replace('!FINAL_ETOT_IS','final etot is').replace('#TOTAL-STRESS (kbar)#','TOTAL-STRESS (KBAR)')
    (target/folder/('running_'+mode+'.log')).write_text(adapted)
    data=dpdata.LabeledSystem(str(target),fmt='abacus/scf' if mode=='scf' else 'abacus/relax').data
energy=np.asarray(data['energies']);cells=np.asarray(data['cells'])
if not energy.size or not np.isfinite(energy).all() or not np.isfinite(cells).all():raise SystemExit('Missing/nonfinite energy or cell')
result={'calculation':mode,'scf_converged':True,'frames':len(energy),'final_energy_ev':float(energy[-1]),'accuracy_validated':False,'original_log_sha256':hashlib.sha256(log.encode()).hexdigest(),'reader_compatibility_view':True}
if mode in ('relax','cell-relax'):
    force=np.asarray(data['forces'])[-1];virial=np.asarray(data['virials'])[-1]
    if not np.isfinite(force).all() or not np.isfinite(virial).all():raise SystemExit('Nonfinite final forces or virial')
    volume=abs(float(np.linalg.det(cells[-1])))
    if volume<=0:raise SystemExit('Invalid cell volume')
    max_force=float(np.linalg.norm(force,axis=-1).max());max_stress=float(np.abs(virial/volume).max()*1602.1766208)
    result.update(max_force_ev_angstrom=max_force,max_stress_kbar=max_stress)
    if max_force>float(params['force_thr_ev']):raise SystemExit('Final forces exceed declared threshold')
    if mode=='cell-relax' and max_stress>float(params['stress_thr']):raise SystemExit('Final stress exceeds declared threshold')
Path('convergence.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print('ABACUS_CONVERGENCE_CHECK_PASSED')
