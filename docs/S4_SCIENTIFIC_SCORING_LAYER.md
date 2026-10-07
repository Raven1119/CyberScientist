# S4 scientific scoring: evidence and unresolved identity

Generated 2026-10-07T14:31:42.479401+00:00. These are public receipt facts and protocol descriptions; no scientific solution or grader implementation is reproduced.

For 18,891 receipts with both Harbor reward and science score, `harbor_score = 100 * harbor_reward` has 0 exceptions at tolerance 0.001. Rows lacking either field remain unknown. The complete checks are in private `scorer/science_layer.csv`.
Attempt [49735](https://play.bohrium.com/api/attempts/49735) has reward 1, Harbor score 100, replay flag 1, and executability/packaging/output_coverage/result_fidelity all 0. Its source is harbor_worker. Trace score 69 and review policy produce observed display score 69. These fields document separate scoring paths; the four zeros do not imply that Harbor reward must be zero.
Public challenge scoring.strategy is metadata, not proof of the worker code actually used. Topic prose, protocol metadata and worker receipts are retained separately; conflicts are not silently resolved.

## Generic ARM contract

The [public protocol](https://play.bohrium.com/api/protocol) declares output coverage as the overlap of deviation targets with expected-output names divided by the expected-output count. Fidelity is the unweighted mean of deviation scores; each SSIM contribution is clipped to 0.3 first. environment_reproducibility is explicitly not computed, so an absent or default value provides no environment validation.
The [ARM documentation](https://play.bohrium.com/api/docs/arm-bundles) describes Dockerfile presence→executability 1 and requirements-only→0.5. Packaging is structural completeness. Trace quality uses a step-count tier once trace extraction occurs, and an earlier stage can leave only the file-presence value. Trace admission is a separate gate from both step-count quality and v8 provenance scoring. A declared characterization weight is not part of the documented parser contract.
Archive evidence checks read file inventories/manifests/characterization metadata, never execute downloaded code. Original archive/file SHA and sanitized SHA remain distinct. Any comparison affected by missing worker normalization, redaction or unavailable files is labelled unknown.

## Is this the public Harbor framework?

The public [Harbor task documentation](https://github.com/harbor-framework/harbor/blob/main/docs/content/docs/tasks/index.mdx) describes per-task test scripts and numeric reward files under /logs/verifier. JSON can contain multiple numeric rewards; plain text can hold a numeric value. This resembles the platform fields but is not evidence of shared implementation.
**Identity: unknown.** Public platform receipts expose harbor_worker, reward, replay and scored_by labels, but no verified package version, repository link or worker source binding to harbor-framework/harbor was found in the inspected platform protocol and documentation. Name similarity and reward scaling do not establish framework identity.

## Scoring forms

Per-topic forms record required files, gates, metrics, mapping parameters, weights, aggregation, hidden-reference/replay requirements and exact source-quote checks. Their source is the public topic, not an inferred hidden grader. Discrete-total checks are valid only after score units and the applicable backend are established; topic prose can describe a different verifier from fallback API scoring metadata.
