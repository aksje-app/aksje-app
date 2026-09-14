# Validation report - RC16.31bx

## Result
**LOCAL BUILD PASS with live acceptance pending.**

## Focused tests
- `tests/test_rc16_31bx_stabilization_ui.py`: **6 passed**.
- `tests/test_v1883_autonomy_overview.py` + current BW parser + BX tests, historical version assertion excluded: **16 passed, 2 deselected**.
- BQ/BL behavior regressions, historical version assertions excluded: **11 passed, 2 deselected**.
- Canonical report / decision reduction / report delivery regressions: **23 passed** with one unrelated old AB wording assertion failing because the current report wording has evolved; no BX logic failure.

## Compile
`app_version.py`, `report_integrity.py`, `autonomy_overview.py`, `market_intelligence.py`, and `runtime_identity.py`: **PASS**.

## Key functional checks
- Duplicate `DOFG.OL`-style canonical rows collapse to one deterministic merged candidate before decision reduction.
- Immediate Utkast start stores the accepted execution id and reruns immediately.
- Polling is tied to the exact pending/durable execution id.
- Unified report file center includes the four daily-use files and an on-demand complete ZIP.
- Blocker text uses a wrapped HTML table.
- Baseline short/insider counts are explicitly labelled as intermediate controls.
- Stale runtime identities are diagnostic-only; fresh mismatches remain blocking.
- BW Euronext XOSL/MERK/XOAS parser remains present and unchanged in policy.

## Not proven locally
External Euronext live response, browser-specific PC/mobile refresh behavior, and the next scheduled Render 08/14/22 runs require post-deploy evidence. RC16.31bx must not be called fully production-ready until those checks pass.
