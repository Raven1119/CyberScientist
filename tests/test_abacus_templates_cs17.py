"""Application/text checks only; scientific template smoke is on Bohrium."""
import importlib.util
from pathlib import Path
import pytest
from cyberscientist import job_checks
ROOT=Path(__file__).resolve().parents[1]/'skills/cyberscientist-job-spec/attachments/abacus'

@pytest.mark.parametrize('case',['scf','cell-relax'])
def test_case_can_be_packaged_and_passes_static_preflight(case):
    files={p.name:p.read_bytes() for p in (ROOT/case).iterdir() if p.is_file()}
    report=job_checks.static(files,{'command':'bash run.sh','backward_files':['OUT.Si','abacus.stdout','convergence.json'],'max_run_time':5},{})
    assert 'abacus' in report['commands']

def test_old_success_cannot_hide_final_failure_or_truncation():
    spec=importlib.util.spec_from_file_location('termination',ROOT/'scf/check_termination.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    good='#SCF IS CONVERGED#\nRelaxation is converged!\nFinish Time : now\n'
    module.require_terminal(good,'cell-relax')
    for text in (good.replace('Finish Time : now',''),good.replace('Relaxation is converged!','Relaxation is not converged yet!'),good+'#SCF IS NOT CONVERGED#\n',good+'#SCF IS CONVERGED#\n'):
        with pytest.raises(ValueError):module.require_terminal(text,'cell-relax')
