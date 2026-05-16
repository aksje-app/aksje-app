# v18.6.0 Streamlit integration snippet
# Legg inn i Daily Report-panelet der rapporten bygges/oppdateres.

from daily_report_v18_6_0_integration import build_v18_6_0_daily_report

st.caption("v18.6.0 — Market Portfolio Forecast Patch")

# Tilpass disse session_state-nøklene til navnene i appen din.
selected_market = st.session_state.get("daily_report_market", st.session_state.get("selected_market", "USA"))
ranking_df = st.session_state.get("ranking_df") or st.session_state.get("latest_ranking_df")
positions = st.session_state.get("positions_df") or st.session_state.get("portfolio_positions")
watchlist = st.session_state.get("watchlist_tickers")
manual_tickers = st.session_state.get("manual_forecast_tickers", "AAPL,MSFT,NVDA")
market_regime = st.session_state.get("market_regime", "neutral")

# forecast_fn må peke til eksisterende funksjon i appen.
# Eksempel: forecast_fn=make_forecast_scenario eller generate_forecast_row
report = build_v18_6_0_daily_report(
    market=selected_market,
    ranking_df=ranking_df,
    positions=positions,
    watchlist=watchlist,
    manual_tickers=manual_tickers,
    forecast_fn=make_forecast_scenario,  # <-- bytt til eksisterende funksjonsnavn
    horizon="1m",
    max_candidates=20,
    market_regime=market_regime,
)

st.info(report["status_text"])

with st.expander("Markedsportefølje brukt i rapporten", expanded=False):
    st.dataframe(report["portfolio"], use_container_width=True)

st.subheader("Topp bullish / sterkeste prognoser")
st.dataframe(report["top_bullish"], use_container_width=True)

st.subheader("Topp risiko / svakeste prognoser")
st.dataframe(report["top_risk"], use_container_width=True)

if not report["errors"].empty:
    with st.expander("Prognosefeil", expanded=False):
        st.dataframe(report["errors"], use_container_width=True)
