# RC16.31bj - Learning Memory Closure

## Scope
This release is intentionally limited to the OOM path identified immediately after `scheduler:learning_maintenance:before`.
No scoring, buy thresholds, risk rules, portfolio rules, execution rules or market-selection rules are changed.

## Root cause addressed
`generate_historical_baseline()` previously materialised up to 100 complete archived canonical reports in one list before the baseline calculation started. Full reports can contain large candidate evidence, news, raw market data and report trees. Holding many complete runs at once could expand Python memory far beyond the raw stored payload and exceed the 2 GiB Render limit.

RC16.31bj now:
- reads the compact report archive index first;
- processes archived reports one at a time;
- immediately projects each report to the minimal learning contract used by the 1/5/20/60-day baseline;
- drops news/evidence/raw payload trees that the learning calculation does not use;
- releases process memory after each archived report;
- stops collecting compact rows once the existing 1500-signal baseline cap is reached.

## OOM observability
Durable breadcrumbs were added inside learning maintenance around:
- maintenance start;
- daily-due and daily evaluation;
- baseline state/due checks;
- archive index load;
- each archived run load;
- historical price-series load;
- baseline build;
- weekly refresh and weekly report.

If a live OOM remains, the next diagnostic package should identify the specific internal learning step instead of only `scheduler:learning_maintenance:before`.

## Compatibility
Historical baseline math and the existing 1/5/20/60-day learning contract remain unchanged. The change is how source reports are loaded and retained in memory, not how signals are scored or evaluated.
