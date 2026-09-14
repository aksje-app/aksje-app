# RC16.31bz - Durable Fine-Grained Progress Closure

## Scope
This release is intentionally limited to progress telemetry and UI monotonicity for manual/report runs. It does not alter investment scoring, BUY thresholds, risk limits, Fresh Trend selection, Norway universe membership, evidence budgets, portfolio rules, or paper-learning rules.

## Fixed
- Added explicit whole-run progress intervals for EXTENDED_ANALYSIS, EVIDENCE, SHORT, INSIDER_BASELINE and SHORT_BASELINE.
- AUTONOMOUS now uses its reported completed/total work units to advance visibly from 84% toward 91%, instead of remaining pinned to one percentage.
- REPORT progress can advance from 93% toward 98% when work units are reported.
- Existing market-scan progress mapping remains compatible; MARKET_DATA still starts at 10% in the established single-market contract.
- Worker-side persistence remains monotonic using max(previous_percent, calculated_percent).
- UI adds a per-execution monotonic display floor so an older browser/session snapshot cannot visibly move the same run backward.
- Live UI text now explains that whole-run progress includes extended analysis, evidence, short, and baseline controls.

## Why
In RC16.31by, long-running phases such as EXTENDED_ANALYSIS and the baseline evidence controls had no dedicated percentage interval. The worker could perform substantial real work while the visible percentage stayed flat, then appear to jump from roughly 15% to the high 40s when the next recognised phase arrived. RC16.31bz closes those invisible intervals rather than cosmetically animating the bar.

## Non-goals
- No artificial/smoothed fake percentage animation.
- No change to analysis order or number of analysed candidates.
- No change to Norway 294-share authoritative universe behavior.
- No change to report semantics or market clock behavior introduced in RC16.31by.
