"""Run inside the prepared Bohrium image; synthetic toolchain smoke only."""
import importlib,importlib.metadata,json
from pathlib import Path
packages={}
for name in ('ase','pymatgen','spglib','phonopy','pybader','dpdata'):
    importlib.import_module(name)
    packages[name]=importlib.metadata.version(name)
Path('imports.json').write_text(json.dumps(packages,sort_keys=True))
print('MATERIALS_IMPORTS_PASSED',json.dumps(packages,sort_keys=True),flush=True)
import numpy as np
from pybader.interface import Bader
n=16
points=np.indices((n,n,n),dtype=float)/n*4
rho=np.exp(-np.sum((points-2)**2,axis=0))+1e-6
b=Bader({'charge':rho},np.eye(3)*4,np.array([[2.,2.,2.]]),
        {'filename':'synthetic','file_type':'cube','prefix':str(Path.cwd())+'/',
         'voxel_offset':np.zeros(3)},threads=1,output='pickle',export_mode=None,prefix=str(Path.cwd())+'/')
b()
expected=float(rho.sum()*64/n**3)
assert np.isfinite(b.atoms_charge).all()
assert np.isclose(b.atoms_charge.sum(),expected,rtol=1e-7,atol=1e-8)
Path('pybader-smoke.json').write_text(json.dumps({'charge_conserved':True,'atoms':len(b.atoms_charge),'synthetic':True}))
print('PYBADER_SMOKE_PASSED',flush=True)
