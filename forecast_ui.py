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
import logging

from typing import Any, Dict, List, Optional, Tuple

import html
import streamlit as st

from forecast_engine import SUPPORTED_HORIZONS, build_forecast, build_all_horizons
from forecast_store import build_and_store_all_horizons, compute_alerts, compute_intelligent_alerts, evaluate_and_learn, get_forecast_vs_actual_series, learning_confidence_adjustment, load_alerts, load_forecast_log, load_latest_forecast, load_learning_stats, save_alerts, summarize_alerts
from forecast_portfolio import build_portfolio_forecast, normalize_holdings
from event_risk_engine import detect_event_risk, summarize_event_risk, event_risk_confidence_breakdown


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

        # yfinance can return either:
        # 1) Series of prices
        # 2) DataFrame with ticker columns, e.g. Close["AAPL"]
        # list(DataFrame) returns column names, so we must select the numeric column first.
        try:
            if hasattr(close, "columns"):
                if ticker in close.columns:
                    close = close[ticker]
                elif len(close.columns) == 1:
                    close = close.iloc[:, 0]
                else:
                    close = close.select_dtypes(include="number").iloc[:, 0]
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)

        if hasattr(close, "dropna"):
            close = close.dropna()

        raw_dates = []
        try:
            raw_dates = list(getattr(close, "index", []) or [])
        except Exception:
            raw_dates = []

        prices = []
        price_dates = []
        for idx, x in enumerate(list(close)):
            try:
                prices.append(float(x))
                if idx < len(raw_dates):
                    d = raw_dates[idx]
                    if hasattr(d, "strftime"):
                        price_dates.append(d.strftime("%Y-%m-%d"))
                    else:
                        price_dates.append(str(d)[:10])
            except Exception:
                continue
        if len(prices) < 30:
            return [], f"For lite historikk for {ticker}. Trenger minst 30 datapunkter."

        # v18.5.27: keep actual trading dates available for the forecast-vs-actual
        # split chart without changing the public return shape used elsewhere.
        try:
            st.session_state[f"forecast_price_dates_latest_{ticker}"] = price_dates
            st.session_state[f"forecast_price_dates_{ticker}_{period}"] = price_dates
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
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
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

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
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

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
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return "Appdata"


def _forecast_cache_key(ticker: str, horizon: str, period: str, ai_score: float, sentiment: float, market_regime: str = "neutral", event_risk: bool = False) -> str:
    base = f"forecast_v1834::{ticker.upper()}::{horizon}::{period}::{int(ai_score)}::{round(float(sentiment), 2)}"
    if str(market_regime or "neutral") == "neutral" and not event_risk:
        return base
    return f"forecast_v18515::{ticker.upper()}::{horizon}::{period}::{int(ai_score)}::{round(float(sentiment), 2)}::{market_regime}::{int(bool(event_risk))}"


def _get_cached_forecast(cache_key: str):
    try:
        return st.session_state.get(cache_key)
    except Exception:
        return None


def _set_cached_forecast(cache_key: str, result_dict: Dict[str, Any]) -> None:
    try:
        st.session_state[cache_key] = result_dict
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


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



def _strength_color(score: int) -> str:
    try:
        score = int(score)
    except Exception:
        score = 50
    if score >= 80:
        return "#22c55e"
    if score >= 65:
        return "#84cc16"
    if score >= 50:
        return "#f59e0b"
    if score >= 35:
        return "#fb7185"
    return "#ef4444"


