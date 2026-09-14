# RC16.31bh - OOM Root Cause Closure

Base: `v19.22.0-rc16.31bg`.

This release is deliberately limited to production memory safety. It does not change scoring, recommendation thresholds, risk limits, portfolio rules or trade authorization.

## Changes

- `scheduled_runner.py` marks the process as scheduler before the storage layer is imported.
- `StorageService.read_json()` measures PostgreSQL payload size before fetching the full payload. Large reads are logged with key, payload MB and process RSS.
- In scheduler context, known legacy repository monoliths are blocked before their full payload is transferred into Python memory. This converts a potential multi-GiB allocation into an explicit diagnostic failure instead of a Render OOM kill.
- Market snapshot history no longer falls back to a full `repositories/market_snapshots.json` read. Legacy rows are fetched with bounded PostgreSQL-side array slicing.
- Strategy orders, fills and account snapshots now use bounded indexed item storage, matching the memory-safe pattern already used for strategy decisions and runs.
- New item indexes are bounded to prevent the replacement index itself from growing without limit.

## Live acceptance target

A full Render cron must complete without `Out of memory (used over 2Gi)`. If an unconverted legacy path still attempts a huge read, the log must show `LARGE_JSON_READ` and/or `Scheduler blocked legacy monolith read` with the exact key before the process can exceed the Render limit.
