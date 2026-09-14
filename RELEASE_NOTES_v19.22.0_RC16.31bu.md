# RC16.31bu - Norway Universe Source Observability

Purpose: make the failed Euronext Norway-universe refresh fully observable on Render without changing investment logic.

Changes:
- Every Euronext source attempt emits `NORWAY_UNIVERSE_ATTEMPT` with strategy, method, requested/final URL, HTTP status, content type, response size, parsed row count, parser and elapsed time.
- Concrete exceptions are retained with the attempt that produced them.
- The latest fetch diagnostic is persisted durably as `market_universe/norway_euronext_fetch_diagnostics.json`.
- Fallback masters carry the persisted fetch diagnostic so `FALLBACK_UNVERIFIED` no longer hides the root cause.
- Manual background-job diagnosis now includes `market/NORWAY_UNIVERSE_FETCH_DIAGNOSTICS.json` and `market/NORWAY_UNIVERSE_MASTER_STATUS.json`.
- No scoring, BUY threshold, risk, Fresh Trend, Paper Trade, portfolio, evidence-budget or market-policy changes.
