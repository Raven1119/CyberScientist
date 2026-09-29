#!/usr/bin/env node
/** Invoke the pinned public deterministic checklist without either model judge. */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const SOURCE_SHA = 'afafd718c1eca6c25fa81231905988b436ff03684581d0410f8cc549599dfa46';
const sha = value => createHash('sha256').update(value).digest('hex');
const args = process.argv.slice(2);
const opts = Object.fromEntries(Array.from({ length: args.length / 2 }, (_, i) => [args[2 * i], args[2 * i + 1]]));
assert.equal(args.length, 6, 'required: --source FILE --manifest FILE --out FILE');
assert.deepEqual(Object.keys(opts).sort(), ['--manifest', '--out', '--source']);
const source = await fs.readFile(opts['--source']);
assert.equal(sha(source), SOURCE_SHA, 'public v6 source hash mismatch');
const manifest = JSON.parse(await fs.readFile(opts['--manifest'], 'utf8'));
assert.ok(Array.isArray(manifest) && manifest.length > 0);
const marker = '\nmain().catch((error: unknown) => {';
const segments = source.toString('utf8').split(marker);
assert.equal(segments.length, 2, 'upstream main marker changed');
const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'cs-checklist-v6-'));
const previousFetch = globalThis.fetch;
globalThis.fetch = async () => { throw Error('model and network calls disabled'); };
try {
  const modulePath = path.join(temp, 'scorer.ts');
  await fs.writeFile(modulePath, segments[0] + '\nexport { loadTrace, lintTrace, collectSubmissionEvidence, buildChecklistReport };\n');
  const scorer = await import(pathToFileURL(modulePath).href);
  await fs.mkdir(path.dirname(path.resolve(opts['--out'])), { recursive: true });
  const output = await fs.open(opts['--out'], 'w');
  try {
    for (const item of manifest) {
      assert.ok(/^([SA]\d{2})$/.test(item.sample) && ['cli', 'fix', 'native'].includes(item.variant));
      const raw = await fs.readFile(item.trace);
      if (item.expected_sha256) assert.equal(sha(raw), item.expected_sha256, `${item.sample} ${item.variant} hash`);
      const trace = await scorer.loadTrace(item.trace);
      const lint = scorer.lintTrace(trace);
      const task = item.task ? await fs.readFile(item.task, 'utf8') : undefined;
      const submission = await scorer.collectSubmissionEvidence(item.outputs || undefined);
      // The final fusion and policy need two private judge values. We invoke
      // neither model nor those reducers with invented values. The checklist
      // itself supplies the deterministic cap and hard-block decision.
      const report = scorer.buildChecklistReport(trace, lint, sha(raw), task, submission, undefined);
      const result = {
        sample: item.sample, variant: item.variant, trace_sha256: sha(raw),
        task_provided: Boolean(task), output_files: submission.file_count,
        format: trace.format, stats: lint.stats,
        codes: report.triggered_negative_codes,
        score: report.score, cap: report.score_cap, hard_block: report.hard_block,
        decision: report.decision,
        items: report.items.filter(x => x.polarity === 'negative').map(x =>
          ({ code: x.code, status: x.status, score_effect: x.score_effect })),
        not_observable_codes: report.not_observable_codes,
      };
      await output.write(JSON.stringify(result) + '\n');
    }
  } finally { await output.close(); }
} finally {
  globalThis.fetch = previousFetch;
  await fs.rm(temp, { recursive: true, force: true });
}
