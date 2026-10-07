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
