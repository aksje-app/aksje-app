# Phase 6 – actual historical data availability audit (2026-10-16)

## Repository evidence
- `quality_valuation_data.py` exposes `live_financial_snapshot()` from Yahoo Finance and annual financial histories, but identifies primary filing verification as `NOT_VERIFIED`. The annual statement year is **not** a verifiable public availability date.
- `candidate_market_data.py` enriches current candidate rows; current snapshots must not be used to backfill a past scan.
- `services/market_snapshot_service.py` captures price/data timestamps and candidate snapshots. A capture time alone does not prove that each historical fundamental value was public at an earlier backtest decision date.
- `services/value_historical_validation.py` requires `fundamentals_known_at`, `historical_universe_member`, and matured outcome dates.
- `scripts/run_value_shadow_backtest.py` is a read-only comparator, not a historical financial-data provider.

## Current verdict
**BACKTEST_NOT_VERIFIABLE** for an empirical 2–3 year point-in-time study until historical dated financial disclosures and universe membership have been sourced and cross-checked. Synthetic tests prove logic only, not investment performance.

## Fastest legitimate route
1. Export actual historical candidate snapshots with source and capture timestamp (where available), keeping historical original price/valuation inputs.
2. Match every financial fact to its first public disclosure date (filing/publication date, not fiscal period end). Keep original currency and units.
3. Build an as-of universe including delisted names, then calculate forward 7/30-session total returns from split/dividend-adjusted price history; prohibit future data and same-ticker duplicate samples.
4. Compare with contemporaneous finalist baseline, report selection/sector/liquidity biases and costs. Fail closed where provenance cannot be verified.
5. Continue prospective Shadow sampling while the data audit is completed. No merge/deploy/trading change without separate authorization.

Do not report real economic gains or an empirical win until these checks are completed.
