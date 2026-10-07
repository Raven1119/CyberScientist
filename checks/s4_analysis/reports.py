"""Publish aggregate rules and statistics; never publicize another solver's trace."""
import json
from collections import Counter
from pathlib import Path

from .common import DEFAULT_DATA,atomic,utcnow
from .dataset import read_table
from .tables import number


def main():
    root=DEFAULT_DATA;docs=Path(__file__).resolve().parents[2]/'docs'
    rules=json.loads((root/'scorer/v8_rules.json').read_text());v8=rules['v8_only'];codes=list(read_table('scorer/code_table.csv'))
    coverage=json.loads((root/'data/coverage.json').read_text())
    lines=['# S4 trace scorer v8: observed rules and limits','',
      'Generated '+utcnow()+'. Source: anonymous public GET snapshots in private `Raven1119/cs-s4-analysis`.',
      f"Snapshot phase: `{coverage.get('phase')}`. {rules['attempts']:,} non-draft attempts, {rules['trace_score_observations']:,} observed trace scores; full per-attempt detail coverage is recorded in `data/coverage.json`.",
      'List-embedded scoring receipts are included. Until detail collection is complete these are preliminary counts; rerunning this script replaces the aggregate report.','',
      '## v8 only','',f"Engine substring `v8-process-evidence-sufficiency`: {v8['attempts']:,} attempts. All {v8['trace_score_observations']:,} observed scores satisfy the 0.025 lattice within numerical tolerance; exceptions: {v8['grid_exceptions']}.",
      'A lattice is compatible with the pinned v6 formula; it does not identify v8 weights or private judge P/H.','',
      '| Decision | Observations | Minimum T | Maximum T |','|---|---:|---:|---:|']
    for key,value in v8['decision_score_ranges'].items():lines.append(f"| {key} | {value['count']} | {value['min']} | {value['max']} |")
    lines+=['','The observations are consistent with an acceptance boundary at 70. They do not establish that T alone determines policy: integrity, semantic block, disagreement and missing-context gates exist in v6. The observed minimum accept score is not a new threshold.','',
      '| Observed score spike | v8 count |','|---:|---:|']
    for item in v8['score_spikes'][:10]:lines.append(f"| {item['score']} | {item['count']} |")
    lines+=['','Pinned v6 uses checklist C and two live judges: `min(0.55*C + 0.25*P + 0.20*(100-H), applicable caps)`. The two judges are averaged and rounded to one decimal first. H≥80 blocks and caps at 29; P<30 caps at 59; disagreement≥30 caps at 69 and routes to review. Checklist/integrity caps remain binding. Score spikes alone do not prove which hidden v8 condition fired.',
      'The local replica uses exact pinned v6 input functions. Public API input and sanitized bundle evidence cannot establish parity with the original platform-normalized trace or worker receipts.','',
      '## Returned deduction codes','',
      'Frequencies below include all engine versions. Per-version co-occurrence, original receipt descriptions/effects and example IDs are queryable in private `scorer/code_table.csv`, `cap_cooccurrence.csv` and `data/deductions.csv`. A zero-effect code is still a returned finding.','',
      '| Code | Occurrences | Returned score effects | In pinned v6 | Example attempt |','|---|---:|---|---|---|']
    for row in codes:
        if row['code']=='unknown':continue
        lines.append('| `'+row['code']+'` | '+row['occurrences']+' | `'+row['effects_json']+'` | '+row['present_in_pinned_v6_source']+' | '+row['sample_attempt_ids'].split(';')[0]+' |')
    lines+=['','N17_PREEXISTING_SUBSTANTIVE_ARTIFACT and N18_PROCESS_EVIDENCE_INSUFFICIENT are absent from pinned v6. Their returned explanations concern artifacts that predate the visible trajectory and insufficient visible process evidence, respectively. Public traces alone cannot prove prior existence or independence of a solution; these findings remain receipt claims until separately supported. N18 returns effect 0, which must not be mistaken for an ordinary additive penalty.','',
      '## Display score','',
      'The simple candidate is accept→Harbor science score, review→science×T/100, block→0. It is checked row by row, without substituting unknowns with zeros.',
      f"Tested {rules['display_formula']['tested']:,} rows at tolerance 0.001; exceptions {rules['display_formula']['exceptions']:,}. Final-receipt subset: {rules['display_formula']['final_tested']:,} tested / {rules['display_formula']['final_exceptions']:,} exceptions.",
      'Exception classes: `'+json.dumps(rules['display_formula']['exception_classes'],ensure_ascii=False)+'`. Negative display sentinels stay negative. Explicit zero reasons and overrides are distinguished from unexplained differences; no universal display formula is asserted.',
      'Each check retains original factor, bonus, score and receipt fields in `scorer/display_formula_checks.csv`; all exceptions retain attempt IDs.','',
      '## Version and time evidence','',
      'Engine counts: `'+json.dumps(rules['engine_counts'],ensure_ascii=False)+'`.',
      f"The public status explicitly labels {rules['grading_time_evidence']['late_scored_status_attempts']:,} attempts `late_scored`. No scoredAt/gradedAt timestamp was exposed in the collected schema. createdAt is submission time; updatedAt can include edits/rescoring and is only a labelled proxy. Engine timelines therefore cannot identify the exact switch time or assert that a submission created within a round was scored within it.",
      'Round 5 has a 24.5-hour window in the public API. Within-round statistics use each actual start inclusive/end exclusive, rather than forcing all six windows to 24 hours.','',
      '## Reproduce','',
      'Run `python -m checks.s4_analysis.facts` and `python -m checks.s4_analysis.reports` from the analysis worktree after collection. Numeric joins use attempt/challenge IDs. `scorer/v8_rules.json` records assumptions, unknowns, source SHA and generation time. No external platform write is performed.','']
    atomic(docs/'S4_TRACE_SCORER_V8.md','\n'.join(lines).encode())
    science=list(read_table('scorer/science_layer.csv'));residuals=[number(r['reward_times_100_residual']) for r in science]
    bad=[r for r in science if number(r['reward_times_100_residual']) is not None and abs(number(r['reward_times_100_residual']))>.001]
    challenge_rows=list(read_table('data/challenges.csv'));backend=Counter(r.get('scoring_backend') or r.get('scoring_strategy') or 'unknown' for r in challenge_rows)
    lines=['# S4 scientific scoring: evidence and unresolved identity','',
      'Generated '+utcnow()+'. These are public receipt facts and protocol descriptions; no scientific solution or grader implementation is reproduced.','',
      f"For {len(science):,} receipts with both Harbor reward and science score, `harbor_score = 100 * harbor_reward` has {len(bad):,} exceptions at tolerance 0.001. Rows lacking either field remain unknown. The complete checks are in private `scorer/science_layer.csv`.",
      'Attempt [49735](https://play.bohrium.com/api/attempts/49735) has reward 1, Harbor score 100, replay flag 1, and executability/packaging/output_coverage/result_fidelity all 0. Its source is harbor_worker. Trace score 69 and review policy produce observed display score 69. These fields document separate scoring paths; the four zeros do not imply that Harbor reward must be zero.',
      'Public challenge scoring.strategy is metadata, not proof of the worker code actually used. Topic prose, protocol metadata and worker receipts are retained separately; conflicts are not silently resolved.','',
      '## Generic ARM contract','',
      'The [public protocol](https://play.bohrium.com/api/protocol) declares output coverage as the overlap of deviation targets with expected-output names divided by the expected-output count. Fidelity is the unweighted mean of deviation scores; each SSIM contribution is clipped to 0.3 first. environment_reproducibility is explicitly not computed, so an absent or default value provides no environment validation.',
      'The [ARM documentation](https://play.bohrium.com/api/docs/arm-bundles) describes Dockerfile presence→executability 1 and requirements-only→0.5. Packaging is structural completeness. Trace quality uses a step-count tier once trace extraction occurs, and an earlier stage can leave only the file-presence value. Trace admission is a separate gate from both step-count quality and v8 provenance scoring. A declared characterization weight is not part of the documented parser contract.',
      'Archive evidence checks read file inventories/manifests/characterization metadata, never execute downloaded code. Original archive/file SHA and sanitized SHA remain distinct. Any comparison affected by missing worker normalization, redaction or unavailable files is labelled unknown.','',
      '## Is this the public Harbor framework?','',
      'The public [Harbor task documentation](https://github.com/harbor-framework/harbor/blob/main/docs/content/docs/tasks/index.mdx) describes per-task test scripts and numeric reward files under /logs/verifier. JSON can contain multiple numeric rewards; plain text can hold a numeric value. This resembles the platform fields but is not evidence of shared implementation.',
      '**Identity: unknown.** Public platform receipts expose harbor_worker, reward, replay and scored_by labels, but no verified package version, repository link or worker source binding to harbor-framework/harbor was found in the inspected platform protocol and documentation. Name similarity and reward scaling do not establish framework identity.','',
      '## Scoring forms','',
      'Per-topic forms record required files, gates, metrics, mapping parameters, weights, aggregation, hidden-reference/replay requirements and exact source-quote checks. Their source is the public topic, not an inferred hidden grader. Discrete-total checks are valid only after score units and the applicable backend are established; topic prose can describe a different verifier from fallback API scoring metadata.','']
    atomic(docs/'S4_SCIENTIFIC_SCORING_LAYER.md','\n'.join(lines).encode())
    print(json.dumps({'public_reports':2,'snapshot_phase':coverage.get('phase'),'generated_at':utcnow()}))


if __name__=='__main__':main()
