# Journal growth and next required report — 16 November 2026

## Problem and resulting behavior

Production's current financial root was 55,575,414 stored bytes, approaching its
existing 64 MiB bound. Each financial mutation rewrote the growing combined
journal. The database itself measured 3,502,732,991 bytes. Raising memory or the
root write limit would defer the same failure.

V2 retains current account values and original event headers/hashes in the root.
Original event payloads live in immutable, period-scoped SHA-256 addressed rows.
Readers materialize one payload at a time, with at most 64 MiB encoded caching
per root and 64 MiB raw / 8 MiB stored bounds per payload. Full chain validation,
economic replay, approvals, execution evidence and financial controls continue.
Root/account deepcopies retain lazy historical references; explicit state copies
remain mutable. Each root transaction locks every historical blob it verifies.

New history is retained. Total database storage is therefore not constant:
original backup, immutable payloads, current account/trade values and small event
headers remain. This removes repeated bulk root rewrites, not legal/audit history.
The small status exposes current root/database bytes, growth since migration and
an early root-budget warning at 16 MiB, before the existing 64 MiB root bound.
No trading settings, learning observations or paid service plans change.

## Controlled activation

Deploy V2 readers to both production web and cron before setting
`RESTART_JOURNAL_PAYLOAD_ARCHIVE_ENABLED=1` on the scheduler. Existing deployment
alignment checks run before maintenance. The next natural cron invocation takes
the existing root lock, verifies the complete source, preserves its exact stored
bytes server-side, externalizes payloads, independently reads/replays the new
root, and compares canonical logical SHA-256 before one atomic commit. A failure
rolls back root, payloads, exact backup and receipt together. No financial/report
callback is run by migration. Repeating migration is idempotent.

Receipt: `scheduler/restart_payload_archive.json`. Backup:
`simulation_restarts/<period>/archive_backups/<stored-sha256>.json`.

Removing the activation flag stops future migrations; an already migrated root
stays V2. Rollback binaries must retain V2 reader support. Restoring only the
pre-migration backup after new trades would lose those later trades and is not
a valid rollback. Backups and blob rows are preserved; no automatic deletion or
archive garbage collection is introduced.

## Verification

- 104 focused checks passed with real isolated PostgreSQL, including complete
  logical identity, exact backup bytes, idempotency, injected final-verification
  rollback, corrupted blobs, ordinary Paper/Autonomy/Superportfolio engines,
  buy/stop/duplicate retry, read-only operator and concurrent blob locks.
- Exact production lifecycle command with PostgreSQL, compression and PC/mobile
  browser checks: 290 passed. Additional final archive checks above include the
  subsequently added lock/operator/source-fingerprint cases.
- Full suite: 2906 passed, 278 skipped, four subtests passed; five unchanged known
  baseline failures: installed dependency pins, obsolete fake cursor context
  manager, universe fixture authority, FX alert ordering, fixed-date SEC filing.
- Read-only independent review identified premature history deepcopy, unbounded
  representation and SHA-before-size-check issues; all corrected and retested.

Private larger-journal probe (synthetic extra receipts, never production data
writes): decoded logical root 356,447,278 bytes, 1,013 preserved events; root
44,161,342 -> 157,438 stored bytes. Complete migration replay and canonical hashes
matched `a63e85c0d8ccb874220897c231bffc853002cd627380e61bcab86831796bd538`.
Migration took 193.6 seconds, process peak RSS 1200.6 MiB. Local cgroup exposed
16 GiB and an unrelated lifetime peak, so this proves measured process memory,
not enforcement of Render's actual 2 GiB limit.
A subsequent full replay, locked identity write and semantic recheck with a
retained 650 MiB process baseline preserved that same SHA-256. Final RSS was
716.4 MiB; overall process peak remained 1200.6 MiB. Total probe time 411.8 s.

## Genuine heavy-report acceptance

Only a newly executed, fixed-slot mandatory 08/14/22 Oslo report after migration
can create `scheduler/report_cycle_acceptance.json`. It requires completed
financial assessment/Autonomy, final PDF validation, matching actual SENT receipt
and observed process plus cgroup current/peak memory <= 2048 MiB. It grants no
financial readiness and preserves source restrictions. Tests, revised/promoted
reports, old catch-up slots and zero-report cron cycles cannot satisfy it.

The scheduler records the small acceptance status each cycle; failed criteria
are visible in a bounded breadcrumb. Until actual production acceptance exists,
status is `WAITING_FOR_HEAVY_REPORT`. No test is described as real report proof.
