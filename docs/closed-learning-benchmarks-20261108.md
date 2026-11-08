# Closed learning positions: measured results, not job counts

Production initially had 129 closed learning positions and no recorded
benchmark returns. New position creation stored PENDING_MARKET_SERIES but no
collector completed that state. This is a missing result path, not simply a
wait for maturity. The independent Shadow cohorts already have benchmark
measurements; they are a different dataset.

## Provider evidence and preserved history

The read-only Render probe on 8 November found that ^OSEAX has no historical
prices. OSEAX.OL identifies the same all-share index but returned only one
daily point. OSEBX.OL returned 131 points over six months; ^OMX and ^GSPC also
returned usable history. Seventy closed rows explicitly selected ^OSEAX;
59 older rows have no benchmark/market metadata. One older position is Brazil.

Do not rewrite those original selections. Try the same-index provider alias
first. If that history cannot cover the trade, record a separate, explicitly
retrospective standard market comparison (OSEBX, OMX30, S&P500 or Ibovespa).
Such a comparison cannot satisfy the strategy benchmark gate. Future Norwegian
learning entries now record OSEBX.OL, matching the existing Shadow module and
using an identifier with historical coverage. This changes measurement metadata,
not buying/selling thresholds, risk, stops, position sizing or trade authority.

## Measurement contract

- Preserve original entry/exit times, prices, P/L, cohorts and journals.
  New evidence lives only in controlled_learning/closed_benchmarks/.
- Compare the actual simulated fill-price return with the latest completed
  official index session close available at each event. Use exchange calendars,
  holidays/early closes and a 15-minute publication buffer. Missing the expected
  session is missing data, not zero or a carried-forward older quote.
- This is a daily reference, not exact intraday benchmark execution. Returns
  are before costs. No actual commissions, FX costs or net alpha are invented.
- Bind receipts to the complete original closed row and verify checksums,
  boundaries, prices, return arithmetic and original-vs-retrospective provenance.
  A receipt for another trade/cohort or a forged eligibility flag is rejected.
- Freeze individual receipts with immutable writes. Commit the shared index
  under its existing transactional mutation API; interruption can resume an
  already-written receipt. Upgrades preserve previous receipts. No financial
  write is retried by this module, and no portfolio/trade document is written.
- Bound batches to 24 (maximum 32) positions. Cache provider series once per
  UTC date. Never redownload completed original measurements. Retry temporary
  missing data after an hour and possible retrospective-to-original upgrades
  weekly, rather than running the same research every cron. Enforce an 8 MiB
  evidence-index ceiling explicitly; reaching it never deletes history.

The source book is read after trading in the optional learning maintenance
phase, including weekends. Menu clicks read a precomputed summary and at most
200 recent comparison rows. They never fetch provider prices. The complete
receipt history remains in the index and immutable documents.

## Interpretation and validation

Show closed-only equal-weighted percentage comparisons by market and original
cohort, separately from the current cohort and from whole-portfolio NAV/P&L.
Exact duplicate source rows are preserved but not counted twice. Closed trades
are a selected sample: open winners/losers, overlapping exposure and costs mean
that this sample alone cannot establish a strategy improvement.

The first read-only calculation covered 128 positions: mean gross fill return
-0.6647%, mean daily-index return +0.2156%, difference -0.8803 percentage points;
46 beat their reference. All comparisons were retrospective. The current
13-position cohort had -6.5307 percentage points excess return. The remaining
Brazil position required the explicit Ibovespa comparator; do not treat it as US.
These preliminary calculations did not modify any production position or rule.

The existing requirements for 30 mature current-cohort closed positions,
20 recorded observation days, complete benchmark coverage, positive excess and
profit factor 1.10 remain. Require verified original benchmark evidence and an
operational PASS; retrospective references cannot validate a strategy. Automatic
promotion remains disabled. Elapsed calendar time without recorded observations
no longer inflates the UI maturity counter.

The UI and future weekly PDFs show the measured outcomes, reference choices and
limitations. Daily Pushover summaries show closed measurement coverage and gross
excess separately from validation-ready positions. Previously published weekly
analysis/PDFs are not regenerated or relabelled.

## Release evidence

Focused tests cover real return arithmetic, unavailable original references,
future/stale/conflicting prices, timezones/holidays/early closes, cohort binding,
forged provenance, restart/idempotency, missing-data retry, frozen daily caches,
preserved proxy upgrades, original benchmark gates, observed-day maturity,
weekend scheduler wiring, message bounds and PDF interpretation.

Final acceptance requires the exact-source Release Gate, real persisted
production collection, unchanged input-history/rule fingerprints, visible
results, successful notification receipts and a completed full Autonomy run
under the real 2 GiB limit. Until then this change is not production-accepted.
