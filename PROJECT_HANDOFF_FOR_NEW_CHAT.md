# Project handoff – v18.5.45 Paper Trading Funds + ETF Support

Header should show `Professional Trading Workspace v18.5.45`.

## New in v18.5.45

- Paper Trading now supports simulated fund/ETF purchases in addition to stocks.
- Added amount-based paper buy for:
  - ETF
  - Indeksfond
  - Aktivt fond
  - Fond
- Added partial/all sell support for paper fund/ETF positions.
- Added optional manual price/NAV entry and yfinance fetch button where available.
- Added simulated monthly savings-plan records for funds/ETF.
- Paper positions and trades now carry `asset_type`, `units_label`, `currency`, `nav_date`, and order metadata.
- Portfolio analysis now reads Paper Trading positions with correct asset type instead of treating all paper positions as stocks.
- No real broker trading is active.

## Storage

- Runtime data is not included in GitHub/zip.
- `data/`, `data/forecasts/`, and `data/services/` should contain only `.gitkeep`.
- Persistent runtime storage should go through `StorageService` / Postgres where configured.

## Verification

- `python -m compileall .`
- `pytest -q` → 87 passed
