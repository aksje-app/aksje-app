# Repeated restart-bundle decoding, 2026-11-05

## Cross-account follow-up, 2026-11-06

The successful 02:00 production cron still decoded the same 126,054,514-byte
bundle four times: once for Superportfolio, once for Autonomy, once for Paper
learning evidence, then a fresh read for UI publication. Its actual cgroup peak
was 864.4 MiB, below 2048 MiB; `OOM_BREADCRUMB` is diagnostic telemetry, not an
OOM event. The remaining duplication was across distinct account cache keys.

A fresh selection now prepares other selected accounts' detached projections
from the same fully verified bundle. Each account independently requires a
matching current route, installation and signed grant. Cache entries bind to
the bundle row version observed **before** the original read; the complete
read window and each additional route are checked before installation. No
bundle/journal/selection is retained, and all projections share the existing
8 MiB total serialized budget and valuation/clock bounds. Broken unrelated
controls are never cached; their own read still fails through normal validation.
Different periods cannot share these projections. Backend failures propagate.

Financial selections and locked transactions remain fresh. UI publication
intentionally retains its independent final full verification. The expected
unchanged-revision cron cost is therefore two full JSON decodes rather than
four; source/control mutations invalidate projections as before. Production
acceptance requires the exact-source Release Gate and another measured full
Autonomy/report/Pushover workload under 2048 MiB, with before/after account
projection hashes and native decode counters recorded in existing PR #190.

Status: implementation under test; production acceptance is pending a complete measured run. No historical or trading-policy data is removed or rewritten by this change.

## Cause and baseline

The ordinary Paper scanner calls `paper_store.load_portfolio()` before candidate evaluation and at several risk/position checks. That calls `production_routing.view('paper')`, then `production_restart.selected()`. Each selection reads and verifies the single bundle containing all three accounts, although these callers only need the current Paper account projection. The same read path is used by other ordinary portfolio consumers. Transactional reads are separate and remain necessary. A further lifetime issue in `StorageService.read_json()` kept the libpq cursor result alive during `json.loads()` even after closing its connection; a fetched Python string and the complete native result could overlap the decoded object graph. The cursor now closes explicitly before decoding, matching the transactional adapter's existing cleanup discipline.

The completed production scheduler instance `crn-d9reb42jobas73d8k500-ckrfj` ran 17:31:06–17:49:29 UTC: 51 logged full bundle reads, payload 101.7–101.8 MiB, Paper scanner COMPLETED, cgroup peak 1532.6 MiB, process peak RSS 1518.0 MiB, hard limit 2048 MiB. That historical count excludes previously uninstrumented locked mutation decodes. An additional baseline job `job-dbmeg3l9fdbs738kr9j0` on source `9b052ad05426271221b5c9ce3d54741759de75c8` instruments both read and locked-mutation callers. It completed 20:36:34–20:41:29 UTC with 6 reads, 0 locked mutations and a 1586.1 MiB cgroup peak (1480.2 MiB peak RSS). Paper was under its existing scan policy, so this is a maintenance workload baseline, not a completed scanner acceptance. The caller trace also confirmed duplicate Paper reads inside `controlled_parameter_learning.learning_evidence_summary()` (closed trades and counterfactual replay). A skipped/deferred cycle alone is not sufficient acceptance.

## Reuse and invariants

Only detached per-account **read views** are reused inside one scheduler/scanner scope. No bundle, account journal, signed trading selection or transaction result is kept in the cache. At most 8 MiB of serialized views is retained; large views and unverified NAV are not cached. Callers receive detached copies. The scope is discarded after the run.

Before every hit, PostgreSQL supplies the live route and row identities (`xmin`, `ctid`) without fetching/detoasting the bundle. An independent financial/control write, STOP/RESUME, route change, deletion or replacement invalidates reuse. Both route and bundle identities are checked again after building a view; concurrent changes fail closed. Database errors are propagated. Installation and the current certificate fingerprint are checked on hits. A verified NAV is never reused past the existing five-day price/FX evidence ceiling or after a backward clock adjustment. Local/custom storage retains the original uncached path.

`selected()`, signature checks, complete bundle verification/replay, journal-prefix checks, advisory/row locks, idempotency and transactional commits remain authoritative and unchanged for writes. Legacy-write prohibition checks now read only the small route: any published route, including a broken/foreign/paused one, forbids a parallel legacy book without loading a bundle merely to reject the write. This check never authorizes trading. Market quote freshness and all trading parameters remain unchanged. Financial writes do not consume UI snapshots. `restart_reporting.snapshot()` now builds the requested family's report only; full bundle integrity verification remains in place, and the default multi-account report remains unchanged.

Every full restart JSON decode now emits `RESTART_JSON_LOAD`, distinguishes `read` and `locked_mutation`, records bytes and a bounded code-only caller aggregate, and counts successful decodes even when a later transformation rolls back. UTF-8 measurement uses bounded chunks, avoiding an instrumentation-induced extra 100 MiB allocation. Scheduler receipts and final logs include these counters, account-reuse hits/misses/invalidations, and actual process/cgroup memory peaks.

## Acceptance

Unit coverage includes 100 candidate reads with one miss, detached results, revision invalidation, certificate replacement, DB failure, concurrent change, cache budget, valuation deadline, clock rollback into the initial validation window, cursor-result cleanup before decoding, and rolled-back decode accounting. The isolated signed PostgreSQL lifecycle verifies real MVCC invalidation, an independent connection, STOP invalidation, fresh signature failure after corruption, and 100 reads with one bundle decode. The complete Release Gate, including unchanged financial/security lifecycles and the retained 92 MiB journal memory acceptance, must pass before promotion.

Production acceptance requires the deployed source SHA, completed full scheduler/report identifiers, both decode kinds/callers, actual reuse counts and peak memory below 2048 MiB. Report workload differences explicitly; do not present a market-closed or cooldown-only run as equivalent to a completed scanner/report. Append final observed evidence to the existing PR #190; do not create a new PR for this fix.

Intermediate deployed a830 benchmark: 10 identical Paper reads needed 1 complete decode in 20.101 seconds (baseline 10 / 147.876 seconds), with exactly the same projection hash. Peak cgroup memory was 881.4 MiB versus 852.4 MiB baseline; the shared bundle had grown during the ordinary evening run. This is evidence of lower read amplification/time, not lower first-decode peak. Final cursor-lifetime and clock-boundary fixes require a fresh complete Release Gate and final production measurements. The ordinary pre-deployment evening cron 21:01:16–21:25:41 completed its report and scheduler with warnings and peaked at 1875.5 MiB / 2048 MiB, providing a contemporary full-workload memory baseline.
