#!/usr/bin/env node
/** Offline behavior checks against a pinned public scorer, never a v8 predictor.
 * Fetch the public source separately; this program has no network/model calls.
 * Usage: node --experimental-strip-types checks/audit_public_trace_scorer.mjs
 *   --source <trace-score-cli/src/index.ts> --out <ignored-report.json>
 * Optional --trace, --submission and --task inspect only local existing files.
 * Reports with a real trace may contain private evidence: keep them ignored.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const SOURCE_SHA256 = 'afafd718c1eca6c25fa81231905988b436ff03684581d0410f8cc549599dfa46';
const COMMIT = '81c434907e7b0a2feccc79236f6601f7abbc1d84';
const ENGINE = 'trace-score-cli/0.3.0-beta.1+evidence-checklist-v6-contextual-signals';
const hash = (value) => createHash('sha256').update(value).digest('hex');
const options = {};
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i];
  const value = process.argv[i + 1];
  if (!['--source', '--out', '--trace', '--submission', '--task', '--playground-cli'].includes(key) || !value || value.startsWith('--') || key in options) {
    throw new Error('Expected unique --source/--out and optional --trace/--submission/--task/--playground-cli values');
  }
  options[key] = value;
}
if (!options['--source'] || !options['--out']) throw new Error('--source and --out are required');
const source = await fs.readFile(options['--source']);
assert.equal(hash(source), SOURCE_SHA256, 'Refuse to execute an unverified scorer revision');
// No import-time CLI main and no live judge invocation; retain exact upstream functions.
const marker = '\nmain().catch((error: unknown) => {';
const text = source.toString('utf8');
assert.equal(text.split(marker).length, 2);
const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'cs-scorer-source-audit-'));
const oldFetch = globalThis.fetch;
globalThis.fetch = async () => { throw new Error('Network disabled in offline scorer audit'); };
try {
  const modulePath = path.join(temp, 'scorer.ts');
  await fs.writeFile(modulePath, text.split(marker)[0] + '\nexport { loadTrace, lintTrace, buildChecklistReport, automaticScoreComponents, automaticScorePolicy, scoreTraceExcerpt, collectSubmissionEvidence, firstPositiveComputationEvent };\n');
  const scorer = await import(pathToFileURL(modulePath).href);
  const checks = [];
  const reduce = (name, checklistScore, cap, provenance, risk, decision, disagreement, expectedScore, expectedDecision, hardBlock = false) => {
    const checklist = { score: checklistScore, score_cap: cap, hard_block: hardBlock, decision: 'accept', quality_class: 'acceptable' };
    const llm = { content_json: { provenance_sufficiency: provenance, hack_risk: risk, decision, judge_disagreement: disagreement } };
    const components = scorer.automaticScoreComponents({ trace_quality_score: 13 }, checklist, llm);
    const policy = scorer.automaticScorePolicy(checklist, components, llm);
    assert.ok(Math.abs(components.fusion_score - expectedScore) < 1e-8, name);
    assert.equal(policy.decision, expectedDecision, name);
    checks.push({ name, score: components.fusion_score, cap: components.score_cap, decision: policy.decision });
  };
  reduce('weighted_formula', 100, 100, 90, 5, 'likely_clean', 0, 96.5, 'accept');
  reduce('eighteen_checklist_points_cost_9_9_fusion_points', 82, 100, 90, 5, 'likely_clean', 0, 86.6, 'accept');
  reduce('rule_score_is_not_fusion_checklist', 100, 100, 100, 0, 'likely_clean', 0, 100, 'accept');
  reduce('honest_low_provenance_cap', 100, 100, 29, 0, 'likely_clean', 0, 59, 'review');
  reduce('provenance_30_does_not_trigger_59_cap', 100, 100, 30, 0, 'likely_clean', 0, 82.5, 'accept');
  reduce('semantic_block', 100, 100, 100, 80, 'likely_hack_or_unclean', 0, 29, 'block');
  reduce('semantic_block_is_ceiling_not_fixed_score', 0, 100, 0, 99, 'likely_hack_or_unclean', 0, 0.2, 'block');
  reduce('disagreement_cap', 100, 100, 100, 0, 'needs_review', 30, 69, 'review');
  reduce('judge_review_label_not_itself_policy_veto', 100, 100, 65, 40, 'needs_review', 0, 83.25, 'accept');
  reduce('checklist_cap_cannot_be_compensated', 49, 49, 100, 0, 'likely_clean', 0, 49, 'review');
  reduce('low_provenance_overrides_high_pre_cap', 100, 100, 20, 0, 'likely_clean', 0, 59, 'review');
  // An uncapped exact boundary: 0.55*70 + 0.25*70 + 0.20*70 = 70.
  reduce('uncapped_70_accept', 70, 100, 70, 30, 'likely_clean', 0, 70, 'accept');
  reduce('uncapped_below_70_review', 69, 100, 70, 30, 'likely_clean', 0, 69.45, 'review');
  reduce('hard_integrity_block', 0, 20, 100, 0, 'likely_clean', 0, 20, 'block', true);
  const inspect = async (tracePath, submissionPath, taskPath) => {
    const trace = await scorer.loadTrace(tracePath);
    const lint = scorer.lintTrace(trace);
    const submission = await scorer.collectSubmissionEvidence(submissionPath);
    const task = taskPath ? await fs.readFile(taskPath, 'utf8') : undefined;
    const checklist = scorer.buildChecklistReport(trace, lint, hash(await fs.readFile(tracePath)), task, submission, undefined);
    const positive = scorer.firstPositiveComputationEvent(trace.events);
    return { format: trace.format, stats: lint.stats, checklist, excerpt: scorer.scoreTraceExcerpt(trace),
      positive_computation_event: positive ? { index: positive.index, kind: positive.kind, text: positive.text } : null };
  };
  const native = [
    { type: 'thread.started', thread_id: 'synthetic' },
    { type: 'item.completed', item: { id: 'm1', type: 'agent_message', text: 'Synthetic reasoning before tool execution.' } },
    { type: 'item.started', item: { id: 'c1', type: 'command_execution', command: 'python src/reproduce.py' } },
    { type: 'item.completed', item: { id: 'c1', type: 'command_execution', command: 'python src/reproduce.py', aggregated_output: 'generated outputs/result.json; verified', exit_code: 0 } },
    { type: 'item.completed', item: { id: 'm2', type: 'agent_message', text: 'Synthetic conclusion after tool execution.' } },
  ];
  const arm = [
    { step_type: 'thought', body: native[1].item.text },
    { step_type: 'tool_call', tool_call_id: 'c1', tool_name: 'shell', tool_args: { command: native[2].item.command } },
    { step_type: 'tool_result', tool_call_id: 'c1', tool_output: native[3].item.aggregated_output },
    { step_type: 'thought', body: native[4].item.text },
  ];
  const parser = {};
  for (const [label, rows] of [['codex_native', native], ['arm', arm]]) {
    const fixturePath = path.join(temp, `${label}.jsonl`);
    await fs.writeFile(fixturePath, rows.map(row => JSON.stringify(row)).join('\n') + '\n');
    const result = await inspect(fixturePath);
    parser[label] = { format: result.format, stats: result.stats, codes: result.checklist.triggered_negative_codes, cap: result.checklist.score_cap };
  }
  assert.equal(parser.codex_native.stats.assistantMessages, 0);
  assert.equal(parser.codex_native.stats.toolCalls, 0);
  assert.ok(parser.codex_native.codes.includes('N04_TRACE_SCHEMA_INVALID'));
  assert.ok(!parser.arm.codes.includes('N04_TRACE_SCHEMA_INVALID'));
  assert.equal(parser.arm.stats.toolCalls, 1);
  checks.push({ name: 'native_codex_parser_loses_roles_but_arm_does_not', passed: true });
  const numericOnlyEvents = [
    { index: 1, role: 'assistant', kind: 'tool_call', text: 'python src/calc.py', toolName: 'shell' },
    { index: 2, role: 'tool', kind: 'tool_result', text: '42', toolName: 'shell', raw: { exit_code: 0 } },
  ];
  assert.equal(scorer.firstPositiveComputationEvent(numericOnlyEvents), undefined);
  checks.push({ name: 'successful_python_with_numeric_output_not_recognized_as_computation', passed: true });
  const events = Array.from({ length: 100 }, (_, i) => ({ index: i + 1, role: 'assistant', kind: 'thought', text: `event ${i + 1} ` + 'x'.repeat(1000) + ' TAIL_MARKER' }));
  const excerpt = scorer.scoreTraceExcerpt({ events });
  assert.ok(excerpt.length < events.length);
  assert.ok(excerpt.every(event => event.text.length === 900 && !event.text.includes('TAIL_MARKER')));
  checks.push({ name: 'event_sampling_and_900_character_prefix', input_events: 100, excerpt_events: excerpt.length, passed: true });
  const report = { schema: 'cyberscientist/public-scorer-source-audit/v1', source_commit: COMMIT, source_sha256: SOURCE_SHA256, engine: ENGINE, scope: 'offline_public_v6_only_not_historical_v8_prediction', checks, parser };
  if (options['--playground-cli']) {
    const cli = path.resolve(options['--playground-cli']);
    const cliHash = hash(await fs.readFile(cli));
    assert.equal(cliHash, 'd231fefe0f11a481866aeae399906fc587e75d95c0cf08ff405b3f6f7ee48b03', 'Refuse unverified Playground CLI build');
    const conversions = {};
    for (const [name, rows] of [['clean', native], ['with_transport_error', [...native, { type: 'error', message: 'Synthetic transport timeout' }]]]) {
      const input = path.join(temp, `${name}.jsonl`);
      const output = path.join(temp, `${name}.arm.jsonl`);
      await fs.writeFile(input, rows.map(row => JSON.stringify(row)).join('\n') + '\n');
      const child = spawnSync(process.execPath, [cli, 'trace', 'convert', '--trace', input, '--out', output], { encoding: 'utf8', timeout: 30_000 });
      assert.equal(child.status, 0, child.stderr || String(child.error || 'CLI failed'));
      const steps = (await fs.readFile(output, 'utf8')).trim().split('\n').map(line => JSON.parse(line));
      conversions[name] = steps.map(step => step.step_type);
    }
    assert.deepEqual(conversions.clean, ['thought', 'tool_call', 'tool_result', 'thought']);
    assert.deepEqual(conversions.with_transport_error, ['error']);
    report.playground_conversion = { cli_sha256: cliHash, conversions };
    checks.push({ name: 'playground_transport_error_discards_codex_research_events', passed: true });
  }
  if (options['--trace']) report.local_trace = await inspect(options['--trace'], options['--submission'], options['--task']);
  await fs.mkdir(path.dirname(path.resolve(options['--out'])), { recursive: true });
  await fs.writeFile(options['--out'], JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ engine: ENGINE, checks_passed: checks.length, output: options['--out'] }));
} finally {
  globalThis.fetch = oldFetch;
  await fs.rm(temp, { recursive: true, force: true });
}
