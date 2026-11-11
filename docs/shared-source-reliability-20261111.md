# Shared source reliability

One PR covers source request coordination, persisted Retry-After, cache reuse and source-search diagnostics. It does not change financial approvals, trading parameters, evidence requirements or historical learning data.

## Failure modes and correction

The old NewsAPI client recorded Retry-After but did not gate later requests; its thread lock, counters and cache were local to each service filesystem. Failed/uncertain HTTP calls were charged only after receiving a response, and identical query parameters were cached separately for each purpose. Source status inference matched the substring `rate`, so a corporate parsing error could be mislabeled as a rate limit. These are reproducible code defects, not proof that every historical RATE_LIMITED count was an HTTP 429.

PostgreSQL coordination uses a credential-scoped session advisory lock and the existing app_kv_store. Request reservations are committed before HTTP, and the session lock survives commits and releases on connection close. Concurrent owners defer without sending a request. Health reads committed state without acquiring the source request lock. Database/coordination failures never trigger local uncoordinated requests. Local development uses a file lock.

Provider counters are small; per-query cache rows are at most 512 KiB and retained at most 400 per credential. Cleanup touches only that credential's source_cache namespace. No growing cache monolith or new worker is introduced. Query identity excludes consumer purpose and includes a credential hash; credentials are never stored. Cache TTL and credential isolation remain enforced. Retry-After supports seconds and HTTP dates, persists across UTC rollover, and uses a 60-second fallback for invalid/missing headers. Uncertain transport remains charged.

The first shared-budget day has unknown earlier provider usage. It is conservatively reserved rather than resetting a live quota. The receipt/health exposes `handoff_pending` and `UNKNOWN_PRIOR_QUOTA_USAGE`; new NewsAPI HTTP requests resume after the next UTC day starts (01:00 Europe/Oslo in November). Other sources continue. This is a deliberate one-time availability cost, not evidence that the provider actually exhausted its quota. Once the ledger exists, restarts/deploys preserve it. Only the source provider namespace is written.

Pushover includes source-search counts (hits, no hits, failures, not searched) before verbose runtime metadata, using the report's canonical source summary. Cooldown/coordination deferrals are explicitly not searched, and source errors are not mislabeled as missing credentials. Insider discovery retains its secondary-source role. A found article never becomes verified insider transaction evidence automatically.

## Subscription assessment

NewsAPI's pricing page, retrieved 11 November 2026, states Developer has a 24-hour article delay, 100 requests/day, and is for development/testing only; staging and production require a subscription. Source: https://newsapi.org/pricing . The app's plan label says Developer, but that label does not prove the actual account subscription. No subscription is purchased or upgraded by this PR. The existing conservative client cap of 50 requests/day is retained pending verified entitlement and actual needs.

## Verification

31 existing focused baseline tests passed. Regression tests were observed failing for cooldown, cross-purpose reuse, uncertain HTTP accounting, corporate-error classification, truthful reporting and malformed counter handling. The combined focused set passed 56 tests, including real PostgreSQL session-lock, bootstrap, shared cache/quota and bounded-cache tests.

One complete local suite checkpoint: 2726 passed, 261 skipped, 4 subtests passed; four unchanged baseline failures: `test_production_roots_and_complete_lock_are_exact_and_installed` (local dependency pins), `test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch` (FakeCursor context manager), `test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master` (universe authority fixture), `test_new_breach_sends_pushover_after_configuration_change` (time-dependent FX alert). Final exact-head CI and production evidence are recorded in the PR.

The historical report's individual SOURCE_ERROR provider causes still require source records; the Render read-only connector was temporarily returning Internal error during this investigation. Unknown causes must not be marked fixed. The next ordinary full reports must demonstrate source coverage separately from the database repair in PR201.
