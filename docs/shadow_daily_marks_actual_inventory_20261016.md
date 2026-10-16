# Existing real historical daily marks — 2026-10-16

Read-only SQL on Render Postgres `aksje_paper_db`, `app_kv_store`, key `controlled_learning/observation_cohorts.json`:

- 91 actual Shadow observation records; entry dates 2026-08-31 to 2026-10-06.
- **2,497 persisted daily marks**, including price, market_date, return_pct, benchmark_price, benchmark_return_pct and excess_return_pct. All 91 observations have a daily_marks array.
- These are existing historical *recorded results* and must not be discarded or conflated with newly introduced full-replay snapshots (which only began 2026-10-13).
- Short-horizon aggregate measured returns have been confirmed separately: 1 day 91 samples -0.804% mean, 5 day 91 +0.115%, 20 day 90 -0.373%. This does not establish causal selection advantage or net-of-cost profits.

Suggested reproducibility query (read-only):
```sql
SELECT count(*) observations,
 min(v->>'entry_market_date') first_entry,
 max(v->>'entry_market_date') last_entry,
 sum(jsonb_array_length(v->'daily_marks')) daily_marks
FROM app_kv_store, lateral jsonb_array_elements(payload::jsonb) v
WHERE name = 'controlled_learning/observation_cohorts.json';
```

**Before publication**: verify ticker price series are split/dividend-adjusted; assert trading-session order and de-duplicate repeated market dates; compare stored returns to observed price and benchmark entry policy; check missing delisted tickers. Source/provider publication/filing timestamps have not been independently verified.
