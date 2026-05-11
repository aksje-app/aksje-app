# Project handoff – v18.5.28 Event Risk Alerts + Confidence Adjustment

## Status
This package continues from v18.5.27 and completes point 5: **Varsler / hendelsesrisiko**.

## What changed
- Updated single source of truth in `app_version.py` to `v18.5.28`.
- Strengthened `event_risk_engine.py`:
  - earnings risk via `earnings.get_earnings` / `FINNHUB_API_KEY`
  - macro events via `MACRO_EVENT_CALENDAR_JSON`
  - realized volatility and large recent move detection
  - news-risk keyword detection via `news.get_news` / `NEWSAPI_KEY`
  - compact event-risk summary helper
  - explicit confidence-breakdown helper
- Updated `forecast_engine.py`:
  - forecast summaries now include base confidence, event adjustment, learning adjustment, total adjustment, event-risk flag and event-risk summary
  - avoids hidden double-penalty when event-risk engine already supplies a confidence adjustment
- Updated `forecast_store.py`:
  - forecast payloads persist event-risk details/diagnostics
  - event-risk alerts are replayed into intelligent/common alert stream
- Updated `forecast_ui.py`:
  - “Hendelsesrisiko nær?” is now backed by concrete detection when data is available
  - shows event-risk alerts and confidence breakdown
  - passes event adjustment and learning adjustment separately
  - persists event-risk alerts via the existing alert log / StorageService path

## Verification
```bash
python -m compileall .
pytest -q
# 32 passed
```

## Expected UI marker
```text
Professional Trading Workspace v18.5.28
```

## Notes
- Runtime data is excluded from the package. `data/`, `data/forecasts/`, and `data/services/` contain only `.gitkeep`.
- Alerts/storage still use `StorageService`/Postgres first with local fallback.
- Next planned work after Render smoke-test: point 6 persistent storage hardening, then point 7 legacy cleanup.
