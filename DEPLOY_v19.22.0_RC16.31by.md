# Deploy - RC16.31by

## Recommended deployment

Use the clean DELTA package and replace the included production files in the repository. Commit and deploy the same commit to web, scheduler and paper scanner.

Changed production files:
- `app_version.py`
- `decision_report.py`
- `market_intelligence.py`
- `norway_exchange_universe.py`
- `report_contracts.py`
- `report_integrity.py`
- `runtime_memory.py`

No environment-variable changes are required.

## Immediate Render checks

1. All runtime identities show `v19.22.0-rc16.31by` and the same commit.
2. Start one manual `Utkast - Norge`.
3. Closed market UI should show `Åpner 09:00` before the opening, not the current clock as the primary closed-market value.
4. Technical report mission must not say `Oppsummer USA`.
5. Complete Norway coverage should remain authoritative with 294 instruments (or the current official count) and the three Oslo market segments.
6. The report should show explicit funnel semantics rather than a misleading 70/20/10 composition table in full-universe mode.
7. Visible evidence quality should use `ready / controlled`, e.g. `8/20`, not `8/60`.
8. Final artifact release gate must complete when total cgroup usage is elevated mainly by file cache but effective non-reclaimable memory is below the 1450 MB soft limit.
9. If cgroup usage reaches >=97% of the hard limit, the final export guard must still block.
