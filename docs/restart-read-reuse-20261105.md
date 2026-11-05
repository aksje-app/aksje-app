# Repeated restart-bundle decoding, 2026-11-05

Status: implementation under test; production acceptance is pending a complete measured run. No historical or trading-policy data is removed or rewritten by this change.

## Cause and baseline

The ordinary Paper scanner calls `paper_store.load_portfolio()` before candidate evaluation and at several risk/position checks. That calls `production_routing.view('paper')`, then `production_restart.selected()`. Each selection reads and verifies the single bundle containing all three accounts, although these callers only need the current Paper account projection. The same read path is used by other ordinary portfolio consumers. Transactional reads are separate and remain necessary.

The completed production scheduler instance `crn-d9reb42jobas73d8k500-ckrfj` ran 17:31:06–17:49:29 UTC: 51 logged full bundle reads, payload 101.7–101.8 MiB, Paper scanner COMPLETED, cgroup peak 1532.6 MiB, process peak RSS 1518.0 MiB, hard limit 2048 MiB. That historical count excludes previously uninstrumented locked mutation decodes. An additional baseline job `job-dbmeg3l9fdbs738kr9j0` on source `9b052ad05426271221b5c9ce3d54741759de75c8` instruments both read and locked-mutation callers. It completed 20:36:34–20:41:29 UTC with 6 reads, 0 locked mutations and a 1586.1 MiB cgroup peak (1480.2 MiB peak RSS). Paper was under its existing scan policy, so this is a maintenance workload baseline, not a completed scanner acceptance. The caller trace also confirmed duplicate Paper reads inside `controlled_parameter_learning.learning_evidence_summary()` (closed trades and counterfactual replay). A skipped/deferred cycle alone is not sufficient acceptance.

## Reuse and invariants

Only detached per-account **read views** are reused inside one scheduler/scanner scope. No bundle, account journal, signed trading selection or transaction result is kept in the cache. At most 8 MiB of serialized views is retained; large views and unverified NAV are not cached. Callers receive detached copies. The scope is discarded after the run.

Before every hit, PostgreSQL supplies the live route and row identities (`xmin`, `ctid`) without fetching/detoasting the bundle. An independent financial/control write, STOP/RESUME, route change, deletion or replacement invalidates reuse. Both route and bundle identities are checked again after building a view; concurrent changes fail closed. Database errors are propagated. Installation and the current certificate fingerprint are checked on hits. A verified NAV is never reused past the existing five-day price/FX evidence ceiling or after a backward clock adjustment. Local/custom storage retains the original uncached path.

`selected()`, signature checks, complete bundle verification/replay, journal-prefix checks, advisory/row locks, idempotency and transactional commits remain authoritative and unchanged for writes. Legacy-write prohibition checks now read only the small route: any published route, including a broken/foreign/paused one, forbids a parallel legacy book without loading a bundle merely to reject the write. This check never authorizes trading. Market quote freshness and all trading parameters remain unchanged. Financial writes do not consume UI snapshots. `restart_reporting.snapshot()` now builds the requested family's report only; full bundle integrity verification remains in place, and the default multi-account report remains unchanged.

Every full restart JSON decode now emits `RESTART_JSON_LOAD`, distinguishes `read` and `locked_mutation`, records bytes and a bounded code-only caller aggregate, and counts successful decodes even when a later transformation rolls back. UTF-8 measurement uses bounded chunks, avoiding an instrumentation-induced extra 100 MiB allocation. Scheduler receipts and final logs include these counters, account-reuse hits/misses/invalidations, and actual process/cgroup memory peaks.

## Acceptance

Unit coverage includes 100 candidate reads with one miss, detached results, revision invalidation, certificate replacement, DB failure, concurrent change, cache budget, valuation deadline and rolled-back decode accounting. The isolated signed PostgreSQL lifecycle verifies real MVCC invalidation, an independent connection, STOP invalidation, fresh signature failure after corruption, and 100 reads with one bundle decode. The complete Release Gate, including unchanged financial/security lifecycles and the retained 92 MiB journal memory acceptance, must pass before promotion.

Production acceptance requires the deployed source SHA, completed full scheduler/report identifiers, both decode kinds/callers, actual reuse counts and peak memory below 2048 MiB. Report workload differences explicitly; do not present a market-closed or cooldown-only run as equivalent to a completed scanner/report. Append final observed evidence to the existing PR #190; do not create a new PR for this fix.
