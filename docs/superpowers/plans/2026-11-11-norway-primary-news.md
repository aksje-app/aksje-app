# Norwegian primary news implementation plan

Spec: docs/superpowers/specs/2026-11-11-norway-primary-news-design.md
Goal: restore dated, correctly identified Norwegian disclosure news using one PR and one final CI run.

- [x] Record current focused baseline and RED regression cases.
- [x] Add services/norway_primary_news.py: strict bounded instrument/issuer parsing, minute-precision CET/CEST publication, original observation time, 50-entry/256KiB per-instrument persistent cache, 2MiB response and two-request limit.
- [x] Integrate in news_intelligence.fetch_news_intelligence and enrich_rows, forwarding ISIN/MIC and retaining source scope/provenance. Use primary evidence first, preserve RSS and other gates.
- [x] Block production Developer/free NewsAPI requests before cache or HTTP; label the reason truthfully in news/insider diagnostics and health.
- [x] Verify edge cases, replay the three privately captured real issuer pages, run complete checks once changes are stable, and request one independent final review. Fix important findings RED/GREEN before opening the PR.
- [ ] One exact-head CI, merge and deploy both existing services. Observe health/runtime and available normal receipts; never force trades or a financial report to prove coverage.

Review focus: wrong issuer/market/symbol, future or missing dates, headline-only represented as full text, cached observation time rewritten, stale empty windows labeled complete, cache/payload growth, production free-plan calls, absence mistaken for evidence. The source is company-controlled disclosure and not independent journalistic corroboration.

Ruling: use the issuer See All link derived from verified product metadata (two bounded requests), rather than only the five-item instrument widget, because the issuer listing provides precise CET/CEST dates and an observable lower window bound. No guarantee is made beyond returned rows.
Ruling: activation requires the small normal-cron source probe; deployment alone did not prove Render could reach the source. No new job/schedule or forced financial run.

Final review: one independent whole-branch review completed. Important findings were fixed in one RED/GREEN pass: disable redirects before a second HTTP send; retain original issuer publisher and count only relevant retained RSS hits for independent-source credit; require complete runtime, identity, timestamp and listing evidence for production acceptance. Malformed probe retry timestamps fail closed without crashing cron. 112 focused tests passed with PostgreSQL 18 after fixes.
Ruling: acceptance-receipt completeness was regraded Important because missing proof could activate a source in production. It is fixed rather than deferred.
Final verification after the single review fix pass: full local suite 2761 passed, 268 skipped, 4 subtests passed; the four documented pre-existing baseline failures are unchanged. No workflow checks or financial gates were waived.
