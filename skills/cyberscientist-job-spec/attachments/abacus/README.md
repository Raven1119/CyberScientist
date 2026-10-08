ABACUS PW Si tooling examples. Each case is self-contained: use scf/ or cell-relax/ as the Job input_directory, set command to bash run.sh, and supply a compatible PBE Si.upf in that directory. Run in an authorized Bohrium environment containing ABACUS, dpdata and NumPy.

Register OUT.Si, abacus.stdout and convergence.json in backward_files. Use measured smoke time to size the Job limit. Do not package both sibling cases as one input root. These parameters are small tooling examples; convergence does not establish production cutoff/k-point convergence or a benchmark answer. SCF and relaxation checks fail closed if evidence is missing. Cell relaxation checks final force and zero-target stress thresholds.

Parameter reference: https://github.com/deepmodeling/abacus-develop/blob/develop/docs/quick_start/hands_on.md

The pinned dpdata reader uses an explicitly derived temporary log view for the current ABACUS energy/stress headings. Numerical values and original logs stay unchanged; convergence.json records the original log SHA256. Final SCF, normal termination and relaxation terminal markers are checked before reading frames.
