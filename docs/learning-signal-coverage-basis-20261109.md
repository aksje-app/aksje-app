# Signal coverage and consistent forward research — 2026-11-09

The user authorized repairing the existing learning process after the source/coverage audit. This change keeps one observation engine, the existing daily/weekly maintenance and the existing 120-observation limit. It does not create a worker, a cron job, a trade, a parameter promotion or a full historical backfill.

## Coverage independent of sampling

Every scheduled, non-test report that passes the existing final release gate writes one small immutable census of all STRICT and MODERATE recommendation occurrences. Its key hashes the original report identity; its content binds signal time, instrument, recommendation group, snapshot identity and documented reference fields. A reference price is never represented as an executed fill. Missing/conflicting price identity is recorded explicitly without losing the recommendation itself.

The census is independent of the capped outcome sample. It allows reconstruction of later recommendations even when a ticker is already active. Sampling now permits a new group or new measurement method for an existing ticker, fixing the VEI control-to-buy omission while preserving the earlier observation. Repeated same-group appearances within V2 remain one active sample; repeated occurrences remain in the report census and must not be counted as independent trades. No old source row is relabeled retrospectively.

Each census is limited to 500 recommendation instruments and 256 KiB. Exceeding either budget fails explicitly; the list is never silently truncated. Immutable read-back detects same-report content conflicts. A successful census and a successful sample write are distinct facts. Report code captures `signal_available_at` after the existing final gate and requires it for census commits. A long-running report cannot use an opening before its qualified recommendation was available. The report's final persisted run contains a separate post-gate `learning_registration_receipt`; canonical content and already-built PDF/text retain their truthful pre-gate preview and are not mutated into conflicting copies.

No large shared index is added. Existing report IDs locate their receipts. No extra quote request is made during registration. Historical signal occurrences are not silently backfilled or claimed as newly recorded by this release.

## Measurement V2

New samples use `NEXT_COMMON_OPEN_ADJUSTED_PROXY_V2`. The entry is the first exchange opening strictly after the signal time. A pre-open signal can use that day's opening; a midday or after-close signal uses the next eligible opening. An opening exactly equal to the signal timestamp is excluded. Both stock and benchmark use the same entry session. Outcome 1 is that session's completed close, and outcome 5/20/60 is the fifth/twentieth/sixtieth completed exchange session starting with entry. This differs from legacy horizon definitions and must not be pooled with them.

Only bars whose exchange has closed plus a 15-minute publication buffer are eligible. Missing expected entry bars or intervening sessions do not silently move entry/outcome dates. The loader preserves raw open/close and provider-adjusted open/close; no open is synthesized from a close. Adjusted open is raw open multiplied by adjusted-close/raw-close from the same provider bar. The series is identified as a provider-adjusted total-return proxy, not a verified cash dividend ledger.

Returns are normalized to entry=100 within each downloaded curve. A later corporate-action rescaling of historical prices cancels between the entry and outcome denominators; a newly adjusted close is never divided by a frozen raw signal quote. Each frozen measurement retains the source denominators used. Revised normalized returns are flagged, not rewritten to manufacture consistency. Original raw signal references remain attached to the source observation/census.

Norway uses OSEBX gross return; USA uses the available S&P 500 total-return series `^SP500TR`. The Swedish gross-return candidate could not be verified as available through this provider. Swedish stock returns can be measured, but benchmark/excess remain null until a documented compatible source is configured. A price-only index is never substituted for a total-return benchmark, and missing benchmark data is never zero performance.

These are **gross total-return proxies in listing currency**, not actual fills, net NOK portfolio profit, tax returns or a cost/FX ledger. `net_return_pct` remains null and `net_result_verified` false. Approved economic/accounting policies and the historical exit research cost model are unchanged.

## Legacy evidence and reports

Legacy and V2 cohorts are reported separately. When V2 observations exist, headline horizon statistics use V2 only and expose the number of retained legacy references. With legacy evidence alone, its descriptive view is explicitly marked unqualified and no headline signal-alpha figure is published. Reports/UI warn that these are gross references, not net NOK profits. Historical baselines and already-published artifacts are preserved; this change does not retroactively correct their numbers. The existing 78-row quarantine and financial account histories are unchanged.

## Validation and rollout

Regression tests first reproduced the hidden control-to-buy signal and missing basis controls. New tests cover immutable coverage, full sampling quota, invalid reference identity, preview/no-write behavior, after-close/weekend/pre-open/midday timing, incomplete sessions, missing entry bars, dividend rescaling, normalized-history revision rejection, missing benchmarks and method separation. PostgreSQL tests are part of the existing release gate.

Before merge/deploy: focused learning and PostgreSQL suite, full suite with baseline failures identified, independent code review and required release gate. After deployment: verify exact web/cron commit, public health and a normal scheduler run. Census persistence for a real report is only claimed once a qualifying scheduled report has actually run; deployment alone is not evidence of that event. No new historical profitability claim is permitted by this change.

Validation evidence before PR: 70 focused learning/PostgreSQL tests passed. The full local suite completed with 2,673 passed, 230 skipped and 4 subtests passed. The same four failures previously reproduced on the unchanged baseline remain: `test_production_roots_and_complete_lock_are_exact_and_installed` (local transitive pins), `test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch` (legacy FakeCursor context-manager support), `test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master` (live universe authority), and `test_new_breach_sends_pushover_after_configuration_change` (time-dependent additional FX alert). An independent review checked the implementation; identified clock/benchmark/report-receipt edge cases were covered and corrected. A live-provider local replay of GOD.OL and AAPL produced versioned gross reference outcomes at 1/5/20 sessions with net returns explicitly null. Historical registration times were only conservative replay inputs, not proof of original publication time.
