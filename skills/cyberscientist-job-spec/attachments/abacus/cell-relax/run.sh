#!/usr/bin/env bash
set -euo pipefail
python check_inputs.py
abacus > abacus.stdout 2>&1
python check_results.py
