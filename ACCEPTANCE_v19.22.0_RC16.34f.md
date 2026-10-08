# rc16.34f Activation history memory

## Observed incident
Render web service restarted on 2026-10-07 around 23:16 UTC after a memory-limit notification. Logs show repeated 27.3–27.5 MiB activation-history reads and process RSS rising from 620.1 to 999.4 MiB. Minute-resolution Render metrics do not capture the actual limit crossing, so this is a confirmed allocation problem and plausible contributor, not proof of the sole OOM cause.

## Change
New activation analyses use independent documents and an atomically updated metadata index. Latest reads fetch at most one candidate from each of the new/legacy sources. History merges timestamp-ordered, deduplicated pages, supporting offsets with at most 500 results. Old collections remain unchanged and old IDs remain retrievable. PostgreSQL transfers only selected rows; the local fallback streams individual records rather than decoding the monolith. No portfolio or trading-policy changes.

## Validation
- 36 focused tests passed, including old activation/account/execution tests and prior bounded repository contracts.
- Seven new regression tests cover preservation, ordering and mixed-source pagination; concurrent saves; index-write failure; local streaming/Unicode; parameter-bound PostgreSQL queries; and database failure without local fallback.
- A 40 MiB legacy collection latest read used 1.77 MiB peak Python allocations, below the regression ceiling of 6 MiB. This is a synthetic read test, not a whole-app memory measurement.
- All 24 release contract checks passed. Syntax and diff checks passed.
- Two predecessor release-identity checks initially rejected the new release letter; updated successor expectations and both passed on rerun.
- Broad CI regression and active repository suites must pass before merge. Render deploy and live OOM verification are pending.

## Deploy and rollback
No destructive migration is required. Deploy latest main after merge. Check activation view/history and memory under repeated refresh. Monitor the web service separately from the cron service. Legacy history is retained, but older releases cannot discover newly indexed analyses; rollback should keep this repository/storage fix or explicitly read indexed documents. Do not rewrite the monolith to implement rollback.
