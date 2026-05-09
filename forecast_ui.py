"""
forecast_ui.py

Bygg 2: Scenario-graf i egen UI-seksjon.

Denne modulen er isolert fra auto trading og global oppdatering.
Den bruker forecast_engine.py fra Bygg 1 og viser:
- ticker-felt
- horisontvalg
- bull/base/bear-graf
- usikkerhetsbånd
- enkle tallkort
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import streamlit as st

from forecast_engine import SUPPORTED_HORIZONS, build_forecast, build_all_horizons


def _fetch_close_prices_yfinance(ticker: str, period: str = "1y") -> Tuple[List[float], Optional[str]]:
    """Hent sluttkurser via yfinance hvis tilgjengelig."""
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return [], "Mangler ticker."

    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return [], "yfinance er ikke tilgjengelig i miljøet."

    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return [], f"Fant ingen prisdata for {ticker}."
        close = df["Close"]
        if hasattr(close, "dropna"):
            close = close.dropna()
        prices = [float(x) for x in list(close)]
        if len(prices) < 30:
            return [], f"For lite historikk for {ticker}. Trenger minst 30 datapunkter."
        return prices, None
    except Exception as exc:
        return [], f"Klarte ikke hente prisdata for {ticker}: {exc}"


def _format_price(value: float) -> str:
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return "0.00"


def _format_pct(value: float) -> str:
    try:
        sign = "+" if float(value) >= 0 else ""
        return f"{sign}{float(value):.2f}%"
    except Exception:
        return "0.00%"


def _risk_color(risk: str) -> str:
    risk = (risk or "").lower()
    if risk == "lav":
        return "green"
    if risk == "høy":
        return "red"
    return "orange"


def _render_plotly_chart(result) -> None:
    """Render scenario-graf. Bruker Plotly hvis tilgjengelig."""
    try:
        import plotly.graph_objects as go  # type: ignore
    except Exception:
        st.warning("Plotly er ikke tilgjengelig. Viser tabell i stedet.")
        st.dataframe(result.to_dict()["points"], use_container_width=True)
        return

    points = result.points
    x = [p.date_label for p in points]
    base = [p.base for p in points]
    bull = [p.bull for p in points]
    bear = [p.bear for p in points]
    lower = [p.lower_band for p in points]
    upper = [p.upper_band for p in points]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=x,
        y=upper,
        mode="lines",
        line=dict(width=0),
        hoverinfo="skip",
        showlegend=False,
        name="Øvre usikkerhetsbånd",
    ))
    fig.add_trace(go.Scatter(
        x=x,
        y=lower,
        mode="lines",
        fill="tonexty",
        fillcolor="rgba(148, 163, 184, 0.18)",
        line=dict(width=0),
        hoverinfo="skip",
        showlegend=True,
        name="Usikkerhetsbånd",
    ))
    fig.add_trace(go.Scatter(x=x, y=bull, mode="lines", name="Bull", line=dict(width=2)))
    fig.add_trace(go.Scatter(x=x, y=base, mode="lines", name="Base", line=dict(width=3)))
    fig.add_trace(go.Scatter(x=x, y=bear, mode="lines", name="Bear", line=dict(width=2)))

    fig.update_layout(
        title=f"{result.ticker} teoretisk scenario ({result.summary.horizon})",
        xaxis_title="Dato",
        yaxis_title="Kurs",
        height=430,
        margin=dict(l=10, r=10, t=55, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_forecast_section(default_ticker: str = "AAPL") -> None:
    """Render prognosemodul v1, Bygg 2."""
    st.markdown("## 🔮 Fremtidsscenario / Prognose")
    st.caption(
        "Teoretiske bull/base/bear-scenarioer. Dette er ikke fasit eller investeringsråd."
    )

    with st.expander("▸ Prognosemodul v1 — klikk for å åpne/lukke", expanded=False):
        c1, c2, c3 = st.columns([2.2, 1.4, 1.4])
        with c1:
            ticker = st.text_input("Ticker", value=default_ticker, key="forecast_ticker_v1831").strip().upper()
        with c2:
            horizon_labels = {
                "1d": "1 dag",
                "1w": "1 uke",
                "1m": "1 måned",
                "3m": "3 måneder",
                "6m": "6 måneder",
            }
            horizon = st.selectbox(
                "Horisont",
                options=list(SUPPORTED_HORIZONS.keys()),
                format_func=lambda x: horizon_labels.get(x, x),
                index=2,
                key="forecast_horizon_v1831",
            )
        with c3:
            period = st.selectbox(
                "Historikk",
                options=["6mo", "1y", "2y", "5y"],
                index=1,
                key="forecast_history_period_v1831",
            )

        ai_score = st.slider("AI-score-justering", 0, 100, 50, 1, key="forecast_ai_score_v1831")
        sentiment = st.slider("Sentiment-justering", -1.0, 1.0, 0.0, 0.05, key="forecast_sentiment_v1831")

        run = st.button("Lag prognosegraf", key="forecast_run_v1831", use_container_width=True)

        if not run:
            st.info("Velg ticker og trykk «Lag prognosegraf».")
            return

        prices, error = _fetch_close_prices_yfinance(ticker, period=period)
        if error:
            st.warning(error)
            return

        try:
            result = build_forecast(
                ticker,
                prices,
                horizon,
                ai_score=float(ai_score),
                sentiment_score=float(sentiment),
            )
        except Exception as exc:
            st.error(f"Klarte ikke lage prognose: {exc}")
            return

        s = result.summary
        st.markdown("### 📈 Scenario-resultat")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Nå", _format_price(s.current_price))
        k2.metric("Base", _format_price(s.base_price), _format_pct(s.base_pct))
        k3.metric("Bull", _format_price(s.bull_price), _format_pct(s.bull_pct))
        k4.metric("Bear", _format_price(s.bear_price), _format_pct(s.bear_pct))
        k5.metric("Confidence", f"{s.confidence}%", s.risk)

        _render_plotly_chart(result)

        risk_color = _risk_color(s.risk)
        st.markdown(
            f"""
            <div style="border:1px solid rgba(148,163,184,.25);border-radius:12px;padding:.8rem 1rem;">
              <b>Forklaring:</b><br>
              {s.explanation}<br><br>
              <b>Risiko:</b> <span style="color:{risk_color};font-weight:800;">{s.risk}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


        st.markdown("### 📊 Sammenligning av horisonter")

        try:
            all_results = build_all_horizons(
                ticker,
                prices,
                ai_score=float(ai_score),
                sentiment_score=float(sentiment),
            )

            horizon_rows = []
            horizon_names = {
                "1d": "1 dag",
                "1w": "1 uke",
                "1m": "1 måned",
                "3m": "3 måneder",
                "6m": "6 måneder",
            }

            for h, data in all_results.items():
                s2 = data["summary"]
                horizon_rows.append({
                    "Horisont": horizon_names.get(h, h),
                    "Base %": f"{s2['base_pct']:+.2f}%",
                    "Bull %": f"{s2['bull_pct']:+.2f}%",
                    "Bear %": f"{s2['bear_pct']:+.2f}%",
                    "Confidence": f"{s2['confidence']}%",
                    "Risiko": s2["risk"],
                })

            st.dataframe(horizon_rows, use_container_width=True, hide_index=True)
        except Exception as _forecast_compare_error:
            st.warning(f"Kunne ikke bygge horisont-tabell: {_forecast_compare_error}")

        if result.warnings:
            st.warning(" ".join(result.warnings))
