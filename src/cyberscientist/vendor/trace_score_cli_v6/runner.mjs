#!/usr/bin/env node
// Invoke only the pinned public deterministic functions; never call judges.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const sourcePath = new URL('./index.ts', import.meta.url);
const sha = value => createHash('sha256').update(value).digest('hex');
const source = await fs.readFile(sourcePath);
assert.equal(sha(source), 'afafd718c1eca6c25fa81231905988b436ff03684581d0410f8cc549599dfa46');
const [tracePath, taskPath, outputsPath, reportPath] = process.argv.slice(2);
assert.ok(tracePath && taskPath && outputsPath && reportPath && process.argv.length === 6);
const marker = '\nmain().catch((error: unknown) => {';
const parts = source.toString('utf8').split(marker);
assert.equal(parts.length, 2);
const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'cs-checklist-'));
globalThis.fetch = async () => { throw Error('network and model calls disabled'); };
try {
  const modulePath = path.join(temp, 'scorer.ts');
  await fs.writeFile(modulePath, parts[0] + '\nexport { loadTrace, lintTrace, collectSubmissionEvidence, buildChecklistReport };\n');
  const scorer = await import(pathToFileURL(modulePath).href);
  const raw = await fs.readFile(tracePath);
  const trace = await scorer.loadTrace(tracePath);
  const lint = scorer.lintTrace(trace);
  const task = await fs.readFile(taskPath, 'utf8');
  const submission = await scorer.collectSubmissionEvidence(outputsPath);
  const report = scorer.buildChecklistReport(trace, lint, sha(raw), task, submission, undefined);
  const lengths = trace.events.map(event => event.text.replace(/\s+/g, ' ').trim().length);
  await fs.writeFile(reportPath, JSON.stringify({
    visibility: {status:'observed', unit:'UTF-16 after whitespace folding',
      event_count:lengths.length, over_900:lengths.filter(n => n > 900).length,
      over_900_ratio:lengths.length ? lengths.filter(n => n > 900).length/lengths.length : null,
      max_chars:lengths.length ? Math.max(...lengths) : 0,
      key_evidence_in_first_900:'unknown_without_semantic_and_worker_input_evidence'},
    trace_sha256: sha(raw), format: trace.format, stats: lint.stats,
    paired_tool_calls: lint.tool_schema.matched_call_ids,
    codes: report.triggered_negative_codes, score: report.score,
    cap: report.score_cap, decision: report.decision, hard_block: report.hard_block,
    items: report.items.filter(item => item.polarity === 'negative').map(item =>
      ({ code: item.code, status: item.status, score_effect: item.score_effect })),
  }));
} finally {
  await fs.rm(temp, { recursive: true, force: true });
}
