# RC16.31bg - Memory Closure

RC16.31bg is built directly on RC16.31bf. Scope is intentionally limited to memory safety and scanner configuration observability.

## Changes

- Process-wide scheduler memory guard with default soft limit 1450 MB (`SCHEDULER_MEMORY_SOFT_LIMIT_MB`).
- Memory checkpoints are recorded through the scheduler pipeline so diagnostics can identify the phase that raises RSS/cgroup memory.
- Controlled `MEMORY_DEFERRED` exit before the Render 2 GiB hard limit when pressure is already visible between phases.
- Paper-scanner memory limit is capped by the scheduler soft limit, even if `SCANNER_MEMORY_SOFT_LIMIT_MB` is higher.
- Strategy decisions and strategy runs no longer rewrite their legacy monolithic JSON arrays on each upsert. New rows are stored as independent item documents with lightweight bounded indexes.
- Legacy strategy history remains available through bounded PostgreSQL-side JSON array reads rather than transferring the complete legacy payload to Python.
- Scanner configuration receipts now report the same effective Norway-only setting used by `scanner_worker.py`.
- No scoring, recommendation, risk, portfolio or trading thresholds changed.
