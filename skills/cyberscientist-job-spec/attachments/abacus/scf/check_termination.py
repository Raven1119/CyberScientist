"""Text-only terminal checks before parsing numerical frames."""
import re

def require_terminal(log, mode):
    scf=list(re.finditer(r"#SCF IS (CONVERGED|NOT CONVERGED)#",log))
    finish=list(re.finditer(r"Finish\s+Time\s*:",log))
    if not scf or scf[-1][1]!="CONVERGED" or not finish or finish[-1].start()<scf[-1].start():
        raise ValueError("Final SCF convergence and normal termination not confirmed")
    if mode in ("relax","cell-relax"):
        relax=list(re.finditer(r"Relaxation is (converged|not converged yet)!",log))
        if not relax or relax[-1][1]!="converged" or relax[-1].start()<scf[-1].start() or finish[-1].start()<relax[-1].start():
            raise ValueError("Final relaxation convergence not confirmed")
