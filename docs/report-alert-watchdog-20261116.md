# Missing required report: independent liveness and useful diagnostics

On 16 November the 14:00 Oslo report started at 13:00:25 UTC. Render explicitly
reported `Out of memory (used over 2Gi)` at 13:18:24 UTC. The application retained
only its started history row and an ACTIVE diagnostic owner. SIGKILL bypassed the
Python cleanup/error handler. The missing-report notifier trusted that stale
owner and suppressed the afternoon warning until a later report replaced and
released it. The alert receipt is 22:07:03 UTC, just after evening completion.
Its displayed runtime identified the notifier's release, not the failed worker.

The corrected notifier observes the actual report advisory lock in PostgreSQL,
with a bounded native owner read. A dead owner's old ACTIVE flag cannot suppress
an alert. A genuinely held lock protects only the same job and exact scheduled
slot; a manual or different-slot report cannot hide a missed fixed report.
Database/owner uncertainty defers classification rather than asserting death.
Observation precedes delivery-history reading so completion between those reads
cannot create a false missing-report alert.

A startup check runs before the heavy coordinator lane, including cycles whose
heavy work is DEFERRED_BUSY. It uses a separate advisory lock to serialize alert
receipt handling. Native history reads never repair or rewrite scheduled-job
profiles. Successful legacy warning receipts are imported by a bounded server
projection into the small `scheduler/required_report_missing_alerts.json` row,
preventing repeat alerts without rewriting the whole configuration document.
The existing later check remains a fallback and shares this deduplication lock.

Small status: `scheduler/required_report_watchdog.json`, including check time,
owner observation, alerts sent and deployed commit. Queries have a 5-second
statement timeout and 1-second lock timeout; owner/history/trace/receipt reads
have explicit bounds. No financial journal, parameter, execution evidence or
report is changed/replayed by this observer. No paid resources are added.

Alerts prefer the stored report error, then a trace error tied to the same job
and scheduled slot. Without a stored cause, they identify loss of the process's
report lock, last registered phase and heartbeat in Europe/Oslo, and explicitly
state that the stop cause was not saved. They direct the operator to Render.
The application does not have a Render log API credential and cannot assert a
provider OOM solely from an interrupted process. Malformed diagnostic records
fall back to the warning instead of preventing it. Sensitive error values are
redacted and message details bounded. A hard-kill cause is never invented.

Verification: 21 new checks (12 unit, 9 real PostgreSQL); 66 targeted checks pass.
Tests cover killed/disconnected sessions, real long-held locks, current-owner
replacement, separate alert locking, legacy deduplication without configuration
changes, startup despite busy heavy work, invalid/missing/oversized owners,
malformed diagnostics, completion ordering and redaction. Independent review
found no remaining blockers. Full local suite: 2918 passed, 288 skipped, four
subtests passed; five unchanged baseline failures: dependency installation pins,
obsolete fake cursor, universe fixture authority, FX alert ordering and fixed-date
SEC evidence age. Required release CI validates the final submitted tree.
