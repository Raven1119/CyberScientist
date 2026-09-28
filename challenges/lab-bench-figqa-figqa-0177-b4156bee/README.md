# FigQA-0177: validated scientific score reconstruction

The [upstream public question](https://github.com/Future-House/LAB-Bench/blob/998a8e0a40cf116c80e1b0e7a805ebb5fb9fa838/FigQA/figqa-v1-public.jsonl)
has instance ID `ae9125e5-ce14-46f9-9ff7-d7bda1e101e1` and semantic answer **M10**.
The frozen Bohrium challenge orders M10 as **B**. Upstream randomizes option order,
so this letter must not be reused for another challenge. The public benchmark
[evaluator](https://github.com/Future-House/LAB-Bench/blob/998a8e0a40cf116c80e1b0e7a805ebb5fb9fa838/labbench/evaluator.py)
compares the parsed answer with the target. The Bohrium task requests
`outputs/answer.txt` containing a single `[ANSWER]X[/ANSWER]` answer.

This scorer implements the canonical case: B gives 100 scientific points;
A/C/D/E give 0. It accepts outer whitespace and reads only the answer file.
Missing, ambiguous, unsafe, oversized or noncanonical inputs return exit 2 and
`status=unverified`; historical evidence does not establish the hidden parser's
tolerance for malformed input. No scientific result is fabricated for these cases.
The implementation uses the Python standard library and matches the existing
CyberScientist `scorer.json`/JSON-output contract.

Run scientific evaluation through an authorized Bohrium sandbox:

```sh
CS_SCORER_VERSION=<manifest hash> python3 scorer/score.py science.zip
```

The host-side `checks/replay_figqa.py prepare` audits local command/output
snapshots and generated/received bundle bindings, then prepares answer-only ZIPs
and a separate label manifest under `.package-checks`. Its `evaluate` phase must
run in Bohrium. Historical scores are never passed as grader inputs.

The real 2026-09-28 replay matched **11/11** eligible historical scientific scores,
MAE **0**, maximum absolute error **0**. A twelfth record was excluded because its
generated and received bundle hashes differed. There are only **two distinct
answer-file contents** among the eligible records: ten B answers and one C answer.
This establishes sample agreement on the canonical interface, not broad parser
equivalence or independent statistical generalization.

This scorer does not reconstruct trace scores, display-score gating, ARM
executability checks, receipt validity or platform acceptance. See the complete
audit, including the unsuccessful Lean preparation, in
`docs/LOCAL_SCORER_REPLAY_2026-09-28.md`.
