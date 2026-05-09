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

from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from forecast_engine import SUPPORTED_HORIZONS, build_forecast, build_all_horizons
from forecast_store import build_and_store_all_horizons, compute_alerts, load_alerts, load_forecast_log, load_latest_forecast, save_alerts


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




def _extract_ticker_from_value(value: Any) -> Optional[str]:
    """Best-effort extraction of ticker symbols from common app data structures."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().upper()
        if 1 <= len(cleaned) <= 12 and all(ch.isalnum() or ch in ".-" for ch in cleaned):
            return cleaned
        return None
    if isinstance(value, dict):
        for key in ("ticker", "symbol", "Ticker", "Symbol", "code"):
            if key in value:
                return _extract_ticker_from_value(value.get(key))
    return None


def _collect_forecast_candidates(limit: int = 80) -> List[str]:
    """Collect tickers from session state, portfolio, watchlist and ranking-like objects.

    This is intentionally defensive. It should never break the app if keys change.
    """
    candidates: List[str] = []

    def add(value: Any) -> None:
        ticker = _extract_ticker_from_value(value)
        if ticker and ticker not in candidates:
            candidates.append(ticker)

    try:
        # Common session-state keys used in apps like this.
        keys = [
            "selected_ticker",
            "ticker",
            "active_ticker",
            "forecast_ticker",
            "watchlist",
            "portfolio",
            "paper_portfolio",
            "holdings",
            "positions",
            "top_picks",
            "ai_ranking",
            "ranking_rows",
            "recommendations",
            "scan_results",
        ]

        for key in keys:
            if key not in st.session_state:
                continue
            value = st.session_state.get(key)
            if isinstance(value, dict):
                # If it is a portfolio dict, holdings may be nested values.
                add(value)
                for k, v in value.items():
                    add(k)
                    add(v)
                    if isinstance(v, list):
                        for item in v:
                            add(item)
                    elif isinstance(v, dict):
                        for vv in v.values():
                            add(vv)
            elif isinstance(value, list):
                for item in value:
                    add(item)
            else:
                add(value)
    except Exception:
        pass

    # Try local app files if they exist. Safe and optional.
    try:
        import json as _json
        from pathlib import Path as _Path

        for filename in ("watchlist.json", "portfolio.json", "paper_portfolio.json", "data/watchlist.json", "data/portfolio.json"):
            path = _Path(filename)
            if not path.exists():
                continue
            try:
                data = _json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                for k, v in data.items():
                    add(k)
                    add(v)
                    if isinstance(v, list):
                        for item in v:
                            add(item)
            elif isinstance(data, list):
                for item in data:
                    add(item)
    except Exception:
        pass

    return candidates[:limit]


def _render_candidate_picker(default_ticker: str) -> str:
    """Render safe quick-pick UI for existing app sources."""
    candidates = _collect_forecast_candidates()
    if not candidates:
        st.caption("Ingen portefølje-/watchlist-/ranking-kandidater funnet ennå. Bruk manuelt ticker-felt.")
        return default_ticker

    options = ["Manuelt søk"] + candidates
    choice = st.selectbox(
        "Raskvalg fra appdata",
        options=options,
        index=0,
        key="forecast_candidate_picker_v1833",
        help="Henter kandidater fra session state, portefølje, watchlist eller ranking hvis tilgjengelig.",
    )
    if choice != "Manuelt søk":
        return choice
    return default_ticker


def _candidate_source_label(ticker: str) -> str:
    """Best-effort label for where a ticker likely came from."""
    ticker = (ticker or "").upper()
    try:
        for key, label in [
            ("portfolio", "Portefølje"),
            ("paper_portfolio", "Paper"),
            ("holdings", "Portefølje"),
            ("positions", "Portefølje"),
            ("watchlist", "Watchlist"),
            ("top_picks", "AI-ranking"),
            ("ai_ranking", "AI-ranking"),
            ("ranking_rows", "Ranking"),
            ("recommendations", "Anbefalinger"),
            ("scan_results", "Scan"),
        ]:
            value = st.session_state.get(key)
            if isinstance(value, dict):
                blob = str(value).upper()
                if ticker in blob:
                    return label
            elif isinstance(value, list):
                blob = str(value).upper()
                if ticker in blob:
                    return label
    except Exception:
        pass
    return "Appdata"


def _forecast_cache_key(ticker: str, horizon: str, period: str, ai_score: float, sentiment: float) -> str:
    return f"forecast_v1834::{ticker.upper()}::{horizon}::{period}::{int(ai_score)}::{round(float(sentiment), 2)}"


def _get_cached_forecast(cache_key: str):
    try:
        return st.session_state.get(cache_key)
    except Exception:
        return None


def _set_cached_forecast(cache_key: str, result_dict: Dict[str, Any]) -> None:
    try:
        st.session_state[cache_key] = result_dict
    except Exception:
        pass


def _render_quick_candidates_panel(limit: int = 12) -> Optional[str]:
    """Render concrete quick actions for candidates found in appdata."""
    candidates = _collect_forecast_candidates(limit=limit)
    if not candidates:
        st.caption("Ingen hurtigkandidater funnet fra portefølje/watchlist/ranking ennå.")
        return None

    st.markdown("#### Hurtigvalg")
    st.caption("Velg raskt en aksje fra portefølje, watchlist eller ranking-data hvis appen har dette tilgjengelig.")

    selected = None
    cols = st.columns(4)
    for i, ticker in enumerate(candidates[:limit]):
        label = _candidate_source_label(ticker)
        with cols[i % 4]:
            if st.button(f"{ticker}", key=f"forecast_quick_{ticker}_{i}_v1834", use_container_width=True, help=f"Kilde: {label}"):
                selected = ticker

    return selected


def _render_forecast_result_cards(summary) -> None:
    """Build 5: tydeligere tallkort for valgt horisont."""
    st.markdown("### 📈 Scenario-resultat")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Nå", _format_price(summary.current_price))
    c2.metric("Base kurs", _format_price(summary.base_price), _format_pct(summary.base_pct))
    c3.metric("Bull kurs", _format_price(summary.bull_price), _format_pct(summary.bull_pct))
    c4.metric("Bear kurs", _format_price(summary.bear_price), _format_pct(summary.bear_pct))
    c5.metric("Confidence", f"{summary.confidence}%")
    c6.metric("Risiko", summary.risk)



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
        st.info("Fase 6–10: Prognosemodulen har lagring, varsler, backtest-struktur og hurtigvalg fra portefølje/watchlist/ranking og enkel cache. Ingen auto-trading-kobling er aktivert.")
        quick_ticker = _render_candidate_picker(default_ticker)
        clicked_candidate = _render_quick_candidates_panel()
        if clicked_candidate:
            st.session_state["forecast_ticker_v1831"] = clicked_candidate
            quick_ticker = clicked_candidate

        c1, c2, c3 = st.columns([2.2, 1.4, 1.4])
        with c1:
            ticker = st.text_input("Ticker", value=quick_ticker, key="forecast_ticker_v1831").strip().upper()
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

        mc1, mc2 = st.columns([1.3, 1.0])
        with mc1:
            market_regime = st.selectbox(
                "Markedsregime",
                options=["neutral", "bull", "bear", "volatile"],
                format_func=lambda x: {"neutral": "Nøytral", "bull": "Bull", "bear": "Bear", "volatile": "Høy volatilitet"}.get(x, x),
                index=0,
                key="forecast_market_regime_v1835",
            )
        with mc2:
            event_risk = st.checkbox("Hendelsesrisiko nær?", value=False, key="forecast_event_risk_v1835")

        st.caption(f"Valgt prognose: {ticker or 'ingen ticker'} · horisont {horizon} · historikk {period} · regime {market_regime}")
        run = st.button("Lag prognosegraf", key="forecast_run_v1831", use_container_width=True)

        if not run:
            st.info("Velg ticker og trykk «Lag prognosegraf».")
            return

        prices, error = _fetch_close_prices_yfinance(ticker, period=period)
        if error:
            st.warning(error)
            return

        cache_key = _forecast_cache_key(ticker, horizon, period, float(ai_score), float(sentiment))
        cached = _get_cached_forecast(cache_key)

        if cached:
            st.caption("Viser cachet prognose for samme ticker/horisont/innstillinger i denne økten.")

        try:
            if cached:
                # Bygg resultat på nytt for grafobjekter, men bruk cache som bevis på at samme analyse er kjørt før.
                result = build_forecast(
                    ticker,
                    prices,
                    horizon,
                    ai_score=float(ai_score),
                    sentiment_score=float(sentiment),
                    market_regime=market_regime,
                    event_risk=event_risk,
                )
            else:
                result = build_forecast(
                    ticker,
                    prices,
                    horizon,
                    ai_score=float(ai_score),
                    sentiment_score=float(sentiment),
                    market_regime=market_regime,
                    event_risk=event_risk,
                )
                _set_cached_forecast(cache_key, result.to_dict())
        except Exception as exc:
            st.error(f"Klarte ikke lage prognose: {exc}")
            return

        previous_payload = load_latest_forecast(ticker)
        try:
            stored_payload = build_and_store_all_horizons(
                ticker,
                prices,
                ai_score=float(ai_score),
                sentiment_score=float(sentiment),
            )
            alerts = compute_alerts(stored_payload, previous_payload)
            save_alerts(alerts)
            if alerts:
                with st.expander("Varsler fra prognosemodulen", expanded=False):
                    for alert in alerts[:8]:
                        st.write(f"{alert.get('level', '').upper()}: {alert.get('message')}")
        except Exception as _store_error:
            st.caption(f"Prognosen ble vist, men kunne ikke lagres/logges: {_store_error}")

        s = result.summary
        _render_forecast_result_cards(s)

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
                market_regime=market_regime,
                event_risk=event_risk,
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


        with st.expander("📚 Prognoselogg og varsler", expanded=False):
            try:
                recent_log = load_forecast_log(limit=10)
                recent_alerts = load_alerts(limit=10)
                st.write(f"Loggede prognoser: {len(recent_log)} siste viste")
                if recent_alerts:
                    st.write("Siste varsler:")
                    for alert in recent_alerts[-10:]:
                        st.write(f"- {alert.get('ticker')} {alert.get('horizon')}: {alert.get('message')}")
                else:
                    st.caption("Ingen lagrede varsler ennå.")
            except Exception as _log_error:
                st.caption(f"Kunne ikke lese prognoselogg: {_log_error}")

        st.markdown("### 🔗 Bruk i resten av appen")
        st.markdown(
            """
            - Bruk denne prognosen som støtte til AI-ranking, ikke som fasit.
            - Sammenlign porteføljeaksjer mot bear/base/bull.
            - Se etter høy confidence kombinert med lav/medium risiko.
            - Vent med auto-trading-kobling til prognose-backtest er på plass.
            """
        )

        if result.warnings:
            st.warning(" ".join(result.warnings))
