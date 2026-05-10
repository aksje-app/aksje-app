# Project handoff – v18.5.19 Smart Universe UI Compaction

Context:
- v18.5.16 completed Testing & Learning hardening.
- v18.5.17 completed Smart Universe Picker as the central stock-selection layer.
- v18.5.19 fixes a real UI issue where clicking "Kjør enkel strategi-test" could appear to do nothing because Streamlit reruns/tabs/expanders could hide the one-run button state.

What changed in v18.5.19:
- Basic strategy-test result is now stored in `st.session_state["tl_basic_strategy_result_v18518"]`.
- The result is rendered after reruns, tab switches, and expander reopen.
- Added spinner, success/error state, timestamp, metrics, chart and optimisation from the persisted payload.
- Normalised yfinance history frames so MultiIndex `Close` data works with StrategyEngine.
- Removed duplicate Score-forklaring status row.
- Added tests for yfinance MultiIndex Close normalisation and the renderable strategy-test payload.

Verification:
- `python -m compileall .` OK.
- `pytest -q` OK: 14 passed.

Recommended next steps:
1. Deploy v18.5.19 to Render.
2. Smoke-test AI Kontrollsenter → Testing & Learning → Kjør enkel strategi-test.
3. Continue with event-risk/prognose hardening.
4. Do legacy cleanup only after AI Kontrollsenter workflows are confirmed live.
