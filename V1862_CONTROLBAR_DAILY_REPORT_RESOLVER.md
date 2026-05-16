# v18.6.2 — Control Bar + Daily Report Data Resolver Cleanup

Concrete fixes in the actual codebase:

- Version updated in `app_version.py` to `v18.6.2`.
- Global update button moved into the same Streamlit column row as the trading controls, directly after `Gjør klar`.
- Removed the large Global Oppdatering action panel from the main flow; it is now only a compact status line.
- Added desktop CSS hardening to prevent vertical button text and word wrapping in horizontal button rows.
- Rebuilt `daily_ai_market_report.py` so Daily Report is input-driven:
  - focus selector
  - market selector
  - top-N selector
  - horizon filter
  - unique ticker filtering
  - manual ticker fallback
- Daily Report candidate resolver now reads from `latest_rankings_v148`, watchlist/session sources, portfolio/session sources and manual tickers.
- Forecast cache is no longer used as an unfiltered STB.OL fallback; forecasts are filtered to selected candidates.
- Added alert review lifecycle for the report: visible alerts can be marked as reviewed and then hidden from the report.

Manual validation targets:

1. Top control row should read approximately:
   `Start | Pause | Stopp | Nødstopp | Gjør klar | Global`.
2. Global text must not wrap vertically.
3. Daily Report must show candidate source diagnostics if no candidates are available.
4. STB.OL must not fill the report unless it is part of the selected candidates.
5. Clicking `Marker viste varsler som gjennomgått` must reduce/hide those alerts.
