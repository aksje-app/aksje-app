# Actual Render historical data inventory — 2026-10-16

Source: **read-only SQL** against Render Postgres `aksje_paper_db` (workspace My Workspace). No portfolio or production writes.

## Verified persisted source data
- `app_kv_store` has **10 historical full-replay market snapshots**, each with **60 candidates**, totaling **600 candidate observations** between **2026-10-13 12:07:53 UTC** and **2026-10-16 12:05:43 UTC**. These contain price, score, metadata, ranking inputs and capture provenance.
- `app_kv_store` also has archived `market_intelligence/runs/MI-*.json` and `market_intelligence/candidate_history.json`; these require field-level suitability review before any return computations.
- `app_jsonl_store` has 2,957 `analysis_pipeline/history.jsonl` records (since 2026-05-25), 1,279 `super_portfolio/audit.jsonl` (since 2026-09-14), 984 `controlled_learning/audit.jsonl` (since 2026-07-20), and 132 `controlled_learning/outcome_audit.jsonl` records (since 2026-10-15). The large operational and market audit streams also contain logs, **not inherently investment price histories**.
- Example actual captured candidate: `GOD.OL` Goodtech at approximately NOK 15.15 in the 2026-10-16 snapshot. This is a historical observation, not a verified adjusted-price series or a recommendation.

## What these actual data can and cannot establish
The replay snapshots provide genuine as-of candidate/decision evidence, allowing candidate-by-candidate comparisons across recorded runs, with timestamps. They do **not** by themselves provide 7/30 **matured trading-session total returns** (recording period <7 trading days), issuer-first-publication provenance for each fundamental, corporate-action adjustments or a delisted historical universe. Do not substitute current Yahoo fundamentals or repeat snapshots for maturated returns.

## Next ingestion contract
Build a read-only extractor on top of `app_kv_store` keys `full_replay/%/market_snapshot.json` and `market_intelligence/runs/MI-*.json`, retaining snapshot ID/date, ticker, candidate score and original raw fields. Join separately to licensed/exchange-vetted split-and-dividend-adjusted historical closes and original filing publication dates; require delisted names. **Never write back to production tables or modify trading decisions.**

## Database verification SQL
```sql
SELECT count(*) AS snapshots,
 sum(jsonb_array_length(payload::jsonb->'candidates')) AS candidate_observations,
 min(payload::jsonb->>'captured_at') AS oldest,
 max(payload::jsonb->>'captured_at') AS newest
FROM app_kv_store
WHERE name LIKE 'full_replay/%/market_snapshot.json';
```
Result: 10 snapshots, 600 observations. This is **genuine source evidence**, not an empirical performance claim.
