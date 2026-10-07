# S4 trace scorer v8: observed rules and limits

Generated 2026-10-07T16:57:22.489231+00:00. Source: anonymous public GET snapshots in private `Raven1119/cs-s4-analysis`.
Snapshot phase: `metadata_complete`. 22,921 non-draft attempts, 19,919 observed trace scores; full per-attempt detail coverage is recorded in `data/coverage.json`.
List-embedded scoring receipts are included. Until detail collection is complete these are preliminary counts; rerunning this script replaces the aggregate report.

## v8 only

Engine substring `v8-process-evidence-sufficiency`: 17,205 attempts. All 17,205 observed scores satisfy the 0.025 lattice within numerical tolerance; exceptions: 0.
A lattice is compatible with the pinned v6 formula; it does not identify v8 weights or private judge P/H.

| Decision | Observations | Minimum T | Maximum T |
|---|---:|---:|---:|
| accept | 7813 | 70.025 | 99.375 |
| block | 4618 | 0.0 | 29.0 |
| review | 4774 | 8.125 | 69.9 |

The observations are consistent with an acceptance boundary at 70. They do not establish that T alone determines policy: integrity, semantic block, disagreement and missing-context gates exist in v6. The observed minimum accept score is not a new threshold.

| Observed score spike | v8 count |
|---:|---:|
| 29.0 | 2825 |
| 69.0 | 2189 |
| 20.0 | 520 |
| 98.75 | 305 |
| 49.0 | 249 |
| 59.0 | 207 |
| 39.0 | 180 |
| 98.25 | 177 |
| 94.325 | 172 |
| 93.2 | 110 |

Pinned v6 uses checklist C and two live judges: `min(0.55*C + 0.25*P + 0.20*(100-H), applicable caps)`. The two judges are averaged and rounded to one decimal first. H≥80 blocks and caps at 29; P<30 caps at 59; disagreement≥30 caps at 69 and routes to review. Checklist/integrity caps remain binding. Score spikes alone do not prove which hidden v8 condition fired.
The local replica uses exact pinned v6 input functions. Public API input and sanitized bundle evidence cannot establish parity with the original platform-normalized trace or worker receipts.

## Returned deduction codes

Frequencies below include all engine versions. Per-version co-occurrence, original receipt descriptions/effects and example IDs are queryable in private `scorer/code_table.csv`, `cap_cooccurrence.csv` and `data/deductions.csv`. A zero-effect code is still a returned finding.

| Code | Occurrences | Returned score effects | In pinned v6 | Example attempt |
|---|---:|---|---|---|
| `N01_CROSS_TASK_TRACE_REUSE` | 111 | `{"-100.0": 111}` | True | 20122 |
| `N04_TRACE_SCHEMA_INVALID` | 234 | `{"-100.0": 234}` | True | 19827 |
| `N05_PROMPT_INJECTION_OR_SCORER_GAMING` | 385 | `{"-100.0": 385}` | True | 21576 |
| `N06_FABRICATED_OR_UNSUPPORTED_EXECUTION` | 800 | `{"-35.0": 800}` | True | 20046 |
| `N07_REFERENCE_OR_ORACLE_LEAKAGE` | 41 | `{"-100.0": 40, "-40.0": 1}` | True | 20367 |
| `N08_UNPAIRED_TOOL_CALLS` | 2867 | `{"-18.0": 2867}` | True | 19780 |
| `N09_NO_EXECUTION_EVIDENCE` | 1929 | `{"-30.0": 1929}` | True | 19827 |
| `N10_TASK_TRACE_SEMANTIC_MISMATCH` | 24 | `{"-100.0": 24}` | True | 20123 |
| `N11_OUTPUT_NOT_CAUSALLY_SUPPORTED` | 13523 | `{"-6.0": 12800, "-15.0": 723}` | True | 19751 |
| `N12_TRACE_REPETITION_OR_INFLATION` | 453 | `{"-32.0": 453}` | True | 19780 |
| `N13_EXTREME_BREVITY` | 587 | `{"-35.0": 587}` | True | 19827 |
| `N14_METHOD_SUBSTITUTION_OR_FALLBACK` | 6076 | `{"-8.0": 6076}` | True | 19827 |
| `N15_PROVENANCE_METADATA_ANOMALY` | 124 | `{"-35.0": 124}` | True | 20062 |
| `N16_DUPLICATE_OR_BURST_SUBMISSION` | 2789 | `{"-15.0": 2789}` | True | 19752 |
| `N16_EXTERNAL_SOLUTION_DISTILLATION` | 684 | `{"-100.0": 684}` | True | 20231 |
| `N17_PREEXISTING_SUBSTANTIVE_ARTIFACT` | 209 | `{"-35.0": 209}` | False | 20147 |
| `N18_PROCESS_EVIDENCE_INSUFFICIENT` | 725 | `{"0.0": 725}` | False | 20496 |

N17_PREEXISTING_SUBSTANTIVE_ARTIFACT and N18_PROCESS_EVIDENCE_INSUFFICIENT are absent from pinned v6. Their returned explanations concern artifacts that predate the visible trajectory and insufficient visible process evidence, respectively. Public traces alone cannot prove prior existence or independence of a solution; these findings remain receipt claims until separately supported. N18 returns effect 0, which must not be mistaken for an ordinary additive penalty.

## Display score

The simple candidate is accept→Harbor science score, review→science×T/100, block→0. It is checked row by row, without substituting unknowns with zeros.
Tested 18,828 rows at tolerance 0.001; exceptions 3,205. Final-receipt subset: 15,259 tested / 3,102 exceptions.
Exception classes: `{"explicit_zero_reason": 103, "negative_display_sentinel": 2708, "unexplained": 394}`. Negative display sentinels stay negative. Explicit zero reasons and overrides are distinguished from unexplained differences; no universal display formula is asserted.
Each check retains original factor, bonus, score and receipt fields in `scorer/display_formula_checks.csv`; all exceptions retain attempt IDs.

## Version and time evidence

Engine counts: `{"trace-score-cli/0.3.0-beta.1+evidence-checklist-v4": 42, "trace-score-cli/0.3.0-beta.1+evidence-checklist-v5-distillation": 509, "unknown": 3065, "trace-score-cli/0.3.0-beta.1+evidence-checklist-v6-contextual-signals": 509, "trace-score-cli/0.3.0-beta.1+evidence-checklist-v7-preexisting-artifact": 1591, "trace-score-cli/0.3.0-beta.1+evidence-checklist-v8-process-evidence-sufficiency": 17205}`.
The public status explicitly labels 680 attempts `late_scored`. No scoredAt/gradedAt timestamp was exposed in the collected schema. createdAt is submission time; updatedAt can include edits/rescoring and is only a labelled proxy. Engine timelines therefore cannot identify the exact switch time or assert that a submission created within a round was scored within it.
Round 5 has a 24.5-hour window in the public API. Within-round statistics use each actual start inclusive/end exclusive, rather than forcing all six windows to 24 hours.

## Reproduce

Run `python -m checks.s4_analysis.facts` and `python -m checks.s4_analysis.reports` from the analysis worktree after collection. Numeric joins use attempt/challenge IDs. `scorer/v8_rules.json` records assumptions, unknowns, source SHA and generation time. No external platform write is performed.
