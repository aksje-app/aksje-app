# Validation Report - RC16.31bm

## Build
- App version: `v19.22.0-rc16.31bm`
- Base: `v19.22.0-rc16.31bl`
- Release: Early Trend and Breakout Intelligence

## Production changes
Clean DELTA contains exactly four production files:
- `app_version.py`
- `candidate_market_data.py`
- `trend_intelligence.py`
- `market_intelligence.py`

No documentation, tests, caches or runtime state are included in DELTA.

## Functional validation
Targeted regression set: **29 passed, 0 failed**.

Coverage includes:
- new 5/10/20d momentum acceleration fields;
- SMA20/SMA50/SMA200 structure and golden-cross detection;
- 20d/60d breakout detection;
- RSI 50/70 context;
- On Balance Volume pressure over 5/10/20 sessions;
- volume confirmation and compact volume series in trend receipts;
- market and sector relative-strength percentiles;
- Early Signal Watchlist independent of total investment-score Top 10;
- explicit continuation, confirmation, invalidation and caution explanations;
- a Hafnia-like strong-trend fixture is classified as `STERKT TIDLIG STYRKESIGNAL` while overbought RSI remains a caution;
- existing BF trend contracts, BK Norway-only/trend UI contracts, BJ learning-memory closure, BH OOM protection and BL UI/memory closure regressions.

The same 29-test set was rerun from a freshly unpacked FULL distribution: **29 passed, 0 failed**.

## Compile
- Changed production files: PASS (`py_compile`).
- Full source tree: PASS (`compileall`).

## Distribution validation
FULL validator: **PASS**
- profile: `full`
- expected version: `v19.22.0-rc16.31bm`
- issues: 0
- final archive hash is published separately in `SHA256SUMS_v19.22.0_RC16.31bm.txt`

## Safety invariants
- Production buy threshold unchanged.
- Risk ceiling unchanged.
- Liquidity/data-quality gates unchanged.
- Portfolio rules unchanged.
- Autonomy/trade authority unchanged.
- Early Trend / Breakout signals are descriptive only and cannot alone create BUY or an order.
- `PRODUCTION_NORWAY_ONLY` behaviour from BK remains intact.
- Memory/OOM closure from BJ/BL remains intact in regression tests.

## Environment limitation
The complete repository-wide pytest collection was not run because this build container does not have `yfinance` installed. The focused production/regression suites above avoid that unavailable external dependency and passed both in the working tree and from the packaged FULL archive.

## Live acceptance still required
One Norway-only Render run should confirm:
- the early-signal watchlist is populated with live market data;
- strong but not overall-Top-10 candidates can still be surfaced by technical early signal;
- explanations are useful and readable in UI/PDF;
- breakout/RSI/volume/OBV values match the live data source;
- no memory regression appears during manual full-report generation.
