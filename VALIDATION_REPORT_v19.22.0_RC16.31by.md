# Validation report - RC16.31by

## Result
**LOCAL BUILD PASS with live Render acceptance pending.**

## Focused tests
- `tests/test_rc16_31by_report_semantics.py`: **7 passed**.
- BX workflow regressions excluding historical version assertion: **5 passed**.
- BW real-payload parser regressions excluding historical version assertion: **6 passed**.
- BU universe observability: **3 passed**.
- BS evidence semantics excluding historical version assertion: **4 passed**.
- BR complete Norway universe excluding historical version assertion: **10 passed**.
- BT live-source regressions excluding historical version assertion: **5 passed**.
- BQ manual-memory/terminal-status regressions excluding historical version assertion: **6 passed**.

## Preview rendering
A copy of the uploaded BX report was re-rendered with BY code after recomputing market status and decision-report semantics.
- Main PDF generated successfully.
- Technical PDF generated successfully.
- Night mission resolves to a Norway-safe overnight mission.
- Closed Norway status resolves to `Åpner 09:00` at 02:10 local time.
- Evidence coverage deduction resolves to `8 av 20 evidenskontrollerte`, not `8 av 60`.

## Memory guard regression
The BX-observed pattern was reproduced synthetically:
- process RSS: 871.0 MB
- cgroup total: 1860.9 MB
- cgroup file cache: 1024.3 MB
- effective non-reclaimable observed: 871.0 MB

In final-export file-cache-aware mode this is **not pressure** at a 1450 MB soft limit. A synthetic 2015/2048 MB cgroup case remains **pressure** because the hard-limit safety threshold is crossed.

## Compile
Changed production modules compile successfully.

## Not proven locally
- Browser-specific PC/mobile polling behavior requires Render/browser validation.
- Durable authoritative exchange-metadata rehydration requires the live Render master snapshot.
- Normal 08:00/14:00/22:00 runs require post-deploy evidence.
- Production readiness is not declared by this local build alone.
