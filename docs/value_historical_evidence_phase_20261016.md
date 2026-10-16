# Historical evidence phase – 2026-10-16

This batch extends PR #104 with an additional fail-closed publication and trading-session gate. Exact observed trading sessions must equal 7 or 30, returns must use source-documented corporate-action adjustments, and publication dates may not occur after a snapshot. Tests cover the new gate. The gate verifies metadata consistency, **not** truth of external data claims.

Historical point-in-time filings, delisted universe lists and adjusted daily prices were not located as a reliable empirical dataset in the repository audit. No economic outperformance claim can be made; the new functions return a read-only descriptive diagnostic after source verification. Production trade rules unchanged.
