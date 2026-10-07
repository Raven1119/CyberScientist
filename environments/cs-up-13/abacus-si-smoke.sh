set -eu
date -u +%FT%TZ > start.txt
binary=$(command -v abacus || true)
if [ -z "$binary" ]; then binary=$(find /opt /usr/local /root /app -maxdepth 7 -type f -name abacus -perm /111 2>/dev/null | head -1 || true); fi
printf 'binary=%s\n' "$binary" > proof.txt
if [ -z "$binary" ]; then echo ABACUS_BINARY_MISSING >> proof.txt; find /opt /root /app -maxdepth 3 -type d 2>/dev/null | head -80 >> proof.txt; cat proof.txt; exit 21; fi
"$binary" --version >> proof.txt 2>&1 || true
pp=$(find /opt /usr/local /root /app -maxdepth 9 -type f -iname '*Si*.upf' 2>/dev/null | head -1 || true)
printf 'pseudo_source=%s\n' "$pp" >> proof.txt
if [ -z "$pp" ]; then echo SI_PSEUDOPOTENTIAL_MISSING >> proof.txt; cat proof.txt; exit 22; fi
cp "$pp" Si.upf
sha256sum "$binary" Si.upf >> proof.txt
cat > INPUT <<'EOF'
INPUT_PARAMETERS
suffix Si
calculation scf
ntype 1
basis_type pw
ecutwfc 30
scf_thr 1.0e-6
scf_nmax 100
pseudo_dir ./
symmetry 1
EOF
cat > STRU <<'EOF'
ATOMIC_SPECIES
Si 28.0855 Si.upf
LATTICE_CONSTANT
10.26
LATTICE_VECTORS
0.0 0.5 0.5
0.5 0.0 0.5
0.5 0.5 0.0
ATOMIC_POSITIONS
Direct
Si
0.0
2
0.0 0.0 0.0 0 0 0
0.25 0.25 0.25 0 0 0
EOF
cat > KPT <<'EOF'
K_POINTS
0
Gamma
2 2 2 0 0 0
EOF
export OMP_NUM_THREADS=1
"$binary" > abacus.stdout 2>&1
cat OUT.Si/running_scf.log >> proof.txt
grep -F '#SCF IS CONVERGED#' OUT.Si/running_scf.log
date -u +%FT%TZ >> proof.txt
echo CS13_SI_SCF_PASSED >> proof.txt
cat proof.txt