def _render_forecast_result_cards(summary) -> None:
    """Build 5: tydeligere tallkort for valgt horisont."""
    st.markdown("### 📈 Scenario-resultat")
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Nå", _format_price(summary.current_price))
    c2.metric("Base kurs", _format_price(summary.base_price), _format_pct(summary.base_pct))
    c3.metric("Bull kurs", _format_price(summary.bull_price), _format_pct(summary.bull_pct))
    c4.metric("Bear kurs", _format_price(summary.bear_price), _format_pct(summary.bear_pct))
    c5.metric("Confidence", f"{summary.confidence}%")
    c6.metric("Risiko", summary.risk)
    c7.metric("Strength", f"{summary.forecast_strength}/100", summary.forecast_strength_label)

    event_adj = int(getattr(summary, "confidence_adjustment_event", 0) or 0)
    learn_adj = int(getattr(summary, "confidence_adjustment_learning", 0) or 0)
    base_conf = int(getattr(summary, "confidence_base", summary.confidence) or summary.confidence)
    event_summary = html.escape(str(getattr(summary, "event_risk_summary", "") or "Ingen konkret hendelsesrisiko funnet."))
    event_badge = "⚠️ Hendelsesrisiko nær" if bool(getattr(summary, "event_risk", False)) else "✅ Ingen konkret hendelsesrisiko"

    st.markdown(
        f"""
        <div style="border:1px solid rgba(148,163,184,.25);border-radius:12px;padding:.65rem .9rem;margin:.35rem 0 .65rem 0;">
          <b>Forecast Strength Score:</b>
          <span style="color:{_strength_color(summary.forecast_strength)};font-weight:900;">
            {summary.forecast_strength}/100 · {summary.forecast_strength_label}
          </span><br>
          <span style="opacity:.82;">Kombinerer base-scenario, bull/bear-forhold, confidence, risiko, volatilitet, regime, AI-score og sentiment.</span><br>
          <span style="opacity:.92;"><b>{event_badge}</b> · Base confidence {base_conf}% · Hendelse {event_adj:+d} · Læring {learn_adj:+d} · Justert {summary.confidence}%</span><br>
          <span style="opacity:.78;">{event_summary}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )





def _render_forecast_vs_actual_chart(series: Dict[str, Any]) -> None:
    """Render forecast vs actual chart with explicit actual/today/future split."""
    try:
        import plotly.graph_objects as go  # type: ignore
    except Exception:
        st.warning("Plotly er ikke tilgjengelig. Viser kompakt status i stedet for graf.")
        st.markdown(
            f"""
            <div style="border:1px solid rgba(56,189,248,.25);background:rgba(15,23,42,.88);border-radius:12px;padding:.7rem .9rem;color:#dbeafe;">
              <b>{series.get('ticker', '')}</b> · {series.get('horizon', '')}<br>
              Faktiskpunkter: {len(series.get('actual_history') or [])} · Prognosepunkter: {len(series.get('forecast_x') or [])} · I dag: {series.get('today_label', 'I dag')}
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    x_full = list(series.get("labels", []) or [])
    actual_x = list(series.get("actual_history_x") or [])
    actual_y = list(series.get("actual_history") or [])
    forecast_x = list(series.get("forecast_x") or [])

    # Prefer v18.5.27 split-series. Fall back to legacy padded arrays if an old
    # stored payload/caller reaches the UI.
    base_y = list(series.get("forecast_base") or [])
    bull_y = list(series.get("forecast_bull") or [])
    bear_y = list(series.get("forecast_bear") or [])
    upper_y = list(series.get("forecast_upper_band") or [])
    lower_y = list(series.get("forecast_lower_band") or [])
    if not forecast_x or not base_y:
        forecast_x = x_full
        base_y = list(series.get("base") or [])
        bull_y = list(series.get("bull") or [])
        bear_y = list(series.get("bear") or [])
        upper_y = list(series.get("upper_band") or [])
        lower_y = list(series.get("lower_band") or [])
    if not actual_x and series.get("actual"):
        actual_padded = list(series.get("actual") or [])
        actual_pairs = [(x, y) for x, y in zip(x_full, actual_padded) if y is not None]
        actual_x = [p[0] for p in actual_pairs]
        actual_y = [p[1] for p in actual_pairs]

    if not actual_x or not actual_y:
        st.warning("Historikk mangler: kan ikke tegne faktisk kurs. Kjør med gyldig historikk først.")
    if not forecast_x or not base_y:
        st.info("Ingen prognosepunkter tilgjengelig ennå.")
        return

    fig = go.Figure()

    if forecast_x and upper_y and lower_y:
        fig.add_trace(go.Scatter(
            x=forecast_x,
            y=upper_y,
            mode="lines",
            line=dict(width=0),
            hoverinfo="skip",
            showlegend=False,
            name="Øvre bånd",
        ))
        fig.add_trace(go.Scatter(
            x=forecast_x,
            y=lower_y,
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(148,163,184,0.18)",
            line=dict(width=0),
            hoverinfo="skip",
            showlegend=True,
            name="Usikkerhetsbånd fremtid",
        ))

    if bull_y:
        fig.add_trace(go.Scatter(x=forecast_x, y=bull_y, mode="lines", name="Bull scenario", line=dict(width=2, dash="dot")))
    if base_y:
        fig.add_trace(go.Scatter(x=forecast_x, y=base_y, mode="lines", name="Base prognose", line=dict(width=3)))
    if bear_y:
        fig.add_trace(go.Scatter(x=forecast_x, y=bear_y, mode="lines", name="Bear scenario", line=dict(width=2, dash="dot")))

    if actual_x and actual_y:
        fig.add_trace(go.Scatter(
            x=actual_x,
            y=actual_y,
            mode="lines+markers",
            name="Faktisk kurs",
            line=dict(width=4),
            hovertemplate="Faktisk kurs<br>%{x}: %{y:.2f}<extra></extra>",
        ))

    today_label = series.get("today_label")
    all_values: List[float] = []
    for values in [actual_y, base_y, bull_y, bear_y, lower_y, upper_y]:
        for value in values or []:
            try:
                if value is not None:
                    all_values.append(float(value))
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)

    if today_label and all_values:
        fig.add_trace(go.Scatter(
            x=[today_label, today_label],
            y=[min(all_values), max(all_values)],
            mode="lines",
            name="I dag",
            line=dict(width=2, dash="dash"),
            hovertemplate="I dag / prognosestart<extra></extra>",
        ))
        fig.add_annotation(
            x=today_label,
            y=max(all_values),
            text="I dag",
            showarrow=False,
            yshift=12,
        )

    fig.update_layout(
        title=f"{series.get('ticker', '')} faktisk historikk vs fremtidig prognose ({series.get('horizon', '')})",
        xaxis_title="Faktisk historikk | I dag | Fremtidig prognose",
        yaxis_title="Kurs",
        height=430,
        margin=dict(l=10, r=10, t=55, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        """
        <div style="display:flex;flex-wrap:wrap;gap:.45rem;margin:.35rem 0 .1rem 0;">
          <span style="border:1px solid rgba(96,165,250,.35);background:rgba(15,23,42,.70);border-radius:999px;padding:.22rem .52rem;color:#bfdbfe;font-size:.75rem;font-weight:850;">Faktisk historikk</span>
          <span style="border:1px solid rgba(250,204,21,.35);background:rgba(66,32,6,.45);border-radius:999px;padding:.22rem .52rem;color:#fde68a;font-size:.75rem;font-weight:850;">I dag</span>
          <span style="border:1px solid rgba(34,197,94,.35);background:rgba(6,78,59,.40);border-radius:999px;padding:.22rem .52rem;color:#bbf7d0;font-size:.75rem;font-weight:850;">Fremtidig prognose</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _render_forecast_vs_actual_panel(ticker: str, horizon: str, current_prices: List[float]) -> None:
    """Render panel comparing latest stored forecast against actual prices."""
    with st.expander("🧪 Prognose vs faktisk", expanded=False):
        st.caption("Sammenligner siste lagrede prognose med faktisk kursutvikling. Dette er grunnlaget for å lære hvor treffsikker modellen er.")

        latest = load_latest_forecast(ticker)
        if not latest:
            st.info("Ingen lagret prognose funnet for denne tickeren ennå. Kjør en prognose først.")
            return

        try:
            actual_dates = st.session_state.get(f"forecast_price_dates_latest_{ticker}", [])
            series = get_forecast_vs_actual_series(latest, current_prices, horizon, actual_dates=actual_dates)
        except Exception as exc:
            st.warning(f"Kunne ikke bygge prognose-vs-faktisk graf: {exc}")
            return

        _render_forecast_vs_actual_chart(series)

        evaluation = series.get("evaluation")
        if evaluation:
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("Feil mot base", f"{evaluation['error_pct']:+.2f}%")
            e2.metric("Faktisk avkastning", f"{evaluation['actual_return_pct']:+.2f}%")
            e3.metric("Retning traff", "Ja" if evaluation["direction_hit"] else "Nei")
            e4.metric("Innen bull/bear", "Ja" if evaluation["inside_bull_bear_range"] else "Nei")

            if st.button("Oppdater læring fra denne evalueringen", key=f"learn_from_eval_{ticker}_{horizon}_v18310"):
                try:
                    actual_values = [v for v in (series.get("actual", []) or []) if v is not None]
                    if not actual_values:
                        st.warning("Ingen faktisk terminalkurs tilgjengelig for læring ennå.")
                    else:
                        learned = evaluate_and_learn(latest, actual_price=actual_values[-1], horizon=horizon)
                        st.success("Lærende confidence er oppdatert.")
                        st.json(learned.get("learning_stats", {}))
                except Exception as _learn_error:
                    st.warning(f"Kunne ikke oppdatere læring: {_learn_error}")
        else:
            st.caption("Ikke nok faktisk kursdata ennå til evaluering.")

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




def _portfolio_sources_from_session() -> List[Dict[str, Any]]:
    """Find likely portfolio holdings in session state."""
    for key in ("portfolio", "paper_portfolio", "holdings", "positions"):
        try:
            if key in st.session_state:
                rows = normalize_holdings(st.session_state.get(key))
                if rows:
                    return rows
        except Exception:
            continue
    return []


def _render_portfolio_forecast_panel(default_horizon: str = "1m") -> None:
    """Render portfolio forecast panel."""
    with st.expander("💼 Porteføljeprognose", expanded=False):
        st.caption("Samlet bull/base/bear-scenario for porteføljen. Bruker portefølje-data hvis de finnes, ellers kan du skrive tickere manuelt.")

        found_holdings = _portfolio_sources_from_session()
        manual_key = f"portfolio_forecast_manual_tickers_v1838_{st.session_state.get('forecast_render_context_v1849', 'normal')}"
        if str(st.session_state.get(manual_key, "") or "").strip().upper() in {"AAPL,MSFT,NVDA", "AAPL,NVDA,MSFT", "AAPL", "STB.OL"}:
            st.session_state[manual_key] = ""
        manual = st.text_input(
            "Manuelle tickere hvis portefølje ikke finnes",
            value=",".join([h["ticker"] for h in found_holdings[:8]]) if found_holdings else "",
            key=manual_key,
            placeholder="Tomt hvis ingen portefolje. Skriv egne tickere ved behov.",
            help="Kommaseparert. Hvis verdier mangler brukes lik vekting.",
        )

        horizon = st.selectbox(
            "Portefølje-horisont",
            options=list(SUPPORTED_HORIZONS.keys()),
            index=list(SUPPORTED_HORIZONS.keys()).index(default_horizon) if default_horizon in SUPPORTED_HORIZONS else 2,
            key=f"portfolio_forecast_horizon_v1838_{st.session_state.get('forecast_render_context_v1849', 'normal')}",
        )

        if found_holdings:
            holdings = found_holdings
            st.caption(f"Fant {len(holdings)} beholdninger fra appdata.")
        else:
            holdings = [{"ticker": t.strip().upper()} for t in manual.split(",") if t.strip()]
            st.caption("Bruker manuelle tickere med lik vekting." if holdings else "Ingen portefolje funnet og ingen manuelle tickere valgt.")

        run_pf = st.button("Lag porteføljeprognose", key=f"portfolio_forecast_run_v1838_{st.session_state.get('forecast_render_context_v1849', 'normal')}", use_container_width=True)
        if not run_pf:
            return

        price_history: Dict[str, List[float]] = {}
        missing: List[str] = []
        for h in holdings:
            ticker = h.get("ticker")
            if not ticker:
                continue
            prices, err = _fetch_close_prices_yfinance(ticker, period="1y")
            if err:
                missing.append(f"{ticker}: {err}")
            else:
                price_history[ticker] = prices

        if not price_history:
            st.warning("Kunne ikke hente prisdata for porteføljen.")
            if missing:
                st.caption(" | ".join(missing[:4]))
            return

        try:
            result = build_portfolio_forecast(holdings, price_history, horizon=horizon)
        except Exception as exc:
            st.error(f"Klarte ikke bygge porteføljeprognose: {exc}")
            return

        p1, p2, p3, p4, p5, p6 = st.columns(6)
        p1.metric("Portefølje nå", f"{result.total_current:,.0f}")
        p2.metric("Base", f"{result.total_base:,.0f}", f"{result.base_pct:+.2f}%")
        p3.metric("Bull", f"{result.total_bull:,.0f}", f"{result.bull_pct:+.2f}%")
        p4.metric("Bear", f"{result.total_bear:,.0f}", f"{result.bear_pct:+.2f}%")
        p5.metric("Confidence", f"{result.weighted_confidence}%")
        p6.metric("Strength", f"{result.weighted_strength}/100", result.risk)

        rows = []
        for h in result.holdings:
            rows.append({
                "Ticker": h.ticker,
                "Vekt": f"{h.weight*100:.1f}%",
                "Base %": f"{h.base_pct:+.2f}%",
                "Bull %": f"{h.bull_pct:+.2f}%",
                "Bear %": f"{h.bear_pct:+.2f}%",
                "Confidence": f"{h.confidence}%",
                "Strength": f"{h.strength}/100",
                "Risiko": h.risk,
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

        try:
            import plotly.graph_objects as go  # type: ignore
            labels = ["Nå", "Bear", "Base", "Bull"]
            values = [result.total_current, result.total_bear, result.total_base, result.total_bull]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=labels, y=values, name="Porteføljeverdi"))
            fig.update_layout(
                title=f"Porteføljeprognose ({horizon})",
                yaxis_title="Verdi",
                height=360,
                margin=dict(l=10, r=10, t=50, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)

        if result.warnings:
            st.warning(" ".join(result.warnings))

def render_forecast_section(default_ticker: str = "AAPL") -> None:
    """Render prognosemodul v1, Bygg 2."""
    st.markdown("## 🔮 Fremtidsscenario / Prognose")
    st.caption(
        "Teoretiske bull/base/bear-scenarioer. Dette er ikke fasit eller investeringsråd."
    )

    with st.expander("▸ Prognosemodul v1 — klikk for å åpne/lukke", expanded=False):
        st.info("Fase 6–10: Prognosemodulen har lagring, varsler, backtest-struktur og hurtigvalg fra portefølje/watchlist/ranking og enkel cache. Ingen auto-trading-kobling er aktivert.")

        _render_portfolio_forecast_panel(default_horizon="1m")
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
                key=f"forecast_horizon_v1831_{st.session_state.get('forecast_render_context_v1849', 'normal')}",
            )
        with c3:
            period = st.selectbox(
                "Historikk",
                options=["6mo", "1y", "2y", "5y"],
                index=1,
                key="forecast_history_period_v1831",
            )

        ai_score = st.slider("AI-score-justering", 0, 100, 50, 1, key=f"forecast_ai_score_v1831_{st.session_state.get('forecast_render_context_v1849', 'normal')}")
        sentiment = st.slider("Sentiment-justering", -1.0, 1.0, 0.0, 0.05, key=f"forecast_sentiment_v1831_{st.session_state.get('forecast_render_context_v1849', 'normal')}")

        mc1, mc2, mc3 = st.columns([1.3, 1.0, 1.15])
        with mc1:
            auto_regime = st.session_state.get("auto_market_regime_v1840", "neutral")
            regime_options = ["neutral", "bull", "bear", "volatile"]
            default_regime_index = regime_options.index(auto_regime) if auto_regime in regime_options else 0
            market_regime = st.selectbox(
                "Markedsregime",
                options=regime_options,
                format_func=lambda x: {"neutral": "Nøytral", "bull": "Bull", "bear": "Bear", "volatile": "Høy volatilitet"}.get(x, x),
                index=default_regime_index,
                key=f"forecast_market_regime_v1835_{st.session_state.get('forecast_render_context_v1849', 'normal')}",
                help="Velges automatisk hvis markedsregime-widgeten er kjørt.",
            )
        with mc2:
            event_risk = st.checkbox(
                "Hendelsesrisiko nær?",
                value=bool(st.session_state.get("auto_event_risk_v1840", False)),
                key=f"forecast_event_risk_v1835_{st.session_state.get('forecast_render_context_v1849', 'normal')}",
                help="Kan settes automatisk ved Stress/Panic-regime.",
            )
        with mc3:
            include_news_risk = st.checkbox(
                "Bruk nyheter i hendelsesrisiko",
                value=False,
                key=f"forecast_include_news_risk_v18531_{st.session_state.get('forecast_render_context_v1849', 'normal')}",
                help="Av som standard for å spare NewsAPI-kall. Når av brukes cache/earnings/makro/volatilitet uten live NewsAPI.",
            )

        st.caption(f"Valgt prognose: {ticker or 'ingen ticker'} · horisont {horizon} · historikk {period} · regime {market_regime} · nyheter i risiko: {'på' if include_news_risk else 'av'}")
        run = st.button("Lag prognosegraf", key="forecast_run_v1831", use_container_width=True)

        if not run:
            st.info("Velg ticker og trykk «Lag prognosegraf».")
            return

        prices, error = _fetch_close_prices_yfinance(ticker, period=period)
        if error:
            st.warning(error)
            return

        event_info = detect_event_risk(ticker, prices, horizon=horizon, include_news=bool(include_news_risk))
        if event_risk and not event_info.get("is_event_risk"):
            event_info = dict(event_info)
            event_info["is_event_risk"] = True
            event_info["confidence_adjustment"] = int(event_info.get("confidence_adjustment") or -10)
            event_info.setdefault("alerts", [])
            event_info["alerts"] = list(event_info.get("alerts", []) or []) + [{
                "ticker": ticker.upper(),
                "horizon": horizon,
                "level": "yellow",
                "category": "manual_event_risk",
                "source": "Hendelsesrisiko",
                "message": "Manuell hendelsesrisiko er slått på for denne prognosen.",
            }]

        effective_event_risk = bool(event_info.get("is_event_risk"))
        event_summary = summarize_event_risk(event_info)

        learning_adj = learning_confidence_adjustment(
            ticker=ticker,
            horizon=horizon,
            base_confidence=50,
        )
        learned_adjustment = int(learning_adj.get("adjustment", 0))
        event_adjustment = int(event_info.get("confidence_adjustment", 0) or 0)
        confidence_breakdown = event_risk_confidence_breakdown(
            base_confidence=50,
            event_info=event_info,
            learning_adjustment=learned_adjustment,
        )

        cache_key = _forecast_cache_key(ticker, horizon, period, float(ai_score), float(sentiment), market_regime, effective_event_risk)
        cached = _get_cached_forecast(cache_key)

        with st.expander("⚠️ Hendelsesrisiko / confidence-justering", expanded=effective_event_risk):
            if event_info.get("alerts"):
                st.warning(event_summary)
                for alert in event_info.get("alerts", [])[:8]:
                    st.write(f"{str(alert.get('level', '')).upper()} · {alert.get('category', 'event')}: {alert.get('message')}")
            else:
                st.success("Ingen konkrete hendelsesrisiko-signaler funnet med tilgjengelige datakilder.")
            st.caption(
                f"Base confidence: {confidence_breakdown.get('base_confidence')}% · "
                f"Hendelser: {event_adjustment:+d} poeng · "
                f"Læring: {learned_adjustment:+d} poeng · "
                f"Justert ca.: {confidence_breakdown.get('adjusted_confidence')}%."
            )
            diagnostics = event_info.get("diagnostics", {}) or {}
            unavailable = []
            for source_name in ["earnings", "news"]:
                src = diagnostics.get(source_name, {}) or {}
                if src.get("available") is False and src.get("error"):
                    unavailable.append(f"{source_name}: {src.get('error')}")
            if unavailable:
                st.caption("Datakilder ikke aktive: " + " | ".join(unavailable[:3]))

        if cached:
            st.caption("Viser cachet prognose for samme ticker/horisont/innstillinger i denne økten.")

        try:
            result = build_forecast(
                ticker,
                prices,
                horizon,
                ai_score=float(ai_score),
                sentiment_score=float(sentiment),
                market_regime=market_regime,
                event_risk=effective_event_risk,
                learned_confidence_adjustment=learned_adjustment,
                event_confidence_adjustment=event_adjustment,
                event_risk_summary=event_summary,
            )
            if not cached:
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
                market_regime=market_regime,
                event_risk=effective_event_risk,
                learned_confidence_adjustment=learned_adjustment,
                event_confidence_adjustment=event_adjustment,
                event_risk_summary=event_summary,
                event_risk_details=event_info,
            )
            basic_alerts = compute_alerts(stored_payload, previous_payload)
            intelligent_alerts = compute_intelligent_alerts(stored_payload, previous_payload)
            event_alerts = []
            for _alert in list(event_info.get("alerts", []) or []):
                _row = dict(_alert)
                _row.setdefault("source", "Hendelsesrisiko")
                event_alerts.append(_row)
            alerts = event_alerts + (intelligent_alerts or basic_alerts)
            save_alerts(alerts)
            if alerts:
                summary_alerts = summarize_alerts(alerts)
                with st.expander("🚨 Intelligent varsling fra prognosemodulen", expanded=False):
                    st.write(
                        f"Totalt: {summary_alerts['total']} · "
                        f"Røde: {summary_alerts['counts']['red']} · "
                        f"Gule: {summary_alerts['counts']['yellow']} · "
                        f"Grønne: {summary_alerts['counts']['green']}"
                    )
                    for alert in alerts[:12]:
                        st.write(f"{alert.get('level', '').upper()} · {alert.get('category', 'varsel')}: {alert.get('message')}")
        except Exception as _store_error:
            st.caption(f"Prognosen ble vist, men kunne ikke lagres/logges: {_store_error}")

        s = result.summary
        _render_forecast_result_cards(s)

        with st.expander("🧠 Lærende confidence", expanded=False):
            try:
                learning_info = learning_confidence_adjustment(
                    ticker=ticker,
                    horizon=horizon,
                    base_confidence=s.confidence,
                )
                stats = load_learning_stats()
                st.write(
                    f"Justering: {learning_info.get('adjustment', 0):+d} poeng · "
                    f"Samples: {learning_info.get('samples', 0)}"
                )
                st.caption(learning_info.get("reason", ""))
                st.json({
                    "global": stats.get("global", {}),
                    "ticker": stats.get("tickers", {}).get(ticker, {}),
                    "horizon": stats.get("horizons", {}).get(horizon, {}),
                })
            except Exception as _learning_error:
                st.caption(f"Læringsinfo ikke tilgjengelig: {_learning_error}")

        _render_plotly_chart(result)

        _render_forecast_vs_actual_panel(ticker, horizon, prices)

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
                event_risk=effective_event_risk,
                event_confidence_adjustment=event_adjustment,
                event_risk_summary=event_summary,
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
                    "Strength": f"{s2.get('forecast_strength', 0)}/100",
                    "Risiko": s2["risk"],
                })

            st.dataframe(horizon_rows, use_container_width=True, hide_index=True)
        except Exception as _forecast_compare_error:
            st.warning(f"Kunne ikke bygge horisont-tabell: {_forecast_compare_error}")


        with st.expander("📚 Prognoselogg og varsler", expanded=False):
            try:
                recent_log = load_forecast_log(limit=10)
                recent_alerts = load_alerts(limit=10)
                st.caption("Varslene sendes også til felles varselsenter øverst i appen.")
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
            - Se etter høy Forecast Strength Score kombinert med høy confidence og lav/medium risiko.
            - Vent med auto-trading-kobling til prognose-backtest er på plass.
            - Bruk intelligent varsling til å prioritere hvilke aksjer/porteføljepunkter som må sjekkes først.
            """
        )

        if result.warnings:
            st.warning(" ".join(result.warnings))
