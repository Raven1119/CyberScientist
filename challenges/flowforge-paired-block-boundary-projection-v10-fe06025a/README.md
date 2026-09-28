# Paired-block scientific scorer

Reconstructs the deterministic scientific rubric in the [public challenge](https://play.bohrium.com/#challenge/flowforge-paired-block-boundary-projection-v10-fe06025a).
This is not the platform's hidden verifier and does not predict trace scores.

**Validation status, 2026-09-28:** real Bohrium evaluation matched **4/4**
historical scientific scores (two 0s, two 100s), with MAE/max error **0**.
All **8** synthetic negative controls also matched the public rubric's expected
scores; these controls have no platform receipts. The fifth historical input,
which imports all Mathlib, remains unverified after cache and transfer failures.
The scorer reports medium confidence. See the
[real replay and limits](../../docs/PAIRED_BLOCK_SCORER_REPLAY_2026-09-28.md).
Earlier environment failures remain in the audit history.

## Rule and prerequisites

Read only `outputs/Problem.lean` and optional `outputs/PHYSICS_MATCH.json` from a science ZIP.
The three required theorem types earn 40, 30 and 20 points. Check them against the
hash-pinned supplied template, with the supplied `PairCore` definitions and Lean
4.32.2. A whole-file compilation error gives zero; a compiled theorem whose
axioms include `sorryAx` or a new axiom earns no points. The accepted foundational
axioms are `propext`, `Classical.choice`, and `Quot.sound`.

Only after all 90 proof points, a valid distinct matching can add 4, 3 and 3 points
for T1→R7, T2→R2, T3→R9. These correspondences follow the supplied option meanings
and agree with the historical full-score answers. Malformed or absent matching
gets no bonus. The public format validator alone is not a correctness grader.

The sandbox must already contain the **immutable author project**, pinned
dependencies and built `PairCore` in `/workspace/paired-block-project` (or
`CS_LEAN_PROJECT`). Use its original `Problem.lean` template, not a candidate.
Install Lean in `/workspace/cs-elan` or expose `lake` on PATH. The manifest's
Ubuntu image alone does not contain these dependencies. Missing infrastructure,
timeouts, modified trusted files and ambiguous packages return exit 2 with
`status=unverified`; they never become a numeric zero.

## Reproduce through the gateway

`checks/historical_scorer_session.py` creates an isolated, explicitly authorized
analysis context without brain/executor sessions. Its `create`, `exec`, `write`,
`read`, and `close` actions use the production sandbox gateway and audit ledger.
It has no Job, model or Attempt authority. Reusing it outside the authorized
task requires fresh bounded sandbox authorization.

1. On the host, use `checks/prepare_paired_block_corpus.py --pairs ...
   --challenge-root ... --output .package-checks/...` to select final historical
   records, check submission-to-receipt hashes and rebuild science-only ZIPs.
   Preserve `samples.json` locally; only `labels.json` lacks account identities.
2. Prepare the immutable project and its pinned toolchain inside the owned
   Bohrium sandbox. Public dependency files may be downloaded on the host and
   transferred if the sandbox's external network is unreliable. Do not compile
   or run scientific evaluation on the host.
   `checks/run_paired_block_remote.py` automates pinned archive verification,
   environment preparation and replay inside the sandbox, with stage logs and a
   deadline. Prepare its local `manifest.json` with dependency hashes and the
   frozen scorer version. Retrieve evidence before deleting the sandbox.
3. Transfer scorer source, science ZIPs and replay driver. Run in the sandbox:

   ```sh
   python3 replay_paired_block.py --scorer scorer/score.py --inputs cases \
     --labels labels.json --project /workspace/paired-block-project \
     --output /workspace/replay-results --version <scorer_manifest_hash>
   ```

   For a single input, the existing application contract is:

   ```sh
   CS_SCORER_VERSION=<scorer_manifest_hash> python3 scorer/score.py science.zip
   ```

4. Retrieve results and logs before `close`; verify resource deletion. Retain raw
   artifacts in ignored local directories. The rebuilt ZIP is not the original
   ARM bundle, so its hash must not be used as an exact original-bundle calibration.

The replay driver keeps historical labels outside grader inputs and creates
eight additional controlled counterexamples. These mutations have no platform
scores. The historical evaluation is retrospective: labels were already known,
and five cases from one research lineage are not five independent problems.
For this fixed public rule, leaving each label out changes no parameters; it is
equivalent to replay, not independent evidence that hidden rules were recovered.

## Scope

This scorer targets one's own auditable proof artifacts. It does not claim to
harden Lean metaprograms against hostile code, prove the physics correspondence
as a Lean theorem, reproduce all hidden resource limits, or establish the
platform's behavior on unobserved partial scores. Scientific output cannot
substitute for the original research trace.
