"""Validate ABACUS's final reported thresholds without a legacy frame reader."""
import math
import re
from check_termination import require_terminal


def final_relaxation(log, params):
    mode = params['calculation']
    require_terminal(log, mode)
    final = log.rsplit('#SCF IS CONVERGED#', 1)[1]
    converged = final.rindex('Relaxation is converged!')
    finished = list(re.finditer(r'Finish\s+Time\s*:', final))[-1].start()
    metrics = final[:converged]
    result = {'calculation': mode, 'scf_converged': True, 'relaxation_converged': True,
              'frames': log.count('#SCF IS CONVERGED#'), 'accuracy_validated': False,
              'metrics_source': 'unmodified final ABACUS summary'}
    for kind, unit, parameter, field in (
            ('force', 'eV/Angstrom', 'force_thr_ev', 'max_force_ev_angstrom'),
            ('stress', 'kbar', 'stress_thr', 'max_stress_kbar')):
        if kind == 'stress' and mode != 'cell-relax':
            continue
        matches = re.findall(r'Largest ' + kind + r' is (\S+) ' + re.escape(unit)
                             + r' while threshold is (\S+) ' + re.escape(unit), metrics)
        if len(matches) != 1:
            raise ValueError('Final ' + kind + ' summary missing or ambiguous')
        observed, reported_limit = map(float, matches[0])
        requested_limit = float(params[parameter])
        if (not all(math.isfinite(x) for x in (observed, reported_limit, requested_limit))
                or observed < 0 or requested_limit <= 0
                or not math.isclose(reported_limit, requested_limit, rel_tol=1e-9, abs_tol=1e-9)
                or observed > requested_limit):
            raise ValueError('Final ' + kind + ' exceeds/mismatches declared threshold')
        result[field] = observed
    energies = re.findall(r'!FINAL_ETOT_IS\s+(\S+)\s+eV', final[converged:finished])
    if len(energies) != 1 or not math.isfinite(float(energies[0])):
        raise ValueError('Final finite energy not confirmed')
    result['final_energy_ev'] = float(energies[0])
    return result
