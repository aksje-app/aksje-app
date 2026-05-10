# Project handoff – v18.5.20 UI Version + Smart Universe Cleanup

Focus for this release:

- Single app version source via `app_version.py`.
- Sticky topbar shows the real running version from `APP_VERSION`.
- Removed old hardcoded `v18.4.7` version text from the visible UI path.
- Smart Universe Picker and Smart AI result tables now render as compact dark HTML tables instead of native Streamlit dataframe boxes that could appear as huge white empty areas.
- Empty result panels now show compact dark/yellow notes instead of blank dataframe containers.
- Table height is content-sized with max-height scrolling.
- Input, textarea, select and multiselect focus/active states are forced to dark styling to avoid white ticker boxes.

Validation:

- `python -m compileall .`
- `pytest -q`

Next recommended steps:

1. Deploy v18.5.20 to Render with clear build cache.
2. Hard-refresh browser / test incognito.
3. Confirm sticky topbar says `Professional Trading Workspace v18.5.20`.
4. Confirm Analyseunivers/Smart Universe no longer shows large white empty boxes.
5. Continue with event-risk/prognose hardening and legacy cleanup.
