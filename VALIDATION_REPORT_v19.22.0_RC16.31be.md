# Validation Report v19.22.0-rc16.31be

## Scope
Production-closure follow-up to RC16.31bd based on the 2026-09-04 live PostgreSQL recovery and storage-retention diagnostics.

## Corrected findings
- Retention no longer silently becomes DRY_RUN when Render omits only `STORAGE_RETENTION_APPLY` from the cron process. Explicit environment values still take precedence; explicit false always disables deletion.
- The release default is APPLY because the operator explicitly enabled retention. Deletion remains fail-closed unless authoritative PostgreSQL is healthy, and remains bounded by the configured batch/time budget and protected-ledger exclusions.
- Retention diagnostics expose configuration source, missing-env state, raw/normalized value, parsed value and effective apply state.
- Wrapped `StorageUnavailableError` exceptions now inspect their cause/context chain, so PostgreSQL recovery is recognized even when the outer error text is generic.
- A completed 30/30 scan interrupted during finalization reports `FINALIZATION_PENDING_STORAGE` and overall `DEGRADED_STORAGE`; an incomplete scan interrupted by transient PostgreSQL recovery reports `DEFERRED_DATABASE`. Both are retryable and do not masquerade as analytical failures.

## Local verification
- `python -m compileall -q .`: PASS.
- Production-closure targeted tests (RC16.31bd + RC16.31be): 12 passed, 0 failed.
- Full pytest collection attempted: blocked by missing build-environment dependency `yfinance`; no product test failure was observed before collection stopped.
- DELTA policy: runtime-only, three changed production files.
- No score thresholds, portfolio/risk limits, report times, strategy weights or trading authority changed.

## Live acceptance still required
Production status requires Render evidence of effective retention deletion, a healthy scanner cycle, and a complete 08:00/14:00/22:00 report sequence with durable JSON/PDF and Pushover, with no unresolved recovery receipt or duplicate authoritative report.
