# Project handoff – v18.5.25 Session State Fix + Forecast Chart

## What changed

- Fixed a Streamlit runtime crash in Analyseunivers / Smart Universe Picker:
  - `st.session_state.ai_universe_manual_list_draft_v18517` is no longer modified after its `st.text_area` widget is instantiated.
  - A separate non-widget key `ai_universe_manual_list_saved_v18525` is used for saved/sync state.
- Updated the app version source to `v18.5.25` in `app_version.py`.
- Forecast-vs-actual chart data is now explicitly split:
  - `actual_history_x` / `actual_history` stops at today's marker.
  - `forecast_x` starts at today and continues into future forecast dates.
  - legacy padded `actual` values after `future_start_index` are forced to `None`.
  - chart legend/status text clarifies actual history, today marker, and future bull/base/bear forecast.
- Added tests for the session-state hotfix and forecast actual/future split.
- Runtime data has been removed from the package; only `.gitkeep` remains in `data/`, `data/forecasts/`, and `data/services/`.

## Verification

```bash
python -m compileall .
pytest -q
# 24 passed
```

## Deploy note

After uploading to GitHub main, run Render:

```text
Manual Deploy → Clear build cache & deploy
```

Header should show:

```text
Professional Trading Workspace v18.5.25
```
