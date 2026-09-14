# v19.22.0-rc16.31be - Production Closure II

This release is a narrow production-stability follow-up to RC16.31bd.

- Storage retention now honors explicit Render values first, supports compatible aliases, and uses the release-level APPLY default when Render omits the single `STORAGE_RETENTION_APPLY` variable from the cron process. Explicit `false` still always disables deletion.
- Retention remains fail-closed unless authoritative PostgreSQL is healthy and writable, remains bounded by batch/time budget, and retains the protected-ledger exclusions.
- Retention diagnostics now identify the configuration source and whether the environment variable was missing.
- Wrapped PostgreSQL recovery exceptions are classified through their exception cause/context chain.
- A 30/30 scan interrupted only during storage finalization is reported as `FINALIZATION_PENDING_STORAGE` / `DEGRADED_STORAGE`, not a false analysis failure.
- A transient database recovery during an incomplete scan is reported as `DEFERRED_DATABASE`; the next cron resumes from the authoritative checkpoint.
- No scoring thresholds, portfolio limits, strategy weights, report times or trading authority are changed.
