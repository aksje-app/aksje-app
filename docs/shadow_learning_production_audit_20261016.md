# Actual Shadow / learning production audit — 2026-10-16

Read-only Render Postgres inspection; **no trades modified**.

## Actual recent state
- `controlled_learning/audit.jsonl`: 984 entries; last `LEARNING_EVALUATED` (2026-10-16T12:07 UTC) reports 137 closed learning+ordinary trades, 41.61% aggregate win rate, profit factor ~1.034. Its *ordinary* portfolio subset has 36 closed trades, profit factor 0.657 and current total return -0.27%. These are distinct cohorts; never conflate aggregate learning PF with ordinary trading PF.
- `controlled_learning/outcome_audit.jsonl`: 132 entries, of which 88 `OBSERVATIONS_REGISTERED`, 43 `OUTCOMES_EVALUATED`, and 1 `HISTORICAL_BASELINE_COMPLETED`.
- Latest `OBSERVATIONS_REGISTERED` has 91 active observations, 0 newly created (capacity 120). Last `OUTCOMES_EVALUATED` at 2026-10-16T04:31 UTC: 91 active, 0 matured, 0 missing, 0 updated.
- `controlled_learning/acceptance_latest.json`: operational verdict PASS **but strategy_readiness NOT_VALIDATED**; clean current cohort has **0 mature closed positions and 0 benchmark-measured positions**, profit factor 0.0 in current quality gate, promotion forbidden. The 0.0 is a no-qualified-sample gate value, **not** achieved investment performance.
- Existing `controlled_learning/historical_baseline.json` is labelled VERIFIED and lists 1,382 historical signals. Its internal analysis reports `matured_count: 0` while displaying 1-day return aggregates. This inconsistency/semantic split needs targeted forensic review before treating those results as quality evidence.
- Existing forward `AUTONOMY.json` is ACTIVE_SHADOW and its configuration uses a 60-day learning probe horizon. New observation cohorts from October cannot truthfully be judged as 60-day matured in October.

## Assessment
Operational mechanics are demonstrably active, but **proven economic improvement is missing**. The acceptance PASS is technical/operational, not an empirical strategy win. Prior engineering emphasis on gates and labels did not deliver the clear outcome report the user needed. Deep-value Shadow from PR100 is an even newer independent read-only diagnostic and must not inherit proof from unrelated legacy learning cohorts.

## Next concrete actions
1. Trace cohort-specific horizon and outcome semantics: distinguish 1, 7, 30 trading sessions and separate 60 *calendar* day probes, while retaining dates and benchmarks.
2. Extract historical signal and outcome tables already persisted, verify return and benchmark provenance and count matured/unmatured per cohort.
3. Audit why the historical baseline shows VERIFIED with 1,382 signals yet matured_count=0, and why current acceptance says PASS/NOT_VALIDATED.
4. Produce explicit coverage/maturity/result report; do not turn not-yet-mature observations into zeros and do not promote live strategies.
