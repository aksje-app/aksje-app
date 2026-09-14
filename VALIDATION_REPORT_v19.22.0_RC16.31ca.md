# Validation Report - RC16.31ca

## Changed production files
- `app_version.py`
- `market_intelligence.py`
- `report_replay_export.py`
- `learning_observation_engine.py`

## Static validation
- Python compile: PASS for all changed production files.

## Targeted tests
- New RC16.31ca closure tests: 4 PASS.
- Relevant report/export/BY/BZ regression set: 37 PASS, 0 FAIL.
- Older tests that hard-code historical release version strings or the superseded duplicate ZIP-button UI are not acceptance criteria for RC16.31ca.

## Real RC16.31bz payload regression
Using the uploaded `MI-20260909-035858` report data:
- Canonical package build contains `report/report.pdf`, `report/report_technical.pdf` and `report/report.json`.
- Diagnostic inclusion was unit-tested because the local build container does not contain Render's durable manual-job diagnostic state.
- Regenerated main PDF shows specific exchange names in recommendation and observation tables.
- PDF rendered successfully to 5 PNG pages for visual inspection; no clipping/overlap was observed in the changed recommendation table.

## Scope safety
No scoring, BUY thresholds, risk policy, Norway-universe selection, Fresh Trend ranking, paper-trading policy or evidence-readiness gates were loosened.
