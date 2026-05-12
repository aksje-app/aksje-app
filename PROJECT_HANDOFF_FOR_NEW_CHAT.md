# Project handoff – v18.5.46 Fixed Income and High Yield Fund Support

Header should show `Professional Trading Workspace v18.5.46`.

## New in v18.5.46

- Added fixed-income fund support to Fond / ETF-analyse:
  - Rente-/obligasjonsfond
  - High yield-fond
  - Pengemarkedsfond
  - Kombinasjonsfond
- Added auto selection sources:
  - Auto rente-/obligasjonsfond
  - Auto high yield-fond
  - Auto pengemarkedsfond
- Added starter universes for bond, high-yield and money-market style ETFs/funds.
- Added alias handling for `Kraft High Yield D` → `KRAFT_HIGH_YIELD_D`.
- High yield is now treated as credit risk / `Kredittsatellitt`, not low-risk bond/core exposure.
- Fixed-income profiles now expose duration/yield when data exists, plus warnings when key data is missing.
- Fund comparator exposes best fixed-income and best high-yield leaders.
- Portfolio analyzer now counts:
  - fixed income share
  - high yield share
  - high yield risk warnings
- Paper Trading fund buy/sell supports the new asset types.

## Important limitation

Free/Yahoo-style data may not contain NAV, duration, yield or fees for Norwegian funds such as Kraft High Yield D. The app can classify the fund and warn about missing data, but full analysis requires a real data source for NAV/fees/yield/duration.

## Storage

- Runtime data is not included in GitHub/zip.
- `data/`, `data/forecasts/`, and `data/services/` should contain only `.gitkeep`.
- Persistent runtime storage should go through `StorageService` / Postgres where configured.

## Verification

- `python -m compileall .`
- `pytest -q` → 95 passed
