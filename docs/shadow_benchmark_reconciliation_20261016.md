# Critical benchmark return reconciliation — 2026-10-16

Read-only, reproducible Render Postgres audit of 2,497 daily marks, comparing reported `return_pct`, `benchmark_return_pct` and `excess_return_pct` to stored entry prices and each mark.

At 0.10 percentage point tolerance:
- Stock return recomputed from stored entry price: **0 discrepancies**.
- Excess-return arithmetic (stock return minus benchmark return): **0 discrepancies**.
- Benchmark return recomputed from stored benchmark entry price: **99 discrepancies**.

Example: `GOOG` / `^GSPC`, entry 2026-08-31, mark 2026-09-01, stored benchmark policy `PREVIOUS_OFFICIAL_CLOSE`, recomputed -1.041% vs recorded -1.2873%. Similar deviations exist for OSEBX.OL and ^OMX. Multiple observation records sharing benchmarks may repeat the same underlying benchmark anomaly: 99 is a **mark count**, not 99 distinct independent market-price faults.

These mismatches could stem from distinct date/price reference conventions or defects; root cause is **not established**. Until reconciled, historic reported excess returns should carry a **BENCHMARK_PROVENANCE_UNVERIFIED** caveat. Do not assert Shadow superiority or automatically modify production policies.

Audit query principle:
`100*(mark.benchmark_price / observation.benchmark_entry_price - 1)` vs `mark.benchmark_return_pct`. Compare both with first available official previous-session close and timezone normalization.

Follow up: trace `learning_observation_engine.py` source of benchmark entry and mark returns, determine appropriate as-of denominator; correct reporting or provenance before publishing results.
