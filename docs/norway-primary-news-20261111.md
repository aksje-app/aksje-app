# Verified Norwegian disclosure news

The evening report MI-20261110-220809 had valid market data for 60 candidates but no decision-valid news. Yahoo company news had 2247 consecutive recorded failures. The pinned yfinance 1.6.0 company-news POST reproduced a 404/maintenance response outside Render. An alternative Yahoo GET worked for AAPL but returned no VEI news; Yahoo's VEI RSS contained only news older than the 14-day window. E24's five raw hits were rejected as unrelated to their target companies. Raising an API cap would not establish useful coverage.

## Primary source and bounds

The old generic Euronext page dropped its name-search query on redirect. The new collector requests the exact instrument using the existing ticker/ISIN/MIC tuple, validates the exchange's own instrument metadata and canonical URL, then follows only that instrument's same-host issuer listing link. Every row must match the issuer. It rejects malformed, future or unordered dates, invalid/duplicate identities, redirects, maintenance responses and oversized pages.

At most two HTTP requests, 2 MiB per response, 50 listing records and 256 KiB per cache document. A one-hour per-instrument cache uses existing authoritative storage. Cache reads revalidate identity and publication/observation times; a cache hit keeps its original observation timestamp. No new worker/table, all-universe scan, large JSON document or financial mutation is introduced. Returning to the source after expiry is a new observation, not historical reconstruction.

Only dated disclosure headlines are collected; article bodies are not downloaded or claimed. CET/CEST is checked against the calendar and converted to UTC at source minute precision. The publication time, observation time, source-document ID, source URL, ISIN/MIC and HEADLINE_ONLY scope survive enrichment. The source is issuer-controlled disclosure, not independent journalism. The time-window completion flag applies to the returned disclosure listing, not all possible company news or a complete historical archive.

Verified primary coverage is used before the broken Yahoo news path. RSS remains available. Wrong identity, failed sources and missing/invalid data stay explicit. Existing evidence relevance rules, scoring formulas, thresholds, signed controls and trade permissions are unchanged. A genuine completed check with no disclosures is handled by the existing CHECKED_NO_EVENTS contract; a missing/invalid listing never becomes a successful empty search.

## Production acceptance

The existing cron runs a source-only probe for VEI.OL, MORLD.OL and SNTIA.OL once per collector schema. It writes only source-cache and acceptance metadata, skips outside production, defers under memory pressure, and retries failures at most once a day. Failed acceptance stays a cron warning. Production news enrichment requires its positive receipt; pending cached results use a different cache identity so acceptance can take effect immediately. No report, strategy or trade is forced by the probe.

The user believes NewsAPI is free. Consistent with its configured Developer label and the provider's documented restrictions, Developer/free requests are blocked when APP_ENVIRONMENT is production, before cache or HTTP. Plan-specific diagnostics are retained. This does not assert verified access to the billing account. No subscription change or paid API call is made. Actual paid entitlement can be reflected in configuration if subsequently confirmed.

## Verification

Regression tests were observed failing for identity, timezone/date validation, response bounds, corrupt cached identity, impossible cached availability, source propagation, production plan enforcement, malformed acceptance receipts, nonproduction probe isolation and cron warning persistence, then passing after correction.

99 focused tests passed against disposable PostgreSQL 18. The full local suite checkpoint passed 2750 tests, skipped 267 and passed 4 subtests. Four unchanged baseline failures remain: test_production_roots_and_complete_lock_are_exact_and_installed (local dependency pins), test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch (old FakeCursor), test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master (existing universe authority fixture), test_new_breach_sends_pushover_after_configuration_change (time-dependent FX alert). No check is relaxed.

Captured real product/issuer pages were replayed privately, with input hashes and file-creation observation upper bounds: VEI 3 fresh headlines, MORLD 8 and SNTIA 8; all three listings crossed the requested 14-day lower bound. These are offline capture replays, not proof of production connectivity, actual trades, returns or full-market coverage. Exact-head CI, one independent review and production probe evidence are recorded in the PR/issue 200.
