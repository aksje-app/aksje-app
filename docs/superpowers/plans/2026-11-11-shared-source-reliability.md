# Shared source reliability implementation plan

Goal: one PR for persistent NewsAPI cooldown, cross-service quota/cache coordination and honest source diagnostics. Build on existing PostgreSQL app_kv_store and existing evidence status contracts; no new worker, paid plan, financial rule or additional reporting pipeline.

Design: a credential-scoped PostgreSQL session lock coordinates small budget records and bounded per-query cache rows. Reserve request count before HTTP, commit without releasing the session lock, and retain cooldown across requests, processes, deploys and UTC rollover. Identical requests share results regardless of consumer purpose. Explicit local development uses file locks. Production database errors fail closed. Cache is limited to 400 rows per credential and 512 KiB per row. A new shared budget with unknown prior usage conservatively reserves the initial UTC day; next UTC day starts normally. Cached/other-source data remain usable. No claim that NewsAPI alone resolves official-source failures or trading evidence.

## One deliverable: coordinated source requests and truthful diagnostics

- [x] Run existing focused baseline once.
- [x] Add regression tests for persisted Retry-After (seconds/date/malformed), concurrent clients, cache reuse across purposes, uncertain HTTP accounting, bootstrap, UTC rollover and malformed/failed source coordination.
- [x] Implement services/newsapi_coordination.py, integrate newsapi_budget.py, propagate attempted/status diagnostics through news and insider discovery. Preserve safety gates and report-level caps.
- [x] Test source-error classification and existing evidence/report contracts together; investigate the previously recorded source failures without pretending to fix unknown providers.
- [ ] One whole-branch review, one complete local suite, one exact-head CI run, merge and deploy both services. Additional CI only if a real failure requires a code change.
- [ ] Verify real production coordination state and normal service health without forcing trades or reports. Document provider-plan freshness assessment and any quota handoff wait.

Review focus: lost/uncertain reservations; simultaneous clients; cooldown at UTC rollover; cross-credential cache isolation; database outages never causing uncoordinated HTTP. Initial shared-budget bootstrap must not reset unknown provider usage.

Execution record: isolated worktree reused, base 5b37448c. One whole-branch reviewer identified three important cases; all reproduced RED and fixed GREEN. Minor deferred: same-process health waits for the existing request RLock; cross-service committed-state health reads remain independent of the PG request lock. Full-suite baseline failures remain documented in shared-source-reliability-20261111.md. No financial records or paid subscription changes.
