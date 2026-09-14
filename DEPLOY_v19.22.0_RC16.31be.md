# Deploy v19.22.0-rc16.31be

Deploy DELTA over verified RC16.31bd, or deploy FULL to both web and report scheduler.

Expected live checks:
1. Both services report `v19.22.0-rc16.31be` and the same commit.
2. Next healthy retention run reports `apply_requested=true`, `apply_enabled=true`, state `PARTIAL` or `COMPLETED`, and a positive deleted count while backlog exists.
3. If `STORAGE_RETENTION_APPLY` is visible in runtime, `apply_config_source` is that variable; if Render omits it, source is `RELEASE_DEFAULT_APPLY_WHEN_ENV_MISSING`.
4. PostgreSQL recovery during scanner finalization must not produce a false hard scanner failure; next cron must resume without re-analysing completed tickers.
5. Production acceptance still requires a healthy scanner cycle plus complete 08:00/14:00/22:00 report sequence with durable JSON/PDF and Pushover.
