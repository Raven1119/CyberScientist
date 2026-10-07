# CS-UP-11 initial collector review

Baseline: `068c3637238ae7647bb15e371642df38510beea0`.
Initial reviewed slice: `0415bc3`; this review does not assert W1–W5 completion.

## Standards

The independent review found a credential-container gap: sensitive dictionaries
and lists were traversed without preserving their credential context. The entire
sensitive field is now redacted, including numeric passwords. Earlier findings
for prefixed opaque access keys and credential-bearing JSON keys were also fixed.
Regression tests cover these cases and replacement-key collisions. No blocking
Fowler heuristic findings were reported.

## Spec

The independent review found three initial defects: premature pagination success
on an empty page, omitted detail requests for display/scientific-only scores, and
unredacted JSON keys. All are fixed. Incomplete pagination preserves partial rows
and records failure. A real zero remains eligible for detail collection.

No unauthorized application-code changes were found. No review agent requested
the platform or accessed the production ledger. The source and data deliveries
are separate: others' traces and archives remain outside this public repository.

## Additional verification

A long uninterrupted text run exposed quadratic email matching during archive
sanitization. Email matching now bounds valid address components, and a million
character regression case runs with the other analysis tests. Public 404s retry
once before recording failure; bundle selection can then advance in rank under
the user's explicit instruction. Actual API coverage is recorded in the private
dataset, independently of these fake regression tests.

## Incremental extraction and replica review

Two independent read-only reviews covered semantic/features/forms extraction,
pinned v6 packet reconstruction, frozen calibration and privacy persistence.
Fixed findings: digest-isolated archive extraction with the same hash/read buffer;
ZIP errors cannot persist raw member names; embedded envd token assignments are
scrubbed; model-cache hits are scrubbed again; all holdout predictions are required
for acceptance; only complete training cohorts can enter model selection; single
input CLI loads the frozen selected mapping; empty or malformed missing-evidence
arrays retain v6 behavior; decimal rounding matches JS binary toFixed boundaries.

The revision-3 data rescan found 20 credential-shaped assignment occurrences across
12 persisted files (three public traces and their cached/prepared derivatives).
Current copies were corrected. Two affected trace files also existed in an earlier
private commit; its history requires owner follow-up. No force push, credential
validation or credential use was performed. A malformed nested archive cannot be
fully inspected as a ZIP and remains an explicit evidence limitation.

46 analysis tests passed after these fixes; compileall and diff whitespace checks
passed. Fake privacy/policy regressions do not establish real platform input parity
or eliminate the recorded private-history follow-up.

## 输入冻结与截断复核补充

修复重复校准先覆盖 packet 后检查哈希的问题：暂存比较、冻结字节复核、单运行互斥；未重新执行历史校准。截断缓存绑定轨迹来源、完整正文、声明、题面和 v6 packet，源变化保留旧版；仅 packet 变化重算偏移而不新增模型调用。每个 chunk/声明必须恰好一个有效答复，缺漏/重复保持 unknown，原生 content/item/parts 正文完整保留。新增反例后本地测试 53 passed。校准选择规格偏差及留出暴露限制另见校准报告。

## Attribution and delivery coverage

Versioned semantic evidence projection preserves frozen extraction bytes and records every claim's source type, exact-quote status and explicit scientific-verification unknown. Staged-object privacy auditing is tested against concurrent working-tree changes. Model usage counts unique successful request receipts, with failed/cancelled billing explicitly unknown. Comparison and analysis coverage include uncollected, empty and non-v8 selected attempts. The data dictionary includes primary JSON/JSONL top-level columns as well as CSV/Parquet. 67 analysis regressions pass; compileall and diff checks pass. These checks do not resolve the earlier private-history credential follow-up.

## Full snapshot and bounded output repair

The completed public snapshot contains 60 topics, 22,921 non-draft list rows and 22,910/22,910 eligible detail GETs, with zero failures. Four additional current-rule IDs are appended without rewriting frozen selection or calibration. The expanded deterministic comparison covers 7,620 selected traces, including empty and unavailable evidence in its denominators. Rhythm denominators retain 13 unknown head-author patterns and 587 assessable patterns. Environment heads use the full detail snapshot rather than the earlier frozen leaderboard.

Three long semantic extractions reached the output-length limit. Persistent negative caching now prevents identical known-truncated requests from being billed again; a changed token budget or bounded concise-output prompt has a different request hash. Complete source input and successful segment caches are retained, existing outputs stay unchanged, and all repairs remain bounded. Independent read-only review found no new blocking issue. All 74 analysis tests, compileall and whitespace checks pass. These checks establish local regression behavior, not semantic accuracy or worker input parity. The frozen 20-record audit and failed calibration acceptance gates remain unchanged.

## Final data verification

Private data revision `6ee216d7225e6a76429e4d1db493583f4caa2592` contains all 7,620 selected traces and 7,333 semantic records (5,053 public-empty unknown). Validation joins every selected ID/ours label, checks all 989,611 event identities, verifies 6,618 truncation input fingerprints with zero failed chunks, and preserves the frozen 60-sample calibration/manual packet SHA. No model worker remains. The final staged-object audit read 23,188 files / 368,744,411 bytes, with zero issues under the current signatures.

The recorded private-history credential incident remains unresolved by this pass. An earlier local process diagnostic also exposed a VSCode connection-token argument in tool conversation output; no value is repeated, used or copied into the repositories. Historical revocation/cleanup and possible local-session token renewal remain owner follow-up. The delivered source/data validation does not certify scientific truth, hidden worker input parity or total billing.
