import json,importlib.metadata,time
from pathlib import Path
import numpy as np,ase,spglib,phonopy,ovito
from ase.build import bulk
from ase.calculators.emt import EMT
from pymatgen.core import Structure
t=time.monotonic();si=bulk("Si","diamond",a=5.43)
symmetry=spglib.get_spacegroup((si.cell.array,si.get_scaled_positions(),si.numbers))
assert symmetry.startswith("Fd-3m")
structure=Structure(si.cell.array,["Si"]*len(si),si.get_scaled_positions());assert len(structure)==2
cu=bulk("Cu","fcc",a=3.6);cu.calc=EMT();energy=cu.get_potential_energy();assert np.isfinite(energy)
proof={"status":"passed","Si_atoms":len(si),"spacegroup":symmetry,"Cu_EMT_energy_eV":energy,"compute_seconds":time.monotonic()-t,"versions":{m:importlib.metadata.version(m) for m in ("ase","pymatgen","spglib","phonopy","ovito")}}
Path("proof.json").write_text(json.dumps(proof));print(json.dumps(proof))
