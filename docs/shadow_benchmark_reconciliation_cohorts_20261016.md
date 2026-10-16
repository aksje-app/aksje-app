# Benchmark drift forensic cohort split — 2026-10-16

Read-only Render PostgreSQL query of all 2,497 persisted daily Shadow marks.

The **99 mismatched marks** occur exclusively among observations with entry_market_date **2026-08-31** and on September 1–3, split by benchmark:
- ^GSPC: 37 marks, 37 observations, only September 1.
- OSEBX.OL: 36 marks, 18 observations, September 1–3.
- ^OMX: 26 marks, 13 observations, September 1–2.

Thus 99 marks correspond to **68 distinct observations**, all belonging to one entry-day cohort, not 99 independent price-source failures. No mismatches found in October marks under the 0.10 pp rule.

The current `learning_observation_engine.evaluate_observations` recomputed benchmark baseline from its data provider on every evaluation and assigned it to `observation["benchmark_entry_price"]`, even with immutable previously measured horizon and daily mark returns. This implementation allows later data revisions to break arithmetic reconciliation. PR #106 now freezes baseline and reports provider drift instead of silently rewriting.

**What remains uncertain:** a causal reconstruction needs an earlier immutable baseline value/provider snapshot for the 2026-08-31 cohort; these data have not been independently recovered. The pattern is strongly consistent with denominator rewriting, not definitive proof. The historical 99 rows remain unrepaired pending independently verified original baselines. Do not recalculate from a present-day provider as though it were an as-of historical value.
